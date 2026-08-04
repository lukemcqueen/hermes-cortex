---
name: bus-connectivity-diagnostics
description: >-
  Diagnostic procedures for Agent Bus connectivity, permissions, and
  message delivery. Covers the three bus paths (docker exec / direct
  backend / nginx), permission model verification, and the rule that
  all bus tests should use the agent-facing path, not admin shortcuts.
version: 1.0.0
category: devops
author: Hermes Cortex
platforms: [linux]
---

# Bus Connectivity & Diagnostics

## Purpose

Diagnose why a bus message isn't arriving at its target. This covers
the three access paths, the permission model, and the critical rule
that admin shortcuts (`hc send`, `docker exec`) must never be used
to validate agent-facing behaviour.

## When to Use

- A message sent over the bus didn't reach the target agent
- An MCP bus tool returned 401 or 403
- You need to verify a remote agent can receive a command
- You need to verify cross-server bus delivery
- You're setting up bus connectivity for a new agent

## The Three Bus Paths

### Path 1: Admin Shortcut — `hc send` / `docker exec`

```bash
hc send esther "subject" "body"
# Internally: docker exec → bus.send() SQL function
```

**Characteristics:**
- ⚠️ Bypasses ALL auth — no Bearer token, no nginx, no permission check
- ⚠️ Bypasses ALL permission checks — can write to any queue regardless of `bus.permissions`
- ⚠️ Only works on the machine with `gbrain-postgres` container
- PowerShell/fast for human admin operations

**Pitfall — NEVER use this to validate agent-facing behaviour.**
A message that works via `hc send` may fail when an agent sends it because `hc send` skips:
- Bearer token validation (`bus.tokens` table)
- Queue permission check (`bus.permissions` table)
- nginx Basic Auth (for external agents)
- `X-Forwarded-User` header parsing

### Path 2: Direct Backend — MCP Tool Path

```bash
TOKEN=$(grep CORTEX_BUS_TOKEN ~/hermes-cortex/.env | cut -d= -f2)
curl -s -X POST http://127.0.0.1:8903/api/pgmq/send \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"queue":"inbox_esther","message":{"from":"moses","to":"esther","topic":"test","subject":"test","body":"ok"},"priority":0}'
```

**Characteristics:**
- ✅ Full auth — Bearer token validated against `bus.tokens`
- ✅ Full permissions — `_check_permission()` validates queue access
- ✅ Same path MCP tools use (`mcp__agent_bus__send`)
- ❌ Only works on the bus server machine (direct access to port 8903)

**Use this for:** Testing from the bus server. Reproduces exactly what MCP tools do.

### Path 3: External nginx — Remote Agent Path

```bash
TOKEN=$(grep CORTEX_BUS_TOKEN ~/hermes-cortex/.env | cut -d= -f2)
curl -s -X POST https://<host>:13004/api/pgmq/send \
  -u "bus_user:password" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"queue":"inbox_orchestrator","message":...}' \
  -k
```

**Characteristics:**
- ✅ Two-layer auth: nginx Basic Auth → bus Bearer token
- ✅ Full permission checks
- ✅ Works from any machine that can reach the host
- ❌ Requires htpasswd credentials + SSL cert

**Use this for:** Testing from a remote machine. Same path a remote agent uses.

## Permission Model

The `bus.permissions` table controls which agents can read/write which queues.
The bus server checks permissions via `_check_permission()` on every send/read.

> ⚠️ **Two ACL schemas exist fleet-wide — match the SQL to the host.** The
> PRIMARY bus (Moses, `core/agent_bus`, :13004) uses per-queue **arrays**
> (`can_read`/`can_write` text[] + `is_admin`) — the queries below. The
> BACKUP bus (Esther, `ops/services/agent-bus`, :14004) uses coarse
> **booleans** (`can_send`/`can_read`/`can_archive`/`can_requeue`). Workers
> send through the primary, so a 403 on worker→orchestrator traffic means
> checking the PRIMARY's array ACL first. `UPDATE ... SET can_write = array(...)`
> only works on the primary; the backup takes `SET can_send = true`.
> See `docs/esther-bus-setup.md` Step 7 for both shapes and the worker
> `inbox_orchestrator` grant.

