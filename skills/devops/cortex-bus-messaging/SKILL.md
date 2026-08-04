---
name: cortex-bus-messaging
version: 1.2.0
category: devops
description: "ORCHESTRATORS ONLY — message the orchestrator via the bus MCP client (inbox_send). Workers use contact-orchestrator.sh (HTTP)."
metadata:
  hermes:
    tags: [bus, messaging, mcp, agent-communication]
    related_skills: [cortex-bus-inbox, cron-request-protocol, fleet-commands]
---

# Agent Bus Messaging — How Orchestrators Talk to Each Other

> ## ⚠️ ORCHESTRATORS ONLY (Moses, Esther)
>
> The `inbox_send` MCP tool described in this skill is available **only on
> orchestrator hosts**. It is configured via the `cortex-bus` MCP server in
> `~/.hermes/config.yaml`, which the doctor enforces as orchestrator-only
> (`ORCH_ONLY_MCP_SERVERS` — it WARNS if present on a worker host).
>
> **Workers (Gisu, Joseph, Kustos, Titus): do NOT use this skill.** You do NOT
> have the MCP client and must not install it. Your bus access is the HTTP
> client only — send to the **shared orchestrator inbox** (default target):
> ```bash
> bash ~/.hermes-cortex/scripts/contact-orchestrator.sh "subject" "body" [priority]
> ```
> See the role matrix at the top of `docs/bus-architecture.md` — the canonical
> "who has what" reference.

## Overview

The Agent Bus (PGMQ) is the communication backbone for Hermes Cortex.
Every agent has an `inbox_{name}` queue. The `inbox_send` MCP tool posts
messages to any agent's queue that your permissions allow.

**ACL (from `bus-architecture.md`):**

| Agent | Can send to |
|-------|------------|
| Moses (orchestrator) | All inboxes + workflow queues |
| Esther (orchestrator) | `inbox_moses`, `inbox_orchestrator`, own inbox, `workflow_step_result`, `inbox_health_check` |
| Workers (Gisu/Joseph/Kustos/Titus) | Same queues as Esther, but via the **HTTP client** (`contact-orchestrator.sh`), not the MCP tool |

**Key rule: workers contact the orchestrator via `contact-orchestrator.sh` (HTTP), targeting the shared `inbox_orchestrator` queue by default.**
Orchestrators use the MCP tool below.

## The MCP Tool: `inbox_send` (orchestrators only)

```python
inbox_send(
    to="moses",          # Target agent name
    subject="...",       # Brief topic line
    priority="normal",   # critical | urgent | normal | notification
    body="..."           # Free-form message content
)
```

The tool is available in every **orchestrator** Hermes session via the
`agent-inbox` MCP server. No setup needed on Moses/Esther.

## Field Guide

| Field | Required | Values | Notes |
|-------|----------|--------|-------|
| `to` | ✅ Yes | `"moses"` | Case-sensitive, lowercase agent name |
| `subject` | ✅ Yes | Free text | Brief topic. `🔧 CRON:` prefix for cron requests |
| `priority` | ❌ No | `critical`, `urgent`, `normal`, `notification` | Defaults to `normal`. Determines Moses' response speed |
| `body` | ✅ Yes | Free text | What you need to say |

## Subject Prefixes

| Prefix | When to Use | Example |
|--------|------------|---------|
| `🔧 CRON:` | Cron job requests | `🔧 CRON: create` |
| *(none)* | General — status, questions, issues | `Disk space warning on /data` |

For cron requests, use the full format from `cron-request-protocol` skill.
For everything else, just write what you need.

## Examples

**Heads-up / issue discovered:**
```python
inbox_send(
    to="moses",
    subject="/data partition at 92%",
    priority="urgent",
    body="/data at 92% capacity (18GB free of 256GB). "
         "Docker logs are the main consumer. "
         "Consider log rotation."
)
```

**Status report:**
```python
inbox_send(
    to="moses",
    subject="Weekly health report",
    priority="normal",
    body="All services healthy. Doctor 42/42. "
         "Ollama uptime: 14d. No cron failures."
)
```

**Question:**
```python
inbox_send(
    to="moses",
    subject="Question about bus queue naming",
    priority="normal",
    body="Should health check messages go to inbox_health_check "
         "or inbox_orchestrator for manual review?"
)
```

**Notification:**
```python
inbox_send(
    to="moses",
    subject="Self-update completed",
    priority="notification",
    body="Version 2.1.0 now running. Update successful."
)
```

## Worker Alternative: contact-orchestrator.sh (HTTP)

Workers do not have `inbox_send`. Their equivalent is the HTTP client:

```bash
bash ~/.hermes-cortex/scripts/contact-orchestrator.sh "QUESTION: bus queue naming" \
  "Should health check messages go to inbox_health_check or inbox_orchestrator?" urgent
```

The script reads URL + auth from `~/.hermes-cortex/cortex-bus.conf`
(fallback) or env vars. Body should be a single line. **Default target is
`inbox_orchestrator`** (the shared orchestrator inbox — seen by whichever
orchestrator is available). See
`docs/contact-protocol-how-to-reach-orchestrator.md`.

## What Happens Next

The orchestrator processes the shared `inbox_orchestrator` in two modes:

| Mode | When | How |
|------|------|-----|
| **In-session** | Luke chatting with Moses | Reads during conversation |
| **Out-of-session** | Between sessions | LLM crons (`cortex-bus-*`) process `inbox_moses` + the shared `inbox_orchestrator` |

Moses classifies messages by a decision framework (see SOUL.md §2):
- **critical/urgent** → auto-acts immediately
- **normal** → auto-acts or escalates to Luke
- **notification** → acknowledges

Every action is verified and delivered with evidence.

## Related Protocols

| Protocol | Direction | Purpose |
|----------|-----------|---------|
| **This skill** | Orchestrator → Orchestrator | General messaging via `inbox_send` |
| **contact-orchestrator.sh** | Worker → Orchestrator | Worker messaging via HTTP client (default: `inbox_orchestrator`) |
| **cron-request-protocol** | Agent → Orchestrator | Structured CRON requests with `🔧 CRON:` prefix |
| **fleet-commands** | Moses → Agent | Operational EXEC/UPDATE commands |
| **fleet-update-protocol** | Moses ↔ Agent | Structured fleet update JSON schemas |

## Reminders

- **Messages land immediately** in the target's queue (state=`pending`)
- **Moses polls** via crons (workday/evening/overnight) + in-session
- **Include a correlation_id** in body if your message expects a response
- **Double-encoded JSON** — body is a JSON string inside a JSON message object. See `fleet-commands` skill for the double-parse pattern
