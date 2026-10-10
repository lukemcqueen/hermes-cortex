---
name: governance-lock-lifecycle
version: 1.1.0
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

## Guarantees (2026-10-02) — the unlock can no longer outlive the run

The deploy unlocks each immutable enforcement file before overwriting it. Two
guarantees make a leftover unlocked state self-correcting:

1. **Relock on error.** `cortex-update.sh` installs `_relock_enforcement` as an
   `EXIT` trap — and `cortex-dogfood.sh` has its own, so the mandated pre-push
   gate does not depend on a CHILD script's trap for a security property. The
   relock runs on success, on error and on signal alike; a FAILED deploy no
   longer leaves the gate tamperable. Verified by failing a deploy on purpose
   (bad `CORTEX_DEPLOY_HOME` → rc=1) and watching all nine files come back
   `----i---------e-------`.
2. **Relock after inactivity.** `agent-remediate-apply.py` (no_agent, every
   10 min) self-heals at the top of every cycle, probing
   `hermes-plugin-lock status` FIRST so the already-locked case costs one
   `lsattr` and no sudo. `cortex_doctor --fix` relocks on a failing
   `Immutable:` check as well.

Consequences for an agent who finds a missing `i` flag: it is a **symptom, not a
task**. Wait one cycle, or run `sudo -n hermes-plugin-lock lock`. Do NOT hand-lock
individual files, and never "fix" it by weakening the check.

### Pitfall 6: A cycle whose remaining deliverable is blocked by a THIRD PARTY has no sanctioned exit

The close gate scores complexity over the lock window and refuses to release the lock while a
sufficiently complex change is unclosed. That is correct when the work is incomplete — but when the
ONLY thing left is something you are forbidden to do (merge over another session's uncommitted
files, edit a generated security artifact, or produce an authorization record that lives in the
operator's own chat), the gate refuses forever, and each `rereview_change` is a fresh sampling call
that returns new findings rather than closure. Two rules follow:

- **Do not re-roll the reviewer.** Once a finding's remedy is impossible or contradicts the
  operator's explicit instruction, state that once with the evidence and stop: repeated re-reviews
  burn tokens and add findings without changing the blocker.
- **Record the blocker instead of forcing a close.** `record_issue` keeps it tracked (give it a
  blocker/obstacle category); the work already committed and deployed stays landed. Never reach for
  a force or replace-lock route to escape it — an override is the operator's call, and asking is
  cheap.
- **Know how the lock actually clears: the TTL, not you.** A lock ages out an hour after its last
  heartbeat, and `check_lock` REFRESHES that heartbeat — so stop calling `check_lock` on a cycle you
  intend to abandon, or you will keep it alive indefinitely. A scored (non-PENDING) cycle left this
  way is clean: the doctor's leak check does not fire. But no push receipt was written, so whoever
  performs the push must run its own close to write one. A held lock does not stop a second session
  acquiring its own, so the deferred work can proceed while yours waits.

### Pitfall 7: "No sanctioned exit" is a claim to TEST, not a conclusion to trust

Before declaring a cycle unrecoverable, enumerate the tools that exist — the answer is often that the
tool was there all along and a wrong assumption hid it. Verified 2026-10-10, one session — the four
claims below are asserted by the committed, re-runnable test
`tests/test_governance_lock_lifecycle_claims.py` (transcript:
`docs/evidence/governance-lock-lifecycle-claims/transcript.txt`), which drives the deployed
`loop-gov-mcp.py` directly:

- **`advance_task_state` retires a mis-framed cycle without an override.** The user asked how to clear
  a cycle that kept being refused for scope drift. Reading the tool list settled it in minutes: the
  state machine carries `cancelled`/`suspended` and logs the reason in `task_events`, so the mis-framed
  task was retired through it (no `force`, no `user_overrode`) and the real work reopened under a
  correctly-named cycle, which closed CLEAN first try. A "no exit" assumption had already cost four
  refusals and an hour-long TTL wait.
- **A bare `check_lock()` is not a status check.** Called with no args it cannot resolve the session
  and returns `{"active": false}` while the lock is live on disk. When the file says active and the
  no-arg call says inactive, **the file is right** — the close will succeed. Do not re-acquire, do not
  open a carrier cycle; that false negative manufactures the very extra cycle you were trying to avoid.
- **`request_interruption` cannot rename a cycle** — it derives the sub-task id by suffixing the
  parent's, so splitting work with it does not fix a mismatched task id. Renaming needs a NEW
  `begin_change` under the correct name (a `reframe_change` tool would be the clean fix; until it
  exists, retire-and-reopen is the sanctioned path).
- **Order matters: do not `cancel` before interrupting.** `request_interruption` refuses a task already
  in a terminal state, so a cancel-then-interrupt sequence wedges. Interrupt (or reopen) first; check
  `TERMINAL_STATES` before sequencing any state transition.
- **The TTL expiry is a real, usable exit.** After a lock expires, `begin_change` under the
  correctly-named task opens a fresh cycle. Waiting out the TTL is preferable to forcing a close on a
  mis-framed one.

General rule: when a gate refuses in a way that looks unbounded, the first move is to re-read the
available tools and their parameters — not to re-roll the reviewer, and never to override.

## Verification

- `check_lock` confirms the purge (active: false) — expect this after every update run
- `cycle_query` shows no PENDING cycles before `end_change`
- `end_change` returns success (no rejection)
- Doctor overall line eventually shows the reduced warn/fail counts


## Related (user-owned, may need `hermes curator adopt`)

- `cortex-deployment-sync` — deploy mechanics, invocation forms, immutable-file pitfalls
- `cortex-preflight` — pre-flight checks + cortex-update side-effect table
- `loop-governance` — scoring internals, lock-lifecycle race history
