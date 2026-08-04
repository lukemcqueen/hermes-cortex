---
name: cross-agent-design
description: >-
  Before designing any cross-agent feature, protocol, or workflow: trace the
  receiving agent's end-to-end connectivity, auth, consumption, and permission
  path. This skill prevents the most expensive mistake in multi-agent systems
  — assuming that because Message A reaches Queue B, Agent C sees it and
  processes it.
version: 1.0.0
category: devops
author: Hermes Cortex
created_from_session: agent-bus-architecture-survey
related_skills:
  - survey-before-action
  - cortex-preflight
  - agent-bus
  - agent-contract
  - session-start-discipline
---

# Cross-Agent Design — Fleet-Aware Protocol Design

## When to Load

Load this skill BEFORE:
- Proposing any feature that involves another agent
- Creating a new message type, topic, or protocol
- Designing a workflow that delegates to another agent
- Sending commands or requests to another agent's inbox
- Writing any code that assumes another agent will see the message

## The Core Principle

**Messages don't "arrive" — they wait.**

When you send a message to `inbox_esther`, it sits in a Postgres queue on your
machine. Whether Esther sees it depends on a chain of infrastructure that is
NOT under your control:

```
Your send → Bus auth → ACL check → Queue write
                                         │
              ┌──────────────────────────┘
              ▼
    Does Esther connect to this Postgres?
         │                    │
        YES                   NO
         │                    │
    Does she have a        Message is orphaned.
    consumer running?      Only the forwarder
         │                 would move it, and
        YES                it's paused.
         │
    Does the ACL allow
    her to read this
    queue?
```

## Pre-Flight Checklist

### 0. Prove it on your own system first

Before ANY cross-agent design, protocol, or command: prove the identical flow works on your own machine first. A test that skips the local step is not a test.

**The trap:** "I sent the EXEC to Esther, the message landed in her queue with msg_id returned, so it's working." This proves SQL works, not orchestration. You must verify the full send→process→respond→read cycle on yourself before involving another machine.

**Local proof checklist:**
1. Send the message to your own inbox (`inbox_moses`) with a unique `correlation_id`
2. Run the consumer manually to process it
3. Verify the response landed back in your inbox
4. Read the response — extract structured fields (exit_code, stdout, success)
5. Archive the test message
6. Only then send to a fleet agent

### 1. Trace the receiving agent's connectivity

```bash
# How does the remote agent connect?
#   - Same Postgres (orchestrators only)? → localhost:15432, Bearer token
#   - External URL (all workers)?         → CORTEX_BUS_URL, Basic Auth
#
# Check the receiving agent's cortex-bus.conf
#   CORTEX_BUS_URL=https://example.com:13004  (or :14004 for Esther)
#   CORTEX_BASIC_AUTH=agentname:password
#   AGENT_NAME=esther
```

**Never assume remote agents have localhost Postgres access.** Only Moses and
Esther (the orchestrators) do. Worker agents connect through nginx with
Basic Auth — a completely different auth path.

### 2. Trace the auth flow

Every agent has exactly ONE of these auth modes:

| Mode | Token type | When used | Who has it |
|------|-----------|-----------|------------|
| Basic Auth | `user:password` (htpasswd) | Through nginx | ALL agents |
| Bearer | `hbus_...` | Direct localhost | Orchestrators only |

**Before sending a command to another agent, verify their auth mode.**
A Bearer-token-based MCP tool won't work on an agent that only has Basic Auth
unless the MCP server is configured to fall back to Basic.

### 3. Verify the consumption pipeline

A message in an agent's inbox is only processed if the agent has a consumer:

| Consumer type | Reads every | Handles | Configured on |
|--------------|-------------|---------|---------------|
| LLM-driven cron | 10-60 min | All message types | Moses (agent-bus-workday/evening/overnight) |
| agent-worker service | ~30 sec | Only `workflow_step` type | Some agents (may cause competing consumer problem) |
| Manual MCP tools | On-demand | All message types | All agents (but only when they read their inbox) |

**If the target agent has no bus-processor cron, your message sits unprocessed
until it times out and goes to DLQ.** The `agent-bus-*` cron jobs are only
configured on Moses by default.

### 4. Verify the ACL allows it

From `bus.permissions` (Postgres table):

