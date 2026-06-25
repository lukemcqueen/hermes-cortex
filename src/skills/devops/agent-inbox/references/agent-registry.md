# Agent Registry — Single Source of Truth for Agent Metadata

## Location

`~/.hermes/state/agent-registry.json`

## Purpose

Centralizes all agent metadata so scripts don't hardcode agent names.
`orch-check-agent-messages.sh` reads routing targets dynamically from here.
`generate-inbox-wrappers.py` generates per-agent watch scripts from here.

## Schema

```json
{
  "version": 1,
  "agents": {
    "<agent-key>": {
      "name": "Display Name",
      "description": "What this agent does",
      "inbox_user": "agent username for inbox (MCP auth)",
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
2. Create config: `~/.hermes/agent-inbox-<agent>.conf` with URL, user, pass
3. Run: `python3 ~/.hermes/scripts/generate-inbox-wrappers.py --apply-crons`

> **Note:** The inbox is now MCP-only. Agents use `inbox_send`, `inbox_read`, and `inbox_watch` MCP tools, not direct API calls.
