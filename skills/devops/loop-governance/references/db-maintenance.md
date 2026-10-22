# DB Maintenance for Loop Governance

> Applies to: `~/.hermes-cortex/data/loop-governance.db`
> Table: `loop_cycles`
> Author: Hermes Cortex — extracted from weekly evaluation pipeline (Jul 2026)
> Schema last MEASURED: 2026-10-22 (`PRAGMA table_info(loop_cycles)`)

## Retention Policy

| Age | Action | Reason |
|-----|--------|--------|
| < 90 days | Keep online | Active scoring, feedback, and analysis |
| ≥ 90 days | Archive to JSON | Reduces DB size without data loss |
| Archived | Compressed or removed | Agent discretion — kept locally for audit trail |

**Recommended schedule:** Weekly, as part of the evaluation pipeline.

## The Retention Script

Lives at **`skills/devops/loop-governance/scripts/loop-retention.py`** and is
exercised by `tests/test_loop_retention.py`. It used to exist only as a listing on
this page, which meant it could not be run, tested, or deployed — and two defects
survived in it because nothing ever executed it (both fixed on 2026-10-22):

- it read the timestamp as **`row[1]`**, a positional index. `timestamp` lands at
  index 1 in today's table *by accident of history* — the table has been widened
  repeatedly and now has 19 columns — so any reorder silently makes the date-range
  report describe a different field. It now locates the column **by name** via
  `PRAGMA table_info`, and refuses with `COULD NOT VERIFY` if there is no
  `timestamp` column at all.
- it wrote the archive **before** checking that the archive directory exists.
  A host whose `data/` dir was never created would abort on the write — and an
  abort placed after the `DELETE` loses rows with no archive. It now creates the
  parent directory first.

```bash
python3 skills/devops/loop-governance/scripts/loop-retention.py            # dry-run (default)
python3 skills/devops/loop-governance/scripts/loop-retention.py --apply    # archive + delete + vacuum
python3 skills/devops/loop-governance/scripts/loop-retention.py --days 180 # custom window
```

Dry-run is the default; the row-count change is asserted before commit and rolls
back on mismatch; the archive is written before anything is deleted.

## Schema (measured, not assumed)

`loop_cycles`, 19 columns as of 2026-10-22, in this order:

```
id, timestamp, task_id, cycle_num, spec_hash, code_hash, test_output_hash,
completeness, quality, progress, composite, no_progress, decision,
user_overrode, outcome_note, schema_version, model_name, session_id,
unscored_reason
```

Sibling tables in the same DB: `adversarial_reviews`, `blob_reviews`,
`config_history`, `content_assets`, `task_events`. Only `loop_cycles` carries
time-based data today; if `config_history` or `content_assets` grow large they
need separate handling — nothing here cascades to them.

## Safety Checks

1. **DB existence check** — exits with `COULD NOT VERIFY` and rc=3 if missing
2. **Table existence check** — exits gracefully if `loop_cycles` doesn't exist
3. **Count assertion** — verifies the deleted row count matches expected, else rolls back
4. **Dry-run mode** — default, requires explicit `--apply` to make changes
5. **No cascading deletes** — see above

## Pitfalls

**The `sqlite3` CLI binary may not be installed** (e.g. minimal Linux images).
Use Python's built-in `sqlite3` module instead — `sqlite3.connect(path)` works
without the system binary.

**A 0-byte `state/loop-governance.db` exists alongside the real one.** The live DB
is the ~170 MB file under `data/`; `state/loop-governance.db` is empty, so a script
pointed at it reports "table not found" and looks like data loss. Check the path and
the file size before concluding anything. `sqlite3.connect` will happily *create* a
missing DB, so a typo'd path yields a silent empty database rather than an error —
the existence check above exists for that reason.

## Verification After Retention

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
