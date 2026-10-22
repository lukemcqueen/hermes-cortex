# Bus API Addressing & Auth Patterns

## Endpoints

| Role | URL | Auth |
|------|-----|------|
| Local loop-governance | `http://127.0.0.1:8903` | Bearer token (`CORTEX_BUS_TOKEN`) |
| Remote bus (primary) | `https://realgospelmessage.com:13004` | Basic auth (`CORTEX_BASIC_AUTH` from cortex-bus.conf) |
| Remote fallback | `https://realgospelmessage.com:14004` | Basic auth (same credentials) |

## Auth Config

Stored in `~/.hermes-cortex/cortex-bus.conf`:

```
CORTEX_BUS_URL=https://realgospelmessage.com:13004
CORTEX_BUS_FALLBACK_URL=https://realgospelmessage.com:14004
CORTEX_BASIC_AUTH=<agentname>:<secret>
AGENT_NAME=<agentname>
```

## API Endpoints (PGMQ-backed)

All relative to the chosen `CORTEX_BUS_URL`:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Health check — returns `{"status":"ok","backend":"pgmq","queues":N}` |
| `/api/pgmq/queues` | GET | List all queues with depth, processing count, DLQ status |
| `/api/pgmq/send` | POST | Send a message to a queue |
| `/api/pgmq/read` | POST | Read (pop) one message from a queue with visibility timeout |
| `/api/pgmq/archive` | POST | Archive a processed message by msg_id |

## Auth Quick Reference

### Bearer (local, 127.0.0.1:8903)

The local server requires a Bearer token. Check `CORTEX_BUS_TOKEN` env var or `cortex-bus.conf`. When neither is set, the local endpoint returns 403 with `"Missing or invalid Authorization header. Use: Authorization: Bearer ***"`.

### Basic (remote, realgospelmessage.com)

```bash
AUTH=$(grep '^CORTEX_BASIC_AUTH=' ~/.hermes-cortex/cortex-bus.conf | cut -d= -f2-)

# List all queues
curl -s -H "Authorization: Basic $(echo -n "$AUTH" | base64)" \
  'https://realgospelmessage.com:13004/api/pgmq/queues'

# Read one message from your queue
curl -s -H "Authorization: Basic $(echo -n "$AUTH" | base64)" \
  -X POST -H 'Content-Type: application/json' \
  -d '{"queue":"inbox_<agentname>","vt":60}' \
  'https://realgospelmessage.com:13004/api/pgmq/read'
```

## Queue Permissions

Each agent can only read/archive from its own queue (`inbox_<agentname>`). DLQ queues follow the same scope (`inbox_<agentname>_dlq`). Attempting to read another agent's queue returns:

```json
{"detail": "Agent '<agentname>' does not have read access to queue 'inbox_other_agent'"}
```

Queue listing (`/api/pgmq/queues`) is unrestricted — any agent can list all queues with their depths.

## Queue State Interpretation

```json
{
  "name": "inbox_esther",
  "depth": 0,         // unread messages waiting
  "processing": 0,    // messages in-flight (visibility timeout, not yet archived)
  "dlq": false,
  "parent": null
}
```

- **depth=0, processing=0**: Queue is clean. No work.
- **depth>0**: Unread messages waiting to be processed.
- **depth=0, processing>0**: Messages are in-flight with a visibility timeout. They're either being actively handled or will return to depth if not archived in time.
- **dlq=true, depth>0**: Dead Letter Queue — messages that exhausted retries need manual inspection.

## Known Queue Inventory (as of 2026-07-20 11:10 KST)

| Queue | Depth | Processing | DLQ | Notes |
|-------|-------|-----------|-----|-------|
| `inbox_esther` | 0 | 0 | No | Clean |
| `inbox_esther_dlq` | 0 | 0 | Yes | Clean |
| `inbox_moses` | 0 | 0 | No | Clean |
| `inbox_moses_dlq` | 0 | 0 | Yes | Previous stale processing item self-resolved |
| `inbox_joseph` | 0 | 0 | No | Clean |
| `inbox_joseph_dlq` | 0 | 0 | Yes | Clean |
| `inbox_gisu` | 0 | 0 | No | Clean |
| `inbox_gisu_dlq` | 0 | 0 | Yes | Clean |
| `inbox_kustos` | 0 | 0 | No | Clean |
| `inbox_kustos_dlq` | 0 | 0 | Yes | Clean |
| `inbox_titus` | 0 | 0 | No | Clean |
| `inbox_titus_dlq` | 0 | 0 | Yes | Clean |
| `inbox_health_check` | **1** | 0 | No | **Persistent message** — depth=1 at 11:10; may be a stale item needing manual clearing; not Esther's queue so cannot read/archive directly |
| `test-q` | 1 | 0 | No | Test artifact — not inbox-related |
| `workflow_step_result` | 0 | 0 | No | Clean |
| `workflow_step_result_dlq` | 0 | 0 | Yes | Clean |

### Queue State Changes (tracked for drift detection)

| Date | Queue | Change | Source |
|------|-------|--------|--------|
| 2026-07-20 11:10 | `inbox_moses_dlq` | processing: 1→0 (self-resolved) | PGMQ list, agent-worker session |
| 2026-07-20 11:10 | `inbox_health_check` | depth: 0→1 (new persistent message) | PGMQ list, agent-worker session |
