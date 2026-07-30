---
name: bus-inbox-check
version: 1.0.0
description: Check agent bus inbox depth and read messages via HTTP API — for use in LLM cron context where inbox_read MCP tool is unavailable.
---

# Bus Inbox Check

Check the PGMQ-based agent bus inbox for pending messages, used during auto-remediation and other cron-driven workflows where the `inbox_read` MCP tool may not be available.

## When to use

- During auto-remediation Phase 2 (checking agent inbox for help requests)
- When running as an LLM-driven cron and need to check for messages
- When the `inbox_read` or `inbox_mcp` MCP tools aren't available in your context

## Credential source

The bus token lives in `~/.hermes-cortex/.env`:

```
CORTEX_BUS_TOKEN=hbus_<hex>
CORTEX_BUS_PORT=8903
```

## Step-by-step

### 1. Check bus health (no auth required)

```bash
curl -s http://localhost:8903/health
```

Expected: `{"status":"ok","backend":"pgmq","queues":16,...}`

### 2. Extract the auth token

```bash
TOKEN=$(grep '^CORTEX_BUS_TOKEN=' ~/hermes-cortex/.env | cut -d= -f2)
AUTH="Authorization: Bearer $TOKEN"
BASE="http://localhost:8903"
```

### 3. Check your inbox depth

```bash
curl -s -H "$AUTH" "$BASE/api/pgmq/depth/inbox_moses"
```

Empty: `{"queue":"inbox_moses","depth":0}` — nothing to do.
Messages: `{"queue":"inbox_moses","depth":3}` — has 3 unread messages.

### 4. Read messages (when depth > 0)

```bash
curl -s -H "$AUTH" -X POST "$BASE/api/pgmq/read" \
  -H "Content-Type: application/json" \
  -d '{"queue":"inbox_moses","vt":30,"limit":5}'
```

The `vt` = visibility timeout in seconds (message becomes visible again after this if not archived). `limit` = max messages to read.

### 5. List all queues (optional — see which agents exist)

```bash
curl -s -H "$AUTH" "$BASE/api/pgmq/queues"
```

## References

- `auto-remediation` skill — full Phase 1-3 workflow that calls this check
- `cron-job-management` skill — context detection (MCP tool vs terminal vs cron)
- Agent bus server at `~/hermes-cortex/ops/services/agent-bus/server.py` — all API routes
- `references/cron-mode-analysis.md` — batch analysis patterns using `python3 -c` via terminal when `execute_code` is blocked in cron mode

## Pitfalls

- The health endpoint (`:8903/health`) does NOT require auth — always check it first before attempting authenticated calls.
- The inbox read endpoint uses **POST**, not GET. GET to `/api/pgmq/depth/{queue}` is fine for depth checks.
- Do NOT archive messages you haven't fully processed. Depth checks are read-only.
- If `curl -s` returns empty or `{"detail":"Not Found"}`, the bus port or path is wrong — verify CORTEX_BUS_PORT in `.env`.

## Port reference (discovery via `ss -tlnp | grep python3`)

| Port | Service | Endpoints | Auth |
|------|---------|-----------|------|
| 8901 | Hermes Cortex Dashboard | `GET /health` | None |
| 8903 | Agent Bus (PGMQ) | `GET /health`, `POST /api/pgmq/read`, `GET /api/pgmq/depth/{queue}`, `GET /api/pgmq/queues` | Bearer token for PGMQ endpoints; `/health` is unauthenticated |
| 8904 | Agent Inbox Web UI (legacy) | `GET /` → HTML page, `GET /api/inbox?topic=<t>&unread_only=true` → JSON inbox | None |
| 8905 | Hermes health vector service | `GET /health` → version/hash JSON | None |

**8904 clarification:** The legacy inbox on port 8904 is NOT fully deprecated for reads. Its `/api/inbox` endpoint returns proper JSON (e.g. `{"count":0,"unread":0,"messages":[]}`) with no auth required — useful as a fallback when the bus token isn't available. It does NOT support the PGMQ write/archive endpoints; use port 8903 for those.

## Diagnosis patterns

### Discover which service owns which port
```bash
ss -tlnp | grep python3
# Output example:
# python3  LISTEN 127.0.0.1:8903  —  Agent Bus (PGMQ)
# python3  LISTEN 127.0.0.1:8904  —  Agent Inbox Web UI
# python3  LISTEN 127.0.0.1:8901  —  Cortex Dashboard
```

### Detect orphaned/ghost systemd units
A service may show as `not-found loaded active running` — the unit file was removed/deleted but the old process keeps running:
```bash
systemctl --user status <service>.service
# Look for: Loaded: not-found (Reason: Unit ... not found.)
#          Active: active (running) since [date]
```
The process is functional but won't survive reboot. To clean up: stop and disable the orphaned unit.
