---
name: orch-weekly-auto-fix
description: "After the weekly opportunity scan identifies issues, run auto-fix patterns — git pull, branch cleanup, Docker restart, permission fixes, disk cleanup — then verify each fix succeeded. Reduces manual intervention for known recurring problems."
version: 1.1.0
author: Hermes Cortex
license: MIT
metadata:
  hermes:
    tags: [cron, automation, maintenance, git, docker, security]
    related_skills: [cron-engineering, public-contribution]
---

# Weekly Auto-Fix (with Verification)

## When to Use

Load this skill when:
- Setting up or modifying the weekly opportunity scan cron job
- A cron agent needs to auto-fix issues it discovers
- You want the scan-fix-verify-report pattern instead of scan-only

## How It Works

The cron runs in four phases:

```
[Phase 1: Scan]  ← LLM-driven, finds issues across git/docker/perms/disk
    ↓
[Phase 2: Fix]   ← Agent attempts fixes, then runs companion script
    ↓
[Phase 3: Verify] ← Re-check each condition post-fix; PASS/FAIL/WARN per check
    ↓
[Phase 4: Report] ← Compact summary: fixed & verified vs needs attention
```

## Setup

### 1. Deploy the companion script

Copy `scripts/orch-weekly-auto-fix.py` from the hermes-cortex repo to `~/.hermes/scripts/`:

```bash
cp hermes-cortex/scripts/orch-weekly-auto-fix.py ~/.hermes/scripts/orch-weekly-auto-fix.py
```

The script handles known fix patterns with built-in verification:
- **git-pull** — pulls upstream changes, then verifies behind count is 0 and no conflicts
- **branch-delete** — removes stale local branches, then verifies they're gone from git branch
- **permissions** — chmod 600/644, then stats the file to confirm
- **disk-cleanup** — cleans bun cache if >100MB, then verifies dir is gone or under threshold
- **docker-restart** — restarts unhealthy/restarting containers, then checks docker ps for healthy status

### 2. Create or update the weekly scan cron

```bash
hermes cron update <job-id> \
  --prompt "$(cat << 'PROMPT'
You are Moses. This is your weekly opportunity scan with auto-fix and verification.

## Phase 1: Scan

Check repos, Docker containers, system files, and cron jobs for issues:
- Git status (behind origin/main? conflicts?)
- Docker container health (unhealthy/restarting?)
- File permissions (world-readable outputs, executable pids?)
- Disk usage (large caches?)
- Cron job errors

## Phase 2: Auto-Fix

Attempt fixes for each issue found:

**Git fixes:** `git pull --rebase --autostash` if behind. Delete stale branches. Merge ready PRs.

**Docker fixes:** `docker restart <name>` for unhealthy containers.

**Permission fixes:** `chmod 600` / `chmod 644`.

**Companion script:** `python3 ~/.hermes/scripts/orch-weekly-auto-fix.py --verbose` as safety net.

## Phase 3: Verify

For each fix, verify the fix actually worked:
- Git: behind count is 0, no conflict markers in git status
- Docker: container shows "Up" or "healthy" in docker ps
- Permissions: stat confirms correct mode
- Disk: cache dir is removed or under threshold

## Phase 4: Report

- ✅ FIXED if fix + verification passed
- ❌ FAILED if fix or verification failed
- Exit silently if nothing needed doing
PROMPT
)" \
  --schedule "0 8 * * 1" \
  --deliver origin
```

## Fix & Verify Patterns

| Pattern | Detection | Fix | Verification |
|---------|-----------|-----|--------------|
| Git behind upstream | `git rev-list --left-right --count HEAD...origin/main` | `git pull --rebase --autostash` | Re-check behind count = 0, no `UU`/`AA`/`DD` in `git status --short` |
| Stale local branches | `git branch -vv` (detect `: gone]`) | `git branch -D <name>` | Branch absent from `git branch` output |
| Docker unhealthy | `docker ps` (status "unhealthy"/"restarting") | `docker restart <name>` | `docker ps` shows "Up" or "healthy" after 3s wait |
| World-readable scorer | `stat -f %p` shows 644 | `chmod 600` | `stat` shows 600 |
| Executable pid file | `stat -f %p` shows 755 | `chmod 644` | `stat` shows 644 or 600 |
| Large bun cache | `du -sh ~/.bun/install/cache` >100MB | `rm -rf` | Dir gone or <100MB remaining |

## Companion Script Output

The script produces structured JSON with verification results:

```json
{
  "actions_taken": ["git-pull: pulled 3 commit(s) from origin/main"],
  "verify_results": [
    {"check": "git-pull", "status": "PASS", "detail": "up to date, no conflicts"},
    {"check": "perms-scorer", "status": "PASS", "detail": "already 600"},
    {"check": "perms-pid", "status": "FAIL", "detail": "mode is 0o755"}
  ],
  "summary": {"fixed": 1, "passed": 2, "failed": 1, "warned": 0}
}
```

On success with nothing to do, outputs empty JSON `{}` (silent — watchdog pattern).

## Pitfalls

- **Don't merge PRs during a rebase conflict.** If `git pull --rebase` fails, report it — don't force push.
- **Don't delete protected branches** (main, master, develop). The script skips them.
- **Docker restart may cause brief downtime.** Only restart containers clearly marked "unhealthy" or "restarting" — not healthy ones.
- **The companion script is a safety net, not the primary fixer.** The LLM agent should attempt reasoning-heavy fixes (git merge, gbrain repair) directly, then use the script for mechanical checks.
- **If nothing was broken, stay silent.** The watchdog pattern applies — the user should not hear from a cron that found nothing to do.
- **Verification adds latency.** Docker verification waits 3s; git verification runs 2 extra commands. This is fine for a weekly cron, but don't add heavy verifications to high-frequency crons.
