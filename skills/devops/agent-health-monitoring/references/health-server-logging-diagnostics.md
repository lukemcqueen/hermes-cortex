# Health Server Logging & Diagnostics

This reference documents the structured logging format in `health-server.py`
(added July 2026) and a diagnostic workflow for investigating health endpoint
instability.

## Log Line Reference

All log lines use ISO-8601 timestamps with milliseconds and are written to stdout
(captured by systemd journal on Linux, log file on other platforms).

```
2026-07-02T08:57:13.625 [LEVEL] PREFIX — message
```

### Prefix Catalog

| Prefix | Level | When | Example |
|--------|-------|------|---------|
| `STARTING` | INFO | Process starts | `STARTING — server=moses agent=m port=8905 os=linux/6.14.0 python=3.11.15` |
| `CONFIG` | INFO | Startup | `CONFIG — _STARTUP_TS=1782950206 HOME=/home/moses` |
| `HEALTH` | INFO | `/api/v1/health` complete | `HEALTH — m total=0.3s resources=0.1s services=0.2s crons=0.0s gbrain=0.0s` |
| `COMPACT` | INFO | `/health` or `/` complete | `COMPACT — e total=20.1s resources=0.0s services=0.1s crons=0.0s gbrain=20.0s` |
| `SLOW CHECK` | INFO | Any single check > 2s | `SLOW CHECK — gbrain_sources took 4.5s` |
| `SLOW COMPACT HEALTH` | WARN | Total request > 5s | `SLOW COMPACT HEALTH — m took 20.1s` |
| `DEADLINE EXCEEDED` | WARN | gbrain check hit 20s cap | `DEADLINE EXCEEDED — gbrain_sources did not finish in 20.0s (20.0s elapsed)` |
| `DEADLINE ERROR` | ERROR | gbrain check threw exception | `DEADLINE ERROR — gbrain_sources failed after 3.2s: [Errno 12] Cannot allocate memory` |
| `CHECK FAILED` | ERROR | Any check threw exception | `CHECK FAILED — services crashed after 0.1s\nTraceback...` |
| `SHUTDOWN` | WARN | Process exiting on signal | `SHUTDOWN — received signal 15, exiting` |

### Reading COMPACT/HEALTH Lines

The per-check timing reveals which check is the bottleneck:

```
COMPACT — e total=20.1s resources=0.0s services=0.1s crons=0.0s gbrain=20.0s
```

Here `gbrain=20.0s` means the gbrain_sources check took 20 seconds — it hit the
deadline. The endpoint still returned HTTP 200 with degraded data.

## Diagnostic Workflow

### Step 1: Is the process running?

```bash
systemctl --user status com.hermes.health-server.service
```

Look for `active (running)` or `failed`. If `failed`, check exit code and
restart count:

```bash
systemctl --user show com.hermes.health-server.service -p NRestarts
systemctl --user show com.hermes.health-server.service -p MainPID -p ExecMainStatus
```

A restart count > 3 in a short window means the process is repeatedly crashing.

### Step 2: Read the journal

```bash
journalctl --user -u com.hermes.health-server.service --since "1 hour ago" --no-pager
```

Look for:
- **DEADLINE EXCEEDED** — which check is hanging (usually gbrain_sources)
- **CHECK FAILED** — traceback showing the crash site
- **SHUTDOWN** — why the process exited
- **STARTING** repeated frequently = crashing on loop

### Step 3: Check Ollama (most common cascade failure)

Ollama's GPU driver crash can destabilize the whole system. Check:

```bash
journalctl --user -u ollama.service --since "1 hour ago" --no-pager | grep -i "vk::DeviceLostError\|Vulkan\|ggml_vulkan"
```

If you see `vk::DeviceLostError` (on old Intel HD 4000 / Ivy Bridge hardware),
the GPU is the root cause. Fix:

```bash
# Force CPU-only inference
systemctl --user edit ollama.service
# Add: Environment="OLLAMA_GPU_LAYER=false"
systemctl --user daemon-reload
systemctl --user restart ollama.service
```

### Step 4: Check OOM kills

```bash
dmesg | grep -i "health-server\|ollama" | grep -i "killed"
```

If the health server or ollama was OOM-killed, check memory pressure:

```bash
free -h
# If < 500MB free, resource pressure is the root cause
```

### Step 5: Test locally (bypasses nginx)

```bash
curl -s --max-time 30 http://127.0.0.1:8905/health | jq .
```

If this works but the external endpoint (via nginx) doesn't, the issue is
nginx, not the health server.

### gbrain Cache TTL & Timing Baseline

The gbrain_sources check caches its result for **900 seconds** (15 minutes).
This is a deliberate trade-off: `gbrain doctor --json` takes **~31 seconds**
on a healthy system (only ~1s CPU — most of the time is I/O waiting on
Ollama embeddings for sync freshness checks). On a system where Ollama is
stressed or crashing, it can take the full 45s internal timeout, or hang
indefinitely.

**Cache parameters:**
- `_GBRAIN_CACHE_TTL = 900` — 15 minutes (bumped from 300 to reduce blocking frequency)
- `_GBRAIN_CACHE_TTL = 300` — was 5 minutes (original; caused a 20s block every 5 min)
- 20s hard deadline via `_run_with_deadline()` prevents the endpoint from
  hanging even when the cache is cold

**Baseline timing values for diagnosis:**
- `gbrain doctor --json` on healthy system: **~31s total** (~1s CPU, ~30s I/O)
- Four non-gbrain checks combined: **< 0.5s** (resources, services, crons)
- Total health endpoint response: **~0.5s** when gbrain cache is warm
- Total with cold gbrain cache: **~20.1s** (hits the 20s deadline)

If you see DEADLINE EXCEEDED in the logs repeatedly, gbrain's underlying
Ollama dependency is the bottleneck — not the health server itself.
See the Ollama GPU crash pitfall in SKILL.md.

### Shared Infra Notification Pattern

When a fix is deployed to shared infrastructure (`health-server.py`,
`health-vector.py`, `cortex-update.sh`, etc.):

1. **Commit and push** to the shared repo
2. **Notify ALL affected agents** via inbox, not just the one that reported the issue
3. Include exact update commands in the notification: `git pull && bash ops/scripts/cortex-update.sh --force-all`
4. CC the user on each notification

This avoids repeated rounds of "is anyone else having this problem?"

## Implementation Details

The logging infrastructure uses Python's `logging` module with a custom
formatter, writing to stdout (where systemd captures it). Key design decisions:

- **`_timed(label, fn)`** — wraps any check function, returns `(result, elapsed_seconds)`.
  Never lets exceptions escape. Logs `SLOW CHECK` if > 2s.
- **`_run_with_deadline(fn, timeout, label)`** — runs a function in a
  `ThreadPoolExecutor(max_workers=2)` with a hard timeout. Returns degraded
  result on deadline exceedance.
- **Shutdown handlers** — SIGTERM and SIGINT handlers log the signal before
  exiting, so journalctl captures why the process stopped.
