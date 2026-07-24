---
name: change-checklist
version: 1.0.0
category: governance
description: "Mandatory verification checklist that every agent MUST load before closing a governance cycle (end_change). Referenced by AGENTS.md as a pre-close requirement."
author: Titus (Hermes Cortex)
license: MIT
metadata:
  hermes:
    tags: [governance, checklist, mandatory, verification, scoring]
---

# Change Checklist — Mandatory Pre-Close Verification

> **⚠️ HARD RULES:**
> 1. Load this skill (`skill_view(name="change-checklist")`) **before** calling `end_change()`. Not optional.
> 2. **Run Phase 5 (Final Verification) before Closing the Cycle.** Do not proceed to Closing until every Phase 5 item passes, including the adversarial scan.
> 3. **Adversarial scan is not optional for code changes.** `python3 ops/scripts/quality/adversarial-verify.py --dir . --level A2 --gate` must exit 0. If it found findings, fix them. Do not close with findings.

## Pre-Work (Before `begin_change`)

- [ ] `mcp_loop_governance_cache_search(query="<what you are about to do>")` — learn from past cycles
- [ ] Read this repo's `AGENTS.md` and `SOUL.md` for agent-specific rules
- [ ] Run `mcp_loop_governance_config_show()` to know current thresholds

## Phase 1 — Tests

- [ ] Run full test suite (`pytest tests/ -x --tb=short`)
- [ ] All tests pass (report exact count)
- [ ] If tests fail: fix before closing cycle. Never close with failing tests unless user explicitly waives.

## Phase 2 — Multi-OS Compatibility

- [ ] If paths changed: verify no Linux-only paths (`/home/`, `/etc/`) used on macOS, and no macOS-only paths used on Linux
- [ ] If service files changed: verify LaunchAgent plists for macOS AND systemd service units for Linux
- [ ] If scripts changed: verify shebangs point to python3.12 (macOS ships Python 3.9 which breaks PEP 604; all Hermes projects require 3.12+)
  - `~/.local/bin/python3.12` is the canonical macOS Hermes Python

## Phase 3 — Multi-Role Verification

- [ ] Agent perspective: does the change work via tools (MCP, terminal)?
- [ ] User perspective: does the change behave correctly when the user runs it?
- [ ] If cron: verify the job creates/updates correctly
- [ ] If config: verify the config is valid (YAML/JSON syntax, nginx -t, etc.)

## Phase 4 — Documentation

- [ ] Did the change affect any public interface? Update `docs/` or `AGENTS.md` accordingly
- [ ] Does the change need a `CONTRIBUTING.md` update?
- [ ] Is there an `ops/` script or config that should be documented in `docs/operations-reference.md`?

## Phase 5 — Final Verification

- [ ] Run `cortex-doctor.py` or equivalent health check
- [ ] **Adversarial scan passed (code changes only):** `python3 ops/scripts/quality/adversarial-verify.py --dir . --level A2 --gate` — **must exit 0**. For targeted scans: `--file <path>`.
- [ ] Verify all services restart cleanly (launchctl list / systemctl status)
- [ ] Verify symlinks are valid
- [ ] Verify no stale paths remain (`grep -r '/home/luke\\|${CORTEX_HOME}\\|${CORTEX_DEPLOY}'` on changed files)

## Closing the Cycle

- [ ] `mcp_loop_governance_cycle_query(task_id="<task-id>")`
- [ ] `mcp_loop_governance_feedback_accept(cycle_id=N, note="verified: <how>")`
- [ ] `mcp_loop_governance_end_change(task_id="<task-id>")`
- [ ] `git add -A && git commit -m "<descriptive message>" --no-verify`
- [ ] `git pull --rebase origin main && git push origin main`

## If Scoring Is Blocked

1. Run `bash ~/.hermes-cortex/tools/loop-governance/verify.sh` if it exists, or `python3 -c "from loop_db import LoopDB; db = LoopDB(); print(db.get_summary_stats())"`
2. If fix takes > 2 min, record manually later
3. **Never skip entirely** — governance-auditor cron flags unscored changes
4. `SKIP_SCORE=1` has been **removed** — the bypass no longer exists. Use `git commit --no-verify` in true emergencies.

## Install

To install this skill (after cloning hermes-cortex):
```bash
mkdir -p ~/.hermes/skills/governance
cp -r ~/hermes-cortex/docs/templates/skills/change-checklist ~/.hermes/skills/governance/
```
Then `/reset` to pick it up, or load with `skill_view(name="change-checklist")`.
