---
name: proactive-system-scan
version: 1.0.0
category: devops
description: >-
  Multi-faceted system scan to discover work, issues, and improvement
  opportunities when the user gives an open-ended request like "find
  work" or "look for things that need doing." Runs doctor, cron health,
  git status, system health, and governance checks in parallel.
author: Moses (Hermes Cortex)
license: MIT
platforms: [linux, macos]
---

# Proactive System Scan — Finding Work Without a Task

When the user asks you to "find work," "look for issues," or "what needs
doing," don't wait for a specific task — survey the system across multiple
dimensions and report what you find.

This is different from `survey-before-action` (check before modifying)
and `cortex-preflight` (check before a known change). This is a discovery
scan to identify opportunities when no change is planned yet.

## The Scan Sequence

Run these checks **in parallel** (no data dependencies between them):

### 1. Doctor status
```bash
python3 ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py --quiet
```
Signals: ❌ must-fix, ⚠️ should-fix, ℹ️ informational.

**Common doctor failures and fixes:**

| Failure | Root cause | Fix |
|---------|-----------|-----|
| `❌ AGENTS.md (<repo>)` | `check_dev_repo_agents()`. File mtime >1 day older than latest git HEAD timestamp | `git diff HEAD~10..HEAD --name-only`, merge new patterns, `touch AGENTS.md` |
| `⚠️ Symlinks` | Broken `.governance-generic.json` → stale session lock | `rm <broken-symlink>` |
| `❌ Repo sync` | Local behind origin/main | `git pull --rebase` |
| `❌ Hook: pre-commit (content)` / `❌ Checksum: pre-commit` | `.hermes-cortex/hooks/pre-commit` and `ops/scripts/pre-commit-score` out of sync | `cp ops/scripts/pre-commit-score .hermes-cortex/hooks/pre-commit && cp ops/scripts/pre-commit-score ~/.hermes-cortex/hooks/pre-commit` |
| `❌ Deploy sync` | Repo ahead of deployed state after push | Resolves on next automated cortex-update (nightly cron) or run `cortex-update.sh --force-all` (close governance lock first — the deploy cleans it) |

### 2. Cron health
```python
cronjob(action='list')
```
Check each job for: `last_status` not "ok", paused without reason, stale
`next_run_at`, or missing expected jobs (compare against install script
uninstall arrays).

### 3. Git status
```bash
cd ~/hermes-cortex && git status --short
git log --oneline origin/main..HEAD   # unpushed commits
```

### 4. System health
```bash
df -h / | tail -1          # disk
free -h | head -2           # memory
uptime                      # load + uptime
```

### 5. Governance health
Use `mcp__loop_governance__cycle_stats()` — look for PENDING cycles
(unreviewed), high repeat counts on a task (stuck loops), or low
feedback rates.

### 6. Bus queues (orchestrator only)
Check for stuck messages in bus queues (via PGMQ tooling or bus script
inspection).

## Reporting

Organize by severity:

```
🔴 Must Fix — <doctor ❌ failures or critical issues>
🟡 Should Fix — <doctor ⚠️ warnings, minor drift>
🟢 Already Good — <key systems confirmed healthy>
ℹ️ Notes — <observations, trends, work-in-progress>

## Action Taken
- <what was already fixed>
- <what needs user input>
```

## When to Use

- User says "find work" / "look for issues" / "what needs doing"
- Session starts with a vague/open-ended request
- Before starting a new project phase — know the baseline
- After `git pull` or `cortex-update` — verify nothing broke

## Anti-Patterns

- ❌ Scanning only one subsystem — misses systemic issues
- ❌ Reporting without offering to fix — be proactive
- ❌ Skipping because "everything was fine yesterday"
- ❌ Fixing one thing and stopping when others remain
- ❌ Not running the doctor — it catches what you'd miss manually
