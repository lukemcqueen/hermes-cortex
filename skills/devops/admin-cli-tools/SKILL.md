---
name: admin-cli-tools
category: development
tags: [cli, bus, postgres, admin, hermes-cortex]
trigger: building or maintaining CLI tools that interact with the agent bus, message queues, or Postgres backend
description: Patterns and architecture for admin-level CLI tools that use direct DB access, not agent-level API auth.
---

# Admin CLI Tools

Principles for building admin CLI tools (tools for the human operator, not for agents).

## Architecture

### Direct DB Access, Not API Auth
Admin tools run **directly against Postgres** via `docker exec psql` — no agent-level auth, no ACLs, no bus API dependency.

```
hc inbox joseph    ← works for ANY agent, no credentials needed
hc watch            ← reads ALL queues simultaneously
hc bus              ← full dashboard from Postgres
```

| Approach | When |
|----------|------|
| **`docker exec psql`** | Query operations (reads, depths, status) |
| **SQL `bus.send()` function** | Send operations |
| **HTTP to bus API** | Only for operations needing PGMQ semantics (rare for admin) |

### Non-Destructive Reads
Use **SQL SELECT** (not PGMQ `read`) to inspect messages without consuming them.

```sql
-- ✅ Non-destructive: messages stay in queue
SELECT * FROM bus.messages WHERE queue_name = 'inbox_X' AND state = 'pending' AND visible_after <= now();

-- ❌ Destructive: PGMQ read marks processing, timeout moves to DLQ
POST /api/pgmq/read  -- bad for admin inspection
```

### No Credential Config
Admin tools need no `HC_BUS_URL`, `HC_BUS_AUTH`, or any auth config. Just `HC_AGENT` (default agent name) for convenience.

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
        ["docker", "exec", "gbrain-postgres", "psql",
         "-U", "gbrain", "-d", "gbrain", "-t", "-c", query],
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
