#!/usr/bin/env python3
"""Publish the cortex-owned DEFAULT skills at the agent-visible location.

TWO ROLES, ONE OWNER EACH (cycle 13491)

  DEFAULTS   <cortex>/skills    REAL directory. Cortex owns the content. The deploy
                                writes here; dynamic skill updates land here first.
  PUBLISHED  ~/.agents/skills   What every harness reads (the cross-client standard
                                path). DERIVED from the defaults — never hand-edited,
                                never an independent owner.

That is how a dynamically updated skill reaches every agent: it lands in the
defaults, and the published view is refreshed from there.

MODES — chosen from MEASURED behaviour. The measurement is RECORDED and re-runnable:
  docs/evidence/skills-ownership-enumeration-probe-2026-10-21.txt holds the probe source,
  the result table (rglob / os.walk / os.walk(followlinks=True) / plain find for a symlinked
  root, a per-skill symlink farm, and a real copy), and the reader-sensitivity finding from
  the live host. Re-run it before trusting the table.

  root (default)  <published> is a SYMLINK to the defaults tree.
                  visible to a plain scan: yes (rglob 1/1, os.walk 1/1).
                  ONE copy of the content, so an update propagates with no copy step
                  and CANNOT drift.
  copy            real files under the published tree, refreshed by content.
                  visible to a plain scan: yes. Use for a harness proven to refuse a
                  symlinked root; a second copy exists, so drift is possible and
                  --check is what catches it.
  REJECTED        a per-skill symlink farm (what Pi uses inside its own
                  settings-registered dir). Measured rglob 0/1, os.walk 0/1 — a plain
                  scan cannot see it, so it is not safe for every harness.

SAFETY
- --check mutates nothing.
- A published path that is NOT ours (a real directory, or a symlink pointing
  elsewhere) is never replaced unless the operator passes --adopt-published; the
  existing tree is then PRESERVED by rename to <published>.pre-publish-<stamp>.
  Nothing is ever deleted.
- In copy mode an entry this tool does not own is reported (FOREIGN), never removed.

EXIT CODES
  0 in sync (or published successfully)
  1 drift found (--check)
  3 COULD NOT VERIFY (defaults missing/empty, or the result is not fully visible)
  4 DECISION REQUIRED (a foreign tree occupies the published path; nothing modified)
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_UNVERIFIABLE = 3
EXIT_DECISION = 4


def skill_dirs(root: Path):
    """Relative paths of every skill directory (the directory holding SKILL.md)."""
    if not root.exists():
        return []
    return sorted({p.parent.relative_to(root) for p in root.rglob("SKILL.md")})


def visible_skills(root: Path) -> int:
    """SKILL.md files a PLAIN tree scan sees from this root (the harness's view)."""
    if not root.exists():
        return 0
    return len(list(root.rglob("SKILL.md")))


def points_at(published: Path, defaults: Path) -> bool:
    return published.is_symlink() and os.path.realpath(published) == os.path.realpath(defaults)


def plan_copy(defaults: Path, published: Path):
    """-> (to_create, to_refresh, foreign) for copy mode."""
    to_create, to_refresh, foreign = [], [], []
    wanted = set(skill_dirs(defaults))
    for rel in sorted(wanted):
        src, dst = defaults / rel, published / rel
        if not dst.exists() and not dst.is_symlink():
            to_create.append(rel)
        elif dst.is_symlink() or not (dst / "SKILL.md").exists():
            to_refresh.append(rel)
        elif (dst / "SKILL.md").read_bytes() != (src / "SKILL.md").read_bytes():
            to_refresh.append(rel)
    if published.exists() and not published.is_symlink():
        for p in sorted(published.rglob("SKILL.md")):
            rel = p.parent.relative_to(published)
            if rel not in wanted:
                foreign.append(rel)
    return to_create, to_refresh, foreign


def publish_root(defaults: Path, published: Path, dry_run: bool, adopt: bool) -> int:
    if points_at(published, defaults):
        print("  published root     : symlink -> defaults (in sync)")
        print(f"  visible to a plain scan: {visible_skills(published)} (expected {len(skill_dirs(defaults))})")
        return EXIT_OK

    occupied = published.is_symlink() or (published.exists() and any(published.iterdir()))
    if occupied:
        what = ("symlink -> " + os.path.realpath(published)) if published.is_symlink() \
            else "a real directory"
        print(f"  OCCUPIED: {published} is {what} — not ours", file=sys.stderr)
        if dry_run:
            print("  DECISION REQUIRED (--check made no changes)", file=sys.stderr)
            return EXIT_DECISION
        if not adopt:
            print("  DECISION REQUIRED: re-run with --adopt-published to preserve the existing "
                  "tree by rename and publish the pointer (nothing is deleted)", file=sys.stderr)
            return EXIT_DECISION
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = published.with_name(f"{published.name}.pre-publish-{stamp}")
        if backup.exists():
            print(f"COULD NOT VERIFY: backup path already exists: {backup}", file=sys.stderr)
            return EXIT_UNVERIFIABLE
        shutil.move(str(published), str(backup))
        print(f"  PRESERVED existing tree by rename -> {backup}")
    elif dry_run:
        print("  would publish the pointer (none present)")
        return EXIT_DRIFT

    published.parent.mkdir(parents=True, exist_ok=True)
    if published.is_symlink():
        published.unlink()
    elif published.is_dir():
        published.rmdir()          # provably empty: the occupancy check above allowed this
    os.symlink(defaults, published)
    print(f"  PUBLISHED {published} -> {defaults}")

    if not points_at(published, defaults):
        print("COULD NOT VERIFY: the published path does not resolve to the defaults",
              file=sys.stderr)
        return EXIT_UNVERIFIABLE
    seen = visible_skills(published)
    print(f"  visible to a plain scan: {seen} (expected {len(skill_dirs(defaults))})")
    if seen != len(skill_dirs(defaults)):
        print("COULD NOT VERIFY: a plain scan does not see every skill", file=sys.stderr)
        return EXIT_UNVERIFIABLE
    return EXIT_OK


def publish_copy(defaults: Path, published: Path, dry_run: bool) -> int:
    to_create, to_refresh, foreign = plan_copy(defaults, published)
    print(f"  to create          : {len(to_create)}")
    print(f"  to refresh         : {len(to_refresh)}")
    print(f"  foreign (reported) : {len(foreign)}")
    for rel in foreign[:10]:
        print(f"    FOREIGN (not touched): {rel}")
    if dry_run:
        return EXIT_OK if not (to_create or to_refresh) else EXIT_DRIFT

    published.mkdir(parents=True, exist_ok=True)
    for rel in to_create + to_refresh:
        src, dst = defaults / rel, published / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.is_symlink():
            dst.unlink()
        elif dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)

    wanted = skill_dirs(defaults)
    missing = [rel for rel in wanted if not (published / rel / "SKILL.md").exists()]
    print(f"  visible to a plain scan: {visible_skills(published)} "
          f"({len(wanted)} published by us, {len(foreign)} foreign reported)")
    if missing:
        print(f"COULD NOT VERIFY: {len(missing)} published skills unreadable "
              f"(e.g. {missing[:3]})", file=sys.stderr)
        return EXIT_UNVERIFIABLE
    return EXIT_OK


