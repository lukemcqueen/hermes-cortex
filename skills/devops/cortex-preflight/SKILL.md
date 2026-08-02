---
name: cortex-preflight
description: >-
 Hermes Cortex supporting pre-flight checks — supplements Hermes default
 survey-before-action with repo-specific checks: git search, Hermes boundary,
 deployment verification.
version: 1.0.0
category: devops
author: Hermes Cortex
license: MIT
platforms: [linux, macos]
related_skills:
 - survey-before-action
 - change-checklist
 - agent-fundamentals
---

# Cortex Preflight — Supporting Pre-Flight Checks

## Purpose

Supplements the `survey-before-action` skill with checks specific to the Hermes Cortex repo. Run this **after** `survey-before-action` but **before** writing any code or making any changes.

## Checklist

### 1. Check git for missing files

`search_files()` only scans disk. If it finds nothing, the file may still exist in git (committed but not deployed):

```bash
# Search git history for the file
cd ~/hermes-cortex
git log --oneline --all -- "**/<pattern>*"

# View a file that exists in git but not on disk
git show HEAD:<path-to-file>
```

**Common scenario:** Script exists in the repo (`ops/scripts/manage/foo.py`) but was never deployed to `~/.hermes-cortex/scripts/foo.py`. Running `cortex-update.sh ` fixes this.

### 2. 🛡️ GOVERNANCE FILE WORKFLOW — ORCHESTRATORS ONLY

**This rule is for orchestrators only (Moses, Esther). Non-orchestrators: stop here — send an inbox message to Moses requesting a change to any of these files.**

If you ARE an orchestrator, hooks, enforcer plugin, and skills follow this rule:

1. **Fix the REPO SOURCE first** in `~/hermes-cortex/` — never the deployed copy
2. **Commit, push**, then run `cortex-update.sh --force-all` to deploy
3. **A fix applied to the deployed copy WILL be overwritten** on the next cortex-update

**Specific files (always fix repo source, never deployed copy):**
- `~/.hermes/plugins/governance-enforcer/__init__.py` → `plugins/governance-enforcer/__init__.py`
- `~/.hermes-cortex/scripts/pre-commit-score` → `ops/scripts/pre-commit-score`  
- `~/.hermes-cortex/hooks/pre-commit` → symlink to `scripts/pre-commit-score`
- `~/.hermes/skills/<category>/<name>/SKILL.md` → `skills/<category>/<name>/SKILL.md`
- All files in `~/.hermes-cortex/scripts/` with a `register()` entry in `cortex-update.sh`

**Non-orchestrators:** if you discover a bug in hooks, enforcer, or skills, send an inbox message to Moses with `🔧 GOVERNANCE: <what's wrong>`. Do not attempt to fix the deployed copy — the pre-commit hook and dogfood check will block you.

### 3. Hermes boundary check

Before editing any file, confirm it's ours to edit:

| File location | Action |
|---------------|--------|
| In `~/hermes-cortex/` | ✅ Ours — modify freely |
| In `~/.hermes/` AND in repo `skills/` | ✅ Ours — modify the repo copy, deploy |
| In `~/.hermes/` but NOT in repo | ❌ Hermes default — do NOT touch |
| In `~/.hermes-cortex/state/*` | ✅ Live config — modify directly |
| In `~/.hermes/config.yaml` | ✅ Live config — modify directly |

**Don't** modify Hermes default skills: (none — all repo skills under `skills/` are ours to maintain).

If you need to extend a Hermes default, create a **supporting skill** in the repo instead.

### 3. Verify deployed copies match repo

A source change in the repo is not deployed until `cortex-update.sh ` runs:

```bash
# Check if a script is registered for deployment
grep -n "register.*<script-name>" ~/hermes-cortex/ops/scripts/cortex-update.sh

# Check if it exists at the runtime path
ls -la ~/.hermes-cortex/scripts/<script-name>

# If missing, deploy
bash ~/hermes-cortex/ops/scripts/cortex-update.sh
```

