# Fleet Bus Architecture Reference

> **Quick reference: topology, auth, ACL, ports, consumption patterns.**
> All values verified against live deployment.
> Complementary to: `docs/reference/cortex-bus-config.md`

---

## Port Map

| Port | Service | Who uses it |
|------|---------|-------------|
| `:8903` | Bus backend (FastAPI, PGMQ) | Localhost — systemd `cortex-bus.service` |
| `:8905` | Health server (Flask, vector ping) | Fleet health checks — **NOT the bus** |
| `:15432` | mycortex Postgres (`bus.*` schema) | Only Moses/Esther — contains ALL queues |
| `:13004` | nginx → Bus (Moses, primary) | All agents via `CORTEX_BUS_URL` |
| `:14004` | nginx → Bus (Esther, backup) | Fallback via `CORTEX_BUS_FALLBACK_URL` |

## Auth — Two Paths

### Path A: External (ALL worker agents)

```
Agent → nginx (:13004) → Bus (:8903)
         │                    │
    auth_basic            X-Forwarded-User
    (htpasswd)            (set by nginx)
```

**No Bearer token needed.** nginx validates Basic Auth, injects `X-Forwarded-User`.

### Path B: Direct (orchestrators only)

```
Agent → Bus (:8903) directly
         │
    Bearer token
    (CORTEX_BUS_TOKEN)
```

### Auth Resolution Chain (cortex_bus.py)

```
1. CORTEX_BUS_TOKEN set?   → Bearer    (direct localhost)
2. CORTEX_BASIC_AUTH set?  → Basic     (nginx proxy)
3. Neither?                → HTTP 401
```

no_agent crons use Path A — `_read_config()` reads `CORTEX_BASIC_AUTH` from `cortex-bus.conf`.

## ACL Model (`bus.permissions`)

| Agent | READ | SEND |
|-------|------|------|
| **Moses** | inbox_moses + dlq + health_check | **ALL** queues — every inbox, workflow, health |
| **Everyone else** | Own inbox only | inbox_moses + own inbox + workflow_step_result + health_check |

**Key rule:** Only Moses can initiate cross-agent sends. All others reply to Moses.

## How Agents Consume Messages

| Consumer | Freq | Handles | Where configured |
|----------|------|---------|-----------------|
| LLM cron (`cortex-bus-*`) | 10-60 min | **All** message types | Moses (3 crons: workday/evening/overnight) |
| agent-worker service | ~30s | Only `workflow_step` type | May be on any agent |
| MCP tools (`inbox_read`) | On-demand | Any | All agents, but requires a session |

## Bus Forwarder

**Status: PAUSED** (since 2026-07-20). Was paused after vt=0 peek bug fix.

Without the forwarder, all messages live ONLY in Moses' Postgres. Esther's bus is isolated.

## Queues

| Queue | Purpose |
|-------|---------|
| `inbox_{agent}` | Per-agent inbox |
| `inbox_{agent}_dlq` | Dead letter (3+ retries) |
| `workflow_dispatch` | YAML workflow submissions |
| `workflow_step_result` | Completed workflow steps |
| `workflow_timeout` | Stalled workflow detection |
| `inbox_health_check` | Health pings from all agents |
| `test-q` | Ad-hoc testing |
