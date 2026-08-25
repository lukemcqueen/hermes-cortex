---
name: governance-lock-lifecycle
version: 1.0.0
category: devops
description: "Use when blocked after cortex update or end_change rejects."
author: Hermes Cortex curator
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [governance, lock, cortex-update, loop-governance, deploy]
    related_skills: [loop-governance, cortex-deployment-sync, cortex-preflight, two-hard-rules]
---

# Governance Lock Lifecycle During Deploy Operations

**Class of task:** any session that runs `cortex-update.sh` (or any deploy that triggers `purge-stale-governance-locks.py`), then hits `GOVERNANCE LOCK REQUIRED` on a subsequent tool call, or finds `end_change` rejecting with "no scored cycle". Also covers the "pull latest → update → doctor → fix" loop.

## The Core Mechanic

`cortex-update.sh` runs `purge-stale-governance-locks.py` at the **END of EVERY run** — it removes **every** `.governance-*.json` lock file, **including your active session's lock**. This is by design (Pitfall 4 in `cortex-deployment-sync`), but the blast radius is bigger than most agents expect:

1. **ALL terminal is gated, not just writes.** The enforcer's `GOVERNANCE LOCK REQUIRED` fires on ANY `terminal()` call without an active lock — even a read-only `grep` of the update log. `ls`, `grep`, `cat`, `git status` all blocked until you re-acquire.
2. **`read_file` / `search_files` / `skill_view` are NOT gated.** These are the escape hatch for inspecting output between the purge and your re-acquire.
3. **Each re-acquire creates a NEW pending cycle** under the same `task_id`. Two re-acquires → three pending cycles total (original + 2). All must be scored before `end_change()` or it rejects.

## The Working Sequence (verified 2026-08-03)

```text
begin_change(task_id="pull-latest-cortex-update")     # cycle #1
git pull --rebase --autostash origin main
cortex-update.sh > /tmp/update-full.log 2>&1          # redirect UNDER the lock
                                                      #   ← purge fires, lock GONE
# terminal() now blocked — use read_file on /tmp/update-full.log
check_lock → active: false                            # confirm
begin_change(same task_id)                            # cycle #2 — REQUIRED before more terminal
... fix work ...
begin_change(same task_id)                            # cycle #3 if purged again
...
cycle_query(task_id=...)                              # lists ALL pending cycles
feedback_accept(id=N1, note=...)                      # score EVERY one
feedback_accept(id=N2, note=...)
feedback_accept(id=N3, note=...)
end_change(task_id=...)                               # only now succeeds
```

## Pitfalls

### Pitfall 1: Redirect capture must happen UNDER the lock

`cortex-update.sh > /tmp/log 2>&1` is fine **while the lock is active** (the redirect is the point — it survives the purge). But a `;`-chained command like `cortex-update.sh > log 2>&1; grep ...` can be classified as a write by the enforcer and blocked **before** it runs if the lock was already purged. Pattern to avoid: run the update, then try to grep the log in the same command — the grep half dies.

### Pitfall 2: `| tail -60` truncates the embedded doctor report

The update's output embeds the full doctor run (475+ lines: 268 pass · 9 warn · 2 fail · 3 info). `tail -60` only shows the summary + REQUIRED ACTIONS, hiding WHICH checks failed. Always redirect to a file and `read_file` the whole thing — you need the per-check ⚠️/❌ lines to fix anything.

### Pitfall 3: Score ALL pending cycles, not just the newest

`end_change(task_id)` rejects with "no scored cycle" if ANY cycle for that task is still PENDING. `cycle_query(task_id)` returns them all — iterate and `feedback_accept` each ID before closing. This is the #1 cause of the "end_change rejected" confession.

### Pitfall 4: Doctor remediation hints may not match the real CLI

The doctor's REQUIRED ACTIONS print commands like `Check: hermes cron logs --name agent-...` — but `logs` is NOT a valid `hermes cron` subcommand and `runs` rejects `--name`. Valid subcommands: `list, create, add, edit, pause, resume, run, remove, rm, delete, status, runs, history, tick`. Pass the cron name **positionally** (`hermes cron runs <name>`), no `--name` flag. Don't burn cycles re-trying the doctor's literal suggestion.

### Pitfall 5: The survey gate fires on ANY `.py` write, even throwaway

Writing `/tmp/inspect.py` triggers the domain-skill gate: "write blocked until `test-driven-development` loaded". Loading it satisfies the gate — it does NOT obligate a TDD cycle for a disposable inspection script (TDD's own exceptions cover throwaway prototypes). State this explicitly ("gate satisfied — disposable script, no test cycle") so the user isn't confused about why TDD was loaded.

## Verification

- `check_lock` confirms the purge (active: false) — expect this after every update run
- `cycle_query` shows no PENDING cycles before `end_change`
- `end_change` returns success (no rejection)
- Doctor overall line eventually shows the reduced warn/fail counts


## Related (user-owned, may need `hermes curator adopt`)

- `cortex-deployment-sync` — deploy mechanics, invocation forms, immutable-file pitfalls
- `cortex-preflight` — pre-flight checks + cortex-update side-effect table
- `loop-governance` — scoring internals, lock-lifecycle race history
