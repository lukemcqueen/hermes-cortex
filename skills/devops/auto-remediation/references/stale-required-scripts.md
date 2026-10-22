# Stale `required_scripts` After Repo Reorganization

## Error Signal

The `remediation-sensor.py` (no_agent, every 5m) reports:

```json
{
  "type": "script_missing",
  "severity": "high",
  "detail": "Missing script: cron-auto-remediate.sh",
  "context": { "path": "/home/esther/.hermes/scripts/cron-auto-remediate.sh" }
}
```

All cron jobs have `last_status: "ok"` — no actual failures. The sensor's
`check_scripts()` has a hardcoded `required_scripts` list that hasn't been
updated after a repo reorganization.

## Root Cause

The hermes-cortex repo was reorganized: operational scripts moved from
`src/scripts/` (deleted) → `ops/scripts/{health,manage}/`. The sensor's
`required_scripts` list was never updated to source from the new paths.

Scripts affected in this deployment:

| Sensor name | Repo path |
|---|---|
| `cron-auto-remediate.sh` | `ops/scripts/health/cron-auto-remediate.sh` |
| `daily-lesson-mine.sh` | `ops/scripts/manage/daily-lesson-mine.sh` |
| `update-session-state.sh` | `ops/scripts/manage/update-session-state.sh` |

## Fix

```bash
# Locate via git
cd ~/hermes-cortex
git ls-files -- '*/cron-auto-remediate.sh'
# → ops/scripts/health/cron-auto-remediate.sh

# Copy from actual repo path
cp ~/hermes-cortex/ops/scripts/health/cron-auto-remediate.sh ~/.hermes/scripts/
chmod +x ~/.hermes/scripts/cron-auto-remediate.sh
# Repeat for each missing script
```

## Verification

```bash
python3 ~/.hermes/scripts/remediation-sensor.py
# Should output: []
```

## Lesson

When a repo reorganization moves scripts (e.g. `src/` → `ops/`), two things
get stale and must both be updated:
1. The sensor/watchdog's `required_scripts` list (or deploy step)
2. The `auto-remediation` skill's fix-table entry for "Script not found"
