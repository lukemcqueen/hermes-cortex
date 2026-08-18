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
| `cortex-bus-evening` | M-F 19,20,22 | After-hours catch-up |
| `cortex-bus-overnight` | M-F 3am | Overnight sweep |

## Decision Framework

Each message is classified by:
- **Priority**: critical / urgent / normal / notification
- **Scope**: simple / moderate / complex / multi-agent
- **Action**: AUTO-ACT / delegate / escalate / acknowledge

## Bus Messages as Tasks (TL-v2 S4/S5 — ORCHESTRATORS)

Since TL-v2 S4, the fleet handler (`agent-message-handler.py`) creates a
`tasks.tasks` row (`source='inbox'`, linked by `correlation_id`) for every
tracked subject it receives: `EXEC`, `UPDATE_REQUEST`, `TASK_REQUEST`
(`Task:` prefix), `PROPOSAL`, `ISSUES`, `IMPROVEMENTS`.

**The orchestrator's inbox_read session OWNS the lifecycle transition for
report-type subjects** (ISSUES / PROPOSAL / IMPROVEMENTS / Task:) that were
left in the queue for human/LLM handling. The handler cannot complete them —
it is no_agent and only closes EXEC/UPDATE tasks at Result-receipt.

**When you (the orchestrator) process one of these from the inbox:**

1. `inbox_read` → message with `subject` = `ISSUES:` / `PROPOSAL:` /
   `IMPROVEMENTS:` / `Task:` and a `correlation_id`.
2. **Mark in_progress** the moment you start acting on it:
   ```bash
   python3 ~/.hermes-cortex/scripts/task-db.py update \
     --by-correlation <correlation_id> --status in_progress
   ```
3. **Complete it when handled** (fix applied, proposal filed, issue
   triaged — with evidence):
   ```bash
   python3 ~/.hermes-cortex/scripts/task-db.py update \
     --by-correlation <correlation_id> --status completed
   ```
4. If you defer it (needs Luke, blocked), leave it pending or pause it —
   **never silently drop**: a pending inbox task is the durable record.

**Why:** the task row IS the audit trail Luke sees in Telegram. A message
you handle but never transition leaves a false "pending" forever. The
`task_*` MCP tools (`task_update` with `by_correlation`) are the same path.

**Never** archive an ISSUES/PROPOSAL message without acting on its task
row. The stale sweep pauses stuck `in_progress` inbox tasks after 1h
(`TASKS_STALE_HOURS`), so a crash between pickup and handling degrades to
`paused` — visible, never lost.

## Key Files

- Bus backend: `core/cortex_bus/server.py`
- Queue module: `core/cortex_bus/queue.py`
- Bus config: `~/.hermes-cortex/cortex-bus.conf`
