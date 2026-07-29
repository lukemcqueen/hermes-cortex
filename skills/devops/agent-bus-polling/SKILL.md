---
name: agent-bus-polling
description: "Agent Bus polling setup — MCP tools, cron, verification."
category: devops
version: 2.0.0
author: Hermes Cortex (Hermes Cortex)
metadata:
  hermes:
    tags: [bus, polling, mcp, setup]
    related_skills: [agent-bus, agent-bus-inbox, agent-bus-automation]
---

# Agent Bus Polling Setup

Set up an agent machine to poll the Agent Bus for inter-agent messages.

## Overview

Each agent needs:

1. **MCP tools** — `inbox_watch`, `inbox_read`, `inbox_send` via the `agent-bus-inbox` MCP server
2. **Cron jobs** — LLM-driven processor crons that use the Inbox Message Decision Framework

## Setup

The bus is already configured in `cortex-bus.conf`. Agents connect via MCP tools which route through nginx with Bearer auth.

### Prerequisites

- Agent has bus connectivity (check with `inbox_watch()`)
- Agent is registered in `bus.agent_registry` or has a queue
- `CORTEX_BUS_TOKEN` is set in `.env`

### Testing

Test message flow:
```python
inbox_send(to="moses", subject="Test", body="Hello from agent")
inbox_watch()
inbox_read()
```

## References

- `agent-bus` skill — Full bus operations guide
- `agent-bus-inbox` skill — MCP tool reference
- `cortex-bus.conf` — Connection settings
