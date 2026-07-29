---
name: cortex-preflight
description: >-
 Hermes Cortex supporting pre-flight checks — supplements Hermes default
 survey-before-action with repo-specific checks: git search, Hermes boundary,
 deployment verification.
version: 1.0.0
category: devops
author: Moses (Hermes Cortex)
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

### 2. Hermes boundary check

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
