---
name: agent-inbox-automation
description: "Architecture for automated Agent Bus processing — crons (agent-bus-workday/evening/overnight) process messages via MCP tools using the Inbox Message Decision Framework."
category: devops
version: 2.0.0
author: Moses (Hermes Cortex)
metadata:
  hermes:
    tags: [bus, cron, automation, messaging]
    related_skills: [agent-bus, agent-inbox, agent-inbox-polling]
---

# Agent Bus Automation

Two-tier architecture for reading and acting on Agent Bus messages.

## Architecture

```
┌─────────────────────┐     detects (every 10m)     ┌──────────────┐
│  Bus Flag Sensor    │ ──────────────────────────► │   User/Tg    │
│ (no_agent=true)     │     output unread details    │   (notify)   │
└─────────┬───────────┘                              └──────────────┘
          │
          │  sensor output available for context_from
          ▼
┌─────────────────────┐     reads + acts (varies)   ┌──────────────┐
│  Bus Processor      │ ──────────────────────────► │   MCP Tools  │
│ (LLM-driven cron)   │     inbox_read, inbox_send   │   (execute)  │
└─────────────────────┘                              └──────────────┘
```

## Cron Schedule

| Cron | Schedule | Scope |
|------|----------|-------|
| `agent-bus-workday` | M-F 9-17 (hourly) | Full processing |
| `agent-bus-evening` | M-F 18,20,22 | After-hours catch-up |
| `agent-bus-overnight` | M-F 3am | Overnight sweep |

## Decision Framework

Each message is classified by:
- **Priority**: critical / urgent / normal / notification
- **Scope**: simple / moderate / complex / multi-agent
- **Action**: AUTO-ACT / delegate / escalate / acknowledge

Silent when healthy — no output when all messages are routine.

## Key Files

- Bus backend: `ops/services/agent-bus/server.py`
- Queue module: `core/agent_bus/queue.py`
- Bus config: `~/.hermes-cortex/cortex-bus.conf`
