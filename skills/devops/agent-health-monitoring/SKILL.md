---
name: agent-health-monitoring
description: Cross-server agent health monitoring using binary status vectors — deploy health endpoints on each agent, poll from orchestrator, alert on state transitions.
version: 3.5.0
author: Hermes Cortex
platforms: [macos, linux]
---

# Agent Health Monitoring

## ⚠️ Mandatory Health Verification Protocol — FOLLOW EVERY TIME

Before claiming any agent is healthy or reporting health status, execute these steps **in order**. Localhost checks are NOT sufficient — external reachability is the only valid measure.

### Step 1: Identify the external health URL

For the current agent (Moses), read `CORTEX_HEALTH_URL` from `.env`:
```bash
grep CORTEX_HEALTH_URL ~/hermes-cortex/.env
# → https://example.com:13007/health
```

For remote agents in the registry, read `health_url` from `agent-registry.json` (merged with local overrides from `~/.hermes/agent-registry.local.json`). The public registry's `http://127.0.0.1:PORT/health` defaults are LOCALHOST PLACEHOLDERS — never trust them as the external truth.

### Step 2: Probe the external URL

```bash
curl -sS --max-time 10 <EXTERNAL_HEALTH_URL>
```

This returns the full vector (e.g. `{"v":[1,1,-1,1,1,1,1,1,1],"h":"m","t":...}`). Use the external response. Discard any localhost-only curl you ran earlier — it does not count.

### Step 3: Decode every non-1 element

For each `-1` in the vector:
- **Index 0** → resources (CPU/memory/disk)
- **Index 1** → services (nginx, ollama, gbrain, etc.)
- **Index 2** → no_errored_crons — check `cronjob action='list'` for `last_status != "ok"`
- **Index 3** → no_stale_crons
- **Index 4** → nginx
- **Index 5** → ollama
- **Index 6** → gbrain
- **Index 7** → disk
- **Index 8** → gbrain_sources

### Step 4: Diagnose each issue

For errored crons (index 2 = -1): find the failing cron by checking the cron list for errors, then read that cron's output from `~/.hermes/cron/output/<job_id>/latest.md`.

### Step 5: Report honestly

State: "External URL: <url> → vector, [x] of [9] green, [n] issues: <list>". Never claim "healthy" or "green" unless the external URL returned all 1s.

> **Common failure:** You curl localhost (127.0.0.1:8905 or 127.0.0.1:13007), it returns all-1s, and you claim healthy. Meanwhile the external URL returns -1 at index 2 because a cron errored. Localhost bypasses nginx TLS and may serve cached/stale data. The external URL is the source of truth.

---

> **Principle: Verify before building.** When diagnosing fleet health issues, first verify the existing registry covers all known agents. The `agent-registry.json` + `agent-registry.local.json` should list every agent. Do not build speculative registration or discovery infrastructure when the registry is already populated. If an agent is unreachable, check whether it's a server (HTTP-polled) or client-only (inbox-pushed) agent before building new communication channels.

Monitor agent servers via a **binary status vector** — a compact JSON payload
with deliberately **no authentication** because the data is minimal
(just `1`=up, `-1`=down, `0`=n/a per service). The vector contains no secrets,
no PII, no version info — just eight bytes of binary flags.

> **Key design decision:** Health endpoints run on plain HTTP with no auth.
> Putting a binary status vector behind Basic Auth adds latency and token overhead
> for zero security value. The agent inbox (which carries actual messages) still
> uses per-agent credentials. See PITFALLS below.

## ⚠️ Two Vector Formats in Play

