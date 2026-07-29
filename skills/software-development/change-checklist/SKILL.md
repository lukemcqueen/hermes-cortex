---
name: change-checklist
version: 2.0.0
category: software-development
description: "Mandatory pre-ship verification before calling end_change(). Covers Phase 0 survey, test, multi-OS, multi-role, docs, final verification, and reflexion. Every governance cycle must run this before closing."
author: Hermes Cortex
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [governance, testing, documentation, multi-os, multi-role, quality]
    related_skills: [loop-governance, change-test-loop, two-hard-rules, cron-job-management, survey-before-action, agent-contract]
---

# Change Checklist — Pre-Ship Validation

## The Workmanship Principle

Before the checklist: every change you ship is a reflection of your workmanship.
**Do not stop at the obvious path.** The easy path — changing one file, running
one test — is never the complete path. For every change, ask:

- What else does this touch? Configs, docs, other agents, deployed state?
- Did I verify the SYMPTOM resolves (not just the code path)?
- Did I check sibling locations for the same flaw?
- Did I run the doctor to see if my change broke something else?
- Did I push changes so the whole fleet benefits?

Agents that ship incomplete work erode trust. The checklist below is the
minimum — your judgment determines when the work is genuinely done.

### Writing quality for prompts, docs, and skills

When creating or updating cron prompts, command output examples, or skill
content in this session, apply these two principles:

1. **Concrete examples, never abstract placeholders.** Show real-looking values
   (`43 cycles scored`, `$0.006/run`, `2026-07-15 10:01 KST`), not annotated
   templates (`[N] cycles`, `<cost>`, `<datetime>`). LLMs mimic concrete
   structure faithfully; they interpret placeholders loosely.

2. **Be concise — every sentence must earn its place.** If a sentence doesn't
   change agent behavior, it's token waste. After writing, review: "Would the
   agent do anything differently if I deleted this?" If no, delete it.

## When to Load This Skill

Load this skill **before calling `end_change()`** on any change that:
- Modifies scripts (`.sh`, `.py`, `.rb`, `.js`)
- Changes deploy configs (nginx, systemd, launchd)
- Adds/modifies crons
- Updates docs that other agents consume
- Changes `cortex-update.sh` or `install-crons.sh`

## Phase 0b: Load Relevant Skills (Before begin_change)

Before opening a governance lock, ensure you have the right domain knowledge loaded:

- [ ] **skills_list()** for the category matching your task (e.g. 'devops' for bus changes, 'survey' for research tasks)
- [ ] **skill_view()** on any matching skill — read the full content, not just the description
- [ ] **Verify loaded** — a skill isn't loaded until you've read its content via skill_view(). Just knowing the name exists doesn't count.

> **Common failure:** Starting work with zero skills loaded, getting corrected by the user mid-task, then having to redo work. Load skills first, even for "trivial" tasks.

## Phase 0: Survey the Change Surface

Before making any change, map the full scope. A single cron rename can touch 10+ locations. **Always do this first:**

- [ ] **search_files()** for the old name/term across the entire repo — find every reference
- [ ] **Cron manifest**: check `install-crons.sh` AND `install-orch-crons.sh` — uninstall arrays (expected-cron list for doctor), create_cron blocks, guard messages
- [ ] **Updater**: check `cortex-update.sh` for `register()` calls
- [ ] **Doctor**: check `cortex-doctor.py` — `parse_expected_crons()` and `parse_orch_crons()` read from install script uninstall arrays
- [ ] **Deployed path**: after creating/recreating, verify `~/.hermes-cortex/scripts/<script>` exists at the runtime path (not just the repo)
- [ ] **Doc index**: check `DOCS-INDEX.md` needs an entry update
- [ ] **Cross-references**: grep for old term in other scripts' comments, docstrings, deprecation notices
- [ ] **Category awareness**: is this orchestrator-only (orch-*) or general? 
  - **Decision rule**: does this need to run on EVERY agent or only orchestrators (Moses/Esther)?
    - Orchestrator-only → `install-orch-crons.sh` with `orch-*` prefix
    - All agents → `install-crons.sh` with `agent-*` or descriptive name
    - Agent-side (no_agent) → `install-crons.sh` with `agent-*` prefix
  - Update the `fleet-reference.md` cron table category column
