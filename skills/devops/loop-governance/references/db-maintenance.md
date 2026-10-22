# DB Maintenance for Loop Governance

> Applies to: `~/.hermes-cortex/data/loop-governance.db`
> Table: `loop_cycles`
> Author: Hermes Cortex — extracted from weekly evaluation pipeline (Jul 2026)

## Retention Policy

| Age | Action | Reason |
|-----|--------|--------|
| < 90 days | Keep online | Active scoring, feedback, and analysis |
| ≥ 90 days | Archive to JSON | Reduces DB size without data loss |
| Archived | Compressed or removed | Agent discretion — kept locally for audit trail |

**Recommended schedule:** Weekly, as part of the evaluation pipeline.

## Full Retention Script

This is the complete, deployable script. Save to `~/.hermes-cortex/scripts/retention.py` for reuse.

```python
#!/usr/bin/env python3
"""
Loop Governance DB Retention — archive cycles older than 90 days and VACUUM.

Usage:
    python3 retention.py                    # dry-run (default)
    python3 retention.py --apply            # actually archive + vacuum
    python3 retention.py --days 180         # custom retention window
"""
import sqlite3, os, json, argparse
from datetime import datetime

def main():
    parser = argparse.ArgumentParser(description="Archive old loop governance cycles")
    parser.add_argument("--apply", action="store_true", help="Actually archive and delete")
    parser.add_argument("--days", type=int, default=90, help="Retention window in days")
    parser.add_argument("--db", default=os.path.expanduser("~/.hermes-cortex/data/loop-governance.db"),
                        help="Path to loop-governance DB")
    args = parser.parse_args()

    if not os.path.exists(args.db):
        print(f"DB not found: {args.db}")
        return

    conn = sqlite3.connect(args.db)
    cur = conn.cursor()

    # Verify table exists
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='loop_cycles'")
    if not cur.fetchone():
        print("Table 'loop_cycles' not found in DB — nothing to do.")
        conn.close()
        return

    # Count old cycles
    cur.execute(f"SELECT COUNT(*) FROM loop_cycles WHERE timestamp < datetime('now', '-{args.days} days')")
    old_count = cur.fetchone()[0]

    if old_count == 0:
        print(f"No cycles older than {args.days} days. DB is clean.")
        before = os.path.getsize(args.db)
        cur.execute("VACUUM")
        conn.commit()
        after = os.path.getsize(args.db)
        freed = before - after
        print(f"Vacuumed: {before} → {after} bytes ({freed} freed)")
        conn.close()
        return

    # Read old cycles
    cur.execute(f"SELECT * FROM loop_cycles WHERE timestamp < datetime('now', '-{args.days} days')")
    old_rows = cur.fetchall()
    cur.execute("PRAGMA table_info(loop_cycles)")
    cols = [c[1] for c in cur.fetchall()]
    archive = [dict(zip(cols, row)) for row in old_rows]

    # Compute stats for reporting
    total_before = cur.execute("SELECT COUNT(*) FROM loop_cycles").fetchone()[0]
    db_before = os.path.getsize(args.db)

    if args.apply:
        # Archive to JSON
        archive_path = os.path.expanduser(
            f'~/.hermes-cortex/data/loop-cycles-archive-{datetime.now().strftime("%Y%m%d")}.json'
        )
        with open(archive_path, 'w') as f:
            json.dump(archive, f, indent=2, default=str)

        # Delete
        cur.execute(f"DELETE FROM loop_cycles WHERE timestamp < datetime('now', '-{args.days} days')")

        # Verify count
        total_after = cur.execute("SELECT COUNT(*) FROM loop_cycles").fetchone()[0]
        expected = total_before - old_count
        assert total_after == expected, f"Count mismatch: deleted {total_before - total_after}, expected {old_count}"

        conn.commit()

        # Vacuum
        cur.execute("VACUUM")
        conn.commit()

        db_after = os.path.getsize(args.db)

        print(f"Archived {old_count} cycles → {archive_path}")
        print(f"Deleted {old_count} rows from loop_cycles")
        print(f"DB: {db_before} → {db_after} bytes (freed {db_before - db_after} bytes)")
        print("Retention complete.")
    else:
        # Dry-run
        print(f"[DRY RUN] Would archive {old_count} cycles older than {args.days} days:")
        # Show date range of old cycles
        min_ts = min(r[1] for r in old_rows)  # timestamp is index 1
        max_ts = max(r[1] for r in old_rows)
        print(f"  Date range: {min_ts} → {max_ts}")
        print(f"  DB size: {db_before} bytes")
        print(f"  Remaining after cleanup: ~{total_before - old_count} cycles")
        print("Pass --apply to execute.")

    conn.close()

if __name__ == "__main__":
    main()
```

## Safety Checks

The script above includes:

1. **Table existence check** — exits gracefully if `loop_cycles` doesn't exist
2. **DB existence check** — exits if DB file is missing
3. **Count assertion** — verifies the deleted row count matches expected
4. **Dry-run mode** — default, requires explicit `--apply` to make changes
5. **No cascading deletes** — `loop_cycles` is the only table with time-based data;
   if `config_history` or `content_assets` grow large, they need separate handling

## Pitfall — sqlite3 CLI binary may not be installed

The `sqlite3` command-line tool is not always present (e.g. minimal Linux images).
Always use Python's built-in `sqlite3` module instead:

```python
import sqlite3
conn = sqlite3.connect(path)  # works without the system sqlite3 binary
```

## Verification After Retention

After running retention, verify with:

```python
import sqlite3, os
db = os.path.expanduser('~/.hermes-cortex/data/loop-governance.db')
conn = sqlite3.connect(db)
cur = conn.cursor()
cur.execute("SELECT COUNT(*), ROUND(AVG(composite),1) FROM loop_cycles")
count, avg = cur.fetchone()
cur.execute("SELECT MIN(timestamp), MAX(timestamp) FROM loop_cycles")
min_ts, max_ts = cur.fetchone()
print(f"Remaining: {count} cycles, avg {avg}/10")
print(f"Range: {min_ts} → {max_ts}")
print(f"DB size: {os.path.getsize(db)} bytes")
conn.close()
```