### 4. Check what agent type you are

Some actions are agent-type specific. Check before proceeding:

```bash
# Agent name
echo "${AGENT_NAME:-$(hostname)}"

# Are you an orchestrator? Check for orch-* crons
cronjob action=list | grep "orch-"
```

| Agent type | Can do |
|------------|--------|
| orchestrator (Moses, Esther) | Fleet dispatch, bus operations, skill lifecycle |
| server-agent (Joseph, Kustos, Gisu) | Local maintenance, health reports |
| dev-agent (Titus) | Local reports, push-only bus |

### 5. Check for stale deploy references — EVERY deploy location

Before renaming or removing a file, check **every** location that could reference the old name. A single stale ref in an unchecked directory is a trust violation.

```bash
# Search ALL deploy locations — not just the obvious ones
for dir in \
 ~/hermes-cortex/ops/scripts/ \
 ~/hermes-cortex/ops/install/ \
 ~/hermes-cortex/ops/scripts/cortex_doctor/ \
 ~/hermes-cortex/hooks/ \
 ~/hermes-cortex/.hermes-cortex/ \  # skills, references, config
 ; do
 [ -d "$dir" ] && grep -rn "<old-name>" "$dir" 2>/dev/null
done
```

**Critical directories that are easy to forget:**
- `cortex_doctor/` — contains checks, expected cron lists, and remediation hints
- `hooks/` — pre-commit, pre-push scripts may reference service names
- `config/` — repo-owners.yaml, skills manifests
- `state/` — seen-file tracking (e.g., inbox-flag-seen)
- `manage/` — subdirectory scripts (stale-ref-watchdog, etc.)

A single rename can touch: `cortex-update.sh` (register + unregister), install scripts (create + uninstall arrays), `cortex-doctor/checks.py` (remediation hints), `check-system.sh` (service lists), `service-recovery.py` (service labels), and `cron-schedules.md`.

### 6. Verify other agents won't be affected

Before making structural changes (renaming scripts, changing bus protocol, modifying shared configs):

```bash
# Search all agent profiles
grep -rn "<changed-path>" ~/hermes-cortex/profiles/
grep -rn "<changed-protocol>" ~/hermes-cortex/AGENTS.md
```

## Anti-Patterns

- ❌ **Searching only disk, not git** — file may exist in repo but not deployed
- ❌ **Editing a Hermes default skill** — create a supporting skill instead
- ❌ **Claiming "file doesn't exist" without checking git** — wastes everyone's time
- ❌ **Changing only the repo source, not deploying** — other agents see the commit but the runtime doesn't change
- ❌ **Changing only the deployed copy, not the repo** — next cortex-update overwrites your changes

## Deployment Pitfalls — cortex-update.sh Side Effects

These are known side-effects of running `cortex-update.sh` (or `cortex-update.sh --force-all`). You must account for each one before and after deploy.

### Pitfall 1: SOURCE header breaks checksums

`cortex-update.sh` adds a SOURCE header to every deployed `.sh` and `.py` file. Since 2026-08-02 the header sits **below the shebang** (a header above it breaks direct `./script.py` execution):

```
#!/usr/bin/env python3
# SOURCE: ops/scripts/foo.py
# Do NOT edit this file — edit the source above and run: bash cortex-update.sh
```

This means the raw MD5 between the repo source and the deployed copy will always differ. The doctor's `_content_md5()` function strips this header before computing the hash. **Always use `_content_md5()` not `_md5()` on deployed paths** — otherwise every deployed file will falsely show a checksum mismatch.

### Pitfall 2: cortex-update.sh cleans the governance lock

`cortex-update.sh` runs `purge-stale-governance-locks.py` at the end of its run, which removes **every** `.governance-*.json` lock file — including the current session's lock. After a deploy, your lock will be gone. **Re-acquire with `begin_change()` after deploy** before making further changes.

### Pitfall 3: Skills-loaded marker gets stale from daemon sessions (FIXED)

