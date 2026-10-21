#!/usr/bin/env python3
"""Invert skills-tree ownership so Hermes Cortex owns it (cycle 13491).

WHY: the fleet is moving off the Hermes agent. Cortex owns the skill library, so
the directory that is REAL must be the cortex one, and the Hermes path (and any
other harness path we keep alive during the transition) becomes a POINTER to it.
The opposite direction is what shipped originally — see docs/symlink-policy.md —
and this tool is the sanctioned way to reverse it per host.

STATES (classified from the filesystem, never assumed):

  OLD        cortex path is a symlink resolving to the borrower's real tree
             -> migrate: move the real tree to the cortex path, then link back
  NEW        cortex path is a real directory and the borrower is either absent
             or a symlink resolving to it  -> nothing to do
  BOTH_REAL  BOTH paths are real directories: two owners of one library.
             NEVER guessed. Exit 4 and require an explicit decision:
               --adopt-borrower  borrower wins; the cortex tree is PRESERVED by
                                 rename to <cortex>.pre-migration-<stamp>
                                 (nothing is ever deleted)
               --keep-borrower   leave both trees untouched, exit 4
  UNVERIFIABLE  a path is missing, dangling, or points somewhere unexpected
             -> exit 3 (COULD NOT VERIFY, never a silent pass)

EXIT CODES
  0 NEW (already correct, or migration applied and verified)
  1 OLD (migration is required — the direction is wrong)
  3 COULD NOT VERIFY (missing / dangling / unexpected target)
  4 BOTH REAL (an explicit decision is required; nothing was modified)

SAFETY
- --check never mutates anything.
- Migration MOVES (rename), never copy-then-delete; no tree is ever removed.
- The non-winning tree in a both-real resolution is preserved by rename.
- Success is only reported after re-classifying the result and comparing the
  SKILL.md count with the pre-migration count. A failed verification reports
  COULD NOT VERIFY rather than claiming success.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

EXIT_NEW = 0
EXIT_OLD = 1
EXIT_UNVERIFIABLE = 3
EXIT_DECISION = 4

OLD = "OLD"
NEW = "NEW"
BOTH_REAL = "BOTH_REAL"
UNVERIFIABLE = "UNVERIFIABLE"


def count_skills(root: Path) -> int:
    """Number of SKILL.md files under root (0 when root is absent/unreadable)."""
    if not root.exists():
        return 0
    return sum(1 for _ in root.rglob("SKILL.md"))


def _content_map(root: Path) -> dict:
    """relpath -> sha256 for every SKILL.md under root."""
    out = {}
    if not root.exists():
        return out
    for path in sorted(root.rglob("SKILL.md")):
        out[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def classify(cortex: Path, borrower: Path, pointer_target: "Path | None" = None) -> str:
    """pointer_target: the path the borrower MUST resolve to (default: cortex)."""
    expected = os.path.realpath(pointer_target) if pointer_target is not None else os.path.realpath(cortex)
    cortex_is_link = cortex.is_symlink()
    borrower_is_link = borrower.is_symlink()
    cortex_is_real = cortex.is_dir() and not cortex_is_link
    borrower_is_real = borrower.is_dir() and not borrower_is_link

    if cortex_is_link:
        target = os.path.realpath(cortex)
        if not os.path.exists(target):
            return UNVERIFIABLE                     # dangling pointer
        if borrower_is_real and target == os.path.realpath(borrower):
            return OLD
        return UNVERIFIABLE                         # links somewhere unexpected

    if cortex_is_real:
        if borrower_is_link:
            if os.path.realpath(borrower) == expected:
                return NEW
            return UNVERIFIABLE                     # borrower points elsewhere
        if borrower_is_real:
            return BOTH_REAL
        if borrower.exists():
            return UNVERIFIABLE                     # exists, but not a dir
        return NEW                                  # borrower not installed here

    return UNVERIFIABLE                             # cortex path absent


def divergence_report(cortex: Path, borrower: Path) -> str:
    c, b = _content_map(cortex), _content_map(borrower)
    only_c = sorted(set(c) - set(b))
    only_b = sorted(set(b) - set(c))
    differing = sorted(k for k in set(c) & set(b) if c[k] != b[k])
    lines = [
        f"  cortex-only skills: {len(only_c)}" + (f" (e.g. {', '.join(only_c[:3])})" if only_c else ""),
        f"  borrower-only skills: {len(only_b)}" + (f" (e.g. {', '.join(only_b[:3])})" if only_b else ""),
        f"  same relpath, divergent content: {len(differing)}"
        + (f" (e.g. {', '.join(differing[:3])})" if differing else ""),
    ]
    if not only_c and not only_b and not differing:
        lines.append("  trees are byte-identical")
    else:
        lines.append("  TREES ARE DIVERGENT — a count comparison would not show this")
    return "\n".join(lines)


def migrate(cortex: Path, borrower: Path, backup_cortex: bool, stamp: str,
            pointer_target: "Path | None" = None) -> int:
    """OLD (or resolved BOTH_REAL) -> NEW. Moves the real tree, then links back."""
    link_to = pointer_target if pointer_target is not None else cortex
    pre_count = count_skills(borrower)
    real_source = os.path.realpath(borrower) if borrower.is_dir() else os.path.realpath(cortex)

    if backup_cortex and cortex.exists() and not cortex.is_symlink():
        # Preserve the non-winning tree. rename, never delete.
        backup = cortex.with_name(f"{cortex.name}.pre-migration-{stamp}")
        if backup.exists():
            print(f"ERROR: backup path already exists: {backup}", file=sys.stderr)
            return EXIT_UNVERIFIABLE
        shutil.move(str(cortex), str(backup))
        print(f"PRESERVED non-winning cortex tree by rename -> {backup}")

    if cortex.is_symlink():
        cortex.unlink()                             # remove ONLY the pointer
    elif cortex.exists():
        print(f"ERROR: cortex path is occupied and was not adopted: {cortex}", file=sys.stderr)
        return EXIT_UNVERIFIABLE

    shutil.move(real_source, str(cortex))           # rename the real tree into place
    print(f"MOVED real skills tree -> {cortex}")

    if not borrower.exists() and not borrower.is_symlink():
        borrower.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(link_to, borrower)
        print(f"LINKED {borrower} -> {link_to}")

    # Verify before claiming success.
    state = classify(cortex, borrower, pointer_target)
    post_count = count_skills(cortex)
    if state != NEW or post_count != pre_count:
        print(
            f"COULD NOT VERIFY: state={state} pre_count={pre_count} post_count={post_count}",
            file=sys.stderr,
        )
        return EXIT_UNVERIFIABLE
    print(f"VERIFIED: cortex path is real, borrower pointer resolves to it, "
          f"{post_count} skills on both paths")
    return EXIT_NEW


def main() -> int:
    default_cortex = Path(os.environ.get("CORTEX_HOME", Path.home() / ".hermes-cortex")) / "skills"
    default_borrower = Path.home() / ".hermes" / "skills"

    ap = argparse.ArgumentParser(description=(__doc__ or "invert skills-tree ownership").split("\n")[0])
    ap.add_argument("--cortex-root", default=str(default_cortex),
                    help="the tree cortex must OWN (real directory after migration)")
    ap.add_argument("--borrower-root", default=str(default_borrower),
                    help="the harness tree that must become a pointer")
    ap.add_argument("--pointer-target", default=None,
                    help="what the borrower pointer must resolve to. Defaults to the cortex "
                         "root; set it to the agent-visible published tree "
                         "(e.g. ~/.agents/skills) when that is the location harnesses read.")
    ap.add_argument("--check", action="store_true",
                    help="report only; never mutate")
    ap.add_argument("--adopt-borrower", action="store_true",
                    help="BOTH_REAL only: borrower tree wins, cortex tree preserved by rename")
    ap.add_argument("--keep-borrower", action="store_true",
                    help="BOTH_REAL only: leave both trees untouched (acknowledged divergence)")
    args = ap.parse_args()

    cortex = Path(args.cortex_root)
    borrower = Path(args.borrower_root)
    pointer_target = Path(args.pointer_target) if args.pointer_target else None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    state = classify(cortex, borrower, pointer_target)
    print(f"cortex-root   : {cortex} (real={not cortex.is_symlink() and cortex.is_dir()})")
    print(f"borrower-root : {borrower} (symlink={borrower.is_symlink()})")
    print(f"state         : {state}")

    if state == NEW:
        print(f"OK: cortex owns the tree; {count_skills(cortex)} skills")
        return EXIT_NEW

    if state == UNVERIFIABLE:
        print("COULD NOT VERIFY: a path is missing, dangling, or points somewhere "
              "unexpected — resolve it before migrating", file=sys.stderr)
        return EXIT_UNVERIFIABLE

    if state == BOTH_REAL:
        print(divergence_report(cortex, borrower))
        if args.keep_borrower:
            print("KEEP: both trees left untouched by explicit request")
            return EXIT_DECISION
        if not args.adopt_borrower:
            print("DECISION REQUIRED: both paths are real directories. Nothing was modified. "
                  "Re-run with --adopt-borrower (borrower wins; cortex tree preserved by rename) "
                  "or --keep-borrower (leave both).", file=sys.stderr)
            return EXIT_DECISION
        if args.check:
            print("--check: no changes made (would adopt the borrower tree)")
            return EXIT_DECISION
        return migrate(cortex, borrower, backup_cortex=True, stamp=stamp,
                       pointer_target=pointer_target)

    # OLD
    if args.check:
        print("MIGRATION REQUIRED: cortex is a symlink into the borrower's tree. "
              "Re-run without --check to invert ownership.")
        return EXIT_OLD
    return migrate(cortex, borrower, backup_cortex=False, stamp=stamp,
                   pointer_target=pointer_target)


if __name__ == "__main__":
    sys.exit(main())
