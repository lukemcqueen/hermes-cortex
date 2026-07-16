# Agent Registry — Single Source of Truth for Agent Metadata

## Location

`~/.hermes-cortex/state/agent-registry.json`

## Purpose

Centralizes all agent metadata so scripts don't hardcode agent names.
Scripts read routing targets dynamically from the registry.
`generate-bus-wrappers.py` generates per-agent watch scripts from here.

## Schema

```json
{
  "version": 1,
  "agents": {
    "<agent-key>": {
      "name": "Display Name",
      "description": "What this agent does",
      "inbox_user": "agent username for bus (MCP auth)",
      "inbox_watch_schedule": "every 10m",
      "inbox_deliver": "local"
    }
  },
  "routing": {
    "broadcast_topics": ["luke", "all", "general"],
    "agent_prefix_topics": true,
    "default_topic": "general"
  }
}
```

## Adding a New Agent

1. Add entry to the registry JSON
2. Create config: `~/.hermes/agent-bus-<agent>.conf` with URL, user, pass
3. Run: `python3 ~/.hermes/scripts/generate-bus-wrappers.py --apply-crons`

> **Note:** The Agent Bus is now MCP-only. Agents use `inbox_send`, `inbox_read`, and `inbox_watch` MCP tools, not direct API calls.