- [ ] **Doctor compatibility**: after updating `install-crons.sh` or `install-orch-crons.sh`, verify `cortex-doctor.py`'s `parse_expected_crons()` (reads main uninstall array, excludes orch) and `parse_orch_crons()` (reads orch uninstall array) properly cover the new entry. Run the doctor to confirm: `python3 ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py --quiet`
- [ ] **Install array sync (non-negotiable)**: After any cron rename or addition, verify the `create_cron` block name matches the uninstall array entry EXACTLY. The doctor parses uninstall arrays as its expected cron list. Drift means the doctor validates the wrong set. Run:
  ```bash
  python3 ~/hermes-cortex/ops/scripts/manage/fix-cron-duplicates.py
  ```
  Zero issues = arrays are in sync.
- [ ] **Old cron cleanup**: If you added a new cron with a new name (e.g. `orch-bus-audit-watchdog` replacing `bus-audit-watchdog`), confirm the old one was removed via the script or direct jobs.json edit. Crons don't self-destruct.
- [ ] **Test run**: after deploy, run the actual script to verify exit code 0
- [ ] **Governance lock verified**: After `begin_change()`, confirm the lock is active with `check_lock`. The lock is session-scoped (`.governance-{session_id}.json`) — no generic symlink needed.
- [ ] **PII scan**: run `bash ~/hermes-cortex/ops/scripts/secret-leak-detector.sh` and review any PII warnings before pushing. Check for real domains, `/home/<username>/` paths, and email addresses in new/changed files.

## The Checklist

### Phase 1: Test the Change

Run the actual script/config and verify it works. **No simulated output.**  
See `references/testing-deployable-scripts.md` for detailed testing patterns by script type.

- [ ] **Script changes:** Run the script with relevant inputs and verify real output
  - `bash script.sh --help` or `python3 script.py` — confirm it runs without errors
  - If it produces a config: verify the output has correct paths for the OS you're on
  - If it's a cron job: create it with `cronjob(action='run')` and inspect the delivery
  - ⚠️ **Manual `python3 script.py` does NOT update the cron scheduler's `last_status`.** The doctor reads the scheduler's recorded status, not the script exit code. After fixing a cron, ALWAYS run `cronjob action='run' job_id=<id>` to refresh the scheduler's status. Then run the doctor to confirm it clears.
  - ⚠️ **Don't test in isolation** — run the full command, not an imported function

- [ ] **Config changes:** Diff generated vs deployed
  - `diff /tmp/hermes-services-processed.conf /etc/nginx/sites-available/hermes-services.conf`
  - Confirm only the changes you intended

- [ ] **Syntax check:** Already caught by pre-commit hook, but verify for unstaged files too
  - `.sh` → `bash -n file.sh`
  - `.py` → `python3 -c "import py_compile; py_compile.compile('file.py', doraise=True)"`
  - `.yaml` → `python3 -c "import yaml; yaml.safe_load(open('file.yaml'))"`

- [ ] **nginx changes:** Run `sudo nginx -t` to validate syntax

### Phase 2: Verify Multi-OS Compatibility

Every change that touches paths or system commands must work on both Linux and macOS.

- [ ] **Path patterns:** Search changed files for hardcoded paths:
  ```
  /etc/nginx/         → must use ${NGINX_DIR} or NGINX_BREW_DIR
  /opt/homebrew/      → must be guarded by OS check (IS_MAC or uname)
  /root/              → must use CORTEX_HOME or Path.home()
  ~/         → must use $HOME or Path.home()
  ~/        → must use $HOME or Path.home()
  ```

