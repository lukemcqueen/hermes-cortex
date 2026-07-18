# Agent Registry — Single Source of Truth for Agent Metadata

## Location

`~/.hermes-cortex/state/agent-registry.json`

## Purpose

Centralizes all agent metadata so scripts don't hardcode agent names, URLs,
or capabilities. Scripts read routing targets and agent capabilities dynamically
from the registry.

`generate-bus-wrappers.py` generates per-agent watch scripts from here.
`orch-fleet-watchdog.py` reads health URLs from here.
Future fleet-update orchestration will read capability declarations from here.

## Schema (v4)

```json
{
  "version": 4,
  "health_vector_map": ["resources", "services", ...],
  "routing": {
    "broadcast_topics": ["luke", "all", "general"],
    "agent_prefix_topics": true
  },
  "agents": {
    "<agent-key>": {
      "name": "Display Name",
      "role": "orchestrator | server-agent | dev-agent",
      "hostname": "machine-hostname",
      "is_server": true,
      "is_orchestrator": false,
      "accessible": true,
      "platform": "linux | macOS",
      "health_method": "http | inbox",
      "health_url": "https://...",
      "description": "Free-text",
      "inbox_user": "agent-bus-username",
      "inbox_watch_schedule": "every 10m",
      "inbox_deliver": "local",
      "capabilities": {
        "has_git": true,
        "has_sudo": false,
        "has_cron_tool": false,
        "has_terminal": true,
        "bus_mode": "poll | push_only | both",
        "maintenance_window": "any | off-peak",
        "git": {
          "remote": "origin",
          "default_branch": "main",
          "repo_path": "~/hermes-cortex"
        },
        "deploy": {
          "update_method": "cortex-update",
          "doctor_path": "~/hermes-cortex/ops/scripts/manage/cortex-doctor.py"
        }
      }
    }
  }
}
```

### Capabilities Field Reference

| Field | Values | Meaning |
|-------|--------|---------|
| `has_git` | bool | Can run git commands (pull, status) |
| `has_sudo` | bool | Can sudo for nginx, systemctl, docker |
| `has_cron_tool` | bool | Has `cronjob` MCP tool (orchestrators only) |
| `has_terminal` | bool | Can execute shell commands |
| `bus_mode` | `poll`, `push_only`, `both` | How agent receives work items |
| `maintenance_window` | `any`, `off-peak` | When updates can run |
| `git.remote` | string | Git remote name |
| `git.default_branch` | string | Branch to pull |
| `git.repo_path` | string | Path to repo clone |
| `deploy.update_method` | string | Script to run for updates |
| `deploy.doctor_path` | string | Path to doctor script |

### bus_mode Semantics

| Mode | Meaning | Example Agents |
|------|---------|---------------|
| `poll` | Agent polls bus periodically via inbox_watch | Gisu, Kustos, Joseph |
| `push_only` | Agent only pushes health, cannot receive bus work | Titus |
| `both` | Agent can receive and send bus messages freely | Moses, Esther |

## Adding a New Agent

1. Add entry to the registry JSON with all fields including `capabilities`
2. Create config: `~/.hermes/agent-bus-<agent>.conf` with URL, user, pass
3. Run: `python3 ~/.hermes/scripts/generate-bus-wrappers.py --apply-crons`

> **Note:** The Agent Bus is now MCP-only. Agents use `inbox_send`, `inbox_read`, and `inbox_watch` MCP tools, not direct API calls.
