# Agent Registry — Single Source of Truth for Agent Metadata

## Location

`~/.hermes-cortex/state/agent-registry.json`

The repo ships two templates:
- `ops/install/deploy/agent-registry.json.example` — populated example with realistic data
- `ops/install/deploy/agent-registry.template.json` — `{{PLACEHOLDER}}` vars for setup scripts

## Purpose

Centralizes all agent metadata so scripts don't hardcode agent names, URLs,
or capabilities. Scripts read routing targets and agent capabilities dynamically
from the registry.

`generate-bus-wrappers.py` generates per-agent watch scripts from here.
`orch-fleet-watchdog.py` reads health URLs from here.
`fleet-audit.py` validates every agent against Fleet Ready Score levels.
Future fleet-update orchestration will read capability declarations from here.

## Schema (v4)

Every agent MUST have entries for **all 5 fleet concerns** as defined in PRD-005:

| Concern | Field | What it tracks |
|---------|-------|----------------|
| **Identity & Trust** | `fleet_concerns.identity` | Principal type (claw/assistant), permissions, tool scope |
| **Topology** | `fleet_concerns.topology` | Hierarchical/P2P/blackboard, parent agent |
| **Choreography** | `fleet_concerns.choreography` | Bus access mode, inbox, typed handoff schemas |
| **Economics** | `fleet_concerns.economics` | Token budgets, concurrent runs, cost center |
| **Sovereign Control** | `fleet_concerns.sovereign_control` | Autonomy tier (F1-F3), kill switch, deny paths |

