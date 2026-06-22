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
      "inbox_user": "htpasswd username for inbox",
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
2. Create htpasswd: `htpasswd /usr/local/etc/nginx/.htpasswd <user>`
3. Create config: `~/.hermes/agent-inbox-<agent>.conf` with URL, user, pass
4. Run: `python3 ~/.hermes/scripts/generate-inbox-wrappers.py --apply-crons`

The registry auto-generates:
- `~/.hermes/scripts/agent-inbox-<agent>.sh` wrapper
- A `inbox-<agent>` cron job with the right schedule
- Routing in `orch-check-agent-messages.sh` (reads dynamically each run)