There is **one** deployed health vector format in the ecosystem. Earlier
documentation described a FastAPI `health-server.py` variant — that file was
**removed from the repo** (July 2026, commit `42fb8374`, "remove redundant
FastAPI health-server") and `health-vector.py` running via `health-vector.service`
is the **only** deployed server. Do not look for `health-server.py` — it does
not exist in the repo and is not deployed anywhere in the fleet.

| Format | Source | Vector length | Indices mean | Used by |
|--------|--------|---------------|--------------|---------|
| **Compact health** | `health-vector.py` → `CHECK_FUNCTIONS` / `get_vector()` | **9 elements** | Aggregated check results (see below) | Every deployed health endpoint (`:13007/health`, `:12007/health`, `:14007/health` — nginx proxy to `:8905`) |

### Compact Health Format (DEPLOYED) — 9-element `v` array

This is the format returned by every deployed health endpoint
(`health-vector.py` via `health-vector.service` — see
`references/health-vector-schema-migration.md` for the 8→9 element migration).

```python
v = [
    1 if resources_ok else -1,         # [0] resources — CPU/memory/disk within limits
    1 if services_ok else -1,          # [1] services — all critical services are running
    1 if no_errored else -1,           # [2] no errored crons — all cron jobs ran without error
                                       #     ⚠️ See references/watchdog-vs-crash-semantics.md
                                       #     "errored" includes watchdog scripts that correctly
                                       #     exited non-zero on detection — not just crashes
    1 if no_stale else -1,             # [3] no stale crons — schedule-aware (2x expected interval, not hardcoded 24h)
    1 if nginx_ok else -1,             # [4] nginx — pgrep nginx
    1 if ollama_ok else -1,            # [5] ollama — pgrep ollama
    1 if gbrain_ok else -1,            # [6] gbrain — pgrep gbrain
    1 if disk_ok else -1,              # [7] disk — disk usage < 80%
    1 if gbrain_sources_ok else -1,    # [8] gbrain sources — all gbrain sources healthy
]
```

**Semantics:** `1` = healthy, `-1` = unhealthy/warning, `0` = not applicable / not installed on this system.

| Value | Meaning |
|-------|---------|
| `1` | Service is running or condition is satisfied |
| `0` | Service is **not installed** on this agent (nginx on a macOS dev box, gbrain on a minion, etc.) |
| `-1` | Service IS installed but **not running**, or condition is violated |

The `0` value is supported by `health-vector.py`'s check functions. Each
per-service check now uses `shutil.which()` to detect if the binary exists
before probing for the running process — returns `0` if not found.

`health-server.py` (FastAPI variant, **removed in commit `42fb8374`**) still only
returned `1` or `-1` since it aggregated checks per-machine where all services
should be present. Only `health-vector.py` is deployed — see the retired-server
note in the diagnostics section below.

### Legacy Health Vector Format (NOT DEPLOYED) — 8-element `v` array

From the old `health-vector.py` template. Not actively deployed but may be
referenced in older documentation or templates.

| Index | Service | Code |
|-------|---------|------|
| 0 | nginx | 1=up, -1=down, 0=n/a |
| 1 | Ollama | same |
| 2 | gbrain | same |
| 3 | Cortex Dashboard | same |
| 4 | Langfuse web | same |
| 5 | Langfuse worker | same |
| 6 | Docker | same |
| 7 | Hermes Gateway | same |

### Critical: Never assume index meaning across formats

If you see vector index 3 = -1, it means:
- **In compact format (DEPLOYED):** Stale cron jobs (no_stale = False)
- **In legacy format:** Cortex Dashboard is down

**Always check which format the endpoint serves** before diagnosing.
See `references/compact-health-vector-format.md` for detailed source
code reference.

## Architecture

```
                        ┌──────────────────────┐
                        │  Agent Registry v3+   │
                        │  health_method per     │
                        │  agent in JSON         │
                        └───────┬──────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────┐
│  Moses (orchestrator)                                 │
│  orch-health-report.py (hourly) /                     │
│  orch-fleet-watchdog.py (5 min)                       │
│                                                       │
│  for each agent:                                      │
│    if health_method == "http":  ──→ HTTP GET :PORT    │
│    if health_method == "inbox": ──→ read inbox_       │
│                                     health-check      │
│                                     state file        │
│                                                       │
│  State tracked by fingerprint vector                  │
│  Alerts only on state transitions                     │
└─────────────────────────┬────────────────────────────┘
                          │
            ┌─────────────┼─────────────────┐
            ▼             ▼                   ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│  Gisu (server)   │ │  Joseph (server) │ │  Titus (macOS)   │
│  health-vector.py│ │  health-vector.py│ │  NO inbound      │
│  --serve :13007  │ │  --serve :12007  │ │                  │
│  HTTP-polled     │ │  HTTP-polled     │ │  health-vec-push │
│                  │ │                  │ │  → PGMQ bus      │
└──────────────────┘ └──────────────────┘ │  inbox_health_   │
                                          │  check queue     │
                                          │  every 10 min    │
                                          │  (launchd plist) │
                                          └──────────────────┘
```

- **Server agents** (health_method="http"): Moses polls their health vector server directly on the agent's assigned port. Each agent has its own port (see table below).
- **Client-only agents** (health_method="inbox"): Push their health vector to the PGMQ bus queue `inbox_health_check` (`health-vector-push.sh`, POST `/api/pgmq/send`). The `orch-clean-health-queue` cron (every 10 min) drains the queue and persists each agent's latest vector to `~/.hermes-cortex/state/inbox-health-state.json`; `orch-health-report.py` reads that file.

### ⚠️ Two Orthogonal Monitoring Systems

The fleet runs **two independent monitoring systems** that measure different things. They can disagree — bus-offline does not mean health-down, and health-green does not mean bus-active. Understanding the distinction prevents confusion:

| System | Script | What it measures | "Offline" means | Feed |
|--------|--------|-----------------|-----------------|------|
| **HTTP Health Vectors** | `orch-health-report.py`, `orch-fleet-watchdog.py` | Service-level health (resources, services, crons, nginx, ollama, gbrain, disk) | Service is down or degraded | `GET /health` endpoint per agent |
| **Bus Liveness** | `orch-fleet-watchdog.py` | Agent bus activity — last time the agent produced a PGMQ audit log event | Agent hasn't touched the bus recently (may be sleeping, idle, or disconnected) | `bus.audit_log` in Postgres |

**When they disagree:**
- **Bus shows 🌙 offline but health is 🟢**: The agent is running and serving but hasn't processed any bus messages recently. Common for agents that only do local cron work or whose bus-processing crons run on a sparse schedule.
- **Health shows 🔴 but bus shows ✅**: An agent has a service issue but can still post to the bus. The bus liveness check alone is insufficient for true health assessment.

**Diagnosis procedure when an agent appears offline:**
1. Check the bus audit log: `docker exec mycortex-postgres psql -U mycortex -d mycortex -t -c "SELECT created_at, action FROM bus.audit_log WHERE agent_name='<name>' ORDER BY created_at DESC LIMIT 5;"`
2. Check the HTTP health endpoint via external URL (see Verification Protocol above)
3. If bus shows offline but external URL shows healthy → agent is alive, just idle on the bus
4. If both show offline → real problem

❌ **Do this first:** Check the EXTERNAL HTTPS URL (Steps 1-2 of Verification Protocol), not the bus audit log. The bus is a secondary indicator — health is the primary one.

### Per-Agent Port Allocation

Each server agent gets a dedicated **external** port for nginx SSL termination.
The health-vector process binds to **127.0.0.1** (loopback) on the internal port
(typically 8905) — nginx proxies `<external-port>/health` → `127.0.0.1:<internal-port>`.
This prevents port conflicts and ensures TLS is handled at the proxy layer.

External port mapping (agents poll the nginx SSL port):

| Agent | External port (nginx SSL) | Internal port (health-vector) | Method |
|-------|--------------------------|-------------------------------|--------|
| Moses | 13007 | 8905 | HTTP poll via nginx proxy |
| Gisu | 13007 | 8905 | HTTP poll via nginx proxy |
| Kustos | 13007 | 8905 | HTTP poll via nginx proxy |
| Joseph | 12007 | 8905 | HTTP poll via nginx proxy |
| Esther | 14007 | 8905 | HTTP poll via nginx proxy |
| Titus | — | — | Inbox push |

> **PII note:** Actual domains are set via local override (`~/.hermes/agent-registry.local.json`),
> not committed to the public repo. See PITFALLS > Public repo PII.

### Agent Registry health_method

Each agent in `agent-registry.json` declares how Moses should poll it:

```json
"moses": {
  "health_method": "http",
  "health_url": "http://127.0.0.1:13007/health"
},
"gisu": {
  "health_method": "http",
  "health_url": "https://<gisu-domain>:13007/health"
},
"titus": {
  "health_method": "inbox"
}
```

**For PII safety**, the public repo stores port hints in description fields only.
Actual `health_url` values are configured via a local override file (see below).

## Components

### 1. `health-vector.py` — Agent-side health probe

Installed on every agent server. Two modes:

```bash
# Standalone (JSON to stdout)
python3 health-vector.py

# HTTP server (listens on <PORT>)
python3 health-vector.py --serve <PORT>

# Human-readable check
python3 health-vector.py --check
```

**Output format:**
```json
{"v": [1, 1, 1, 1, 1, 1, 1, 1], "h": "m", "t": 1700000000}
```

**Hostname convention:** The `h` field should be a **single character** per agent
for compact display in health reports:
| Agent | `h` value |
|-------|-----------|
| Moses | `"m"` |
| Gisu | `"g"` |
| Kustos | `"k"` |
| Joseph | `"j"` |
| Esther | `"e"` |
| Titus | `"t"` |

Set by `HEALTH_HOSTNAME` env var, falling back to the hostname's first character
(`moses` → `m`, `gisu` → `g`, `titus` → `t`). Override per-machine if the
hostname doesn't match the table:
```python
HOSTNAME = os.environ.get("HEALTH_HOSTNAME") or os.uname().nodename.split(".")[0][:1].lower() or "m"
```
Run the service with `Environment=HEALTH_HOSTNAME=m` in the unit if the hostname
ever diverges from the convention.

**Bind address:** The server binds to **127.0.0.1** (loopback) when behind an
nginx proxy to avoid port conflicts. nginx terminates TLS on `0.0.0.0`.
```python
server = HTTPServer(("127.0.0.1", port), HealthHandler)  # not "0.0.0.0"
```

Each check function probes for the service:
- **nginx**: `pgrep -x nginx`
- **Ollama**: systemd/launchd service, fallback to `pgrep ollama`
- **gbrain**: systemd/launchd service, fallback to `pgrep gbrain`
- **Cortex Dashboard**: `curl http://127.0.0.1:8901/api/health`
- **Langfuse web/worker**: Docker container check
- **Docker**: `dockerd` process or `/var/run/docker.sock`
- **Hermes Gateway**: `pgrep -f "gateway run"`

### `health-server.py` — RETIRED (removed commit `42fb8374`)

> ⚠️ **This server is retired.** The FastAPI `health-server.py` was removed from
> the repo in July 2026 (commit `42fb8374`); `health-vector.py` via
> `health-vector.service` is the **only** deployed health server. The log-format
> reference below is kept for reading HISTORICAL journal logs from before the
> removal — it does not describe the current `health-vector.py` (which logs
> minimally). Diagnostic procedure for the CURRENT server: check the
> `health-vector.service` unit and its journal instead
> (`systemctl --user status health-vector.service`,
> `journalctl --user -u health-vector.service`).

As of July 2026, the retired `health-server.py` had structured logging with per-request timing.
Every request writes a line to stdout (captured by systemd journal) showing each
check's duration:

```
2026-07-02T08:57:13.625 [INFO] COMPACT — m total=20.1s resources=0.0s services=0.1s crons=0.0s gbrain=20.0s
2026-07-02T08:57:13.625 [WARNING] SLOW COMPACT HEALTH — m took 20.1s
```

**Log line reference:**

| Prefix | Level | When | Example |
|--------|-------|------|---------|
| `STARTING` | INFO | Process starts | `server=moses agent=m port=8905 os=linux/6.14.0 python=3.11.15` |
| `CONFIG` | INFO | Startup | `_STARTUP_TS=1782950206 HOME=/home/moses` |
| `HEALTH` | INFO | `/api/v1/health` complete | `m total=0.3s resources=0.1s services=0.2s crons=0.0s gbrain=0.0s` |
| `COMPACT` | INFO | `/health` or `/` complete | `e total=20.1s resources=0.0s services=0.1s crons=0.0s gbrain=20.0s` |
| `SLOW CHECK` | INFO | Any single check > 2s | `gbrain_sources took 4.5s` |
| `SLOW COMPACT HEALTH` | WARN | Total > 5s | `m took 20.1s` |
| `DEADLINE EXCEEDED` | WARN | gbrain check hit 20s cap | `gbrain_sources did not finish in 20.0s (20.0s elapsed)` |
| `DEADLINE ERROR` | ERROR | gbrain check threw exception | `gbrain_sources failed after 3.2s: [Errno 12] Cannot allocate memory` |
| `CHECK FAILED` | ERROR | Any check threw exception | `services crashed after 0.1s\\nTraceback...` |
| `SHUTDOWN` | WARN | Process exiting (signal) | `received signal 15, exiting` |

**gbrain cache TTL:** The gbrain_sources check caches its result for **900 seconds**
(15 minutes) to avoid running the expensive `gbrain doctor --json` subprocess on
every request. The original 300s (5 min) TTL was bumped to reduce blocking
frequency. Baseline timing on a healthy system: `gbrain doctor --json` takes
**~31 seconds** (only ~1s CPU — the rest is I/O waiting on Ollama embeddings for
sync freshness checks). The cache is invalidated after TTL expires, but the 20s
deadline ensures the endpoint never blocks more than 20s even when the cache is cold.

**Process restart tracking:** The gbrain_sources check runs in a `ThreadPoolExecutor`
with a hard 20-second deadline. If exceeded, the endpoint returns a degraded response
(`gbrain_sources_ok = -1`) instead of blocking the entire health endpoint. Check
restart count with:

```bash
# Total restarts since service started
systemctl --user show com.hermes.health-server.service -p NRestarts

# Recent crashes with exit codes
journalctl --user -u com.hermes.health-server.service --since "1 hour ago" --no-pager | grep -E "STARTING|SHUTDOWN|CHECK FAILED|DEADLINE"
```

**Key diagnostic procedure (RETIRED server, historical):** when the retired
health endpoint timed out:

1. Check if process is running: `systemctl --user status com.hermes.health-server.service` (historical — the CURRENT unit is `health-vector.service`)
2. Read recent logs for DEADLINE EXCEEDED lines — they tell you which check is hanging
3. Look for CHECK FAILED lines with tracebacks — crash evidence
4. Check if OOM-killed: `dmesg | grep -i "health-server" | grep -i "killed"`
5. Check if other services are destabilizing the system (see Ollama GPU crash pitfall below)

See `references/health-server-logging-diagnostics.md` for full details.

### `health-vector.py` — Lightweight standalone probe

### 2. `orch-health-report.py` — Orchestrator poller (HTTP + inbox state)

Runs as a `no_agent` cron on Moses (`orch-health-report-weekday` hourly M-F 9-18,
`orch-health-report-saturday`). Reads `agent-registry.json` to find agents and
their `health_method`. (The former `orch-team-health.py` poller was **removed
from the repo** in commit `69e3cf8e` — superseded by `orch-fleet-watchdog.py`
for state-change alerting; the hourly report is `orch-health-report.py`.)

**Two fetch strategies:**

| health_method | Strategy | Description |
|---------------|----------|-------------|
| `"http"` | HTTP GET | Poll `health_url` endpoint (e.g. `http://agent:13007/`) |
| `"inbox"` | Bus state read | Read latest vector from `~/.hermes-cortex/state/inbox-health-state.json` (persisted by `orch-clean-health-queue` every 10 min), fallback to a live `bus_read("inbox_health_check")` |

```python
def _fetch_http(url: str, auth: str = "") -> dict | None:
    """HTTP GET to a health-vector endpoint. Supports Basic Auth."""
    headers = {"Accept": "application/json"}
    if auth:
        # Auth sent to inbox endpoint (not health endpoint — health has none)
        headers["Authorization"] = f"Basic {encoded}"
    with urlopen(url, timeout=5, headers=headers) as resp:
        return json.loads(resp.read().decode())
```

```python
def _fetch_inbox(agent_key: str) -> tuple[dict | None, str | None]:
    """Read the latest health ping for an inbox agent from persisted bus state.

    Returns (parsed_health_data, ts_iso) or (None, None).
    The ``orch-clean-health-queue`` cron drains ``inbox_health_check`` every
    10 min and persists each agent's latest vector to
    ``~/.hermes-cortex/state/inbox-health-state.json`` — this reads that file
    (with a live queue peek as fallback).
    """
    state_file = Path.home() / ".hermes-cortex" / "state" / "inbox-health-state.json"
    try:
        if state_file.exists():
            state = json.loads(state_file.read_text())
            entry = state.get(agent_key)
            if entry and isinstance(entry.get("vector"), list):
                return {"v": entry["vector"]}, entry.get("ts", "")
    except (json.JSONDecodeError, OSError):
        pass
    return None, None
```

**Timeout:** 5 seconds per agent (was 3s — increased to handle transient SSL handshake jitter on external endpoints). Short enough that 5 unreachable agents don't block the poller (~25s total). Remote endpoints behind SSL/nginx can have brief DNS/TCP jitter that exceeds 3s — 5s gives headroom for transient blips without hanging on real outages. If an agent doesn't respond in 5s, it's unreachable.

**Inbox flow (client-only agents, current):** The retired file-inbox anchor-keep
pattern (keep oldest ping, DELETE newer ones via `api/inbox`/`api/delete`) is
**gone** — the `api/inbox` endpoint no longer exists on the PGMQ bus server.
Today:

1. `health-vector-push.sh` POSTs the vector to the PGMQ queue `inbox_health_check` (`/api/pgmq/send`, subject `health`)
2. `orch-clean-health-queue` (every 10 min) drains the queue, archives each ping, and persists the latest vector per agent to `~/.hermes-cortex/state/inbox-health-state.json`
3. `orch-health-report.py` reads that state file (fallback: live `bus_read` peek)

No accumulation: the queue is drained every 10 min and the state file holds at
most one entry per agent (always the latest ping).

**Last-seen tracking:** The drain timestamp is recorded to
`~/.hermes-cortex/state/last-seen.json` on each successful drain. This is used to
suppress Telegram alerts during laptop sleep — if no new pings arrive within a
configurable window, the poller stays silent instead of alerting. Without this,
every lid-close would generate a 🔴 alert within 10 minutes.

**State tracking:** Compares fingerprints between runs. Only alerts on **state transitions**:
- Service was up (1) → now down (-1): alert with 🔴
- Service was down (-1) → now up (1): resolution with ✅
- Agent unreachable: alert with 🔴
- Agent back online: resolution with ✅

> **Watchdog pattern: silent = healthy.** When `orch-fleet-watchdog.py` produces empty stdout,
> it means no state changed since last poll — everything is stable. Empty output is NOT
> a sign of a broken cron. If you suspect the poller is broken, check
> `~/.hermes-cortex/state/agent-health-data.json` for the latest snapshot.
>
> Similarly, if a client-only agent (Titus, `health_method: inbox`) shows as "🔴 unreachable"
> in `orch-health-report.py`, check whether the agent has pushed health data recently
> (`~/.hermes-cortex/state/inbox-health-state.json` has an entry, and it's fresh).
> For laptop agents, "unreachable" during sleep hours is **expected** — the
> `last-seen.json` grace period suppresses alerts during sleep, but the health report will
> still show the current state. See the "Client-only agent unreachable (laptop sleep)" pitfall below.

The bus connection is read from `~/.hermes-cortex/cortex-bus.conf`
(`CORTEX_BUS_URL` + `CORTEX_BASIC_AUTH`, or Bearer `CORTEX_BUS_TOKEN`). Each
agent has their own credentials — never share the orchestrator's credentials
with peer agents. See `references/inbox-health-format.md` for the push format,
queue details, and the code-duplication warning between the health scripts.

**Health data** is written to `~/.hermes-cortex/state/agent-health-data.json`
for dashboard consumption.

### 3. `health-vector-push.sh` — Client-only push script

For agents with no inbound access (`health_method="inbox"`). Runs on a cron/launchd schedule:

```bash
# Determines hostname, runs health-vector.py --check,
# POSTs the JSON vector to the PGMQ bus queue inbox_health_check
# (reads CORTEX_BUS_URL + CORTEX_BASIC_AUTH from ~/.hermes-cortex/cortex-bus.conf)
bash ~/hermes-cortex/ops/scripts/health-vector-push.sh
```

**macOS launchd plist** at `docs/templates/com.hermes.health-push.plist`:
```xml
<dict>
    <key>Label</key>
    <string>com.hermes.health-push</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>-c</string>
        <string>exec "$HOME/hermes-cortex/ops/scripts/health-vector-push.sh"</string>
    </array>
    <key>EnvironmentVariables</key>
    <dict>
        <key>AGENT_NAME</key>
        <string>titus</string>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
    <key>StartInterval</key>
    <integer>600</integer>  <!-- 10 minutes -->
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/com.hermes.health-push.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/com.hermes.health-push.err</string>
</dict>
```

Requires `CORTEX_BUS_URL` + `CORTEX_BASIC_AUTH` (or Bearer `CORTEX_BUS_TOKEN`) in
`~/.hermes-cortex/cortex-bus.conf` (the push script reads them from there).
**Each client agent uses their OWN credentials** — never Moses' password.

### 4. `agent-registry.json` — Agent configuration (public)

Located at `ops/install/deploy/agent-registry.template.json` (deployed to
`~/.hermes-cortex/state/agent-registry.json`). The public repo version stores
port hints in the `description` field but does NOT contain actual domain names:

```json
{
  "version": 3,
  "agents": {
    "moses": {
      "name": "Moses",
      "health_method": "http",
      "health_url": "http://127.0.0.1:13007/health"
    },
    "gisu": {
      "name": "Gisu",
      "health_method": "http",
      "description": "set health_url locally, port 13007"
    },
    "titus": {
      "name": "Titus",
      "platform": "macOS",
      "health_method": "inbox"
    }
  }
}
```

### 5. `~/.hermes/agent-registry.local.json` — Local override (private)

Actual domain URLs are configured on the orchestrator via a local override file
in `~/.hermes/` (which is gitignored). The poller merges it on top of the public registry:

```json
{
  "version": 3,
  "agents": {
    "gisu": {
      "health_url": "https://<actual-gisu-domain>:13007/health",
      "accessible": true
    },
    "joseph": {
      "health_url": "https://<actual-joseph-domain>:12007/health",
      "accessible": true
    }
  }
}
```

The override file only needs to specify the fields that differ from the public registry.
`orch-fleet-watchdog.py` / `orch-health-report.py` merge them automatically — no config change needed.

### 6. `orch-health-report.py` — Health snapshot report (Telegram delivery)

Runs as a `no_agent` cron producing a compact emoji-bar snapshot of every agent's
health — designed for mobile Telegram display. Zero LLM tokens.

**Silent-when-clean (2026-08-11, Luke directive):** the snapshot is delivered
ONLY when the fleet health signature changes — new issue, recovery, or first
run after deploy. Persistent identical state → empty stdout → no delivery.
Signature is per-agent status + failing services, persisted to
`~/.hermes-cortex/state/health-report-sig.json`. The `orch-fleet-watchdog.py`
(5-min, transition-based) remains the primary alert channel; this hourly
report now mirrors it instead of pinging every hour.

**Two health methods — same display code:**
- `http` agents: `_fetch(url)` → parses `{"v": [...]}`
- `inbox` agents: `_fetch_inbox_vector(agent_key)` → reads latest vector from
  `~/.hermes-cortex/state/inbox-health-state.json` (persisted by
  `orch-clean-health-queue`) → parses `{"v": [...]}`

Both paths return the same vector format, so the emoji bar and failure listing code is shared.

**Schedule:**
| Cron | Schedule | Meaning |
|------|----------|---------|
| `orch-health-report-weekday` | `0 9-18 * * 1-5` | Every hour Mon-Fri 9AM–6PM KST |
| `orch-health-report-saturday` | `0 11,17 * * 6` | Sat 11AM + 5PM KST |

**Output format:**
```
━━━ Agent Health — Wed 10:12 UTC ━━━

Moses ✅
🟢🟢🟢🟢🟢🟢🟢🟢

Esther ⚠️ 1 down
🟢🟢🔴🟢🟢🟢🟢🟢
  gbrain 🔴
```

The script (`ops/scripts/agent/orch-health-report.py`) reads the same agent registry
with local overrides as `orch-fleet-watchdog.py`, polls every agent's health
endpoint (or reads the persisted inbox state for client-only agents), and outputs
compact markdown with emoji status bars.

**Deployment:** Create crons with `no_agent=True` and `script=orch-health-report.py`.
Copy the script to `~/.hermes/scripts/` first. See AGENTS.md for full setup.

## Deployment

### To install on a new server agent

1. **Open the firewall port:**
   ```bash
   sudo ufw allow <PORT>/tcp
   ```
   Replace `<PORT>` with the agent's assigned port from the table above.

2. **Install the health server as a systemd user service** (Linux) — the current
   server is `health-vector.py`; the unit template ships in the repo:
   ```bash
   cp ~/hermes-cortex/docs/templates/health-vector.service ~/.config/systemd/user/
   systemctl --user daemon-reload
   systemctl --user enable --now health-vector.service
   ```
   (The retired FastAPI `health-server.py` / `com.hermes.health-server.service`
   was removed in commit `42fb8374` — do not install it.)

   On macOS (launchd), run `health-vector.py --serve <port>` under a launchd
   agent (no bundled plist; write your own with `ExecStart` pointing at
   `~/hermes-cortex/ops/scripts/health/health-vector.py`).

   The systemd unit uses `%h` (systemd home specifier) so it works across
   different user accounts with zero hardcoded paths. It runs
   `health-vector.py` with:
   - `Restart=always`, `RestartSec=5`
   - Logging to the systemd journal (`journalctl --user -u health-vector.service`)
   - `Nice=10`, `IOSchedulingClass=idle` (never starves interactive work)

   ⚠️ **After installing any new service, add it to `agent-service-recovery.py`'s `SERVICES` list.**
   Otherwise a crash or SIGTERM leaves it dead until a human notices — the auto-recovery
   script only restarts services in its watchlist.
   See `references/service-recovery-blind-spot.md` for the checklist and example.

3. **Verify locally:**
   ```bash
   curl -s http://127.0.0.1:8905/health
   # → {"v":[...], "h":"moses", "t":...}
   ```

4. **Set up nginx proxy** to terminate TLS and proxy `/health` to the internal health server:
   ```nginx
   server {
       listen <PORT> ssl;
       location /health {
           proxy_pass http://127.0.0.1:8905;
       }
   }
   ```
   Then verify externally with TLS:
   ```bash
   curl -sfk https://<agent-domain>:<PORT>/health
   ```

5. **Set up bus config** for agent-to-agent messaging:
   ```bash
   # ~/.hermes-cortex/cortex-bus.conf
   # Each agent uses their OWN credentials — ask Moses to create a htpasswd entry
   CORTEX_BUS_URL="https://<moses-domain>:13004"
   CORTEX_BASIC_AUTH="your-agent-name:<your-password>"
   AGENT_NAME="your-agent-name"
   ```

### To install on a client-only agent (macOS)

1. **Set up bus config:**
   ```ini
   # ~/.hermes-cortex/cortex-bus.conf
   CORTEX_BUS_URL="https://<moses-domain>:13004"
   CORTEX_BASIC_AUTH="<your-agent-name>:<your-password>"
   AGENT_NAME="<your-agent-name>"
   ```
   `chmod 600 ~/.hermes-cortex/cortex-bus.conf`

2. **Install the launchd push agent:**
   ```bash
   cp ~/hermes-cortex/docs/templates/com.hermes.health-push.plist ~/Library/LaunchAgents/
   launchctl load ~/Library/LaunchAgents/com.hermes.health-push.plist
   ```

3. **Test:**
   ```bash
   AGENT_NAME=titus bash ~/hermes-cortex/ops/scripts/health-vector-push.sh
   ```
   Silent = success. Errors go to `/tmp/com.hermes.health-push.err`.

## Diagnostic Procedure: "Hourly report says 🔴 unreachable, manual run is green"

**Trigger:** The hourly `orch-health-report` (what lands in Telegram) marks an agent
— usually Moses itself — 🔴 unreachable, but a manual `python3
~/.hermes/scripts/orch-health-report.py` minutes later is green. Real outage vs
monitoring artifact? Run this sequence in order. (Discovered 2026-08-04: Moses
red at 13:00/14:00/15:00, green at 15:03.)

1. **Read the actual cron output** (not the chat paste):
   `~/.hermes/cron/output/<job_id>/latest.md` — keyed by job ID, never name
   (`cronjob action='list'` → `orch-health-report-weekday`). Check whether it
   fails every run or just some (sporadic = timing; constant = config/outage).
2. **Probe the external URL** — the ONLY health truth (localhost curls are not
   evidence):
   ```bash
   curl -skS -w "\nHTTP=%{http_code} %{time_total}s\n" --max-time 15 https://<domain>:<port>/health
   ```
3. **Measure latency repeatedly** — run 5+ probes. If responses are 2-10s, the
   endpoint itself is slow → find the slow check:
   ```bash
   cd ~/hermes-cortex/ops/scripts/health && python3 - <<'EOF'
   import time, importlib.util
   spec = importlib.util.spec_from_file_location("hv", "health-vector.py")
   hv = importlib.util.module_from_spec(spec); spec.loader.exec_module(hv)
   for fn in hv.CHECK_FUNCTIONS:
       t0=time.time(); r=fn(); print(f"{fn.__name__:<28}{time.time()-t0:>7.3f}s -> {r}")
   EOF
   ```
   Any check > 1s is the culprit. As of 2026-08-04: `check_mycortex` shelled out
   to `mycortex doctor --json` (~1.7s+) on EVERY request with no cache.
4. **Check the health server journal for BrokenPipeError** — clients timing out
   mid-write:
   `journalctl --user -u health-vector.service --since "1 hour ago" --no-pager | grep -A6 "line 448"`
   A traceback at `self.wfile.write(...)` = the poller gave up while the server
   was still computing. Not a server crash — a symptom.
5. **Check server concurrency**: `health-vector.py` uses `HTTPServer`
   (single-threaded) — pollers (hourly report, fleet watchdogs, dashboard)
   arriving within seconds at :00 serialize behind a slow request and queue
   past their client timeouts. Fix: `ThreadingHTTPServer`.
6. **Compare poller timeouts**: `grep -n TIMEOUT ops/scripts/agent/orch-health-report.py`
   vs `ops/scripts/agent/orch-team-health.py`. (The former
   `agent-health-monitor.py` was removed 2026-08-04 — deprecated,
   superseded by `orch-fleet-watchdog.py`.) A 3s timeout against a
   server that takes 2-9s under burst = guaranteed false red. Fleet guidance:
   5s minimum for external SSL-terminated endpoints.
7. **Fix pattern (all three layers, 2026-08-04 commit 03d95312):**
   - slow check → short-TTL cache (60s; same pattern as the retired
     health-server.py gbrain cache)
   - single-threaded server → `ThreadingHTTPServer`
   - short poller timeout → 3s → 5s
8. **Verify through the scheduler, not manually**: `bash cortex-update.sh`
   (deploy; purges gov locks — re-acquire), `systemctl --user restart
   health-vector.service` (unit runs the repo file; running process needs a
   restart to load new code), `cronjob action='run' job_id=<id>`, then confirm
   the cron output shows ✅. Manual `python3` runs do NOT update the scheduler's
   `last_status` or the doctor's run-evidence.

**Rule of thumb:** sporadic "unreachable" for the self-poll only (other agents
green) = timing/concurrency on the local health server, not an outage. Check
latency distribution and server threading BEFORE touching the registry, nginx,
or firewalls.

## Health-Report Pitfall: Stale SERVICE_MAP

The orchestrator poller (`orch-health-report.py`) has a hardcoded `SERVICE_MAP` that maps vector indices to service names. Over time, if the agent-side health endpoint changes format (e.g. from 8-element `health-vector.py` to 9-element `health-server.py`), the poller's map becomes stale and misreports every vector.

**Verification procedure when adding a new agent or after a health-endpoint update:**

1. Poll the new/updated endpoint directly: `curl -sS --max-time 5 https://<agent-url>/health`
2. Count the vector elements — is it 8 or 9?
3. Read the agent's `health-server.py`/`health-vector.py` `_build_compact_health()` function to confirm the exact index-to-service mapping
4. Update `SERVICE_MAP` in `orch-health-report.py` to match
5. **Also update** `health_vector_map` in `agent-registry.json` — it must match the same order
6. Run the poller once manually (`python3 ops/scripts/agent/orch-health-report.py`) and verify the output shows the correct service names

**Real example:** Remote agents run `health-server.py` which produces a 9-element vector `[resources, services, no_errored_crons, no_stale_crons, nginx, ollama, gbrain, disk_ok, gbrain_sources_ok]`. The poller had an 8-element map from the old `health-vector.py` template `[nginx, ollama, gbrain, cortex-dashboard, langfuse-web, langfuse-worker, docker, hermes-gateway]`, causing index 3 = -1 to report as "cortex-dashboard down" when it actually meant "stale cron jobs".

---

| Pitfall | Symptom | Fix |
|---------|---------|------|
| **Public repo PII** | Actual domain names committed to the public hermes-cortex repo | Use `~/.hermes/agent-registry.local.json` for real URLs. The public repo stores port hints only. |
| **Health URL uses internal address** | Poll passes locally but fails from orchestrator because the path bypasses nginx/TLS. See `references/agent-registry-structure.md` for rules on external vs internal URLs, hostname vs host conventions, and example-file sync. | Always use the externally-reachable nginx SSL URL as `health_url`. Poll `https://domain:PORT/health` not `http://127.0.0.1:8905/health`. |
| **Sharing orchestrator credentials** | Peer agents get Moses' htpasswd password. If one is compromised, all are. | Each agent gets their own htpasswd entry. `sudo htpasswd /etc/nginx/.hermes-htpasswd <agent-name>` on Moses' server. |
| **pgrep -x -f combined** | `_pgrep("gateway run", full=True)` with `exact=True` default produces `pgrep -x -f "gateway run"` which requires exact command-line match (full string), not substring | Use `_pgrep("gateway run", exact=False, full=True)` to produce `pgrep -f "gateway run"` for substring match |
| **Agent registry uses dict key, not name** | Duplicate agent entries in health data — one with key from registry, another from fallback | Registry entries use the dict key (e.g. "moses") as the agent key, not the `name` field (e.g. "Moses"). The fallback check must compare against the same namespace. |
| **Cortex Dashboard uses "overall" not "healthy"** | Legacy format handler reports healthy=False when services are actually up | Dashboard returns `{"overall": "healthy"}`, not `{"healthy": true}`. Check `data.get("overall") == "healthy"`. |
| **Compact format has different indices from legacy** | You see vector[3] = -1 and assume "Cortex Dashboard" is down. Actually it means "stale cron jobs" in the deployed compact format. | Always check the backend script serving the endpoint. `health-server.py` → compact 9-element format. `health-vector.py` → can serve either format; check CHECK_FUNCTIONS length. |
| **`-1` means "unhealthy/warning", not "down"** | The compact format has no `0` (n/a) — every index is always `1` or `-1`. A stale cron job (index 3) returns `-1` but the service is not "down" — it just hasn't run recently. See `references/schedule-aware-stale-detection.md` for how the stale threshold is computed from cron expressions (replaces hardcoded 24h). | Understand the semantics: `-1` may indicate a warning condition, not necessarily a service outage. |
| **`-1` for uninstalled services** | Agents without a given binary (e.g. nginx on a macOS dev box) report `-1` because the check function only looks for the running process. Titus' nginx = -1 is misleading — it's not "nginx is down", it's "nginx doesn't exist on this machine" | Per-service checks (`check_nginx()`, `check_ollama()`, `check_gbrain()`) now use `shutil.which()` to detect if the binary exists. Returns `0` (not applicable) if not found. `check_services()` also returns `0` if no services are installed on the system (macOS fallback). See `references/uninstalled-service-detection.md`. |
| **External endpoint timeout sensitivity** | Agents behind nginx SSL (Moses 13007, Joseph 12007, Esther 14007) occasionally get marked "unreachable" even though they respond in ~0.1s — DNS/TCP jitter on the HTTPS handshake spikes past the 3s timeout | Use 5s timeout for the orchestrator poller. 3s is fine for localhost (127.0.0.1) but external SSL-terminated endpoints need headroom. Polls every 10m — 5s per agent doesn't block the cycle. |
| **Orchestrator self-poll must use external HTTPS URL** | When the orchestrator polls itself (Moses polls Moses), the code fallback defaults to `http://127.0.0.1:13007/` — plain HTTP to a port nginx serves with `ssl` only. Nginx returns 400 "plain HTTP sent to HTTPS" → poll fails. | The self-poll URL MUST use the external HTTPS domain through nginx (e.g. `https://domain:13007/health`). Configure this via `agent-registry.local.json` — set Moses' `health_url` to the same external URL other agents use to reach Moses. The code fallback is a dev-only safety net that doesn't work when the nginx health block is SSL-only. Verify: `curl -sk https://$(hostname -f):13007/health` should succeed. If it doesn't, the registry URL is wrong or the nginx health block is misconfigured. |
| **Long timeout on unreachable agents** | Poller takes 60+ seconds when 4+ agents are down | Short timeout (5s). The poller runs every 10 minutes. If an agent doesn't respond in 5s, it's unreachable. |
| **Client-only agent unreachable (laptop sleep)** | Without the last-seen grace tracking, Moses alerts every 10 min when a laptop closes its lid. The `last-seen.json` grace period handles this naturally — pings stop during sleep, but alerts are suppressed within the window. See `docs/agent-onboarding.md` for the agent-side setup. |
| **Agent has nginx running but is NOT a server** | If a client-only agent (Titus) has nginx installed for local dev, you might assume it's now reachable as a server | nginx on a dev machine does NOT make it a server. Client agents ALWAYS use `health_method: inbox` — never add a `health_url` for them, even if nginx is running. The presence of a web server does not imply reachability. Check `is_server` in the agent registry before setting up polling. |
| **Agent has inbox on the same port as health** | Gisu had inbox on 13004, can't put health on the same port | Use a different port scheme. Moses/infra agents: 13007. Joseph: 12007. Esther: 14007. Avoid conflicts with existing inbox/dashboard ports. |
| **Triple-sync requirement: SERVICE_MAP, CHECK_FUNCTIONS, --check labels** | You update the SERVICE_MAP docstring to 9 elements but the actual CHECK_FUNCTIONS list still returns 8 → the endpoint returns wrong vector length and downstream pollers misdiagnose every index | Always update all three: (1) SERVICE_MAP doc comment, (2) CHECK_FUNCTIONS list, (3) --check labels. Verify with `curl -s http://127.0.0.1:<PORT>/` and count elements. Run `python3 health-vector.py --check` to validate labels match. Commit to repo after testing. |
| **Health queue backlog (drain stopped)** | Health pings accumulate in `inbox_health_check` (queue depth grows, `inbox_watch` returns MB-sized results). Means the `orch-clean-health-queue` cron stopped, or the push script targets the wrong queue. Check queue depth: `docker exec mycortex-postgres psql -U mycortex -d mycortex -t -c "SELECT state, COUNT(*) FROM bus.messages WHERE queue_name='inbox_health_check' GROUP BY state;"` and the cron's last run. |
| **Consumer-producer sync: update consumer after verifying producer format, not before** | | You update the orchestrator health report script (consumer) to handle a format you assume Titus sends, without first verifying what he actually pushes | Pull the latest data from the producer first — read their actual format, test the endpoint, THEN update the consumer. Never update a consumer based on assumptions about the producer's format. The workflow is: (1) check what the producer sends, (2) write consumer to match, (3) verify both directions. |
| **Dashboard `_find_pid()` does literal substring, not regex** | Service patterns like `gbrain.*autopilot`, `[o]llama serve` use `.*` regex syntax, but `_find_pid()` does `if pattern_lower in line.lower()` — a literal substring check. The dot-star is never matched as a wildcard. | Use actual substrings that appear in `ps aux` output: `"gbrain autopilot"` not `"gbrain.*autopilot"`, `"ollama"` not `"[o]llama serve"`. The patterns in `server.py`'s `_health()` dict must match the literal process command line. Verify by grepping `ps aux` for the exact substring before adding. |
| **Rich health-report format from inbox agents** | Titus pushes a JSON health report with services, issues, resources, uptime fields — not a compact `{"v": [...]}` vector. The `_parse_vector_body()` function in `orch-health-report.py` doesn't handle this format and returns `None`, marking the agent as unreachable. | `_parse_vector_body()` must detect `"type": "health-report"` in the JSON body and route to a rich-report parser (`_parse_rich_report()`) that converts the rich data to a vector while preserving metadata under a `_rich` key for `_build_structured_data()` to use. See `references/rich-health-report-format.md`. |
| **Health queue pings dropped before report reads them** | The hourly report finds no vector for an inbox agent because `orch-clean-health-queue` already drained and archived the pings (queue is transient). | The drain cron persists each agent's latest vector to `~/.hermes-cortex/state/inbox-health-state.json`; the report reads that file (live queue peek is only a fallback). If Titus shows 🔴, check that file exists and is fresh — if missing, the drain cron is not running. |
| **Inbox agents show 🔴 because report still calls retired `api/inbox`** | Report queries `GET /api/inbox?...` which returns 404 on the PGMQ bus (endpoint removed in the inbox→PGMQ migration, commit `0f01556d`). Every inbox agent shows 🔴 unreachable despite healthy pushes; last-seen stays stale. | `_fetch_inbox_vector()` must read `inbox-health-state.json` (or `bus_read("inbox_health_check")`), NOT `api/inbox`. Fixed 2026-08-04 — see the implementation in `orch-health-report.py` and `orch-clean-health-queue.py`. |
| **Endpoint path is `/health`, not bare `/`** | Poller gets 404 on the root endpoint | The health-vector server serves at `GET /health`, not `GET /`. `curl -s http://127.0.0.1:8905/health`, not `http://...:8905/`. |
| **Sharing untested URLs** | User calls you out for sending configs without verification | Test EVERY endpoint with `curl --max-time 5` from the external perspective before sharing with the user or peer agents. Do NOT only test from localhost — that only proves nginx is up locally. Check from the agent's perspective by reading the nginx access log for their IP or by using an external port checker. When an agent reports a connectivity issue, test ALL external endpoints (dashboard, langfuse, inbox, health) before diagnosing — a single endpoint being down vs all being down tells you whether it's a per-service or per-server/network problem. |
| **Old `com.hermes.health-server.service` vs current `health-vector.service`** | Docs mention a FastAPI `health-server.py` service on port 8905 — it was **removed from the repo** (July 2026). If `com.hermes.health-server.service` still exists on a machine it's an orphan from a pre-removal deploy. | The **current** canonical server is `health-vector.service` running `health-vector.py --serve 8905` (9-element compact vector, schedule-aware stale detection). If both units exist, disable the orphan: `systemctl --user disable --now com.hermes.health-server.service && systemctl --user enable --now health-vector.service`. Verify with `systemctl --user list-units | grep health`. |
| **`check_services()` returns -1 when none are installed** | On macOS or agents without nginx/ollama/gbrain, `check_services()` iterates all key services and returns -1 if any is missing — even if the service isn't supposed to be there. | Fix: detect whether any key service is **installed** before checking. On Linux, check systemd unit existence. If none are present, return `0` (not applicable). On macOS, if no relevant processes are found via pgrep, return `0` instead of `-1`. |
| **Ollama GPU crash cascade** | Health endpoint times out because Ollama crashes the GPU driver (Vulkan on old Intel HD 4000 iGPU, Ivy Bridge 2012). Ollama's vk::DeviceLostError destabilizes system resources, causing the health server to OOM-restart repeatedly (23+ restarts observed). The health vector looks broken but it's actually a cascading failure from Ollama. | Force Ollama to CPU-only on machines with old/incompatible GPUs: set OLLAMA_GPU_LAYER=false (or --cpu flag). On Ivy Bridge / HD 4000 era hardware, the iGPU does not support Vulkan fully. Check restart count: systemctl --user show com.hermes.health-server.service -p NRestarts. Check ollama journal: journalctl --user -u ollama.service --since 1 hour ago --no-pager. If you see vk::DeviceLostError in ollama logs, the GPU is the root cause. |
| **Orphan service: `Loaded: not-found` + `Active: active (running)`** | `systemctl --user status <service>` shows `Loaded: not-found` but the service is still running. The unit file was deleted/removed but the process from a previous load is alive. It will NOT auto-start on reboot. | Don't restart blindly — that fails because the unit file is missing. Find the source unit (check repo `ops/install/` or private repo) and re-install: `cp <source> ~/.config/systemd/user/ && systemctl --user daemon-reload && systemctl --user restart <service>`. If no source unit exists, the service was intentionally removed — stop the orphan cleanly. Cross-reference with `ss -tlnp | grep python3` to match ports to PIDs. |
| **Bus liveness vs health vector disagreement** | Agent shows offline (bus audit log) but green (HTTP health vector). You investigate a non-issue. | Check both signals before deciding. Bus-offline + health-green = alive but idle. Bus-offline + health-down = real problem. See the Two Orthogonal Monitoring Systems section above. |
| **Paused cron trips stale/errored checks (FIXED 2026-07-31)** | A paused job (`enabled: false`, e.g. `orch-bus-forwarder-sync` paused for maintenance) keeps its old `last_run_at`. The stale check computes elapsed vs its schedule (e.g. `*/2 * * * *`) and flags it permanently stale — health index 3 red forever. Same for a paused job with a frozen `last_status: error`. | `check_no_stale_crons()` and `check_no_errored_crons()` skip jobs with `enabled != true`. Paused jobs are intentionally not running — their frozen timestamps/statuses must not drive the health vector. If health index 2 or 3 is red, first check whether the offender is paused before blaming the cron. |
| **Bounded hour-range schedules flagged stale overnight (FIXED 2026-08-19, commit 90573ba9)** | Both orchestrators show index 3 = -1 (`no_stale_crons`) every night while a fresh local `python3 health-vector.py` run is all-green. Root cause: a cron with a bounded hour range (e.g. `0 8-22 * * *`, `orch-backlog-driver`) had its max legit silence computed as 1h (the `-` branch returned 3600), so after 2h of overnight silence it was flagged stale. The fix returns the overnight wrap gap `(24 - b + a) * 3600`. **Deploy lag:** the repo/deployed script were already fixed but the long-lived `health-vector.service` process (running since Aug 13) held the old code in memory — a process restart is required after ANY health-vector.py change (`systemctl --user restart health-vector.service`); the file copy alone never reloads it. Verify via the EXTERNAL URL, not localhost. | After any `health-vector.py` edit: restart `health-vector.service` on the host AND its peer orchestrator (moses↔esther both run it). Diagnosis signature: external endpoint `-1` at index 3 while a fresh local script run returns `1` = stale in-memory code, not a real stale cron. Check `systemctl --user status health-vector.service` uptime vs the repo commit date. |
| **Gateway restart interrupts in-flight LLM crons** | A gateway restart ("Stopping gateway for restart...", drain timeout at 180s) kills in-flight cron sessions. They are marked `interrupted` → `last_status: error` with NO output file written. Health index 2 goes red until each cron completes a new run. All affected crons share the exact same `last_run_at` timestamp (the interruption moment). | Not a cron bug — recovery is automatic on the next scheduled run. Verify: same-timestamp errors across several crons + gateway shutdown log lines at that moment. To confirm the crons re-ran, check `~/.hermes/logs/agent.log` for new `cron_<jobid>_<newer-timestamp>` sessions. If the red persists past the next run, then investigate the cron itself. |
| **Errored cron feeds health vector index 2** | Health shows -1 at index 2 (no_errored_crons). A watchdog exited non-zero legitimately detecting a real problem (e.g. ClickHouse merge failures from langfuse-health-watchdog). | Read the failing cron output from cron output dir. Fix the underlying problem, not the health check. The watchdog and health vector are working correctly. |
| **Persistent index-2 red on a REMOTE agent (2026-08-11)** | A remote agent's vector shows `no_errored_crons` red for hours with no transition — the fleet watchdog stays silent (transition-based) and, since 2026-08-11, the hourly report also stays silent on unchanged state. The red is invisible until it flips. | Diagnose proactively via fleet EXEC: `hc send <agent> EXEC '{"command":"cortex-doctor.py","params":["--quiet"],"timeout":240,"output_schema":"RAW"}' --self-tested`, then poll `bus.archives` for `EXEC_RESULT` (~5.5 min). The doctor output names the errored cron (`⚠️ Cron status (<name>) — last run: error`). Fix in the repo, then `UPDATE_REQUEST` the agent. Note: a remote agent N commits behind also fails updates until it pulls — check `git_sha_after` in the UPDATE_RESULT, not just `success` (see fleet-commands skill). |
| **Sporadic self-poll "unreachable" while manual run is green (FIXED 2026-08-04)** | Hourly report marks Moses 🔴 unreachable at :00 while a manual run minutes later is green. Root cause chain: `check_mycortex` runs `mycortex doctor --json` (~1.7s+) on every request with no cache → single-threaded `HTTPServer` serializes the :00 poller burst → 2-9.6s wall times → report's 3s timeout fires → BrokenPipeError in the server journal. Other agents stay green because their endpoints are on other hosts. | Three-layer fix (commit 03d95312): cache the slow check (60s TTL), `ThreadingHTTPServer`, poller `TIMEOUT` 3→5. Diagnostic steps in the "Diagnostic Procedure" section above. |
| **Laptop agent shows green forever after it stops pushing (FIXED 2026-08-04)** | Inbox-method agent (Titus) stops pushing health pings, but the hourly report keeps showing ✅ green indefinitely. `_fetch_inbox_vector` read the persisted vector from `inbox-health-state.json` unconditionally — no staleness check — so the 30-min grace / 🔴 unreachable logic never engaged. (Found 2026-08-04: Titus pushed until 18:48 KST then stopped; report still showed 9 greens at 19:20.) | Freshness gate in the state-file read (commit 16400583): if the persisted vector's `ts` is older than `LAPTOP_GRACE_MINUTES`, return None so the caller applies the offline/unreachable path. A laptop agent that is not pushing must show unavailable — never stale green. |