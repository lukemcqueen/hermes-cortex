#!/usr/bin/env python3
"""Backfill `unscored_reason` on cycles closed by the OLD orphan reaper.

Why this exists
---------------
The doctor's `Orphan-cycle resolution` check exists to keep `closed` distinguishable
from `judged` (Luke, 2026-10-02: "there should be no open cycles ... i want honesty
and doing things the right way"). The CURRENT reaper writes an explicit
`unscored_reason` tagged ``[orphan-reaper]``; rows closed BEFORE that change carry a
bare ``MOVE_ON`` decision with no ``unscored_reason`` at all, so their provenance
survives only as prose inside ``outcome_note``. The check reports those rows as INFO
so they are never silently read as judged — but an INFO that nothing can clear is a
report nobody can act on.

This tool clears it the way the current reaper would have: every legacy row gets the
reason it was actually closed, derived from the row's OWN ``outcome_note``, so the
distinction the check protects is made rather than asserted. It changes no score,
no decision, and no outcome_note.

Idempotent. ``--dry-run`` is the default and writes nothing.

Usage:
  python3 ops/scripts/manage/backfill-legacy-reaper-cycles.py              # dry run
  python3 ops/scripts/manage/backfill-legacy-reaper-cycles.py --apply
  python3 ops/scripts/manage/backfill-legacy-reaper-cycles.py --db <path>  # tests

Exit codes: 0 = ok (including "nothing to do"); 3 = could not verify (no/unreadable DB).
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

# Must match cortex_doctor/checks.py and mcp-servers/loop-gov-mcp.py — tests assert it.
ORPHAN_REAPER_TAG = "[orphan-reaper]"

DEFAULT_DB = Path.home() / ".hermes-cortex" / "data" / "loop-governance.db"

# The doctor's legacy predicate, mirrored exactly: an empty reason AND the old
# reaper's outcome_note. A row matching this is "closed but not tagged".
LEGACY_SQL = (
    "SELECT id, task_id, session_id, outcome_note FROM loop_cycles "
    "WHERE (unscored_reason IS NULL OR trim(unscored_reason)='') "
    "AND outcome_note LIKE '%auto-resolved by governance MCP%'"
)

LEGACY_REASON = (
    f"{ORPHAN_REAPER_TAG} legacy: closed by the pre-2026-10-02 orphan reaper - bare "
    "MOVE_ON with no unscored_reason (outcome_note: 'auto-resolved by governance MCP'); "
    "not a judged cycle"
)


def _connect(db: Path, *, read_only: bool) -> sqlite3.Connection:
    if read_only:
        return sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    return sqlite3.connect(db)


def legacy_rows(con: sqlite3.Connection) -> list[tuple]:
    """Rows the doctor reports as legacy: closed by the old reaper, never tagged."""
    return con.execute(LEGACY_SQL).fetchall()


def run(db: Path, *, apply: bool, out=print) -> int:
    """Tag every legacy row. Returns 0 ok (incl. nothing to do), 3 could not verify."""
    if not db.exists():
        out(f"COULD NOT VERIFY: no governance DB at {db}")
        return 3
    try:
        con = _connect(db, read_only=not apply)
    except sqlite3.Error as exc:
        out(f"COULD NOT VERIFY: cannot open {db}: {exc}")
        return 3
    try:
        try:
            rows = legacy_rows(con)
        except sqlite3.Error as exc:
            out(f"COULD NOT VERIFY: cannot read loop_cycles in {db}: {exc}")
            return 3

        if not rows:
            out(f"0 legacy reaper row(s) to backfill in {db.name} - nothing to do")
            return 0

        out(f"{len(rows)} legacy reaper row(s) in {db.name}:")
        for cid, task, _sess, _note in rows:
            out(f"  #{cid}  {task}")

        if not apply:
            out("DRY RUN - nothing written. Re-run with --apply to tag these rows.")
            return 0

        con.executemany(
            "UPDATE loop_cycles SET unscored_reason=? WHERE id=? "
            "AND (unscored_reason IS NULL OR trim(unscored_reason)='')",
            [(LEGACY_REASON, cid) for cid, *_ in rows],
        )
        con.commit()
        remaining = len(legacy_rows(con))
        out(f"tagged {len(rows)} row(s) with {ORPHAN_REAPER_TAG!r}; remaining untagged: {remaining}")
        if remaining:
            out(f"COULD NOT VERIFY: {remaining} legacy row(s) still untagged")
            return 3
        return 0
    finally:
        con.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=os.environ.get("LOOP_GOV_DB") or str(DEFAULT_DB),
                    help=f"governance SQLite DB (default: {DEFAULT_DB})")
    ap.add_argument("--apply", action="store_true", help="write the backfill (default: dry run)")
    args = ap.parse_args()
    return run(Path(args.db).expanduser(), apply=args.apply)


if __name__ == "__main__":
    sys.exit(main())
