#!/usr/bin/env python3
"""normalize-precommit-task-ids.py — repair task ids that carry a continuation line.

One-off ledger repair for issue #188. Until 2026-10-20 the pre-commit hook built
its task id with `$(cmd || echo fallback)`, which captures the command's stdout
AND the fallback when the command prints and then exits non-zero. A repo with no
commits makes `git rev-parse --abbrev-ref HEAD` do exactly that (it prints "HEAD"
and fails), so 6,395 rows across 62 ids entered the ledger as e.g.

    precommit-repo-HEAD\\nunknown/update

The hook is fixed at the source (ops/scripts/pre-commit-score), so no NEW ids are
minted that way. This script repairs the historical rows.

DECISION (issue #188, Luke delegated): normalize AND keep the evidence. The id is
rewritten to the form the fixed hook now mints, and the original malformed value is
appended to the row's own audit field (`outcome_note`) — escaped, so the note stays
a single line — and written to a manifest. Repairing the id without recording what
it was would erase the footprint of the bug; recording it without repairing the id
leaves 6,395 rows that no classifier can group.

Safety:
  * DRY RUN by default. Nothing is written without --apply.
  * The ledger file is copied to <db>.backup-<UTC> before the first write.
  * An id that does not reduce to the documented shape is SKIPPED and reported,
    never guessed at.
  * Idempotent: a second --apply finds nothing to do.

Usage:
    python3 normalize-precommit-task-ids.py                      # dry run
    python3 normalize-precommit-task-ids.py --apply               # repair
    python3 normalize-precommit-task-ids.py --apply --manifest PATH
"""
from __future__ import annotations

import argparse
import datetime
import re
import shutil
import sqlite3
import sys
from pathlib import Path

DEFAULT_DB = Path.home() / ".hermes-cortex" / "data" / "loop-governance.db"
DEFAULT_MANIFEST = Path.home() / ".hermes-cortex" / "state" / "task-id-normalization-manifest.txt"

# The documented id shape: precommit-<repo>-<branch>/<slug>
SHAPE = re.compile(r"^precommit-[^/]+/[A-Za-z0-9._-]+$")
HOOK_PREFIX = "precommit-"
NOTE_TAG = "task_id normalized (issue #188): was "


def _is_malformed(task_id: str) -> bool:
    """Any whitespace or control character in an id is a defect."""
    return any(ch.isspace() or ord(ch) < 32 for ch in task_id)


def _escape(value: str) -> str:
    """Render a value for a single-line audit note."""
    out = []
    for ch in value:
        if ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 32:
            out.append(f"\\x{ord(ch):02x}")
        else:
            out.append(ch)
    return "".join(out)


def _normalized(task_id: str) -> str | None:
    """The repaired id, or None when it cannot be derived without guessing.

    The malformed part is always the CONCATENATED FALLBACK, and it lands *inside*
    the branch field, immediately before the original separator:

        precommit-{repo}-{branch}<newline>{fallback}/{slug}

    so the repair drops the newline and the fallback token that followed it —
    which reproduces exactly what the fixed hook mints for the same input (a repo
    with no commits yields `precommit-repo-HEAD/update`, verified against the
    deployed hook). Dropping only the newline, or only the tail, does not work:
    the first loses the slug, the second leaves the fallback behind.
    """
    candidate = re.sub(r"\n[^\n/]*/", "/", task_id)
    candidate = "".join(ch for ch in candidate if not ch.isspace())
    if not candidate.startswith(HOOK_PREFIX):
        return None
    if not SHAPE.match(candidate):
        return None
    if candidate == task_id:
        return None
    return candidate


