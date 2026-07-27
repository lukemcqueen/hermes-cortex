# Compact Health Vector Format — Source Reference

This file documents the exact source code implementing the compact health
endpoint (`/health` and `/` routes) in `health-server.py`.

## Source Location

- File: `hermes-cortex/ops/scripts/health-server.py`
- Function: `_build_compact_health()` (lines ~468-520)
- Route: `GET /health` and `GET /` → returns `_build_compact_health()`

## Canonical Vector Definition

```python
v = [
    1 if resources_ok else -1,         # [0] resources
    1 if services_ok else -1,          # [1] services
    1 if no_errored else -1,           # [2] no errored crons
    1 if no_stale else -1,             # [3] no stale crons
    1 if nginx_ok else -1,             # [4] nginx
    1 if ollama_ok else -1,            # [5] ollama
    1 if gbrain_ok else -1,            # [6] gbrain
    1 if disk_ok else -1,              # [7] disk
    1 if gbrain_sources_ok else -1,    # [8] gbrain sources
]
```

**Key properties:**
- Always 9 elements (unlike legacy 8-element format)
- All values are either `1` (healthy) or `-1` (unhealthy/warning)
- No `0` (n/a) — every check always produces a binary result
- Returned on both `GET /health` and `GET /` routes

## Per-index Semantics

### [0] resources — Resources health
- Checks: disk usage, memory usage, CPU
- `-1` if disk > 90% (critical) or memory > 90% (critical)
- Warning threshold: disk > 80% or memory > 80% (still returns `-1`)

### [1] services — Critical services health
- Checks: nginx, ollama, gbrain via pgrep
- `-1` if any critical service is stopped

### [2] no errored crons — Cron job error status
- Reads `~/.hermes/cron/jobs.json`
- `-1` if any cron job has `last_status: "error"`

### [3] no stale crons — Cron job staleness
- Reads `~/.hermes/cron/jobs.json`
- `-1` if any cron job has not run in >24 hours
- **NOT a service outage** — just indicates potential neglect

### [4] nginx — nginx process status
- `pgrep -f "nginx: master"` check
- `-1` if nginx master process not found

### [5] ollama — Ollama process status
- `pgrep -f ollama` check
- `-1` if ollama process not found

### [6] gbrain — gbrain process status
- `pgrep -f gbrain` check
- `-1` if gbrain process not found

### [7] disk — Disk usage threshold
- Checks `df -h /` disk usage percentage
- `-1` if disk usage ≥ 80%

### [8] gbrain sources — gbrain source health
- Runs `gbrain doctor --json` or `gbrain sources list`
- `-1` if sources are unhealthy, never synced, or have 0 pages
- Gracefully handles gbrain being unavailable (returns healthy = UNKNOWN)

## Response Format

```json
{
  "v": [1, 1, 1, -1, 1, 1, 1, 1, 1],
  "h": "j",
  "t": 1782840651
}
```

| Field | Meaning | Example |
|-------|---------|---------|
| `v` | Status vector (9 elements) | `[1,1,1,-1,1,1,1,1,1]` |
| `h` | Agent identifier (single char) | `"j"` = Joseph, `"m"` = Moses, `"g"` = Gisu, `"t"` = Titus |
| `t` | Unix timestamp | `1782840651` |

## Agent Identifiers

| Agent | `h` value |
|-------|-----------|
| Moses | `"m"` |
| Gisu | `"g"` |
| Kustos | `"k"` |
| Joseph | `"j"` |
| Esther | `"e"` |
| Titus | `"t"` |

Set via `AGENT_ID` env var or falls back to the first character of `SERVER_NAME`
(first segment of `platform.node()`).
