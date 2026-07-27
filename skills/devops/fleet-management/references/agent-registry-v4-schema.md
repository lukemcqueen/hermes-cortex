# Agent Registry v4 — Full Field Reference

## Core Identity Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Display name |
| `role` | string | yes | `orchestrator`, `server-agent`, `dev-agent` |
| `hostname` | string | yes | Machine hostname |
| `is_server` | bool | yes | Can be polled for health |
| `is_orchestrator` | bool | no | Has cronjob MCP tool + bus server |
| `is_backup_orchestrator` | bool | no | Hot standby orchestrator |
| `accessible` | bool | yes | Reachable from orchestrator |
| `platform` | string | yes | `linux` or `macOS` |
| `health_method` | string | yes | `http` (server) or `inbox` (client-only) |
| `health_url` | string | no | Full URL for HTTP health check |
| `description` | string | yes | Free-text role description |
| `inbox_user` | string | yes | PGMQ inbox queue name |
| `inbox_watch_schedule` | string | yes | e.g. `every 10m` |
| `inbox_deliver` | string | yes | `local` (default) |

## Capabilities Fields

| Field | Type | Values | Description |
|-------|------|--------|-------------|
| `has_git` | bool | true/false | Can run git commands |
| `has_sudo` | bool | true/false | Can sudo for system operations |
| `has_cron_tool` | bool | true/false | Has `cronjob` MCP tool (orchestrators) |
| `has_terminal` | bool | true/false | Can execute shell commands |
| `bus_access` | string | `host`, `client` | How agent accesses the bus |
| `maintenance_window` | string | `any`, `off-peak` | When updates can run |
| `git.remote` | string | e.g. `origin` | Git remote name |
| `git.default_branch` | string | e.g. `main` | Branch to pull |
| `git.repo_path` | string | e.g. `~/hermes-cortex` | Path to repo clone |
| `deploy.update_method` | string | e.g. `cortex-update` | Update script |
| `deploy.doctor_path` | string | e.g. `~/.../cortex-doctor.py` | Doctor script path |

## Fleet Concerns — Identity & Trust

| Field | Type | Values | Description |
|-------|------|--------|-------------|
| `principal.type` | string | `claw`, `assistant` | Service account vs end user |
| `principal.permissions` | string | `clone`, `run`, `edit` | Max permission level |
| `principal.tool_scope` | string[] | list of scopes | MCP servers, APIs, repos |
| `principal.version` | string | semver | Agent version or config hash |

## Fleet Concerns — Topology

| Field | Type | Values | Description |
|-------|------|--------|-------------|
| `type` | string | `hierarchical`, `p2p`, `blackboard`, `router`, `market-based` | Fleet topology pattern |
| `parent` | string/null | agent key or null | Parent orchestrator (null for root) |

## Fleet Concerns — Choreography

| Field | Type | Values | Description |
|-------|------|--------|-------------|
| `bus_access` | string | `host`, `client` | Must match capabilities.bus_access |
| `inbox` | string | `inbox_<agent>` | PGMQ inbox queue name |
| `handoff_schemas` | object[] | list | Typed schemas for agent-to-agent handoffs |

## Fleet Concerns — Economics

| Field | Type | Description |
|-------|------|-------------|
| `budget.daily_token_cap` | int | Max tokens per day |
| `budget.concurrent_runs` | int | Max concurrent task runs |
| `budget.cost_center` | string | Billing/cost attribution label |

## Fleet Concerns — Sovereign Control

| Field | Type | Values | Description |
|-------|------|--------|-------------|
| `autonomy_tier` | string | `F1`, `F2`, `F3` | Autonomy level |
| `kill_switch` | bool | true/false | Can be remotely killed? |
| `allow_destructive_ops` | bool | true/false | Can delete/overwrite? |
| `deny_paths` | string[] | glob patterns | Forbidden file paths |

## Observability

| Field | Type | Values | Description |
|-------|------|--------|-------------|
| `langfuse` | bool | true/false | Sends traces to Langfuse |
| `log_level` | string | `debug`, `info` | Agent log verbosity |
| `tracing` | string | `all`, `errors-only`, `off` | Trace capture mode |
| `judge_scorer` | bool | true/false | Has LLM judge scoring cron |

## Service Layer

| Field | Type | Values | Description |
|-------|------|--------|-------------|
| `type` | string | `systemd`, `launchd`, `none` | Service manager |
| `health_endpoint` | bool | true/false | Has /health endpoint |
| `auto_remediate` | bool | true/false | Auto-fixes issues |

## Fleet-Audit CLI Reference

```bash
# Basic F1 validation (all agents, all 5 concerns)
fleet-audit --level F1

# With suggested fixes for failing agents
fleet-audit --level F1 --suggest

# Specific registry file
fleet-audit --level F1 --registry path/to/agent-registry.json

# Future levels
fleet-audit --level F2   # Not yet implemented
fleet-audit --level F3   # Not yet implemented
```

**Exit codes:** 0 = all pass, 1 = one or more failures
