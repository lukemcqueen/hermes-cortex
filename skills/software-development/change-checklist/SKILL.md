---
name: change-checklist
version: 1.1.0
category: software-development
description: "Mandatory pre-ship verification before calling end_change(). Covers Phase 0 survey, test, multi-OS, multi-role, docs, final verification, and reflexion. Every governance cycle must run this before closing."
pinned: true
author: Hermes Cortex
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [governance, testing, documentation, multi-os, multi-role, quality, pre-ship]
    related_skills: [loop-governance, change-test-loop, two-hard-rules, cron-job-management, survey-before-action, agent-contract]
---

# Change Checklist — Pre-Ship Validation

**Mandatory before every `end_change()` call.**

Load this skill BEFORE closing a governance cycle. Run through all phases. Do not skip, batch, or defer.

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

## Phase 0: Survey the Change Surface

Before making any change, map the full scope. A single cron rename can touch 10+ locations. **Always do this first:**

- [ ] **search_files()** for the old name/term across the entire repo — find every reference
- [ ] **Cron manifest**: check `install-crons.sh` — uninstall arrays (expected-cron list for doctor), create_cron blocks, guard messages
- [ ] **Updater**: check `cortex-update.sh` for `register()` calls
- [ ] **Doctor**: check `cortex-doctor.py` — `parse_expected_crons()` reads from uninstall arrays
- [ ] **Deployed path**: after creating/recreating, verify `~/.hermes-cortex/scripts/<script>` exists at the runtime path (not just the repo)
- [ ] **Doc index**: check `DOCS-INDEX.md` needs an entry update
- [ ] **Cross-references**: grep for old term in other scripts' comments, docstrings, deprecation notices
- [ ] **Category awareness**: is this orchestrator-only (orch-*) or general?
  - All agents → `install-crons.sh` with `agent-*` prefix
  - See [`docs/fleet-reference.md`](docs/fleet-reference.md) cron table
- [ ] **Doctor compatibility**: after updating `install-crons.sh`, run the doctor to confirm: `python3 ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py --quiet`
- [ ] **Install array sync (non-negotiable)**: After any cron rename or addition, verify the `create_cron` block name matches the uninstall array entry EXACTLY. The doctor parses uninstall arrays as its expected cron list. Run:
  ```bash
  python3 ~/hermes-cortex/ops/scripts/manage/fix-cron-duplicates.py
  ```
  Zero issues = arrays are in sync.
- [ ] **Old cron cleanup**: If you added a new cron with a new name, confirm the old one was removed. Crons don't self-destruct.
- [ ] **Test run**: after deploy, run the actual script to verify exit code 0
- [ ] **PII scan**: run `bash ~/hermes-cortex/ops/scripts/secret-leak-detector.sh` and review any PII warnings before pushing. Check for real domains, `/home/<username>/` paths, and email addresses in new/changed files.

## Phase 1: Test the Change

Run the actual script/config and verify it works. **No simulated output.**

- [ ] **Did the change actually apply cleanly?** (No errors in write_file/patch/terminal)
- [ ] **If code:** Run it with relevant inputs and verify real output
  - `bash script.sh --help` or `python3 script.py`
  - If it's a cron: run `cronjob action='run' job_id=<id>` — manual `python3 script.py` does NOT update the scheduler's `last_status`
- [ ] **If config:** does the service still start? (Restart/reload and check)
  - nginx: `sudo nginx -t` to validate syntax
  - Diff generated vs deployed config
- [ ] **If cron:** does the script exit 0 when run manually?
- [ ] **Syntax check:** `.sh` → `bash -n`, `.py` → `python3 -m py_compile`, `.yaml` → `yaml.safe_load()`
  - If any `install-crons.sh` or `install-orch-crons.sh` was modified: **mandatory `bash -n`** on both files. This catches array formatting errors (trailing backslash, orphaned semicolons, blank lines in continuation blocks).

## Phase 2: Verify Multi-OS Compatibility

Every change that touches paths or system commands must work on both Linux and macOS.

- [ ] **Path patterns:** Search changed files for:
  - `/etc/nginx/` → must use `${NGINX_DIR}`
  - `/home/luke/` or `/home/moses/` → must use `$HOME`
  - `/opt/homebrew/` → must be guarded by OS check
- [ ] **System commands:**
  - `systemctl` → guard with `IS_LINUX`
  - `launchctl` / `brew` → guard with `IS_MAC`
- [ ] Is this change Linux-only, macOS-only, or cross-platform?
- [ ] If cross-platform: did you test the relevant paths?