```sql
-- Only Moses can send to arbitrary queues.
-- All other agents can only READ their own inbox and SEND to inbox_moses.
SELECT agent_name, can_send, can_read FROM bus.permissions;
```

| Agent | Can send to |
|-------|-------------|
| **Moses** | **Every queue** — all inboxes, workflow queues, health |
| **Everyone else** | Only `inbox_moses`, own inbox, `workflow_step_result`, `inbox_health_check` |

**If you need an agent to reply**, they can only send to `inbox_moses`.
They cannot send to any other agent's inbox.

### 5. Trace the reply path

When the receiving agent replies, verify the path:

```bash
# The agent sends to inbox_moses
# What URL do they use?
#   - CORTEX_BUS_URL (through nginx, port 13004)?
#   - Direct localhost (port 8903)?
# What auth?
#   - Basic Auth for nginx?
#   - Bearer token for localhost?
```

### 6. Account for the bus forwarder (if applicable)

The forwarder (`orch-bus-forwarder.py`) syncs messages between Moses' and
Esther's Postgres instances. **It is currently PAUSED** (since 2026-07-20).

- Without the forwarder, all messages live only in Moses' Postgres
- Agents connecting to Esther's bus see only Esther-local messages
- Cross-server message sync does NOT happen currently

## Common Pitfalls

### ❌ "I sent a message to inbox_esther, why didn't she respond?"

Check, in order:
1. Does Esther connect to the same Postgres instance? (She uses `CORTEX_BUS_URL`)
2. Does she have a bus-processor cron? (`agent-bus-*` jobs in her cron list)
3. Does her ACL allow reading `inbox_esther`? (Yes — every agent reads their own)
4. Was the message consumed by `agent-worker` without being archived? (Competing consumer)

### ❌ "The message was consumed but no response came back — and the queue is empty"

This is the trickiest failure: no evidence left behind. The handler consumed the message, archived it, and exited cleanly — but `send_bus_result` never delivered the reply.

**Diagnostic chain:**

1. **Check `archived_by`** — `bus.archive(queue, msg_id, agent_name)` stores the archiver. Query recent archives to confirm the expected agent consumed it, not a forwarder or admin cleanup:
   ```bash
   sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -t" << 'EOF'
   SELECT queue_name, body->>'subject' as subject,
          archived_at::timestamptz(0), archived_by
   FROM bus.archives
   WHERE archived_at > now() - interval '30 minutes'
   ORDER BY archived_at DESC;
   EOF
   ```
   If `archived_by` matches the target agent → handler ran, reply path is broken.
   If `archived_by` is `moses` or `pre-cleanup` → something else ate it.

2. **Check handler state file** — The handler logs processed correlation_ids:
   ```bash
   cat ~/.hermes-cortex/state/agent-message-state.json
   ```
   If your correlation_id is in `processed_ids` → handler ran. The gap is in `send_bus_result`.

3. **Test `bus_send` independently** — If the handler ran but no reply came, test whether the agent's `bus_send` works:
   ```bash
   python3 -c "
   import sys; sys.path.insert(0, '$HOME/hermes-cortex/ops/scripts')
   from lib.cortex_bus import bus_send
   r = bus_send('inbox_moses', {'from':'test','subject':'TEST','body':{},
                                'correlation_id':'diag'})
   print(f'Send: {r}')
   "
   ```
   Returns `{'msg_id': '...'}` → send works interactively. The cron environment differs.
   Returns `None` → bus_send is broken. Check config, auth, and URL.

4. **AGENT_NAME misconfiguration** — The handler polls `inbox_{AGENT_NAME}`. If AGENT_NAME falls back to hostname (older code) instead of being set in `cortex-bus.conf`, the handler polled `inbox_cisnet03` while you sent to `inbox_gisu`. Check the agent's `cortex-bus.conf` has `AGENT_NAME=<name>`.

5. **Known silent-failure gap** — `send_bus_result()` catches all exceptions internally and returns `False` without propagating. The crash guard's except block is never triggered. The handler logs "Failed to send" to stdout (which the cron runner captures) but returns `True` (all done). The message is archived with no result sent. Being actively fixed.

### ❌ "The message vanished — consumed but I never asked for it"

