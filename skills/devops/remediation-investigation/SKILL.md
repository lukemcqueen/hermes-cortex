---
name: remediation-investigation
description: Trace remediation sensor reports to their source, cross-reference live state, and distinguish transient from chronic cron failures.
version: 1.0.0
---

# Remediation Investigation

## When to Use

Load this skill when:
- The `agent-remediation-sensor` reports a cron_error or service issue
- You need to distinguish a transient timeout from a structural failure
- The auto-remediation skill's known-fix table doesn't cover the reported error
- You need to trace a sensor report back to the actual cron output or jobs.json state

## Sensor Output Architecture

The `agent-remediation-sensor` (no_agent cron, every 5m) writes its findings as JSON
to the **cron output directory**, NOT to a predictable path. Finding it requires scanning.

### Finding the Latest Sensor Output

The sensor's job ID is not predictable. Scan for it:

```bash
find ~/.hermes/cron/output/ -name "*.md" -mmin -10 | xargs grep -l "remediation-sensor\|cron_error\|agent-remediation" 2>/dev/null | head -3
```

Each match is a full .md file containing a JSON array. Read the contents directly.

### Sensor JSON Schema

```json
[
  {
    "type": "cron_error",
    "severity": "high",
    "detail": "Errored cron: orch-skill-lifecycle",
    "context": {
      "job_id": null,
      "name": "orch-skill-lifecycle",
      "last_status": "error"
    },
    "timestamp": "2026-07-26T18:00:30.170571+00:00"
  }
]
```

| Field | Type | Notes |
|-------|------|-------|
| `type` | string | `cron_error`, `disk_pressure`, `service_down`, etc. |
| `severity` | string | `low`/`medium`/`high`/`critical` |
| `detail` | string | Human-readable description |
| `context.name` | string | Cron job name (most useful field) |
| `context.last_status` | string | `error` or `ok` |
| `timestamp` | string | ISO timestamp of when sensor ran |

## Cross-Referencing Sensor vs Live State

The sensor reads `last_status` from `~/.hermes/cron/jobs.json`, which means:

- **The sensor output can be up to 5 minutes stale** — the sensor runs every 5m
- **`last_status="error"` persists** until the job runs again successfully. An error from 12 hours ago still shows as "error" in the sensor report
- **Always cross-reference `last_run_at` timestamp** to determine recency

### Read jobs.json Directly

The `cronjob(action='list')` MCP tool does not exist. Use the raw jobs.json file:

```python
import json, os
with open(os.path.expanduser('~/.hermes/cron/jobs.json')) as f:
    data = json.load(f)
errored = [j for j in data['jobs'] if j.get('last_status') == 'error']
```

Key fields in each job dict:

| Field | Type | What it tells you |
|-------|------|-------------------|
| `name` | str | Cron job name |
| `last_status` | str | `"ok"` or `"error"` |
| `last_error` | str or null | The error message from the last run |
| `last_run_at` | str (ISO) | When the job last ran |
| `next_run_at` | str (ISO) | When it will next run |
| `state` | str | `"scheduled"`, `"paused"`, etc. |
| `enabled` | bool | Is the job active |

## Diagnosing Transient vs Chronic

### Transient (self-heals, no action needed)
- Error message mentions `TimeoutError`, `timeout`, `connection reset`, `5xx status`
- Internet connectivity is fine (`ping -c1 google.com` works)
- The job has a next_run_at in the near future (self-retry)
- The same error has not recurred across multiple sensor ticks

### Chronic (needs structural fix)
- Script not found, permission denied, import error, config error
- The same error persists across 3+ consecutive sensor ticks
- The error message points to a missing file, wrong path, or stale config
- The job's schedule is missed (next_run_at is in the past and last_run_at is days old)

### Fix Patterns

For transient timeouts: no action needed — the job will retry on its next schedule.
For chronic errors: apply the fix from `auto-remediation` skill's known-fix table,
then verify by re-running the failing script or checking the service directly.

## Bus Health Verification

The Agent Bus listens on port **8903** (not 8905):

```bash
curl -s http://localhost:8903/health
# → {"status":"ok","backend":"pgmq","queues":N,...}
```

Requires `CORTEX_BUS_TOKEN` from `~/.hermes-cortex/.env` for direct API calls.
The bus-audit-watchdog (no_agent cron, every 1m) is the primary health indicator.