- [ ] **System commands:** Check for OS-specific binaries:
  ```
  systemctl           → guard with IS_LINUX
  launchctl           → guard with IS_MAC
  brew                → guard with IS_MAC
  apt/yum/dnf         → guard with IS_LINUX
  ```

- [ ] **nginx deploy paths:**
  - Linux: `/etc/nginx/sites-available/hermes-services.conf`
  - macOS: `/opt/homebrew/etc/nginx/servers/hermes-services.conf` (arm64)
  - macOS: `/usr/local/etc/nginx/servers/hermes-services.conf` (x86_64)

### Phase 3: Verify Multi-Role Compatibility

Different agents have different setups. Your change shouldn't break them.

- [ ] **Process/service name audit:** If your change uses `pgrep`, `systemctl`, `launchctl`, or any process-detection tool, verify the name matches the ACTUAL runtime command line. `pgrep -f agent-bus` silently returns nothing when the real daemon is `agent_bus` (underscore, from uvicorn agent_bus.server). Check `ps aux | grep <name>` to see the real argv — use that exact string, not a guess.

- [ ] **Titus (macOS, push-only health, 1 agent, many projects):**
  - No server-level services (no systemd, no nginx necessarily)
  - Health is pushed to inbox, not polled via HTTP
  - Has many project repos with their own `.hermes-cortex/` directories
  - Verify: script doesn't assume nginx is installed or running
  - Verify: script doesn't assume a single repo root

- [ ] **Joseph (Linux, production web/infra server):**
  - Runs full Hermes Cortex stack, nginx, services
  - Has cron jobs for `hermes-update`, `threat-pipeline`, `agent-ip-submission`
  - Deployed scripts go to `~/.hermes-cortex/scripts/`
  - Verify: script doesn't create temp files that need cleanup on production

- [ ] **Esther (Linux, production server):**
  - Same deployment as Joseph but with orchestrator crons
  - Verify: orchestrator-only scripts don't interfere

- [ ] **Kustos (Linux, security server):**
  - Production, may have stricter permissions
  - Verify: scripts handle `PermissionError` gracefully (use `_path_ok()` pattern)

- [ ] **Non-orchestrator agents:**
  - No `cronjob` MCP tool — must request crons via inbox
  - Verify: new cron jobs are registered in `install-crons.sh` or `install-orch-crons.sh`
  - ⚠️ **Message audit:** Scan every output message, warning, and status line your change produces. Would a non-orchestrator agent read it and think they should install an orchestrator-only service (local bus daemon, nginx, etc.)? If yes, rephrase or gate the message behind a role check. A message like "local bus daemon not running" makes agents try to install one.

### Role-Aware Health Check Patterns

When writing health checks or scripts that run on both orchestrator and regular agents:

- **Process-gate localhost checks.** Never curl 127.0.0.1 for a service unless you've verified the daemon process exists first (pgrep -f agent_bus). Non-orchestrators don't run local daemons - curling a dead port is both wasteful and misleading.
- **Never mention irrelevant services in messages.** A non-orchestrator agent should never see "local bus", "local daemon", or similar phrasing. It implies that service should be present, which agents may interpret as an instruction to install it.
- **Severity matters.** If a service is confirmed running (process found, port open), any non-200 response is a FAIL, not a WARN. A faulty service that the doctor knows exists is an error.
- **If no URL is configured, it's a FAIL.** On agents that should have remote connectivity (bus URL, fallback URL), absence of configuration is a hard error - not a SKIP.
- **Check both URLs, not just one.** CORTEX_BUS_URL and CORTEX_BUS_FALLBACK_URL should both be present. Check env and config file; reuse the same config reader pattern.
- **Process names use underscores.** The agent_bus daemon runs under uvicorn as agent_bus.server:app. pgrep -f agent-bus (hyphen) silently returns nothing. Always verify the actual command line with ps aux | grep before hardcoding a pgrep pattern - use that exact string, not a guess.

