---
name: repo-health-review
version: 1.1.0
category: devops
description: >-
  Systematic repo health review — survey scripts, detect duplicates,
  check naming, find gaps, prune dead weight, and produce a structured
  report. Run before major refactors or when asked to audit the repo.
pinned: false
related_skills:
  - cortex-preflight
  - documentation-auditing
  - change-checklist
---

# Repo Health Review — Systematic Audit

## When to Use

- User asks "review the repo", "audit for gaps", "look for consolidation opportunities"
- Before a major refactor
- When onboarding a new team member (to document current state)

## Multi-Axis Audit (preferred for comprehensive reviews)

For thorough reviews, run 3+ parallel subagents via `delegate_task` — one per axis.
Each subagent scans a different dimension simultaneously, keeping your context
uncluttered while they work:

```python
# Standard 3-axis dispatch
delegate_task(tasks=[{
    "goal": "Audit docs for stale paths, broken cross-refs, missing sections",
    "context": "Check docs/ for stale src/, deploy/, runtime/ references..."
}, {
    "goal": "Audit install/update/doctor pipeline",
    "context": "Check cortex-update.sh register() validity, doctor --quick..."
}, {
    "goal": "Audit Linux vs macOS platform support and agent types",
    "context": "Check platform-specific code, SOUL.md profiles..."
}])
```

After subagents return, consolidate findings, fix easy items immediately,
then produce a structured report of what was fixed vs deferred.

## The 7-Pass Review (use for smaller/script-focused audits)

### Pass 1: Structure Survey
```bash
ls ops/scripts/*/           # All script directories
ls docs/                    # All docs
ls skills/                  # All skill categories
```

### Pass 2: Duplicate Detection
Check for files with same name in multiple directories:
```bash
find ops/scripts/ -name '*.py' -o -name '*.sh' | sed 's|.*/||' | sort | uniq -d
```
Verify identical content via MD5 when found:
```bash
md5sum <path1> <path2>
```

### Pass 3: Naming Check
Identify scripts breaking hyphen convention:
```bash
find ops/scripts/ -name '*_*' -not -path '*/__pycache__/*' -not -name '__*'
```
### Pass 4: Registration Check (Bi-Directional)

Check BOTH directions:
- Scripts in `ops/scripts/` that are NOT registered in `cortex-update.sh`
- `register()` entries in `cortex-update.sh` that point to NON-EXISTENT files

```bash
# Direction A: Which scripts are NOT registered?
grep -oP 'register\s+"[^"]+' ops/scripts/cortex-update.sh | sed 's/register "//'

# Direction B: Which registered files are MISSING on disk?
grep -oP 'register\s+"[^"]+' ops/scripts/cortex-update.sh | sed 's/register "//' | while read f; do [ -f "$f" ] || echo "MISSING: $f"; done
```

Stale `register()` entries silently fail during deploy — the file simply
doesn't get copied. Over time this causes the deployed state to diverge
from expectations. Fix by removing the stale line from cortex-update.sh.

Also check for **duplicate registrations** (same file registered twice)
and **path drift** (file was renamed but register wasn't updated, e.g.
`offline_code_index_cron.sh` → `offline-code-index-cron.sh`).

### Pass 4b: Stale Deploy Check

Check for deployed files that are no longer registered in `cortex-update.sh`.
When a `register()` line is removed, the deployed copy stays on disk as
an orphan. The doctor detects these:

```bash
python3 ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py 2>&1 | grep "Stale deploy"
```

Fix with:
```bash
bash ~/hermes-cortex/ops/scripts/cortex-update.sh --clean-stale
```

Or run `cortex-update.sh` (auto-cleans stales after deploy). For non-scripts
deploy targets (dashboard/, bus/, systemd units, launchd plists), manual
cleanup may be needed.

### Pass 4c: Doctor Comprehensive Check

After any structural change, run the full doctor and check ALL sections:

```bash
python3 ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py 2>&1 | grep -E "❌|⚠️|ℹ️" | head -20
```

New in this session (2026-07-23):
- **check_stale_deploys()** — detects orphaned deploy files and missing sources
- **Orphan cron detection** — flags crons in scheduler not in expected list
- **Network safety** — scans for services on 0.0.0.0 (Ollama, Bus, Langfuse)
- **Systemd linger** — verifies Linux user services survive reboot
- **Skills disk presence** — verifies every listed skill exists on disk

The doctor itself was modularized into `cortex_doctor/` package (8 modules).
Monolith at `cortex-doctor.py` is now a 34-line shim. To add a new check:
create a new function in `checks.py` and add it to the `all_checks` list in `cli.py`.

### Pass 5: Doc Cross-Reference
Check which docs are NOT referenced by any other doc, AGENTS.md, or README.md:
```
Search every .md for each doc filename. Unreferenced docs may be lost or stale.
```

