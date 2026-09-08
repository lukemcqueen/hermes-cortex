---
name: cortex-bus-polling
description: "Agent Bus polling setup — MCP tools, cron, verification."
category: devops
version: 2.1.0
author: Hermes Cortex
metadata:
  hermes:
    tags: [bus, polling, mcp, setup]
    related_skills: [cortex-bus, cortex-bus-inbox, cortex-bus-automation]
---

# Agent Bus Polling Setup

Set up an agent machine to poll the Agent Bus for inter-agent messages.

## Prerequisites (check ALL before starting)

1. **MCP tools registered.** The `agent-bus` MCP server must be registered. Verify:
   ```bash
   grep -A5 'agent-bus' ~/.hermes/config.yaml   # entry name is agent-bus (hyphen); script at ~/.hermes-cortex/scripts/cortex-bus-mcp.py
   ```
   If absent, ask the orchestrator (do not self-register — the server lives in the repo).
2. **Bus reachable.** From this machine, the bus health endpoint answers:
   ```bash
   curl -s http://localhost:8903/health
   # Expect: {"status":"ok","backend":"pgmq","queues":20,...}
   ```
   Non-local agents connect via nginx with Bearer auth (see `cortex-bus` skill).
3. **Queue exists for this agent.** The agent must be registered in the agent registry or have a queue. Check the queue list:
   ```bash
   curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8903/api/pgmq/queues
   ```
4. **Token set.** `CORTEX_BUS_TOKEN` in `~/hermes-cortex/.env` (see `bus-inbox-check` skill for extraction steps).

## Setup steps

### Step 1 — Verify MCP tools work

Call the MCP tools directly (available in an interactive session as `inbox_watch`, `inbox_read`, `inbox_send`):

```python
inbox_watch()      # → should return recent/new messages without error
inbox_read()       # → returns [] when inbox empty (normal, not a failure)
```

**If MCP tools are unavailable** (e.g. LLM-cron context), poll over HTTP instead — full procedure in the `bus-inbox-check` skill.

### Step 2 — Confirm a processor cron exists

Polling on this fleet is done by LLM-driven processor crons (`cortex-bus-workday`, `cortex-bus-evening`, `cortex-bus-overnight` — see `hermes cron list`). Non-orchestrator agents cannot create crons directly: request one via `inbox_send` to `inbox_orchestrator` if this machine has none.

### Step 3 — Test message flow (end-to-end)

```python
inbox_send(to="moses", subject="Test", body="Hello from agent")   # 1. send
inbox_watch()                                                      # 2. see it in watch
# then as the receiving side: inbox_read() shows the message
```

**Verify before declaring done:** the sent message appears in `inbox_watch()` output on the sender AND `inbox_read()` on the receiver. A send that returns without error but never appears is a routing failure — check the queue name spelling (queue names are case-sensitive, e.g. `inbox_moses`).

## Decision table: which poll mechanism

| Context | Use |
|---|---|
| Interactive session with MCP tools | `inbox_watch()` / `inbox_read()` directly |
| LLM cron / no MCP tools | HTTP API per `bus-inbox-check` skill (curl + Bearer token) |
| Bus daemon down on this host | Report to orchestrator; do NOT install a local bus daemon unless you are the orchestrator |

## Failure modes & recovery

| Symptom | Cause | Recovery |
|---|---|---|
| `curl :8903/health` returns empty / connection refused | Bus daemon not running on this host | Server agents connect REMOTELY — this is expected off-host. On the bus host: report to orchestrator, do not self-install |
| MCP tool returns empty `[]` | Inbox empty (normal) | No action — empty is success, not failure |
| `inbox_send` succeeds but message never arrives | Wrong recipient queue name | Verify queue list via `/api/pgmq/queues`; resend with exact name |
| 401/403 from HTTP API | Missing/stale token | Re-extract `CORTEX_BUS_TOKEN` from `~/hermes-cortex/.env` per `bus-inbox-check` |
| Messages reappear after read | Visibility timeout (vt) expired before processing | Process within the `vt` window or archive after processing |

## References

- `cortex-bus` skill — full bus operations guide
- `cortex-bus-inbox` skill — MCP tool reference
- `bus-inbox-check` skill — HTTP polling fallback (curl commands)
- `cortex-bus.conf` — connection settings
- Bus server source: `~/.hermes-cortex/bus/server.py` (deployed), `~/hermes-cortex/core/cortex_bus/server.py` (repo); MCP wrapper: `~/.hermes-cortex/scripts/cortex-bus-mcp.py`
