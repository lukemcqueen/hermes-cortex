---
name: agent-inbox
description: "Bus-based agent messaging via MCP tools (inbox_send, inbox_read, inbox_watch) — replaces legacy file-based inbox. See also agent-bus skill for Postgres queue operations."
category: devops
version: 2.0.0
author: Moses (Hermes Cortex)
metadata:
  hermes:
    tags: [messaging, bus, mcp, inbox]
    related_skills: [agent-bus, agent-bus-automation]
---

# Agent Inbox — Bus MCP Tools

> **⚠️ This is the MCP tool interface for the Agent Bus.**
> The legacy file-based inbox has been replaced by the Agent Bus (PGMQ).
> All messaging flows through Postgres-backed queues. See the `agent-bus`
> skill for queue operations, diagnostics, and maintenance.

## Overview

The agent inbox provides MCP tools for agent-to-agent messaging through the bus:

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
- `agent-bus-workday` — M-F 9-5 hourly
- `agent-bus-evening` — M-F every 2h (18,20,22)
- `agent-bus-overnight` — M-F 3am

These process the bus using the Inbox Message Decision Framework.

## References

- `agent-bus` skill — Queue operations, diagnostics, DLQ maintenance
- `agent-bus-automation` — Cron-based processing architecture
- `cortex-bus.conf` — Bus configuration at `~/.hermes-cortex/cortex-bus.conf`