def main() -> int:
    cortex_home = Path(os.environ.get("CORTEX_HOME", Path.home() / ".hermes-cortex"))
    ap = argparse.ArgumentParser(description=(__doc__ or "publish agent skills").split("\n")[0])
    ap.add_argument("--from", dest="defaults", default=str(cortex_home / "skills"),
                    help="the cortex-owned DEFAULTS tree (owner of the content)")
    ap.add_argument("--to", dest="published", default=str(Path.home() / ".agents" / "skills"),
                    help="the agent-visible PUBLISHED location")
    ap.add_argument("--mode", choices=("root", "copy"), default="root")
    ap.add_argument("--adopt-published", action="store_true",
                    help="replace a foreign tree at the published path, preserving it by rename")
    ap.add_argument("--check", action="store_true", help="report only; never mutate")
    args = ap.parse_args()

    defaults = Path(args.defaults)
    published = Path(args.published)
    if not defaults.exists() or not skill_dirs(defaults):
        print(f"COULD NOT VERIFY: defaults tree missing or empty: {defaults}", file=sys.stderr)
        return EXIT_UNVERIFIABLE

    print(f"publish mode={args.mode} defaults={defaults} published={published}")
    print(f"  skills in defaults : {len(skill_dirs(defaults))}")
    if args.mode == "root":
        return publish_root(defaults, published, dry_run=args.check, adopt=args.adopt_published)
    return publish_copy(defaults, published, dry_run=args.check)


if __name__ == "__main__":
    sys.exit(main())