## Phase 3: Verify Multi-Role Compatibility

Different agents have different setups. Your change shouldn't break them.

- [ ] **Does this change affect other agents?** (configs, scripts, crons, docs they rely on)
- [ ] **Titus (macOS):** No systemd, no nginx necessarily. Health pushed, not polled.
- [ ] **Joseph/Esther (Linux prod):** Full stack, production cleanup considerations. Esther has orchestrator crons too.
- [ ] **Kustos (Linux, security):** Stricter permissions. Scripts handle `PermissionError` gracefully.
- [ ] **Non-orchestrator agents:** No `cronjob` MCP tool — request crons via inbox.
- [ ] If yes to any: notify them via inbox or update shared docs.

## Phase 4: Update Documentation

Changes that affect other agents' workflow must be documented.

- [ ] **New script added?** Register in `cortex-update.sh` with `register()` call
- [ ] **New skill added?** Add under `skills/<category>/<name>/` with SKILL.md
- [ ] **New cron?** Add to `install-crons.sh` uninstall array + create_cron block
- [ ] **Config template changed?** Update the template, verify deploy scripts handle it
- [ ] **Agent workflow changed?** Update AGENTS.md or relevant SOUL.md
- [ ] **Does the commit message explain what changed AND why** (not just "fix bug")?
- [ ] **If you added a new file:** is there a `why-new` rationale?

## Phase 5: Final Verification

- [ ] **Stale expected list cleanup**: if you removed any cron during this cycle, verify its name is also removed from the uninstall arrays in `install-crons.sh`. The doctor reads these arrays as the expected cron list.
- [ ] **Doctor runs clean**:
  ```bash
  python3 ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py --quiet
  ```
- [ ] **Verify no stale locks remain** (`mcp_loop_governance__check_lock`)
- [ ] **Are all cycles scored?** No PENDING cycles should remain.
- [ ] **Pre-commit validation ran** (check for "change-validate:" output)
- [ ] **Governance cycle scored** — `feedback_accept()` called before `end_change()`
- [ ] **Change was pushed** — `git push origin main` (after `git pull --rebase`)

## Phase 6: Reflexion (Self-Critique)

**Before end_change(), run the reflexion check:**

- [ ] **Completeness:** Did I verify every claim with a tool call?
- [ ] **Correctness:** Is my reasoning valid, or did I jump to conclusions?
- [ ] **Edge cases:** Did I handle errors, missing files, permission issues?
- [ ] **Side effects:** Did I check for unintended changes (diff, test suite)?
- [ ] **Evidence:** Can I cite a tool call for every claim in my summary?
- [ ] Score confidence: HIGH / MEDIUM / LOW / ZERO
- [ ] If MEDIUM: disclose uncertainty in the delivery
- [ ] If LOW or ZERO: fix before delivering
- [ ] **Blunder check:** "What is the most likely thing I got wrong?"

**This phase is mandatory for all changes that touch multiple files, services, or configurations.** For single-line or trivial changes, a 10-second mental reflexion is sufficient.

## When to Reject

If any Phase 1 check fails → fix first, re-run this checklist.
If Phase 4 is incomplete → fix the docs, don't skip the cycle.
If Phase 5 reveals issues → start a new cycle, don't patch the closure.

## Anti-Patterns to Avoid

| Anti-pattern | Why it's wrong |
|---|---|
| "I tested it manually" | Manual = ad-hoc, not repeatable, no proof. Run the actual tool. |
| "It's just a small config change" | Small changes break prod too. Same checklist applies. |
| "Docs can come later" | Later = never. Update docs before end_change(). |
| "The hook didn't catch it" | The hook is syntax-level. You catch semantics here. |

## Quick Reference: Path Patterns by OS

| Purpose | Linux | macOS (arm64) | macOS (x86_64) |
|---------|-------|---------------|----------------|
| nginx config dir | `/etc/nginx` | `/opt/homebrew/etc/nginx` | `/usr/local/etc/nginx` |
| nginx sites dir | `sites-available/` | `servers/` | `servers/` |
| htpasswd file | `.hermes-htpasswd` | `.htpasswd` | `.htpasswd` |
| Service manager | `systemctl --user` | `launchctl` | `launchctl` |
| Package manager | `apt` / `yum` / `dnf` | `brew` | `brew` |

## Why This Exists

Without a pre-ship checklist, governance cycles get closed with half-verified work — tests skipped, docs stale, other agents unaware. The change-checklist is the quality gate that ensures every scored change is actually shippable.
