---
name: admin-cli-tools
version: 1.0.0
category: development
tags: [cli, bus, postgres, admin, hermes-cortex]
trigger: building or maintaining CLI tools that interact with the agent bus, message queues, or Postgres backend
description: Patterns and architecture for admin-level CLI tools that use direct DB access, not agent-level API auth.
---

# Admin CLI Tools

Principles for building admin CLI tools (tools for the human operator, not for agents).

## Architecture

### Host-Independent HTTP Client, Not Local docker exec (2026-08-06)

Admin tools talk to the Agent Bus over **HTTP** via the shared
`lib/cortex_bus.py` client (`ops/scripts/lib/cortex_bus.py`) — the SAME client
every fleet script uses. This is host-independent: `hc` works identically on
moses' and esther's hosts.

```
hc inbox joseph    ← reads the ACTIVE bus (CORTEX_BUS_URL) over HTTP (peek)
hc watch           ← peeks ALL queues over HTTP (non-destructive)
hc send esther     ← POSTs to the ACTIVE bus
hc exec gisu       ← sends EXEC + polls inbox_moses via peek
```

| Approach | When |
|----------|------|
| **HTTP via lib.cortex_bus** | Default — send (bus_send), peek (bus_peek), queues (bus_list_queues), health (bus_health) |
| **SQL `bus.send()`** | Only for local-Postgres tooling that runs on the bus host (diagnostics) |

**Why not docker exec?** The old `hc` ran `docker exec mycortex-postgres psql`
against the host-LOCAL bus. On Moses' host local == ACTIVE bus (13004), so it
worked. On Esther's host local == her own fallback bus (14004), which NOTHING
polls — every `hc send`/`hc exec` silently vanished into the void. The fix
(2026-08-06, hc-bus-aware) routes everything through the HTTP client with
`CORTEX_BUS_URL` (ACTIVE) + `CORTEX_BUS_FALLBACK_URL` (fallback) + Bearer→Basic
auth fallback. `hc bus` (the deep dashboard) still reads local Postgres — it's
labeled as such in its output.

### Non-Destructive Reads
Use **`bus_peek()`** (GET /api/pgmq/peek/{queue}, added 2026-08-06) to inspect
messages without consuming them. Unlike `bus_read()` (which marks messages
'processing' with a visibility timeout), peek returns pending messages with
their state unchanged — safe for inbox inspection and exec-result polling.

```python
from lib.cortex_bus import bus_peek, bus_send, bus_list_queues, bus_health

msgs = bus_peek("inbox_esther", limit=20)   # ✅ non-destructive list
bus_send("inbox_esther", {"from": "moses", "subject": "EXEC", ...})
depths = bus_list_queues()                   # name/depth/processing/dlq
health = bus_health()                        # active bus, fallback, auth
```

### Agent Identity
Admin tools resolve the operator's agent name from (in order): `HC_AGENT` env →
`hc.env` → `AGENT_NAME` in `cortex-bus.conf` → hostname-derived guess.
**Never default to a hardcoded other agent** — the old `DEFAULT_AGENT="moses"`
made esther's host silently impersonate moses.

## Command Structure

```bash
hc <command> [target] [args...]
```

Commands operate at queue level, one per agent:
- `hc inbox <agent>` — read pending messages
- `hc send <agent> <subject> [body]` — send a message
- `hc watch [agent]` — live-poll (default: all queues)
- `hc bus` — full dashboard (queues, processing, stuck, DLQ)
- `hc depth [agent]` — queue depth

### Watch Modes
- `hc watch` — watches ALL inbox queues (default)
- `hc watch moses` — watches only moses' inbox

## Common Pitfalls

- **Background consumers eat messages**: `agent-worker.py` (systemd service) polls `inbox_moses` via PGMQ `read` continuously. For live tests, send to a different agent's queue or use non-destructive SQL SELECT.
- **Stuck processing messages**: Messages read via PGMQ that aren't archived stay in `processing` state until `bus.recover_timeouts()` runs. Set up a cron for this.
- **Recover_timeouts cron**: Run every 5 min as a `no_agent` cron. Silent when nothing to recover.
- **Don't pipe through bus API for reads**: ACLs restrict per-queue access. Direct Postgres bypasses this for admin tools.

## Web Dashboard Equivalent (Flask)

Same direct-DB principle applies to web UIs:

```python
# Flask API endpoint querying Postgres
def _psql(query: str) -> str:
    r = subprocess.run(
        ["docker", "exec", "mycortex-postgres", "psql",
         "-U", "mycortex", "-d", "mycortex", "-t", "-c", query],
        capture_output=True, text=True, timeout=10,
    )
    return r.stdout.strip() if r.returncode == 0 else ""

@app.route("/api/bus")
@_cached("bus", ttl=5)
def api_bus():
    return jsonify(_bus_data())
```

Key patterns:
- **Dedicated pages > cards on main page**: Create `/bus`, `/langfuse` routes with their own HTML+JS for cleaner UX
- **Nav bar**: Shared across all pages with active tab highlight
- **Cache**: Use `@_cached` decorator with short TTL (5-15s for live data)
- **Render in JS**: `fetch('/api/VARIABLE')` every N seconds, render into `#id-content` div

### JS Scoping Pitfall
`const` and `let` in JS are **block-scoped**. Variables declared inside `if` blocks are not accessible outside them:
```javascript
// WRONG — ReferenceError
if (m.timeout_at) {
  const secs = ...;  // block-scoped
}
html += secs;         // ReferenceError: secs is not defined

// CORRECT — declare outside, assign inside
let secs = 0;
if (m.timeout_at) {
  secs = ...;
}
html += secs;
```

## Related
- `bus.recover_timeouts()` for stuck message cleanup
- `~/.hermes-cortex/dashboard/` — the Cortex Dashboard (Flask app)