### Quick Reference

| Agent | Type | can_write (all queues) | can_read |
|-------|------|-----------------------|----------|
| **moses** | orchestrator | **Every** inbox + `workflow_dispatch` + `workflow_step_result` + health | Own inbox + DLQ + health |
| **esther** | server | `inbox_orchestrator`, `inbox_moses`, `inbox_esther`, `workflow_step_result`, health | Own inbox |
| **joseph** | server | `inbox_orchestrator`, `inbox_moses`, `inbox_joseph`, `workflow_step_result`, health | Own inbox |
| **gisu** | server | `inbox_orchestrator`, `inbox_moses`, `inbox_gisu`, `workflow_step_result`, health | Own inbox |
| **kustos** | server | `inbox_orchestrator`, `inbox_moses`, `inbox_kustos`, `workflow_step_result`, health | Own inbox |
| **titus** | dev | `inbox_orchestrator`, `inbox_moses`, `inbox_titus`, `workflow_step_result`, health | Own inbox |

### Key Permissions Facts

- **Only Moses (is_admin=t) can send to arbitrary inbox queues.** Other agents can only write to their own inbox + `inbox_moses` (reply channel) + `workflow_step_result` + `inbox_health_check`.
- **All agents can reply to Moses** — `inbox_moses` is in every agent's `can_write`.
- **Agents CANNOT message each other directly** — Esther cannot send to Joseph's inbox. All cross-agent communication must go through Moses (orchestrator).
- **`workflow_step_result` is universally writable** — any agent can submit step results from workflow execution.
- **`inbox_health_check` is universally accessible** — any agent can send/receive health pings.

### Verify Permissions

```bash
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -t -c \"
SELECT agent_name, can_read::text, can_write::text, is_admin
FROM bus.permissions ORDER BY agent_name;\\\"\" 2>&1
```

## Auth Flow

```
External client → nginx:13004
  ↓ Basic Auth (htpasswd — /etc/nginx/.hermes-htpasswd)
  ↓ X-Forwarded-User header set by nginx
  ↓ proxy_pass to agent_bus_backend (127.0.0.1:8903)
  ↓ Bearer token forwarded via proxy_set_header Authorization

Bus server _authenticate() has two modes:
  1. X-Forwarded-User present → use that (nginx-authenticated external conn)
  2. Bearer token → validate against bus.tokens table (direct internal conn)
```

## Diagnostics Checklist

When a bus send fails, check in order:

1. **Can the bus server authenticate the agent?**
   - `sg docker -c "docker exec ... SELECT agent_name, token_hash FROM bus.tokens;"`
   - `grep CORTEX_BUS_TOKEN ~/hermes-cortex/.env | cut -d= -f2 | head -c 20`

2. **Does the agent have write permission to the target queue?**
   - Query `bus.permissions` (see above)
   - Check the target queue is in the agent's `can_write` array

3. **Is the queue name correct?**
   - Queues follow pattern `inbox_{agent_name}` (e.g. `inbox_esther`)
   - DLQ queues: `inbox_esther_dlq`

4. **Is the bus reachable?**
   - `curl http://127.0.0.1:8903/health` (direct backend)
   - `curl -k https://127.0.0.1:13004/health` (via nginx)

5. **Is nginx Basic Auth configured correctly?**
   - Check htpasswd file exists: `ls -la /etc/nginx/.hermes-htpasswd`
   - Check nginx config: `grep -A 5 "listen 13004" /etc/nginx/sites-enabled/hermes-services.conf`

6. **Is the target agent's consumer actually running?**
   A message arriving in the queue is not proof the agent will process it. The handler must:
   - Have a cron installed (`cronjob action=list | grep agent-message-handler`)
   - Be polling the CORRECT inbox — see AGENT_NAME triage (step 7)
   - Not be crashed by an exception (check handler state file)

