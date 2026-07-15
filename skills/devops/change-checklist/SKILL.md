---
name: change-checklist
version: 1.0.0
category: devops
description: "Mandatory pre-ship checklist: run before end_change() to ensure the change is tested, documented, OS-aware, and compatible with all agent roles."
author: Moses
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

## Phase 0: Survey the Change Surface

Before making any change, map the full scope. A single cron rename can touch 10+ locations. **Always do this first:**

- [ ] **search_files()** for the old name/term across the entire repo — find every reference
- [ ] **Cron manifest**: check `install-crons.sh` AND `install-orch-crons.sh` — uninstall arrays (expected-cron list for doctor), create_cron blocks, guard messages
- [ ] **Updater**: check `cortex-update.sh` for `register()` calls
- [ ] **Doctor**: check `cortex-doctor.py` — `parse_expected_crons()` and `parse_orch_crons()` read from install script uninstall arrays
- [ ] **Deployed path**: after creating/recreating, verify `~/.hermes-cortex/scripts/<script>` exists at the runtime path (not just the repo)
- [ ] **Doc index**: check `DOCS-INDEX.md` needs an entry update
- [ ] **Cross-references**: grep for old term in other scripts' comments, docstrings, deprecation notices
- [ ] **Category awareness**: is this orchestrator-only (orch-*) or general? Update the `fleet-reference.md` cron table category column
- [ ] **Test run**: after deploy, run the actual script to verify exit code 0

## The Checklist

### Phase 1: Test the Change

Run the actual script/config and verify it works. **No simulated output.**  
See `references/testing-deployable-scripts.md` for detailed testing patterns by script type.

- [ ] **Script changes:** Run the script with relevant inputs and verify real output
  - `bash script.sh --help` or `python3 script.py` — confirm it runs without errors
  - If it produces a config: verify the output has correct paths for the OS you're on
  - If it's a cron job: create it with `cronjob(action='run')` and inspect the delivery
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
  /home/luke/         → must use $HOME or Path.home()
  /home/moses/        → must use $HOME or Path.home()
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

### Phase 4: Update Documentation

Changes that affect other agents' workflow must be documented.

- [ ] **New script added?**
  - Register in `cortex-update.sh` with `register()` call (use the canonical `ops/` path)
  - Add script path to `install-crons.sh` or `install-orch-crons.sh` if it's a cron

- [ ] **New skill added?**
  - Add with SKILL.md under `*/skills/<category>/<name>/`
  - Add to `docs/skills-manifest-reference.md` if it should be auto-loaded

- [ ] **After a repo path restructure:**
  - Scan deployed scripts for stale references: `grep -rn 'hermes-cortex/src/' ~/.hermes-cortex/scripts/ ~/.hermes/scripts/ ~/.hermes-cortex/hooks/`
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

- [ ] **Doctor runs clean** on the changed subsystem:
  ```bash
  python3 ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py --quiet
  ```
- [ ] **Pre-commit validation ran** (check for "change-validate:" output in last commit)
- [ ] **Governance cycle scored** — `feedback_accept()` called before `end_change()`
- [ ] **Change was pushed** — `git push origin main` (after `git pull --rebase`)

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
| "I tested it manually" | Manual = ad-hoc, not repeatable, no proof. Run the actual tool. |
| "It's just a small config change" | Small changes break prod too. Same checklist applies. |
| "I already did the main work, the rest is trivial" | The omitted work (docs, deploy, doctor, push) is where trust breaks. The work isn't done until it's ALL done. |
| "Other OS can wait" | It won't. Ship OS-agnostic on day one. |
| "Docs can come later" | Later = never. Update docs before end_change(). |
| "Titus doesn't need this" | If it runs on Titus, it must be tested there. Push-only ≠ skip. |
| "The hook didn't catch it" | The hook is syntax-level. You catch semantics here. |
| "sudo nginx -t failed" | Don't ship broken syntax. Fix and re-verify. |

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
