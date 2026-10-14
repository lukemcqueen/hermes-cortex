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
- **Know how the lock actually clears: the TTL, not you — and only once you STOP WORKING.** A lock
  ages out an hour after its last heartbeat, and ANY write-class tool call refreshes that heartbeat
  (`_touch_heartbeat` runs on writes), not just `check_lock`. So "wait out the TTL" is not available
  to the session still holding the lock: while it keeps working the lock never goes stale, and the
  wait the docs suggest can never arrive. Reach for a terminal state (Pitfall 8) instead of waiting. A scored (non-PENDING) cycle left this
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

- **`advance_task_state` is also the recovery for a lock stranded by a CRASHED close.** A close that raises after `feedback_accept` leaves the cycle scored-but-PENDING with the lock still held, and a repeated `end_change` throws again rather than clearing it. A terminal transition (`new_state="cancelled"`) releases it — the tool reports "a terminal task holds nothing" — and records the reason in `task_events`. Use that instead of a force/override, and say plainly in the reason what crashed, because the range then has no receipt and the next close must mint one.
- **`advance_task_state` retires a mis-framed cycle without an override.** The user asked how to clear
  a cycle that kept being refused for scope drift. Reading the tool list settled it in minutes: the
  state machine carries `cancelled`/`suspended` and logs the reason in `task_events`, so the mis-framed
  task was retired through it (no `force`, no `user_overrode`) and the real work reopened under a
  correctly-named cycle, which closed CLEAN first try. A "no exit" assumption had already cost four
  refusals and an hour-long TTL wait.
- **Read the lock's FULL picture; `active` alone is only YOUR lock.** A call with no args cannot
  resolve a session, so `active` reports `false` while another session's lock is live on disk — that
  field answers "do *I* hold a lock", never "is any lock held". The call also returns `locks` +
  `live_lock_count` listing every live lock (task, session, agent, repo, heartbeat): read those before
  concluding none exists, and when the lock FILE says active while `active` says false, **the file is
  right** — the close will succeed. Do not re-acquire and do not open a carrier cycle; that false
  negative manufactures the very extra cycle you were trying to avoid.
- **The lock's repo identity is legible in `repo_path`.** A lock stamped from a git repo carries a
  NON-EMPTY `repo_path`; one opened where the cwd is NOT a repo (a plain working copy, a deploy dir)
  has nothing stamped, so it inherits the host-canonical slug with `repo_path` EMPTY. Two locks can
  name the same slug by opposite routes — read `repo_path` to tell them apart, and treat an empty one
  as "this lock does not govern the tree I worked in": the close gate composes review material from
  the named repo, so a mis-tagged lock gets reviewed against a tree that cannot contain the work.
  `loop-gov.py` prints a note naming the cwd and the repo it will claim when it cannot resolve one;
  run governance from inside the repo, or pass `--repo <path>`, rather than accepting the fallback.
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

### Pitfall 8: A lock minted WITHOUT repo identity cannot be closed — only a TERMINAL state clears it

`end_change` refuses such a cycle with "Cannot close: no governed repo to measure complexity — the
self-adversarial review cannot run", because the close composes its review material from the repo the
lock names and this lock names none. Nothing ages it out (Pitfall 6: the owner's own work keeps it
alive), so the lock outlives every retry. Releases:

- **`advance_task_state(task_id=..., new_state="cancelled", reason=...)`** — terminal, and it reports
  "a terminal task holds nothing" because `_release_lock` does not consult repo identity. Name the
  cause in the reason; the range is left without a receipt, so whoever pushes must close something.
- **`blocked` is NOT a release.** It is non-terminal, so it keeps holding the lock — parking a lock
  you cannot close with `blocked` is what turns a stuck cycle into a stuck repo. From `blocked` the
  way out is `cancelled` (or `planning`).
- **A zero-diff placeholder cycle is closed by SCORING it.** `feedback_accept` with an
  `unscored_reason` takes it PENDING → MOVE_ON; "it can never close" is true of `end_change` only, and
  the remaining work is just the lock release above.
- **A different session cannot release it.** Locks are session-scoped, so a later session cannot
  end_change or advance the lock a dead session left; only the TTL purge (or the operator's `rm` of
  the file) clears it. Say so rather than leaving the next agent hunting for a tool.

Diagnose before concluding: read the lock FILE and check `repo_path` / `repo_slug`; empty or absent
identifies this class in one read.

Mint sites: any writer that builds a FRESH lock state instead of re-writing one that already carries
the repo. Re-writers inherit the repo fields, so all 14 other lock-write call sites are unaffected —
and when you fix one fresh-state writer, pin it with a test asserting the state it hands to the writer
carries `repo_path` AND `repo_slug`. Such a lock also creates no claimable task row, so a promotion
that mints one leaves a lock, a cycle and an event but nothing to claim.

**Which refusals free you — and why a freed lock must come with a resolved cycle.** A refusal about
the LOCK'S METADATA (the lock names no repo, or names a repo this session is not working in) judged
nothing: no diff was read, no verdict exists, and **no receipt is written on that path**, so holding
the lock authorises nothing while dead-ending the session that holds it — and the sessions queued
behind it. Current builds RELEASE the lock on those refusals and close the cycle UNSCORED
(`MOVE_ON` plus a reason naming the refusal), which makes the terminal-state route above the path
for a lock left by an older build or a crashed close rather than the only way out. A verdict about
the WORK (findings, reviewer unavailable) is different in kind: the close is refused and the lock is
released so you are not trapped, but the range still needs a CLEAN receipt before it can be pushed —
so re-check the receipt, do not re-close to "clear" it.

Any change that frees a lock must resolve its cycle in the same step. The doctor counts a PENDING
cycle as EXPECTED while a live lock exists and as a leak FAIL the moment the lock is gone, and ANY
doctor FAIL blocks the push for every agent on the host — so releasing alone converts one session's
dead-end into a host-wide block. Before "recovering" a cycle you believe is PENDING, read what the
score reports: `MOVE_ON → MOVE_ON` means something already resolved it, so your scoring was a no-op
rather than the fix, and the remaining problem is elsewhere.

### Testing governance helpers

- **Never drive an entry point whose PRECONDITIONS consult live state to assert one branch.**
  `begin_change` runs the dogfood check and the unscored-PENDING-cycle check before the refusal you
  want to test, so the assertion ends up measuring the host (a dirty tree or an open cycle fails a
  message test). Extract the decision/message into its own function and drive that — and assert BOTH
  directions: the repo-less lock gets the terminal-state guidance, a normal lock still gets the
  ordinary "call end_change".
- **Write lock fixtures with the module's OWN writer** (`_write_lock(state, {"session_id": sid})`),
  never a hand-built path: the path helper need not share the global you swapped, so the entry point
  starts a NEW session and the test passes while measuring the wrong subject.

## Verification

- `check_lock` confirms the purge (active: false) — expect this after every update run
- `cycle_query` shows no PENDING cycles before `end_change`
- `end_change` returns success (no rejection)
- Doctor overall line eventually shows the reduced warn/fail counts


## Related (user-owned, may need `hermes curator adopt`)

- `cortex-deployment-sync` — deploy mechanics, invocation forms, immutable-file pitfalls
- `cortex-preflight` — pre-flight checks + cortex-update side-effect table
- `loop-governance` — scoring internals, lock-lifecycle race history