7. **AGENT_NAME Triage — "Wrong Inbox" Pattern**
   
   The handler polls `inbox_{AGENT_NAME}`. If AGENT_NAME resolves wrong, it polls the wrong queue and silently does nothing with messages intended for it.
   
   **Resolution chain:** `os.environ["AGENT_NAME"]` → `cortex-bus.conf` → `socket.gethostname()` (now errors out, older handler silently falls back).
   
   **Diagnostic:**
   ```bash
   cd ~/hermes-cortex && python3 -c "
   import os
   print(f'ENV AGENT_NAME={os.environ.get(\"AGENT_NAME\", \"not-set\")}')
   conf = os.path.expanduser('~/.hermes-cortex/cortex-bus.conf')
   if os.path.exists(conf):
       for line in open(conf):
           if line.startswith('AGENT_NAME='):
               print(f'CONFIG AGENT_NAME={line.split(\"=\",1)[1].strip()}')
   else:
       print('Config file not found')
   import socket
   print(f'HOSTNAME FALLBACK={socket.gethostname()}')
   "
   ```
   
   **Fix:** Add `AGENT_NAME=<name>` to `~/.hermes-cortex/cortex-bus.conf`. The handler now errors out if missing instead of silently polling the wrong queue.

8. **Simulate Cron Environment — Strip Env Vars**
   
   The handler runs via cron with NO environment variables. `cortex_bus.py` is designed to fall back to the config file, but the fallback chain can break if `Path.home()` differs in the cron context.
   
   **Test:**
   ```bash
   cd ~/hermes-cortex && python3 -c "
   import os, sys
   for k in ['CORTEX_BUS_URL','CORTEX_BASIC_AUTH','CORTEX_BUS_TOKEN',
             'AGENT_NAME','CORTEX_DEPLOY_HOME']:
       os.environ.pop(k, None)
   sys.path.insert(0, 'ops/scripts')
   from lib.cortex_bus import bus_send, CONFIG_FILE
   print(f'Config exists: {CONFIG_FILE.exists()}')
   r = bus_send('inbox_moses', {'from':'test','subject':'TEST',
                                 'body':{},'correlation_id':'cron-sim'})
   print(f'Send result: {r}')
   "
   ```
   
   If `None` with `Config exists: True` → `Path.home()` in cron resolves differently. If `Config exists: False` → the config file is missing from the cron user's home.

## Verification — Confirm Delivery

```bash
# Check the target queue for the message
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -t -c \"
SELECT msg_id::text, body->>'from' as sender, body->>'subject' as subject,
       body->>'topic' as topic, state, enqueued_at::timestamptz(0)
FROM bus.messages WHERE queue_name = 'inbox_esther' AND state = 'pending'
ORDER BY enqueued_at DESC LIMIT 5;\"\" 2>&1
```

## Formulating a Bus Test Plan

When asked "how do we test the bus?" or when setting up connectivity for a new agent, follow the **survey-first** protocol:

1. **Survey the fleet** — query agent registry for bus_access, role, health_method
2. **Check bus health** — verify the bus is running and authenticating
3. **Check permissions** — confirm can_write arrays match expectations
4. **Check queue state** — clear any backlog before sending test messages
5. **Trace consumption** — know which handler/poll interval applies per agent
6. **Build test scenarios** — start with self-test, then host agent, then client agents
7. **Verify delivery** — 6-checkpoint send -> consume -> process -> respond -> read -> inbox-verify
8. **Cleanup** — archive test messages to prevent DLQ cycling

See `references/bus-test-plan-framework.md` for the full protocol with exact commands for every step.

## Pitfalls

- ❌ **Using `hc send` for agent testing** — bypasses everything. Always use the direct backend API for same-machine tests.
- ❌ **Testing with `test-q`** — `test-q` exists but only Moses has write permission. Other agents get 403. Test against the actual target queue.
- ❌ **Assuming `hc inbox` works on remote machines** — `hc inbox` uses `docker exec` to the local Postgres. Only works on the bus server.
- ❌ **Bearer token without Basic Auth through nginx** — nginx returns 401 before the bus server is reached. Both layers are required for the external path.