### Pass 6: Stale File Check
- `__pycache__` directories
- `.pytest_cache` directories
- Root-level test files (should be in `tests/`)
- Zero-byte files
- `runtime` symlinks

### Pass 7: Gap Analysis
- PRDs with no named implementation
- Overlapping scripts doing similar things
- Features documented but not wired

### Pass 8a: Platform & Agent-Type Consistency

Check that platform-aware code handles both Linux and macOS:

```bash
grep -rn "systemctl\|launchctl\|brew\|apt-get\|platform\|uname" ops/scripts/ --include="*.py" --include="*.sh"
```

Identify scripts that assume one platform without an OS guard. Key patterns:
- `systemctl` used without falling back to `launchctl` on macOS
- `apt-get` used on macOS (should be `brew`)
- Hardcoded paths like `/home/` (Linux-only) or `/Users/` (macOS-only)

Check SOUL.md profiles for platform consistency:
- Does each agent profile declare a `platforms:` field in frontmatter?
- Do orchestrator profiles specify Linux?
- Do dev-agent profiles specify macOS/Linux?

Check agent-type coverage in docs:
- `docs/agent-architecture.md` — lists all 4 roles (orchestrator, backup-orch, server-agent, dev-agent)?
- `docs/fleet-reference.md` — maps real agent names (Moses, Esther, etc.) to roles?
- `docs/cron-schedules.md` — split by `orch-*`, `agent-*`, `local-*` prefixes?
- `AGENTS.md` — mentions agent type differences?

### Pass 8b: Cross-Script Deploy/Install/Doctor Consistency Audit

**Purpose:** Verify that the three core lifecycle scripts — `install.sh`, `cortex-update.sh`, and `cortex_doctor/` — agree on agent-type branching. If they diverge, agents get false-positive doctor failures, wrong cron expectations, or orphan deploy artifacts.

**Run when:** User asks to audit agent-type branching, fix doctor false positives on non-orch agents, or verify deploy/install/doctor pipeline consistency. Also run before adding a new agent type.

**Methodology — check 5 dimensions:**

#### 8b-1: Capability Model vs Role Model

Identify whether the system uses a **capability model** (`CORTEX_PROFILE=core|laptop|server` — how much hardware) or a **role model** (`--agent-type orchestrator|server|dev` — what services to run):

```bash
# Which model does install.sh use?
grep -n 'CORTEX_PROFILE' ops/install/install.sh | head -5
grep -n 'agent.type\|agent_type\|--agent-type' ops/install/install.sh | head -5

# Which model does the doctor use?
grep -n 'is_orch\|IS_ORCH\|hostname\|agent.type' ops/scripts/manage/cortex_doctor/config.py
```

**Gap to detect:** A capability model (CORTEX_PROFILE) cannot distinguish between an orchestrator (needs bus server + dashboard + nginx) and a server-agent (needs bus client + crons, NOT dashboard/nginx). When both map to `server`, orchestrator-only services get deployed to server-agents and produce doctor false positives.

#### 8b-2: register() Guard Coverage in cortex-update.sh

Check whether orchestrator-only service files (dashboard, agent-bus server, nginx configs) are **conditionally registered** or deployed to every agent:

```bash
# Are dashboard/bus/nginx files registered unconditionally?
grep -n 'register.*dashboard\|register.*bus\|register.*nginx' ops/scripts/cortex-update.sh

# Is deploy_nginx_configs() guarded?
grep -B3 -A3 'deploy_nginx_configs' ops/scripts/cortex-update.sh

# Is deploy_system_scripts() guarded?
grep -B3 -A3 'deploy_system_scripts' ops/scripts/cortex-update.sh
```

**Check:** Is there an `IS_ORCHESTRATOR`, `IS_SERVER`, or `CORTEX_PROFILE` guard on these? If they run unconditionally, server-agents and dev-agents get files they don't need. The only guard is `CORTEX_SKIP_NGINX` env var — optional, not default.

#### 8b-3: Doctor EXTERNAL_SERVICES Hardcoding

The doctor's `config.py` defines `EXTERNAL_SERVICES` — endpoints it checks for health. If this list is hardcoded with Dashboard, Langfuse, and Agent Bus, it will FAIL on every non-orch agent:

```bash
grep -A10 'EXTERNAL_SERVICES' ops/scripts/manage/cortex_doctor/config.py
```

**Check:** Is there agent-type awareness? Does the doctor skip Dashboard/Langfuse checks on server-agents that don't host them? Also check `check_nginx()` — does it run unconditionally?

#### 8b-4: Cron Separation and Doctor Cron Expectation

Three cron layers should be cleanly separated. Verify cross-referencing:

