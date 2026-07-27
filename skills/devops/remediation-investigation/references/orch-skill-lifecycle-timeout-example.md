# Worked Example: orch-skill-lifecycle Timeout

## Sensor Report

On 2026-07-26 at 18:00:30 UTC (03:00:30 KST+09 on 2026-07-27), the sensor reported:

```json
{
  "type": "cron_error",
  "severity": "high",
  "detail": "Errored cron: orch-skill-lifecycle",
  "context": { "name": "orch-skill-lifecycle", "last_status": "error" }
}
```

## Investigation

### 1. Find the actual error message

Read `~/.hermes/cron/jobs.json` and find the job:

```python
import json
with open('~/.hermes/cron/jobs.json') as f:
    data = json.load(f)
for j in data['jobs']:
    if j['name'] == 'orch-skill-lifecycle':
        print(j['last_error'])
```

### 2. Read the error

```
TimeoutError: Cron job 'orch-skill-lifecycle' idle for 602s (limit 600s)
— last activity: waiting for non-streaming API response
```

### 3. Check the schedule

- Runs daily at 04:00 KST (schedule: `0 4 * * *`)
- Last run: 2026-07-26 04:11 (failed)
- Next run: 2026-07-27 04:00 (~54 minutes away)

### 4. Assess

- **Error type:** TimeoutError — transient API issue
- **Internet?** `ping -c2 google.com` — 35ms, 0% loss ✅
- **Other crons affected?** All 45+ other jobs ran fine ✅
- **Is the same error persisting?** This is the first consecutive report (1 sensor tick) — no chronic pattern yet

### 5. Decision

**Transient timeout — no action needed.** The job self-retries at 04:00 KST.
Do NOT restart the service, do NOT raise an alert. Report SILENT.

## What to watch for

- If the same error appears in the next sensor tick AFTER the 04:00 run → it's chronic (provider timeout too aggressive)
- If the job never runs (next_run_at kept slipping) → the cron scheduler may be stuck
- If multiple different jobs start timing out → systemic provider/network issue
