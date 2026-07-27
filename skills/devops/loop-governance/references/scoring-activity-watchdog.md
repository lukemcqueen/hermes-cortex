# scoring-activity-watchdog — Design Reference

## Purpose

A no_agent watchdog that closes the **config-only change blind spot** in loop governance enforcement. Config-only changes (cron migrations, sudoers entries, systemd services, nginx configs, package installs) never flow through git and are invisible to the pre-commit hook and score-auditor. This watchdog alerts when daily scoring activity is below expected thresholds.

## Cron Schedule

`0 14,20 * * *` (twice daily: 14:00 and 20:00 KST)

## Script Location

`~/.hermes/scripts/scoring-activity-watchdog.py` (deployed manually, not via installer)

## Core Logic

```python
DB_PATH = "~/.hermes/data/loop-governance.db"
THRESHOLDS = {
    14: 1,  # by 2pm: at least 1 change scored
    20: 2,  # by 8pm: at least 2 changes scored
}

conn = sqlite3.connect(DB_PATH)
today = datetime.date.today().isoformat()
cur = conn.execute(
    "SELECT COUNT(*) FROM loop_cycles WHERE timestamp >= ?",
    (today,)
)
count = cur.fetchone()[0]

# Find the highest threshold that the current hour meets
expected = max(v for k, v in THRESHOLDS.items() if hour >= k)

if count < expected:
    # Alert — stdout delivered to origin
    print(f"⚠️  Scoring activity low: {count} cycle(s) today ...")
    exit(1)

# Silent exit — no output, no delivery
exit(0)
```

## DB Schema

The `loop_cycles` table in `~/.hermes/data/loop-governance.db`:

```sql
CREATE TABLE loop_cycles (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT NOT NULL DEFAULT (datetime('now')),
    task_id         TEXT NOT NULL,
    cycle_num       INTEGER NOT NULL,
    spec_hash       TEXT,
    code_hash       TEXT,
    test_output_hash TEXT,
    completeness    REAL NOT NULL,
    quality         REAL NOT NULL,
    progress        REAL NOT NULL,
    composite       REAL NOT NULL,
    no_progress     INTEGER NOT NULL DEFAULT 0,
    decision        TEXT NOT NULL,
    user_overrode   INTEGER,
    outcome_note    TEXT,
    schema_version  INTEGER DEFAULT 1,
    model_name      TEXT DEFAULT 'nomic-embed-text'
);
```

## Common Query Patterns

```sql
-- Cycles today
SELECT COUNT(*) FROM loop_cycles WHERE timestamp >= date('now');

-- Cycles in last N hours
SELECT COUNT(*) FROM loop_cycles WHERE timestamp >= datetime('now', '-4 hours');

-- Un-feedbacked cycles
SELECT id, task_id, timestamp, composite, decision
FROM loop_cycles WHERE user_overrode IS NULL
ORDER BY timestamp DESC;

-- Recent cycles summary
SELECT id, task_id, composite, decision, user_overrode
FROM loop_cycles ORDER BY id DESC LIMIT 10;
```

## Threshold Design

| Time | Expected | Rationale |
|------|----------|-----------|
| Before 14:00 | 0 | Work may not have started yet |
| 14:00–19:59 | ≥1 | At least one change should be scored by mid-afternoon |
| 20:00+ | ≥2 | Full day of work should have multiple scored changes |

Thresholds are conservative to avoid false alerts on slow days. They can be tightened if the team becomes consistent about scoring.

## Adding to a New Machine

1. Copy `scoring-activity-watchdog.py` to `~/.hermes/scripts/`
2. Create the cron:
   ```
   cronjob action=create name=scoring-activity-watchdog schedule="0 14,20 * * *" no_agent=true script=scoring-activity-watchdog.py deliver=origin
   ```
3. Test: `python3 ~/.hermes/scripts/scoring-activity-watchdog.py; echo $?`