> **FIXED (2026-08-01):** per-session marker files made this entire pitfall
> obsolete. `cortex-update.sh` re-deploying the enforcer plugin no longer
> invalidates your session's skills proof — your marker file at
> `state/skills-loaded/<session-id>` survives the plugin reload, so write tools
> keep working after a cortex-update. (Pre-fix behaviour, kept for history: the
> redeploy reset the plugin's in-memory tracking and the shared marker was
> treated as invalid, forcing a reload of the 8 always-skills after every
> cortex-update.)

The skills-loaded proof lives at `~/.hermes-cortex/state/skills-loaded/<session_id>` —
**one file per session** (since 2026-08-01). Each session that loads all 8
always-section skills auto-creates its OWN marker via `_auto_create_skills_marker()`.
Concurrent sessions (telegram, cli 1, cli 2 on one server; cron jobs; background
subagents) can never overwrite each other's proof, because they never share a
file. The governance enforcer plugin blocks write tools until THIS session's
marker is valid.

**Why per-session files:** the pre-2026-08-01 single shared
`~/.hermes-cortex/state/.skills-loaded` file was raced by every concurrent
session — any session loading skills overwrote the one file with its own ID,
blocking the other sessions' write tools mid-task (observed 6× in one session).
The daemon guard (cron_/bg_), subagent guard, and P1-A sticky-marker-per-lock
rule were all patches on that shared file; per-session files remove the shared
state entirely, so the whole guard class was deleted.

**Result:** each session's marker is created when it loads all 8 skills and
persists for the session. No session can take another's marker away.

**Recovery if write tools are blocked:**
1. Load all 8 always-section skills via `skill_view()` (the marker auto-creates)
2. Write tools unblocked

### Pitfall 4: Hook symlinks prevent drift

Deployed hooks (`~/.hermes-cortex/hooks/`) are **absolute symlinks** created by
`install_precommit_hook()` in `cortex-update.sh`. Each hook points to its source
script in `~/.hermes-cortex/scripts/`:

| Deployed hook | Symlink target |
|---|---|
| `hooks/pre-commit` | `scripts/pre-commit-score` |
| `hooks/pre-push` | `scripts/pre-push-pull` |
| `hooks/post-commit` | `scripts/post-commit-audit` |
| `hooks/post-push` | `scripts/post-push-audit` |
| `hooks/post-merge` | standalone (registered via `register()`) |

When the symlinks are correct, updating the source script in `ops/scripts/` and
running `cortex-update.sh` automatically propagates to the deployed hook. If a
hook is a standalone file copy instead of a symlink, it will drift from the repo
source and the doctor will flag it.

**Repo `.hermes-cortex/hooks/` directory:** Contains only a `README.md`.
The actual hook deploy is handled by `cortex-update.sh` at runtime —
the repo directory tracks documentation, not deployable files.

The doctor checks: (1) deployed hook exists, (2) it's a valid symlink to an
existing target, (3) content matches the repo source.

### Pitfall 5: PENDING cycles accumulate

Every `begin_change()` creates a new cycle in the loop-governance DB. When `cortex-update.sh` cleans the governance lock (Pitfall 2) and you re-acquire with `begin_change()`, the old cycles stay in `PENDING` state — they are never automatically scored. If you don't manually score them before `end_change()`, the doctor will report unscored cycles as a governance leak. **Score all PENDING cycles via `feedback_accept` or `feedback_override` before calling `end_change()`.**

| Check | What to do |
|-------|-----------|
| SOURCE header | Use `_content_md5()` on deployed paths |
| Lock cleaned | Re-acquire lock with `begin_change()` |
| Stale skills marker | Reload the 8 always skills — per-session marker (`state/skills-loaded/<session-id>`) auto-creates |
| __pycache__ stale bytecode | Fixed in hermes-plugin-lock (auto-clears on unlock) |
| Drift prevention | Verify hooks are relative symlinks |
| PENDING cycles | Score all before `end_change()` |