```bash
# Universal crons (all agents)
grep -n 'agent-' ops/scripts/install-crons.sh | head -5

# Orchestrator-only crons
grep -n 'orch-' ops/scripts/install/install-orch-crons.sh | head -5

# Dev-agent crons — local-* prefix (created manually, no installer exists)
grep -n 'local-' ops/scripts/install-crons.sh | head -5
```

**Check path 1:** Does the doctor's `parse_expected_crons()` correctly exclude orch crons from the universal expected list?

```bash
grep -A15 'parse_expected_crons' ops/scripts/manage/cortex_doctor/config.py
```

**Check path 2:** Does `check_crons()` correctly identify orchestrator hosts and only FAIL on missing orch crons for those hosts?

```bash
grep -A15 'orch_crons_list' ops/scripts/manage/cortex_doctor/checks.py
```

**Check path 3:** Does `check_crons()` check the `IS_ORCHESTRATOR` env var (like cortex-update.sh does), or only hostname? Hostname-only is brittle — won't match fresh installs or custom hostnames.

**Gap to detect:** If `parse_expected_crons()` doesn't match `install-orch-crons.sh`, or if `check_crons()` hostname detection differs from `install-orch-crons.sh`, the doctor will produce inconsistent results.

#### 8b-5: Dev-Agent Minimal Path

Check whether dev agents (e.g. `titus`) have a valid automated setup path:

```bash
# Is there an install-local-crons.sh script?
find ops/ -name '*local*' 2>/dev/null

# Does install.sh --agent-type dev exist?
grep 'dev\|titus' ops/install/install.sh

# Does cortex-update.sh skip dashboard/bus/nginx for dev agents?
grep 'IS_DEV\|agent.dev\|dev.minimal\|skip.*dev' ops/scripts/cortex-update.sh
```

**Gap to detect:** Dev agents with no automated installer must create `local-*` crons manually. If the `local-*` prefix is documented in comments but no scaffolding exists (no installer, no doctor awareness, no update guard), the dev-agent path is incomplete.

#### 8b-6: Verify Hostname Detection Uniformity

The same hostname/orch-detection logic should appear in:
1. `cortex-update.sh` (lines ~1412-1438) — `IS_ORCHESTRATOR` env var + hostname fallback
2. `cortex_doctor/checks.py` (lines ~407-421) — hostname only
3. `install-orch-crons.sh` (lines ~29-39) — `IS_ORCHESTRATOR` env var + hostname fallback

**Gap:** If the doctor doesn't read `IS_ORCHESTRATOR` from `.env`, it will fail to detect orchestrator hosts not named moses/esther. Scripts 1 and 3 agree; script 2 may be out of sync.

#### 8b-7: Produce Cross-Script Consistency Table (see also: `references/agent-type-system.md`)

After checking all 5 dimensions, produce a table showing which files branch on what:

```markdown
| Dimension | install.sh | cortex-update.sh | cortex_doctor/ |
|-----------|-----------|-----------------|----------------|
| Service install guard | CORTEX_PROFILE=server | none (unconditional deploy) | none (hardcoded EXTERNAL_SERVICES) |
| Nginx deploy guard | CORTEX_PROFILE=server | CORTEX_SKIP_NGINX (optional) | none (always checks) |
| Orch cron guard | N/A | IS_ORCHESTRATOR + hostname | hostname only |
| Dev-agent path | none | none | none |
```

This table makes gaps visible at a glance. Each row that differs by column is a consistency failure.

## User Preference Signals

When the user corrects your approach or style, capture the lesson:

| Signal | Response |
|--------|----------|
| "No. Refactor. Do it right" | Don't take shortcuts — thin wrappers are tech debt. Do the full refactor, not a compromise. |
| "Finish. Don't wait for future" | Don't defer actionable items. Fix them in the same session — every issue found during audit must be fixed or explicitly acknowledged before reporting done. |
| "Thoroughly test" | Every change must be exercised with real tool output before reporting done. |
| "Make agent X aware of Y" | If the doctor or pipeline should check for Y, add a check — don't just document it. |
| User repeats a correction | Add a structural guardrail (skill update, pre-commit hook, doctor check, auto-cleanup) that makes the mistake impossible. |

Encode these in the relevant skill's SKILL.md body — not just in memory.
Skills capture "how to do this class of task for this user"; memory
captures "who the user is and what the current situation is."

## Deliverable

Produce a structured report with:
1. **Summary** — counts: scripts, docs, skills, issues found, issues fixed
2. **Fixed Items** — what was changed (moved, renamed, pruned, archived)
3. **Documented Items** — what was noted for future action
4. **Priority Recommendations** — ordered by effort vs impact

## Anti-Patterns

- ❌ Only searching disk, not git — file may exist in repo but not deployed
- ❌ Skipping MD5 verification — two files with same name may differ
- ❌ Not checking cross-references before renames — breaks other agents
- ❌ Leaving stales without documenting the decision
