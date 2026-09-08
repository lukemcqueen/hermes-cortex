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
- `inbox_get_agent` — Get details for a specific agent by name
- `inbox_discover` — Fetch a remote agent's Agent Card (capabilities)
- `inbox_cancel_task` — Send a cancel request for a pending task
- `inbox_delete` — Delete/archive a message from the queue

## Envelope Contract (validated at ingestion — violations get 400 + reason)

Every `inbox_send` body must use ONLY these keys — anything else is rejected:

| Key | Rule | Example |
|-----|------|---------|
| `from` | MUST be your authenticated agent name; spoofed senders rejected | `"from": "worker-1"` |
| `to` | Target agent name (see `inbox_list_agents`) | `"to": "moses"` |
| `subject` | UPPER_CASE protocol name | `"subject": "DOCTOR_TEST"` |
| `body` | Message content | free text / JSON string |
| `correlation_id` | UUID linking related messages | keep on replies |
| `timestamp` | ISO 8601 | |
| `priority` | `critical` \| `urgent` \| `normal` \| `notification` | |
| `type` | Message type | |

Limits: **64 KiB max per message** · **600 sends/hour/agent** (429 over quota).

## Failure Modes

| Symptom | Cause | Fix |
|---------|-------|-----|
| `400` on send naming a key | Disallowed envelope key | Remove the key — allowlist is exact (table above) |
| `400: spoofed sender` | `from` ≠ authenticated agent | Use your real agent name from `inbox_list_agents` |
| `429` on send | Over 600 sends/hr | Wait for the quota window to reset |
| `inbox_read` empty but work pending | Routed to another queue | `inbox_list_agents()` to confirm target name |
| MCP tool not found | Bus MCP not registered | Non-orchestrators: use the HTTP client (`contact-orchestrator.sh`), NOT the MCP client — installing the bus server/MCP client fails the doctor |

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
