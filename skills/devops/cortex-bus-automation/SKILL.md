---
name: cortex-bus-automation
description: "Automated Agent Bus processing via MCP."
category: devops
version: 2.0.0
author: Hermes Cortex
metadata:
  hermes:
    tags: [bus, cron, automation, messaging]
    related_skills: [cortex-bus, cortex-bus-inbox, cortex-bus-polling]
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
| `cortex-bus-workday` | M-F 9-17 (hourly) | Full processing |
| `cortex-bus-evening` | M-F 18,20,22 | After-hours catch-up |
| `cortex-bus-overnight` | M-F 3am | Overnight sweep |

## Decision Framework

Each message is classified by:
- **Priority**: critical / urgent / normal / notification
- **Scope**: simple / moderate / complex / multi-agent
- **Action**: AUTO-ACT / delegate / escalate / acknowledge

## Key Files

- Bus backend: `core/cortex_bus/server.py`
- Queue module: `core/cortex_bus/queue.py`
- Bus config: `~/.hermes-cortex/cortex-bus.conf`