### Phase 4: Update Documentation

Changes that affect other agents' workflow must be documented.

- [ ] **New script added?**
  - Register in `cortex-update.sh` with `register()` call (use the canonical `ops/` path)
  - Add script path to `install-crons.sh` or `install-orch-crons.sh` if it's a cron

- [ ] **New skill added?**
  - Add with SKILL.md under `*/skills/<category>/<name>/`
  - Add to `docs/skills-manifest-reference.md` if it should be auto-loaded

- [ ] **After a repo path restructure:**
  - Scan deployed scripts for stale references: `grep -rn 'hermes-cortex/ops/' ~/.hermes-cortex/scripts/ ~/.hermes/scripts/ ~/.hermes-cortex/hooks/`
  - Fix live execution paths first (not comments), then update config paths in `~/.hermes/config.yaml`
  - Create backward-compat symlinks from old paths to new paths for any remaining references
  - Update `repo-organization` skill's canonical directory tree if the layout changed

- [ ] **Config template changed?**
  - Update comments in `deploy/nginx/hermes-services.conf` (the template itself)
  - Verify deploy scripts (`cortex-update.sh`, `install-nginx-full.sh`, `hermes-services-apply.py`) handle the new placeholder

- [ ] **Agent workflow changed?**
  - Update `AGENTS.md` if the execution contract, governance, or inbox framework changed
  - Update relevant agent `SOUL.md` files if their behavioral principles changed

- [ ] **New deployment dependency?**
  - Update `docs/agent-onboarding.md`
  - Update `docs/service-layer-decision.md` if service layer changed

### Phase 5: Final Verification

- [ ] **Stale expected list cleanup**: if you removed any cron during this cycle, verify its name is also removed from the uninstall arrays in `install-crons.sh` and `install-orch-crons.sh`. The doctor reads these arrays as the *expected cron list*. A name in the uninstall array but no matching live cron = false ❌ on the doctor.
- [ ] **Stale bus/state artifact cleanup**: after a debugging or testing cycle, clean up leftover test artifacts before calling end_change(). Check:
  - Bus messages: `DELETE FROM bus.messages WHERE ...` — stale test messages with old correlation IDs accumulate and confuse subsequent diagnostics
  - State files: `~/.hermes-cortex/state/message-tracker.json`, `fleet-update-state.json` — stale tracker entries cause noisy "overdue" alerts
  - Cron tracker: check `local-*` cron output for references to stale correlation IDs — stop tracking crons that reference expired test data
  - Rule of thumb: if you sent test messages during this cycle, delete them before end_change(). The user should not see your debugging artifacts.
- [ ] **Doctor runs clean** on the changed subsystem — confirm it shows `✅ Crons registered` (not ❌ Crons missing), `✅ Orch crons`, `✅ Crons total`:
  ```bash
  python3 ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py --quiet
  ```
- [ ] **Pre-commit validation ran** (check for "change-validate:" output in last commit)
- [ ] **Governance cycle scored** — `feedback_accept()` called before `end_change()`
- [ ] **Change was pushed** — `git push origin main` (after `git pull --rebase`)
- [ ] **Cron delivery audit:** If you created or modified a cron job, verify its `deliver` destination actually goes somewhere visible. `deliver: "origin"` delivers nowhere if the cron was created from a script or non-chat context. No_agent watchdogs with `deliver: "local"` are invisible. Alerts should go to a chat the user sees.
- [ ] **Timeout/deadline audit:** If you set a timeout, deadline, or alert threshold, verify it matches expected task duration. An agent completing a fix in 5 minutes should not have a 60-minute deadline. Rule of thumb: deadline = 3× expected worst-case completion time. A 15-minute default catches most failures within one alert cycle.

