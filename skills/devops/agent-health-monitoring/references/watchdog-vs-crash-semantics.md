# Watchdog vs Crash Semantics in Health Vector

Health vector index `[2]` = `no_errored_crons` — but "errored" in the health
server's cron check means **any cron with `last_status: "error"`** in jobs.json.
This conflates two very different situations:

## Two Meanings of "Errored"

### 1. Crash/Failure — the script actually broke

Something went wrong executing the script:
- Script not found / missing path
- Python import error / syntax error
- Permission denied
- Timeout exceeded

**Fix:** Debug the script. The cron truly needs attention.

### 2. Detection — the watchdog worked correctly

A no_agent watchdog script exited non-zero because it **detected a real condition**
— not because it crashed:
- `scoring-activity-watchdog` → found 0 governance cycles today, exited 1
- `disk-watchdog` → found disk above threshold, exited 1
- `model-health-watchdog` → found model missing, exited 1

**No fix needed.** The watchdog is doing its job. The `-1` in the health vector is
accurate — there IS a condition to be aware of — but it's not a script failure.

## How to Tell the Difference

### Step 1: Get the full health response, not just the compact vector

```bash
curl -sk https://localhost:13007/api/v1/health | python3 -m json.tool
```

The compact `/health` endpoint only shows the vector. The full `/api/v1/health`
endpoint includes `checks.cron_health` with a list of errored job names.

### Step 2: Read the errored cron's last output

The cron output tells you WHAT happened — crash (traceback) or detection (intentional message):

```bash
# Find the cron output directory by job_id
ls ~/.hermes/cron/output/<job_id>/
cat ~/.hermes/cron/output/<job_id>/output.txt
```

### Step 3: Diagnose based on the output

| Output pattern | Meaning | Action |
|---------------|---------|--------|
| Python traceback / ImportError | Crash | Fix the script |
| "command not found" / "No such file" | Crash | Install the missing dep |
| Intentionally worded alert (*"⚠️  Scoring activity low: 0 cycles today"*) | Detection | Verify the condition is real |
| Exit code 1 with structured message | Detection | Check if the condition resolved |
| Exit code 1 with stdout that explains why | Detection | The watchdog worked |

### Step 4: Verify the condition, not the error

For detection-type "errors", verify whether the thing the watchdog detected is real:

```bash
# For scoring-activity-watchdog: how many cycles today?
python3 -c "
import sqlite3
db = '~/.hermes-cortex/data/loop-governance.db'
c = sqlite3.connect(db)
print(c.execute(\"SELECT COUNT(*) FROM loop_cycles WHERE timestamp >= date('now')\").fetchone()[0])
"
```

If the condition is real and being addressed, the health `-1` is correct — it will
clear when the watchdog next runs and finds the condition resolved.

## Implications for Dashboards

Health dashboards that display per-agent vector bars will show `🔴` on index `[2]`
whenever any watchdog has recently detected a condition — even if the watchdog
worked perfectly. This is **by design**: the health endpoint reports the state of
the system, and an active detection IS that state.

To distinguish at a glance:
- **Process-level crash** → the errored cron list changes rarely and always has the same jobs
- **Detection event** → the errored cron list changes as conditions come and go

If a single cron stays in "errored" state across multiple watchdog runs, it's
likely a crash (the watchdog runs every few minutes, and each run finds the same
error). If it comes and goes, it's likely a detection watchdog.
