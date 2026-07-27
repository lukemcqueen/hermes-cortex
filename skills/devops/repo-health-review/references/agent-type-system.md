# AGENT_TYPE System — Reference

## Why

Before this system existed, agent roles were inferred from hostname
(Moses/Esther = orchestrator, everything else = server). This was brittle:
fresh installs, custom hostnames, and dev agents all got wrong role
assignment, causing false-positive doctor failures and unnecessary deploy
artifacts.

## Canonical Detection Chain

Every component (doctor, cortex-update.sh, os-config.sh, install-orch-crons.sh)
uses this same chain:

1. `AGENT_TYPE=orchestrator|server|dev` env var (primary — set in `.env`)
2. `IS_ORCHESTRATOR=true` (backward compat, pre-AGENT_TYPE installs)
3. Hostname `moses`/`esther` → orchestrator (legacy fallback)
4. Default: `server`

## Shared Helper: check_agent_type()

**File:** `ops/scripts/install/os-config.sh`

```bash
source ops/scripts/install/os-config.sh
check_agent_type "orchestrator" "${BASH_SOURCE[0]}" || exit 1
```

Behaviour when agent type doesn't match:
- Prints: `❌ <script> requires AGENT_TYPE=<required> (current: <actual>)`
- Prints uninstall advice: `AGENT_TYPE=<required> bash <script> --uninstall`
- Returns exit code 1

## What Uses It

| Component | File | Behaviour |
|-----------|------|-----------|
| os-config.sh | `ops/scripts/install/os-config.sh` | Defines `CORTEX_AGENT_TYPE` and `check_agent_type()` |
| cortex-update.sh | `ops/scripts/cortex-update.sh` | Installs orch-* crons only if AGENT_TYPE=orchestrator |
| cortex-doctor | `cortex_doctor/config.py` | `AGENT_ROLE` constant, skips Dashboard/Langfuse/Bus on non-orch |
| install-orch-crons.sh | `ops/scripts/install/install-orch-crons.sh` | Self-audits: refuses on non-orch, gives uninstall advice |

## Setting Up a New Agent

```bash
# In ~/hermes-cortex/.env:
AGENT_TYPE=orchestrator   # or server, dev
```

## Doctor Role Awareness

When `AGENT_TYPE=server` or `AGENT_TYPE=dev`:
- `check_services()` skips Dashboard HTTP, Langfuse HTTP, Agent Bus HTTP
- Bus direct health and gbrain checks still run (they're localhost)
- nginx checks still run (they check installed state)
- 38 checks in quick mode (vs 41 for orchestrator)

## What NOT to Do

- Don't use hostname for role detection in new code
- Don't hardcode `moses`/`esther` in role checks
- Don't create new orch-only scripts without a `check_agent_type()` guard
- Don't check `IS_ORCHESTRATOR` in new code — use `AGENT_TYPE` instead
