---
name: agent-bus-messaging
version: 1.0.0
category: devops
description: "Message Moses via Agent Bus. inbox_send, fields, examples."
metadata:
  hermes:
    tags: [bus, messaging, mcp, agent-communication]
    related_skills: [agent-bus-inbox, cron-request-protocol, fleet-commands]
---

# Agent Bus Messaging — How Agents Talk to Each Other

> **Use this when you need to send a message to Moses (or another agent) via the**
> **Agent Bus for any reason — not just cron requests.**

## Overview

The Agent Bus (PGMQ) is the communication backbone for Hermes Cortex.
Every agent has an `inbox_{name}` queue. The `inbox_send` MCP tool posts
messages to any agent's queue that your permissions allow.

**ACL (from `bus-architecture.md`):**

| Agent | Can send to |
|-------|------------|
| Moses | All inboxes + workflow queues |
| Esther/workers | `inbox_moses`, own inbox, `workflow_step_result`, `inbox_health_check` |

**Key rule: Workers (Esther, Joseph, Gisu, Kustos, Titus) can send to
`inbox_moses`.** This is the primary way to talk to the orchestrator.

## The MCP Tool: `inbox_send`

```python
inbox_send(
    to="moses",          # Target agent name
    subject="...",       # Brief topic line
    priority="normal",   # critical | urgent | normal | notification
    body="..."           # Free-form message content
)
```

The tool is available in every Hermes session via the `agent-inbox` MCP
server. No setup needed.

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
         "or inbox_moses for manual review?"
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

## What Happens Next

Moses processes inbox in two modes:

| Mode | When | How |
|------|------|-----|
| **In-session** | Luke chatting with Moses | Reads during conversation |
| **Out-of-session** | Between sessions | LLM crons (`agent-bus-*`) process `inbox_moses` |

Moses classifies messages by a decision framework (see SOUL.md §2):
- **critical/urgent** → auto-acts immediately
- **normal** → auto-acts or escalates to Luke
- **notification** → acknowledges

Every action is verified and delivered with evidence.

## Related Protocols

| Protocol | Direction | Purpose |
|----------|-----------|---------|
| **This skill** | Agent → Moses | General messaging via `inbox_send` |
| **cron-request-protocol** | Agent → Moses | Structured CRON requests with `🔧 CRON:` prefix |
| **fleet-commands** | Moses → Agent | Operational EXEC/UPDATE commands |
| **fleet-update-protocol** | Moses ↔ Agent | Structured fleet update JSON schemas |

## Reminders

- **Messages land immediately** in the target's queue (state=`pending`)
- **Moses polls** via crons (workday/evening/overnight) + in-session
- **Include a correlation_id** in body if your message expects a response
- **Double-encoded JSON** — body is a JSON string inside a JSON message object. See `fleet-commands` skill for the double-parse pattern