def _plan(conn: sqlite3.Connection) -> tuple[list[tuple[int, str, str]], list[tuple[int, str]]]:
    rows = conn.execute(
        "SELECT id, task_id, outcome_note FROM loop_cycles WHERE task_id IS NOT NULL"
    ).fetchall()
    changes: list[tuple[int, str, str]] = []
    skipped: list[tuple[int, str]] = []
    for row_id, task_id, _note in rows:
        if not _is_malformed(str(task_id)):
            continue
        fixed = _normalized(str(task_id))
        if fixed is None:
            skipped.append((row_id, str(task_id)))
        else:
            changes.append((row_id, str(task_id), fixed))
    return changes, skipped


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(DEFAULT_DB), help=f"ledger path (default: {DEFAULT_DB})")
    ap.add_argument("--apply", action="store_true", help="write the repair (default: dry run)")
    ap.add_argument("--manifest", default=str(DEFAULT_MANIFEST), help="where to record old→new ids")
    args = ap.parse_args(argv)

    db = Path(args.db).expanduser()
    if not db.exists():
        print(f"ledger absent: {db} — nothing to repair")
        return 0

    conn = sqlite3.connect(db)
    changes, skipped = _plan(conn)
    distinct_old = sorted({old for _row, old, _new in changes})
    print(f"ledger                : {db}")
    print(f"malformed rows        : {len(changes) + len(skipped)}")
    print(f"  repairable          : {len(changes)} (across {len(distinct_old)} distinct ids)")
    print(f"  skipped (no guess)  : {len(skipped)}")
    for row_id, task_id in skipped[:10]:
        print(f"      row {row_id}: {task_id!r} does not reduce to {SHAPE.pattern}")

    if not changes:
        print("RESULT: nothing to do")
        conn.close()
        return 0

    if not args.apply:
        print("\nDRY RUN — no writes. Re-run with --apply to repair.")
        for _row, old, new in changes[:5]:
            print(f"  {old!r} → {new!r}")
        if len(changes) > 5:
            print(f"  … and {len(changes) - 5} more")
        conn.close()
        return 0

    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = db.with_name(db.name + f".backup-{stamp}")
    shutil.copy2(db, backup)
    print(f"\nbackup written        : {backup}")

    manifest_lines = [
        "# task-id normalization — issue #188",
        f"# ledger   : {db}",
        f"# backup   : {backup}",
        f"# when     : {stamp}",
        f"# rows     : {len(changes)} across {len(distinct_old)} distinct malformed ids",
        "#",
        "# original (malformed) → normalized. The original is also appended to each",
        "# row's outcome_note, so the footprint of the bug survives this repair.",
        "#",
    ]
    for row_id, old, new in changes:
        note = conn.execute("SELECT outcome_note FROM loop_cycles WHERE id = ?", (row_id,)).fetchone()
        existing = (note[0] if note and note[0] else "")
        addition = f"{NOTE_TAG}'{_escape(old)}'"
        combined = f"{existing} | {addition}" if existing else addition
        conn.execute(
            "UPDATE loop_cycles SET task_id = ?, outcome_note = ? WHERE id = ?",
            (new, combined, row_id),
        )
        manifest_lines.append(f"row {row_id}: {old!r} → {new!r}")
    conn.commit()

    remaining, still_skipped = _plan(conn)
    after = conn.execute(
        "SELECT COUNT(*) FROM loop_cycles WHERE task_id LIKE ?", (HOOK_PREFIX + "%",)
    ).fetchone()[0]
    conn.close()

    manifest = Path(args.manifest).expanduser()
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text("\n".join(manifest_lines) + "\n")
    print(f"manifest written      : {manifest}")
    print(f"repaired rows         : {len(changes)}")
    print(f"malformed remaining   : {len(remaining) + len(still_skipped)}")
    print(f"hook cycles now       : {after}")
    print("RESULT: " + ("PASS — every repairable id normalized" if not remaining and not still_skipped
                       else f"PARTIAL — {len(remaining) + len(still_skipped)} row(s) left"))
    return 0 if not remaining and not still_skipped else 1


if __name__ == "__main__":
    raise SystemExit(main())
