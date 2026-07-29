---
name: fleet-management
version: 1.0.0
category: devops
description: >-
  Fleet-level agent management for Hermes Cortex — agent registry, fleet
  ready score, fleet-audit CLI, adding/removing agents, and multi-slice
  fleet upgrades (S1-S4 pattern). Covers the 5 fleet concerns (identity,
  topology, choreography, economics, sovereign control) per PRD-005.
author: Hermes Cortex / Hermes Cortex
license: MIT
platforms: [linux, macos]
related_skills:
  - agent-bus
  - agent-fundamentals
  - agent-health-monitoring
  - fleet-commands
  - cortex-preflight
triggers:
  - "agent registry"
  - "fleet audit"
  - "fleet ready score"
  - "F1 validation"
  - "add agent"
  - "S1"
---

# Fleet Management — Agent Registry & Fleet Ready Score

## Overview

Fleet management covers the lifecycle of agents in a Hermes Cortex deployment:
registering agents with all 5 fleet concerns, validating readiness via the
Fleet Ready Score, and upgrading the fleet through levels F0 → F3.

## Agent Registry Schema (v4)

The registry lives at `~/.hermes-cortex/state/agent-registry.json`. Each agent
has three structural layers:

### Layer 1: Core Identity

Basic identity fields: `name`, `role`, `hostname`, `is_server`, `platform`,
`health_method`, `inbox_user`, etc.

### Layer 2: Capabilities

Tools and access the agent possesses: `has_git`, `has_sudo`, `has_cron_tool`,
`bus_access`, `maintenance_window`, `git` config, `deploy` config.

### Layer 3: Fleet Concerns (5)

Per PRD-005 REQ-001, every agent must define all 5:

| Concern | Field | What it tracks |
|---------|-------|----------------|
| **Identity & Trust** | `fleet_concerns.identity` | Principal type (claw/assistant), permissions, tool scope |
| **Topology** | `fleet_concerns.topology` | Hierarchical/P2P/blackboard, parent agent |
| **Choreography** | `fleet_concerns.choreography` | Bus access, inbox, handoff schemas |
| **Economics** | `fleet_concerns.economics` | Token budgets, concurrent runs, cost center |
| **Sovereign Control** | `fleet_concerns.sovereign_control` | Autonomy tier (F1-F3), kill switch, deny paths |

Plus `observability` and `service_layer` sections.

See `references/agent-registry-v4-schema.md` for the full field reference.

## Fleet Ready Score (F0-F3)

| Level | Name | Validation |
|-------|------|------------|
| **F0** | None | Agents exist in registry |
| **F1** | Registry + Permissions | `fleet-audit --level F1` — all agents registered, 5 concerns populated |
| **F2** | Shared Inbox + Budgets | `fleet-audit --level F2` — budgets, cost attribution, HITL inbox |
| **F3** | Unattended + Kill Switch | `fleet-audit --level F3` — autonomy, kill switch, audit trail |

## Fleet-Audit CLI

```bash
# Basic F1 validation
fleet-audit --level F1

# With suggested fixes for failing agents
fleet-audit --level F1 --suggest

# Point at a specific registry
fleet-audit --level F1 --registry ops/install/deploy/agent-registry.json.example
```

Exit code: 0 = all pass, 1 = issues found.

## Adding a New Agent

1. Add entry to the registry JSON with all 3 layers (core, capabilities, fleet_concerns)
2. Run `fleet-audit --level F1` to validate
3. Run `python3 ~/.hermes-cortex/scripts/generate-bus-wrappers.py --apply-crons`
4. Register any new scripts in `cortex-update.sh` via `register()`

## Multi-Slice Fleet Upgrades (S Pattern)

Fleet upgrades follow the S1 → S2 → S3 → S4 pattern from `docs/prd/`. Each
upgrade is structured as independent slices:

**Slice protocol:**
1. Present the full slice plan to the user first
2. Execute each slice in order
3. After each slice, deliver a one-line summary of what was done
4. **Continue to the next slice without asking for permission** — the approved
   plan IS the permission. Do not ask "shall I proceed?", "ready for next?",
   or any inter-slice permission check.
5. Only stop between slices if an error changes the approach, the user says
   "stop", or a destructive operation needs approval.

**Why:** Inter-slice permission checks waste turns. The user approved the plan;
execute it.

## References

- `references/agent-registry-v4-schema.md` — full field reference for v4 schema
- `docs/prd/PRD-005-enterprise-integration-v2.md` — PRD defining the 5 concerns
- `skills/devops/agent-bus/references/agent-registry.md` — bus-specific registry usage
