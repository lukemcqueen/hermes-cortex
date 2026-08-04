# Agent-Type Branching Audit — 2026-07-23

## Scope
Audited `install.sh`, `cortex-update.sh`, and `cortex_doctor/` for proper agent-type branching in deploy behavior.

## Files Examined
- `ops/install/install.sh` (2652 lines)
- `ops/scripts/cortex-update.sh` (1501 lines)
- `ops/scripts/manage/cortex_doctor/` (7 modules)
- `ops/scripts/install-crons.sh` (979 lines)
- `ops/scripts/install/install-orch-crons.sh` (482 lines)

## Key Findings

### 1. install.sh — Capability model, not role model
- Uses `CORTEX_PROFILE=core|laptop|server` (hardware capability), not `--agent-type orchestrator|server|dev` (role)
- No `--agent-type` flag exists
- `server` profile installs Langfuse, Dashboard, nginx but cannot distinguish orchestrator from server-agent
- `core` profile is minimal but deploys all scripts unconditionally

### 2. cortex-update.sh — Only cron install is guarded
- `IS_ORCHESTRATOR` guard only covers orch cron installation (lines 1412-1438)
- All `register()` entries for dashboard, cortex-bus server, nginx, orch-bus scripts deploy **unconditionally**
- `deploy_nginx_configs()` and `deploy_system_scripts()` run unconditionally from `main()`
- `verify_services()` always checks dashboard/gateway even on non-orch agents

### 3. cortex_doctor — Partial cron awareness, no systematic type differentiation
- `check_crons()` correctly uses hostname to detect orchestrators (moses/esther)
- `parse_expected_crons()` correctly filters out orch crons from universal list
- But: **`EXTERNAL_SERVICES` hardcodes Dashboard, Langfuse, Agent Bus** — always fails on non-orch
- **`check_nginx()` runs unconditionally** on every agent
- **No `IS_ORCHESTRATOR` env var check** — doctor uses hostname only
- **No `is_server` or `is_dev` concept** anywhere

### 4. Dev agents — No valid minimal path
- `local-*` cron prefix documented in install-crons.sh comment but no installer exists
- No `install-local-crons.sh` script
- No doctor awareness of dev agents

## Gaps Summary
| # | Gap | Severity |
|---|-----|----------|
| 1 | No `--agent-type` flag on install.sh | High |
| 2 | register() entries unconditional in cortex-update.sh | High |
| 3 | deploy_nginx_configs()/deploy_system_scripts() unconditional | Medium |
| 4 | EXTERNAL_SERVICES hardcoded with all services | High |
| 5 | check_nginx() unconditional | Medium |
| 6 | No is_server/is_dev detection in doctor | High |
| 7 | Doctor uses hostname instead of IS_ORCHESTRATOR env var | Low |
| 8 | No dev-agent installer or path | Medium |

## Hostname Detection Mismatch
- `cortex-update.sh`: `IS_ORCHESTRATOR` env var + hostname fallback (moses, esther)
- `install-orch-crons.sh`: `IS_ORCHESTRATOR` env var + hostname fallback (moses, esther)
- `cortex_doctor/checks.py`: hostname only (moses, esther) — no env var read
