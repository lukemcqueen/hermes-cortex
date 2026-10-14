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
sg docker -c "docker exec mycortex-postgres psql -U mycortex -d mycortex -t -c \"
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
- `⚠️ Repo clean` → establish WHAT is uncommitted before assigning it an owner. Several tracked
  `docs/evidence/` files (`briefings/*`, `gateway-suite-results.txt`, and the drift detector's own
  `skill-drift-parity.txt`) are REWRITTEN BY TEST RUNS and by the tools, so a dirty set of exactly
  those is a byproduct of a suite run — not a peer's edit and not abandoned work. Prove it by
  running the suite in a clean worktree of HEAD: the same files come back dirty there with no
  session involved. For anything else, `git log -1 --format='%an %ae' -- <path>` gives authorship,
  and another session's files are never committed, reverted or stashed on the strength of a dirty
  listing alone.
- `ℹ️ Extra crons` → informational, ignore
- `➖ Bus E2E test` → optional test, ignore

### Step 7b: When the FINDING is wrong — the check may be the defect

A doctor/watchdog line is evidence about a CHECK as much as about the host. Before editing
anything to satisfy a finding, confirm the finding is true; the fix then belongs to the CHECK, in
the same cycle, with a test that fails before and passes after.

- **A check that cannot SEE its input reports the input as missing.** A scan that iterates one
directory non-recursively, or one tree while the subjects live in three, produces
"zero consumers / not found" for healthy subjects. Widen the scope to where the subjects actually
live, and **exclude the checker's own package** — a check whose source NAMES every subject it
looks for will otherwise certify itself.
- **A mention is not a use.** Require the READ form (`get_model("VAR")`, `os.environ["VAR"]`,
  `$VAR`) rather than the bare name, or a docstring that documents a variable counts as a
  consumer; likewise require an INVOCATION form (an argv element, a PATH candidate list, a symlink
  map) rather than any line containing the tool's name, or comments, help strings and `echo` text
  count as wiring. Prose that merely names the thing is the noisiest false positive in this class.
- **A "legacy / old / unused" label must be earned by looking for who still uses it.** A CLI that
  a commit hook resolves from PATH and hard-blocks without, or that an auditor shells out to, is
  wired in — deleting it on the check's advice breaks a live path. Report the consumers; keep the
  "leftover" wording only for a tool nothing invokes.
- **The printed `Fix:` must be runnable, and its subject must be what the check claims.** Verify
  the suggested path RESOLVES (a fix string built from a bare filename can render a path that does
  not exist), and that the target really is the kind of thing being judged: an empty `.git/`
  DIRECTORY is not a repository (its `--commit` fix cannot run), and a git WORKTREE of the repo
  under check is that repo on another branch, not a separate dev repo.
- **Never manufacture a fix for a true finding.** "Defined but unused" can be accurate for a
  documented reserved variable, and removing the definition flips the check to a WARN (not
  defined) — report it as a true positive and name the two real options (wire a consumer, or drop
  it from the config) instead of silencing it. When you DO wire the consumer, it must read the
  variable in a form the scan recognises (`get_model("VAR", …)`, `os.environ["VAR"]`, `getenv`,
  `$VAR`): hiding the read inside a new helper of your own (`my_resolver("VAR", …)`) leaves the
  finding intact because the scanner sees only the helper's name — have the consumer call the
  established read form and hand the resolved value to the guard. Same class, one level up: a
  value that must satisfy an HTTP endpoint (`provider/model`) needs a guard that falls back to the
  served default LOUDLY on a bare id, because the variable is per-host `.env` and another host
  still carries the old shape.
- **An INFO that the check can only ever REPORT is a finding nobody can act on — resolve the
  underlying DATA, not the message.** Where the condition is rows in a store (cycles closed by
  an older code path, records with no reason recorded), ship a committed tool that fixes the data:
  `--apply` with a dry-run default, idempotent, its own exit code for "could not verify", an entry
  in the deploy map, and a test that drives it both ways. Prove it live RED→GREEN (the dry run
  names the rows; the apply reports zero remaining), never by deleting or widening the check.
- **Never rename a config value to silence a warning you have not reproduced.** Confirm the NEW
  value both stops the warning AND is accepted by the resolver that actually wires the feature.
  If both candidate names warn in-process, the divergence is in the checker (classically a
  session-time validator that accepts less than the resolver the feature goes through); the rename
  buys nothing and diverges from the platform convention, so REVERT it and report the checker.
  When that checker lives in a tree the operator has excluded from patching, reporting is the
  whole fix — do not edit code you were told not to touch.
- **Prove the tightened warning BOTH ways** — it must still fire on the case it exists for and go
  silent on the case that was noise (see `change-checklist` Phase 1.5).

### Step 8: Fix
Fix each issue without asking (Principle 2 — Be Proactive). Only escalate:
- Data loss (rm -rf, DROP TABLE)
- Privilege escalation
- Service restart affecting production traffic

Known doctor-fix patterns:
- **`⚠️ MCP wiring (<server>) — registered against the HERMES venv`** → re-register against the
  fleet venv, keeping the deployed script paths as `--args`. `hermes mcp add` is INTERACTIVE: it
  asks `Enable all N tools?` and with stdin closed it prints `Cancelled.` and writes NOTHING while
  the `remove` before it already succeeded — so a non-interactive remove/add loop empties
  `mcp_servers:` with every command exiting 0. Answer on stdin (`printf 'y\n' | …`), back the
  config up first, and verify by reading the block back plus the wiring audit. Full recipe:
  load the `mcp-health-monitoring` skill and read its registration runbook
  (`skill_view('mcp-health-monitoring', file_path='references/mcp-registration-runbook.md')`).
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
