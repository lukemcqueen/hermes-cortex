#!/usr/bin/env python3
"""
Loop Governance DB Retention — archive cycles older than N days and VACUUM.

Ships with the loop-governance skill, where it used to exist only as prose inside
references/db-maintenance.md. A script that lives in a document cannot be run,
tested or deployed, so it lives here and the reference points at it.

Usage:
    python3 loop-retention.py                    # dry-run (default)
    python3 loop-retention.py --apply            # archive + delete + vacuum
    python3 loop-retention.py --days 180         # custom retention window
    python3 loop-retention.py --db /path/to.db   # non-default DB

Safety: dry-run is the default, the row-count change is ASSERTED before commit,
and the archive is written before anything is deleted.
"""
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime

DEFAULT_DB = "~/.hermes-cortex/data/loop-governance.db"
TABLE = "loop_cycles"


def timestamp_index(cols):
    """Index of the `timestamp` column, located BY NAME.

    Never hardcode this. The table has been widened repeatedly (19 columns as of
    2026-10-22) and `timestamp` sits at index 1 only by accident of history — an
    ALTER that reorders, a rebuilt table, or a fixture with different column order
    silently makes `row[1]` a different field, and the retention script then
    reports the date range of whatever happens to be second.
    """
    try:
        return cols.index("timestamp")
    except ValueError:
        raise SystemExit(f"COULD NOT VERIFY: {TABLE} has no `timestamp` column "
                         f"(columns: {', '.join(cols)})")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Archive old loop-governance cycles")
    ap.add_argument("--apply", action="store_true", help="Actually archive and delete")
    ap.add_argument("--days", type=int, default=90, help="Retention window in days")
    ap.add_argument("--db", default=os.path.expanduser(DEFAULT_DB), help="Path to the DB")
    args = ap.parse_args(argv)

    if not os.path.exists(args.db):
        print(f"COULD NOT VERIFY: DB not found: {args.db}", file=sys.stderr)
        return 3

    conn = sqlite3.connect(args.db)
    cur = conn.cursor()

    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (TABLE,))
    if not cur.fetchone():
        print(f"Table '{TABLE}' not found — nothing to do.")
        conn.close()
        return 0

    cols = [c[1] for c in cur.execute(f"PRAGMA table_info({TABLE})").fetchall()]
    ts = timestamp_index(cols)

    cutoff = f"-{args.days} days"
    old_count = cur.execute(
        f"SELECT COUNT(*) FROM {TABLE} WHERE timestamp < datetime('now', ?)", (cutoff,)
    ).fetchone()[0]

    total_before = cur.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
    db_before = os.path.getsize(args.db)

    if old_count == 0:
        print(f"No cycles older than {args.days} days. DB is clean.")
        if args.apply:
            cur.execute("VACUUM")
            conn.commit()
            print(f"Vacuumed: {db_before} → {os.path.getsize(args.db)} bytes")
        conn.close()
        return 0

    old_rows = cur.execute(
        f"SELECT * FROM {TABLE} WHERE timestamp < datetime('now', ?)", (cutoff,)
    ).fetchall()
    archive = [dict(zip(cols, row)) for row in old_rows]
    min_ts = min(r[ts] for r in old_rows)
    max_ts = max(r[ts] for r in old_rows)

    if not args.apply:
        print(f"[DRY RUN] Would archive {old_count} cycles older than {args.days} days:")
        print(f"  Date range: {min_ts} → {max_ts}")
        print(f"  DB size: {db_before} bytes")
        print(f"  Remaining after cleanup: ~{total_before - old_count} cycles")
        print("Pass --apply to execute.")
        conn.close()
        return 0

    archive_path = os.path.expanduser(
        f"~/.hermes-cortex/data/loop-cycles-archive-{datetime.now().strftime('%Y%m%d')}.json"
    )
    # The archive is written BEFORE anything is deleted, so it must not be able to
    # fail on a missing directory: a host whose data/ dir was never created would
    # otherwise abort here, and an abort that happens after the DELETE would lose
    # rows with no archive. Create the dir, then write, then delete.
    parent = os.path.dirname(archive_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(archive_path, "w") as f:
        json.dump(archive, f, indent=2, default=str)

    cur.execute(f"DELETE FROM {TABLE} WHERE timestamp < datetime('now', ?)", (cutoff,))
    total_after = cur.execute(f"SELECT COUNT(*) FROM {TABLE}").fetchone()[0]
    expected = total_before - old_count
    if total_after != expected:
        conn.rollback()
        conn.close()
        print(f"REFUSING: count mismatch — deleted {total_before - total_after}, "
              f"expected {old_count}. Rolled back.", file=sys.stderr)
        return 1
    conn.commit()

    cur.execute("VACUUM")
    conn.commit()
    db_after = os.path.getsize(args.db)

    print(f"Archived {old_count} cycles → {archive_path}")
    print(f"Deleted {old_count} rows from {TABLE}")
    print(f"DB: {db_before} → {db_after} bytes (freed {db_before - db_after} bytes)")
    print("Retention complete.")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