### Phase 6: Reflexion (Self-Critique)

**Before end_change(), run the reflexion check:**

- [ ] Load the `reflexion-check` skill
- [ ] Five-question audit:
  - **Completeness:** Did I verify every claim with a tool call?
  - **Correctness:** Is my reasoning valid, or did I jump to conclusions?
  - **Edge cases:** Did I handle errors, missing files, permission issues?
  - **Side effects:** Did I check for unintended changes (diff, test suite)?
  - **Evidence:** Can I cite a tool call for every claim in my summary?
- [ ] Score confidence: HIGH / MEDIUM / LOW / ZERO
- [ ] If MEDIUM: disclose uncertainty in the delivery
- [ ] If LOW or ZERO: fix before delivering
- [ ] **Blunder check:** "What is the most likely thing I got wrong?"

**This phase is mandatory for all changes that touch multiple files, services, or configurations.** For single-line or trivial changes, a 10-second mental reflexion is sufficient.

## Anti-Patterns to Avoid

| Anti-pattern | Why it's wrong |
|---|---|
| "I tested it manually" | Manual = ad-hoc, not repeatable, no proof. Run the actual tool. Also: manual `python3 script.py` doesn't update the cron scheduler's `last_status` — the doctor reads scheduler status, not script exit code. |
| "It's just a health check message — agents won't see it" | Agent-facing messages are instructions. A WARN saying "bus daemon not running" makes agents try to install one. All output is visible to all agents — gate or rephrase accordingly. |
| "I already did the main work, the rest is trivial" | The omitted work (docs, deploy, doctor, push) is where trust breaks. The work isn't done until it's ALL done. |
| "Other OS can wait" | It won't. Ship OS-agnostic on day one. |
| "Docs can come later" | Later = never. Update docs before end_change(). |
| "Titus doesn't need this" | If it runs on Titus, it must be tested there. Push-only ≠ skip. |
| "The hook didn't catch it" | The hook is syntax-level. You catch semantics here. |
| "sudo nginx -t failed" | Don't ship broken syntax. Fix and re-verify. |
| "I'll write a migration script" | The git commit that deletes orphan files IS the migration. A separate script is only needed if the cleanup requires conditional logic across machines. If the commit can do it, ship the commit — not a script nobody will run. |
| "I'll test with a long sleep" | Blind-sleeping 60-90s wastes time when you could poll every 15s and detect completion sooner. Use periodic short-interval polling (`time.sleep(15)` max in a loop up to 8 tries) instead of one long `sleep(90)`. The terminal has a 60s timeout — Python `time.sleep()` loops inside a single terminal command count against the same timeout, so keep each iteration fast. Prefer running checks as separate rapid terminal calls. |
| "It worked from my repo terminal" | A script that works from `~/hermes-cortex/` can fail from the deployed path due to different cwd, env vars, or file resolution. Always test from the actual cron runtime path (`~/.hermes/scripts/`), not just the repo source. `Path(\"\")` from an unset env var is the classic trap — works in a session with the var set, crashes in cron. |

## Quick Reference: Path Patterns by OS

| Purpose | Linux | macOS (arm64) | macOS (x86_64) |
|---------|-------|---------------|----------------|
| nginx config dir | `/etc/nginx` | `/opt/homebrew/etc/nginx` | `/usr/local/etc/nginx` |
| nginx sites dir | `sites-available/` | `servers/` | `servers/` |
| nginx sites-enabled | `sites-enabled/` | `servers/` (same as avail) | `servers/` |
| htpasswd file | `.hermes-htpasswd` | `.htpasswd` | `.htpasswd` |
| nginx log dir | `/var/log/nginx` | `/opt/homebrew/var/log/nginx` | `/usr/local/var/log/nginx` |
| Service manager | `systemctl --user` | `launchctl` | `launchctl` |
| Package manager | `apt` / `yum` / `dnf` | `brew` | `brew` |
