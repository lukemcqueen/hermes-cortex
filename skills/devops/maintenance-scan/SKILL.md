---
name: maintenance-scan
description: >-
  Systematic system health survey run proactively when the user gives an
  open-ended directive to "find work" or "look for issues". 9-step
  sequential scan: inbox → memory → doctor → crons → git → system →
  analyze → fix → verify.
version: 1.0.0
category: devops
author: Hermes Cortex
license: MIT
platforms: [linux]
related_skills:
  - cortex-preflight
  - survey-before-action
  - change-checklist
---

# Maintenance Scan — Proactive System Survey

## Trigger

The user says any of:
- "look for work that needs to be done"
- "find what needs doing"
- "scan for issues"
- "proactive maintenance"
- "find work"
- Any open-ended directive without a specific task

## When NOT to use

- The user already specified a task → route with `agent-flow`
- The user is asking a question or requesting research → use `agent-flow` / `research`
- The user explicitly said "don't fix anything" or "read-only"

## The 9-Step Scan

Run in order. Each step is pass/fail — continue unless blocked.

### Step 1: Inbox

Check the agent bus for pending fleet messages BEFORE touching any tool or running any command. Other agents may have sent requests, reports, or alerts:

```bash
# Queue overview
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -t -c \"
  SELECT queue_name, state, COUNT(*) as count
  FROM bus.messages
  GROUP BY queue_name, state
  ORDER BY queue_name, state;
\""
```

Focus on `inbox_orchestrator` pending messages — those are requests from fleet agents that need attention. Common patterns:
- **Learning Reports**: Routine — handled by orch-skill-lifecycle cron (04:00 daily). Note and move on.
- **CRON requests** from non-orchestrator agents: AUTO-ACT (create or update the requested cron).
- **FIX_REQUEST / FIX_RESULT**: Fleet update round-trips — verify completion, escalate if stalled.
- **EXEC results**: Command output from fleet agents — correlate with outstanding dispatch.

Do NOT archive inbox messages here — the scan is discovery only. Actual processing happens via cortex-bus crons or in-session handling.

### Step 2: Memory & Session

Check what you already know BEFORE querying any external system:

1. **Memory** — `memory()` your persistent notes. Do you already know the schema, patterns, or answers you're about to look up?
2. **session_search()** — 3+ queries about the domain. Was this discussed in a recent session?
3. **Skills** — `skills_list()` for the domain, `skill_view()` on any matching skill.

**Signal:** Any time you're about to write `docker exec psql`, `curl`, `grep`, or `search_files()` — pause and ask: "Is this in my memory or session history?" If yes, check there first. Going to external sources before checking your own knowledge is the most common wasted-turn pattern.

### Step 3: Doctor
```
python3 ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py --quiet
```
Record: pass count, fail count, warn count. Note every ❌ and ⚠️ line.
Exit 0 = clean. Exit 2 = failures present.

### Step 4: Crons
```
cronjob(action='list')
```
Check every job for `last_status: failed`. Flag any paused without reason (`state: paused` with no `paused_reason`).

### Step 5: Git
```
cd ~/hermes-cortex && git status --short
```
Empty = clean. Non-empty = investigate whether changes are intentional or stale.

### Step 6: System
```
df -h / | tail -1        # disk %
free -h | head -2        # RAM
uptime                   # load
```
Hard thresholds: disk >80% used, available RAM <2GiB, load >CPU cores × 2 merit alert (document but don't fix without user approval).

### Step 7: Analyze
Cross-reference findings. Common patterns from the doctor:
- `❌ AGENTS.md (<repo>)` → doc stale, review recent changes, update reference tables
- `⚠️ Symlinks` → broken `.governance-generic.json` → remove stale lock reference
- `⚠️ Repo clean` → uncommitted changes from prior work
- `ℹ️ Extra crons` → informational, ignore
- `➖ Bus E2E test` → optional test, ignore

### Step 8: Fix
Fix each issue without asking (Principle 2 — Be Proactive). Only escalate:
- Data loss (rm -rf, DROP TABLE)
- Privilege escalation
- Service restart affecting production traffic

Known doctor-fix patterns:
- **Symptom signature (2026-08-05):** several LLM crons die with `RuntimeError: No reply: the turn was stopped because session storage could not be written (the transcript would have been lost on restart)... often a full disk`. Usually NOT the disk — `df` shows free space while `~/.hermes/state.db` has ballooned (observed 3.6 GB) with corrupt FTS shadow tables. Doctor neighbours: `Cron status (<name>) — last run: error` + `Stale lock (.governance-cron_*.json) — heartbeat expired Ns ago`.
- **Confirm before repairing (read-only, no lock):** `python3 -c "import sqlite3,os; c=sqlite3.connect('file:'+os.path.expanduser('~/.hermes/state.db')+'?mode=ro', uri=True); print(c.execute('PRAGMA quick_check').fetchone()[0])"` — `btreeInitPage() returns error code 11`, `Rowid ... out of order`, `2nd reference to page ...` = corrupt → `hermes sessions repair` (or `--check-only` to probe). After repair: remove the stale cron lock (`rm -f` per doctor remediation) and re-run the failed crons via `cronjob action='run'` so the scheduler's `last_status` refreshes.
- `state.db FTS write corruption` (doctor issue #1) → `hermes sessions repair` — backs up first and rebuilds the FTS index, but is **slow on a large DB (can exceed 5 min)**: run it with `background=true` and poll, don't block on it (2026-08-05). **⚠️ If repair FAILS with `database disk image is malformed`** (btree corruption, not just FTS), a backup is preserved at `state.db.malformed-backup-<ts>`; verify recoverability with `hermes sessions recover --source <backup> --inspect-only`, then rebuild: `hermes sessions recover --source <backup> --output ~/.hermes/state.db.recovered --allow-partial` (offline, non-destructive; source+WAL snapshotted first). The recovered DB is NOT auto-swapped — the active DB is only replaced with the gateway stopped (swap script: stop gateway → `mv state.db state.db.corrupt` → `mv state.db.recovered state.db` → start gateway; agents cannot restart the gateway — hand the swap to the host operator). Verified 2026-08-05 (live 4.2 GB db).
- `nginx -t` failures mentioning `open() "/run/nginx.pid" failed (13: Permission denied)` when run as non-root are a **pid-file permission artifact, not a config error** — validate with `sudo nginx -t` instead (2026-08-05).

For docs: edit → sync (`cp repo_path ~/.hermes/`) → commit → push → verify.

### Step 9: Re-verify
```
python3 ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py --quiet
```
Confirm: 41 pass · 0 warn · 0 fail — or better than baseline.

## Reporting Format

```
Found {N} issues:
  ❌ {issue} — {what was done}
  ❌ {issue} — {what was done}
System healthy: disk {X}%, RAM {Y}Gi avail, load {Z}
Doctor now {HEALTHY|WARNING|PASS} ✅
```

## Bonded Rule

Do NOT ask "what should I work on?" after "look for work". Run the scan first.
