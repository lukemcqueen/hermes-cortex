---
name: cortex-bus-inbox
description: "MCP inbox tools for cortex-bus messaging."
category: devops
version: 2.0.0
author: Hermes Cortex
metadata:
  hermes:
    tags: [messaging, bus, mcp, inbox]
    related_skills: [cortex-bus, cortex-bus-automation]
---

# Agent Bus Inbox — MCP Tools

> **⚠️ This is the MCP tool interface for the Agent Bus.**
> The legacy file-based inbox has been replaced by the Agent Bus (PGMQ).
> All messaging flows through Postgres-backed queues. See the `cortex-bus`
> skill for queue operations, diagnostics, and maintenance.

## Overview

The agent bus inbox provides MCP tools for agent-to-agent messaging:

- `inbox_send` — Send a message to another agent's queue
- `inbox_read` — Read pending messages from your queue
- `inbox_watch` — Check for new messages
- `inbox_send_task` — Delegate a task to another agent
- `inbox_get_task` — Find a task by ID
- `inbox_list_agents` — List all known agents

## Usage Pattern

1. **Watch** — `inbox_watch()` to check for new messages
2. **Read** — `inbox_read()` to fetch pending messages
3. **Process** — Act on message content
4. **Archive** — Messages auto-archive on read; use `inbox_delete` for explicit cleanup

## Cron Jobs

Bus processing is handled by three crons:
- `cortex-bus-workday` — M-F 9-5 hourly
- `cortex-bus-evening` — M-F every 2h (19,20,22)
- `cortex-bus-overnight` — M-F 3am

## References

- `cortex-bus` skill — Queue operations, diagnostics, DLQ maintenance
- `cortex-bus-automation` — Cron-based processing architecture
- `cortex-bus.conf` — Bus configuration