### ❌ "The MCP tool works on my machine but not on the remote agent"

Your machine (Moses) has a Bearer token for direct localhost access. Remote
agents only have Basic Auth through nginx. The MCP tool resolves auth from
`cortex-bus.conf` — verify the remote agent's config matches their actual
auth mode.

### ❌ "I designed a protocol where Agent X sends to Agent Y directly"

Only Moses can send to arbitrary inboxes. All other agents can only send to
`inbox_moses`. If your protocol requires Esther → Gisu direct messaging,
it won't work at the ACL level. Route through Moses as an intermediary.

### ❌ "I created a new fleet-wide cron without checking what already runs"

Before creating any `agent-*` or `local-*` cron, run `cronjob(action='list')`
and `search_files()` with 3+ terms for the script purpose. The
`scoring-activity-watchdog` already existed when `local-cron-cost-report` and
`local-trace-quality-watchdog` were created — extending the watchdog was the
correct call. Creating new parallel crons fragments the system and creates
duplicate maintenance burden. See `session-start-discipline > references/survey-before-creating.md`.

### ❌ "bus_mode defines how agents communicate"

The field was renamed to `bus_access` (values `host`/`client`) because
`bus_mode` sounded like a configuration instruction to install a bus daemon.
`bus_access` describes capability: does this agent run the bus server (`host`)
or connect to a shared one (`client`)? All agents use `client` except
orchestrators (Moses, Esther) who use `host`.

## Reference

- `agent-bus` skill — bus operations, DLQ management, recovery
- `cortex-preflight` skill — general pre-flight checks (manually authored)
- `docs/reference/cortex-bus-config.md` — detailed config and auth resolution
- `docs/orch-bus-setup.md` — full setup guide with architecture overview
- `agent-message-handler.py` — fleet-wide no_agent consumer (every 5 min)

## Deployment Pattern: Fleet-Wide Features

When a new cross-agent feature needs every agent to support it:

1. **Add handler to `agent-message-handler.py`** — add a new `subject` case
   (e.g. `subject == "EXEC"`) to the existing dispatch chain. This is the
   only consumer that exists on every agent in the fleet.
2. **Register** new or updated files in `cortex-update.sh`
3. **Deploy** via `cortex-update.sh` on each agent
4. **~5 min response time** (handler polls every 5 min)
5. **No LLM cost** (no_agent script — subprocess only)

### Example: EXEC Command (added 2026-07-21)

```
Moses: hc exec esther cortex-doctor.py --json
  → sends EXEC to inbox_esther
  → handler picks up within 5 min
  → runs ~/.hermes-cortex/scripts/cortex-doctor.py --json
  → sends EXEC_RESULT back to inbox_moses
  → hc exec polls and displays result
```

Message schema:
- `subject: EXEC` — body: `{ command: str, params: list, timeout: int }`
- `reply: EXEC_RESULT` — body: `{ success: bool, stdout, stderr, exit_code }`

### Repo-Wide Search for Config/Variable Changes

When fixing a port number, URL, env var name, or file path — **do not fix
just the file you're editing**. Search the entire repo first:

```bash
grep -rn "<old-value>" ~/hermes-cortex \
  --include="*.py" --include="*.md" --include="*.sh" \
  --include="*.yaml" --include="*.conf" \
  2>/dev/null | grep -v ".git/" | grep -v "__pycache__"
```

**Why:** The 8905→8903 bus port fix found 4 stale files across 3 directories
(workflow YAML, server.py default, MCP docstring, architecture doc) that a
single-file fix would have missed. Workflow YAMLs, code docstrings, and
historical plan documents are the most common hiding places.

### Test Like an Agent Would

After making changes, verify through the correct path:

| Path | What it proves | When to use |
|------|---------------|-------------|
| `hc send` (docker exec SQL) | SQL function works | Local dev only — not representative |
| `curl 127.0.0.1:8903 + Bearer` | MCP tools path works | Testing Moses/Esther MCP |
| `curl domain:13004 + Basic` | **External agent path works** | Testing remote agent connectivity |
| `agent-message-handler.py --once` | Consumer picks it up | Testing handler dispatch |

The external path (nginx :13004 + Basic auth) is the only one that proves
a remote agent can send/receive. Always test through the path the
receiving agent would use.
