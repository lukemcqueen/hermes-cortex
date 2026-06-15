---
name: weekly-auto-fix
description: "After the weekly opportunity scan identifies issues, run auto-fix patterns — git pull, branch cleanup, Docker restart, permission fixes, disk cleanup. Reduces manual intervention for known recurring problems."
version: 1.0.0
author: Moses
license: MIT
metadata:
  hermes:
    tags: [cron, automation, maintenance, git, docker, security]
    related_skills: [cron-engineering, public-contribution]
---

# Weekly Auto-Fix

## When to Use

Load this skill when:
- Setting up or modifying the weekly opportunity scan cron job
- A cron agent needs to auto-fix issues it discovers
- You want the scan-report-fix pattern instead of scan-only

## How It Works

The cron runs in three phases:

```
[Phase 1: Scan]  ← LLM-driven, finds issues across git/docker/perms/disk
    ↓
[Phase 2: Fix]   ← Agent attempts fixes, then runs companion script
    ↓
[Phase 3: Report] ← Compact summary: what was fixed vs needs attention
```

## Setup

### 1. Deploy the companion script

Copy `scripts/weekly-auto-fix.py` from the hermes-cortex repo to `~/.hermes/scripts/`:

```bash
cp hermes-cortex/scripts/weekly-auto-fix.py ~/.hermes/scripts/weekly-auto-fix.py
```

The script handles known fix patterns:
- **git-pull** — pulls upstream changes for repos behind origin/main
- **branch-delete** — removes local branches whose remote tracking refs are gone
- **permissions** — chmod 600 on world-readable outputs, 644 on executable pids
- **disk-cleanup** — cleans bun cache if >100MB
- **docker-restart** — restarts unhealthy/restarting containers

### 2. Create or update the weekly scan cron

```bash
hermes cron update <job-id> \
  --prompt "$(cat << 'PROMPT'
You are Moses. This is your weekly opportunity scan with auto-fix.

## Phase 1: Scan

Check ~/brain/*/ and gbrain for incomplete tasks, stale branches, or new ideas. Also check:
- Git status (behind origin/main?)
- Docker container health (restarting/unhealthy?)
- File permissions (world-readable files?)
- Disk usage (large caches?)
- Cron job errors

## Phase 2: Auto-Fix

After identifying issues, attempt to fix them:

**Git fixes:** `git pull --rebase --autostash` if behind. Delete stale branches. Merge ready PRs with `gh pr merge --squash`.

**Docker fixes:** `docker restart <name>` for unhealthy containers.

**Permission fixes:** `chmod 600 ~/.hermes/cron/output/_scorer_summary.json`, `chmod 644 ~/.hermes/gateway.pid`.

**Companion script:** Run `python3 ~/.hermes/scripts/weekly-auto-fix.py --verbose` as a safety net.

## Phase 3: Report

Output max 3 items under 200 chars each. For each, say FIXED or needs manual attention.

If everything was fixed automatically: `✅ All fixed: [items]`
If nothing needed fixing: exit silently.
PROMPT
)" \
  --schedule "0 8 * * 1" \
  --deliver origin
```

### 3. Add toolsets

The cron needs `terminal` and (optionally) `web`:

```bash
# Already set via cronjob tool; verify with:
# cronjob action=list | grep weekly-scan
```

## Fix Patterns

| Pattern | Detection | Fix | Validation |
|---------|-----------|-----|------------|
| Git behind upstream | `git rev-list --left-right --count HEAD...origin/main` | `git pull --rebase --autostash` | Re-run count check |
| Stale local branches | `git branch -vv` (detect `: gone]`) | `git branch -D <name>` | Re-run branch list |
| Docker unhealthy | `docker ps` (status contains "unhealthy"/"restarting") | `docker restart <name>` | Re-run `docker ps` |
| World-readable scorer | `stat -f %p` shows 644 | `chmod 600` | Verify mode |
| Executable pid file | `stat -f %p` shows 755 | `chmod 644` | Verify mode |
| Large bun cache | `du -sh ~/.bun/install/cache` >100MB | `rm -rf ~/.bun/install/cache` | Verify dir gone |

## Pitfalls

- **Don't merge PRs during a rebase conflict.** If `git pull --rebase` fails, report it — don't force push.
- **Don't delete protected branches** (main, master, develop). The script skips them.
- **Docker restart may cause brief downtime.** Only restart containers clearly marked "unhealthy" or "restarting" — not healthy ones.
- **The companion script is a safety net, not the primary fixer.** The LLM agent should attempt the reasoning-heavy fixes (git merge, gbrain repair) directly.
- **If nothing was broken, stay silent.** The watchdog pattern applies — the user should not hear from a cron that found nothing to do.
