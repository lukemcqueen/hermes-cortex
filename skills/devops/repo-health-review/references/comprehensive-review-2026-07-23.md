# Comprehensive Review — 2026-07-23

## Scope
3-axis audit: 168 scripts, 93 docs, 7 PRDs, 7 SOUL.md profiles, install/update/doctor pipeline, Linux/macOS platform support, agent type coverage.

## Methodology
Used `delegate_task` with 3 parallel subagents:
1. Docs audit (stale paths, broken cross-refs)
2. Pipeline audit (install/update/doctor thoroughness)
3. Platform audit (Linux/macOS, agent types, SOUL.md profiles)

## Key Findings

### cortex-update.sh — 14 stale register() entries
Files registered for deployment that no longer exist on disk:
- `bus-sensor.py` (2x), `orch-install-bus.sh`, `change-readiness.sh`
- `inbox-sensor.py`, `inbox-depth-watchdog.sh`, `cortex-bus-monitor.sh`
- `inbox_watcher.py`, `mcp-inbox-proxy`
- `agent-inbox/server.py`, `agent-inbox/com.hermes.agent-inbox.plist`
- `offline_code_index_cron.sh` (old underscore name)
- `gbrain-autopilot.service` (wrong path — `docs/templates/` → `ops/install/deploy/`)

### Duplicate Scripts
- `inbox-flag.py`: 3 identical copies (MD5 match) at `agent/`, `bus/`, `inbox/`
- `remediation-sensor.py`: 2 different copies at `manage/` and `health/`

### Naming Issues
- `offline_code_index_cron.sh` — only script in `manage/` using underscore naming

### Docs Gaps
- `docs/cert-monitoring.md` (8KB) not linked from DOCS-INDEX
- `docs/model-tier-strategy.md` (5KB) unreferenced
- 6 zero-byte `docs/elicit/*.md` files — stale meeting notes

### Platform Gaps
- `check-system.sh` treats Linux as second-class ("optimized for macOS" warning)
- `install.sh` has no rollback for partial failures
- Moses/Gisu SOUL.md profiles missing `platforms:` frontmatter
- `AGENTS.md` doesn't mention orchestrator/server-agent/dev-agent roles

### Fixes Applied This Session
- 14 stale register entries removed from cortex-update.sh
- gbrain-autopilot.service path corrected
- Doctor --quick mode now includes crons + scripts (35 checks vs 31)
- 3 root-level test files moved to tests/
- Root __pycache__ and .pytest_cache deleted
- 4 stale copies pruned (inbox-flag.py ×3, remediation-sensor.py ×1)
- offline_code_index_cron.sh renamed to hyphen convention
- PRD-005 v1 archived (superseded by v2)
- runtime symlink removed
- cortex-doctor.py --quick mode added (with proper refactor, not wrapper)
- run-evals.py standalone auto-fallback added
- PRD-002 marked SUPERSEDED with absorbtion trail