Plus `observability` and `service_layer` (from `docs/agent-architecture.md`).

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
      "is_backup_orchestrator": false,
      "accessible": true,
      "platform": "linux | macOS",
      "health_method": "http | inbox",
      "health_url": "https://...",
      "description": "Free-text",
      "inbox_user": "cortex-bus-username",
      "inbox_watch_schedule": "every 10m",
      "inbox_deliver": "local",

      "capabilities": { ... },

      "fleet_concerns": {
        "identity": {
          "principal": {
            "type": "claw | assistant",
            "permissions": "clone | run | edit",
            "tool_scope": ["scope1", "scope2"],
            "version": "1.0.0"
          }
        },
        "topology": {
          "type": "hierarchical | p2p | blackboard | router | market-based",
          "parent": "orchestrator-name | null"
        },
        "choreography": {
          "bus_access": "host | client",
          "inbox": "inbox_<agent>",
          "handoff_schemas": [
            {
              "from": "sender-agent",
              "schema": "schema-v1",
              "validator": "validate-handoff.sh"
            }
          ]
        },
        "economics": {
          "budget": {
            "daily_token_cap": 50000,
            "concurrent_runs": 1,
            "cost_center": "team-a"
          }
        },
        "sovereign_control": {
          "autonomy_tier": "F1 | F2 | F3",
          "kill_switch": false,
          "allow_destructive_ops": false,
          "deny_paths": ["src/auth/**", ".env"]
        }
      },

      "observability": {
        "langfuse": true,
        "log_level": "info | debug",
        "tracing": "all | errors-only | off",
        "judge_scorer": true | false
      },

      "service_layer": {
        "type": "systemd | launchd | none",
        "health_endpoint": true | false,
        "auto_remediate": true | false
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
| `bus_access` | `host`, `client` | How agent accesses the bus |
| `maintenance_window` | `any`, `off-peak` | When updates can run |
| `git.remote` | string | Git remote name |
| `git.default_branch` | string | Branch to pull |
| `git.repo_path` | string | Path to repo clone |
| `deploy.update_method` | string | Script to run for updates |
| `deploy.doctor_path` | string | Path to doctor script |

### Fleet Concerns Field Reference

**Identity & Trust** — Who the agent is and what it can do:

| Field | Values | Meaning |
|-------|--------|---------|
| `principal.type` | `claw`, `assistant` | Service account (claw) vs end user (assistant) |
| `principal.permissions` | `clone`, `run`, `edit` | Maximum permission level |
| `principal.tool_scope` | `string[]` | Which MCP servers, APIs, repos the agent accesses |
| `principal.version` | `semver` | Agent or config hash version |

**Topology** — How the agent fits in the fleet structure:

| Field | Values | Meaning |
|-------|--------|---------|
| `type` | `hierarchical`, `p2p`, `blackboard`, `router`, `market-based` | Fleet topology pattern |
| `parent` | agent name or null | For hierarchical fleets: orchestrator this agent reports to |

**Choreography** — How the agent communicates:

| Field | Values | Meaning |
|-------|--------|---------|
| `bus_access` | `host`, `client` | Must match `capabilities.bus_access` |
| `inbox` | `inbox_<agent>` | PGMQ inbox queue name |
| `handoff_schemas` | `object[]` | Typed schemas for agent-to-agent handoffs |

**Economics** — Resource allocation:

| Field | Values | Meaning |
|-------|--------|---------|
| `budget.daily_token_cap` | int | Max tokens per day |
| `budget.concurrent_runs` | int | Max concurrent task runs |
| `budget.cost_center` | string | Billing/cost attribution label |

**Sovereign Control** — Autonomy and safety constraints:

| Field | Values | Meaning |
|-------|--------|---------|
| `autonomy_tier` | `F1`, `F2`, `F3` | Autonomy level per Fleet Ready Score |
| `kill_switch` | bool | Can the agent be remotely killed? |
| `allow_destructive_ops` | bool | Can the agent delete/overwrite resources? |
| `deny_paths` | `string[]` | Glob patterns for forbidden file paths |

### bus_access Semantics

| Mode | Meaning | Example Agents |
|------|---------|---------------|
| `host` | Agent runs or connects directly to the bus daemon; full read/write | Moses, Esther |
| `client` | Agent polls the shared bus for messages but does not host it | Gisu, Kustos, Joseph, Titus |

## Fleet Ready Score Levels

See `docs/prd/PRD-005-enterprise-integration-v2.md` for full definitions.

| Level | Name | Validation Command |
|-------|------|--------------------|
| **F0** | None | Agents exist in registry |
| **F1** | Registry + Permissions | `fleet-audit --level F1` |
| **F2** | Shared Inbox + Budgets | `fleet-audit --level F2` |
| **F3** | Unattended + Kill Switch | `fleet-audit --level F3` |

## Adding a New Agent

1. Add entry to the registry JSON with all fields including `capabilities`, `fleet_concerns`, `observability`, and `service_layer`
2. Run `fleet-audit --level F1` to validate the entry
3. Run: `python3 ~/.hermes-cortex/scripts/generate-bus-wrappers.py --apply-crons`

## Validating the Registry

```bash
# Basic F1 validation
fleet-audit --level F1

# F1 validation with suggested fixes
fleet-audit --level F1 --suggest

# Point at a specific registry file
fleet-audit --level F1 --registry ops/install/deploy/agent-registry.json.example
```

## Handoff Schema Validation (S2)

Every bus EXEC and UPDATE_REQUEST now carries **typed payloads** validated
against JSON Schema before sending and after receiving. See `ops/scripts/lib/handoff_schema.py`.

| Schema | Validates | Applied to |
|--------|-----------|------------|
| `EXEC` | Outbound EXEC payload | `hc exec` before send |
| `EXEC_RESULT` | Inbound EXEC result | `hc exec` after receive (default) |
| `WAVE_RESULT` | Aggregated wave output | `hc exec --output-schema WAVE_RESULT` |
| `UPDATE_REQUEST` | Update payload | `orch-bus-fleet-dispatch.py` before send |
| `UPDATE_RESULT` | Update response | `orch-bus-fleet-dispatch.py` after receive |

Usage:
```bash
# Default: validates result against EXEC_RESULT schema
hc exec esther cortex-doctor.py --json

# Custom schema validation on output
hc exec kustos cortex-doctor.py --json --output-schema WAVE_RESULT

# RAW mode: skip result validation
hc exec moses -- df -h / --output-schema RAW
```
