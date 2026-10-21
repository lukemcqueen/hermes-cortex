# Enforcer Known Issues

> **Status:** Verified live on moses 2026-09-17 (session id ends `0aa33802`).
> This document catalogues defects in the governance enforcer / loop-governance
> lock machinery — what the symptom is, what actually happens on disk, and the
> root cause. It records problems found during investigation; code fixes are
> tracked separately.

---

## 1. `check_lock` reports "no active lock" while a valid, non-stale lock exists on disk

> **FIXED 2026-10-13** — `_check_lock` now returns **every live lock on disk**
> (`locks`, `live_lock_count`: task, session, agent, status, repo, heartbeat) beside the
> session-scoped `active`/`lock`, and the tool description says so. A call with no session can
> still resolve only its own lock, but it can no longer read as "no locks at all". Stale locks are
> excluded and an unparseable (mid-write) file is skipped — reported as neither live nor deleted
> (P1-A). Re-executable evidence: `docs/evidence/lock-truth-2026-10-13.txt` (a bare `check_lock`
> naming a live foreign lock), tests `tests/test_lock_truth.py`. The diagnosis below is kept for
> the record.

**Symptom.** `mcp__loop_governance__check_lock` returns `{"active": false, "lock": null}` even
though a `~/.hermes-cortex/state/.governance-*.json` lock file exists, is non-stale, and its
task still has a PENDING cycle in the loop-governance DB. An agent (or the operator) reading
`check_lock` concludes "no governance lock is held" and, combined with a PENDING cycle in
`cycle_query`, reads it as "governance is broken / leaked."

**Verified reproduction (2026-09-17):**
- A lock file for dead session `…754ab805` existed on disk (heartbeat 09:57:44Z, TTL default
  — not stale), while cycle 2682 (`fleet-update-792a8abd`) was PENDING for that same session.
- Yet `check_lock` returned `active:false, lock:null`.
- Meanwhile a new `begin_change` (session `…0aa33802`) created cycle 2683 without a peep — no
  "close out your previous task" refusal (see issue 5).

**Root cause.** `_check_lock()` in `mcp-servers/loop-gov-mcp.py` is **session-scoped**: it calls
`_read_lock(args)`, which resolves the lock path from **this session's** ID
(`_session_lock_path(get_session_id(args))`) and reads only that one file. It does **not** scan
all `.governance-*.json` files. A lock owned by a *different* session — even a live, non-stale
one — is invisible to `check_lock`. The tool's contract ("Check if a governance lock is active")
overpromises: it only reports *this caller's* lock, and returns `null` when another session owns
a perfectly valid lock.

**Consequence.** `check_lock` is misleading as a diagnostic. It cannot tell you "some session
holds an active lock" — only "does *my* session hold a lock." Operators relying on it to detect
a stuck/orphaned lock will get a false "all clear" exactly when a foreign lock + PENDING cycle
still sit in the state dir.

---

## 2. Orphaned-session lock + PENDING cycle are invisible until the heartbeat exceeds TTL (1h)

**Symptom.** A session that died mid-change (its lock file was never released by `end_change`)
leaves both a lock file *and* a PENDING cycle that no mechanism cleans until the heartbeat has
aged past the TTL. Within that window the debris is treated as a *live, in-progress change* —
the doctor's PENDING-cycle check passes it as "current task (lock held)", `check_lock` hides it
(cf. issue 1), and `begin_change` does not refuse on it.

**Verified reproduction (2026-09-17):**
- Session `…754ab805` was **dead**: only one gateway process ran (the live session's). The dead
  session's context ended ~18:57 (skills-state mtime) — its gateway was not in the process list.
- Its lock file still sat in `~/.hermes-cortex/state/` (heartbeat 09:57:44Z, ~35 min old at
  check time → **under** the default TTL).
- Cycle 2682 for that session stayed PENDING.
- Because the lock is under TTL, `_purge_stale_locks()` correctly does **not** unlink it
  (not stale yet), and `_resolve_orphaned_pending_cycles()` — which resolves PENDING cycles
  whose task has **no live lock** — treats `fleet-update-792a8abd` as live (the lock exists),
  so it correctly skips 2682.

**Update 2026-10-02 (Luke: "there should be no open cycles … honesty and doing things the right
way").** When `_resolve_orphaned_pending_cycles()` *does* resolve a cycle it now closes it
**unscored**: decision `MOVE_ON` so the close-out gate sees it closed, plus `unscored_reason` tagged
`[orphan-reaper]` naming facts an auditor can recompute (no live lock for task X; cycle age > TTL).
No score is invented, and every reaped id is logged — previously the `begin_change` sweep reaped
silently, so an abandoned session's bare `MOVE_ON` accumulated and read as a *judged* cycle. The
distinction matters in this DB: 2,966 cycles are `MOVE_ON` with no score and no reason, so "closed"
must never be read as "judged". The doctor's `Orphan-cycle resolution` check now corroborates the
reaper's claim and FAILs on the one contradiction that cannot happen honestly — a reaper-closed
cycle whose **own** session still holds a live lock for the same task (deliberately not the weaker
"the task has no lock now", which a later resumed task would trip). *Still open here: the TTL-window
invisibility described above.*

**Root cause.** Staleness is defined purely by heartbeat age vs TTL (`_is_lock_stale`). There is
no liveness probe (does the owning session still exist? is its process alive?). A session that
dies after `begin_change` but before its heartbeat would age out leaves a lock that is, by the
one available signal, indistinguishable from an actively-in-progress change — until TTL passes.
`_is_lock_stale` has an mtime fallback, but that only helps when the file itself is old; a recent
start heartbeat plus no further heartbeats pins the lock "young" for the full TTL.

**Consequence.** Up to 1 hour of debris per crashed session, during which: the DB holds a PENDING
cycle nobody can score, `check_lock` shows a false clear, and the doctor's "leak" gate is silent.
The recent `fix-gov-lock-purge` (commit `8335f13f` / cycle 2676) closed the *permanent* pin
(malformed/naive heartbeats never aged) but did **not** add a liveness probe, so a *fresh* orphan
is still invisible for the TTL window.

---

## 3. Hundreds of stale PID-scoped session-marker files accumulate with no cleanup

**Symptom.** `~/.hermes-cortex/state/` contains a very large number of
`.hermes-session-{PID}.id` marker files (observed: 200+), each written by the enforcer's legacy
PID-scoped bridge. They are never removed.

**Verified (2026-09-17):** `ls ~/.hermes-cortex/state/.hermes-session-*.id` returned hundreds of
files spanning PIDs from the low hundreds to the millions. The current-session markers
(`.hermes-session-current.id`, `~/.hermes/session.id`) hold the live session ID; the PID-scoped
ones are inert fallbacks.

**Root cause.** The enforcer (`plugins/governance-enforcer/__init__.py`) writes a PID-scoped
marker on every `pre_tool_call` (documented as the legacy fallback bridge in the plugin README),
but nothing ever garbage-collects them. They are a write-only artifact: written forever, removed
never. The fix on 2026-08-02 moved session-ID handoff to per-call args injection (Priority 0),
so these PID markers are rarely even read — they are pure accumulation.

**Consequence.** Unbounded growth of small files in the state dir; minor hygiene, but it warms the
delete path in `_purge_stale_locks` (symlink/dangling cleanup) and inflates `ls`/`find` noise.

---

## 4. Session-scoped lock + cross-session write protection is not surfaced by any single tool

**Symptom.** There is no single MCP call that reports the *complete* governance truth — "which
sessions currently hold locks, for which repo, and which are stale." Each tool shows one slice:
`check_lock` (this session only), `cycle_query` (DB rows, no liveness), `cycle_stats`
(aggregates).

**Root cause.** The lock model is intentional (session-scoped files, repo_slug in content, cross-
session write protection in the enforcer's Phase 2). But the *observability* layer was not
extended to match: `check_lock` was kept session-scoped in the MCP while the enforcer reads all
files. The asymmetry is exactly what makes issues 1 and 2 look like "governance is broken" when it
is actually working as designed for the current session.

**Consequence.** Operators/agents cannot cheaply enumerate live locks or spot an orphan without
grepping the state dir by hand (as this investigation did).

---

## 5. `begin_change` closes out only on *this* session's PENDING cycles

**Symptom.** Per AGENTS.md RULE 2, `begin_change` "refuses while PENDING cycles exist." In
practice it refuses only when **this session** has an unscored PENDING cycle (query filters
`WHERE session_id = ?` and `decision='PENDING'`). A PENDING cycle belonging to a **dead** session
does not trip the gate.

**Verified (2026-09-17):** a new session (`…0aa33802`) called `begin_change`
(`verify-gov-lock-pending`) while cycle 2682 (`fleet-update-792a8abd`, session `…754ab805`) was
still PENDING. The call succeeded and created cycle 2683 — no "close out your previous task"
refusal.

**Root cause.** The close-out gate is deliberately session-scoped (so concurrent sessions don't
block each other — correct for *live* sessions). But it conflates "PENDING cycle from a dead
session" with "none" for this session. There is no fallback that treats a *dead* session's PENDING
cycle as a leak the current session should resolve before opening a new lock.

**Consequence.** A crashed session's PENDING cycle can coexist with new, unrelated work for up to
the TTL window (issue 2), silently violating the "never stack PENDING" intent until the health
check's 24h rule or the >TTL purge finally classifies it.

---

## Summary table

| # | Issue | Verified on | Root cause | Blocks writes? |
|---|-------|-------------|-----------|----------------|
| 1 | `check_lock` false "no lock" when another session holds a live lock | 2026-09-17 | `_check_lock` read only this session's lock file | No (read-only diag) — **FIXED 2026-10-13**: reports every live lock (`locks`/`live_lock_count`) |
| 2 | Fresh orphan (dead session lock + PENDING cycle) invisible for full TTL | 2026-09-17 | Staleness = heartbeat age only; no liveness probe | Partially (silent leak ≥1h) |
| 3 | Stale PID marker files never GC'd | 2026-09-17 | Legacy bridge written forever, never cleaned | No |
| 4 | No single tool shows complete lock truth | 2026-09-17 | Observability layer not extended with session-scoped model | No |
| 5 | `begin_change` close-out ignores PENDING cycles from dead sessions | 2026-09-17 | Close-out gate filters only `this session_id` | No (but weakens RULE 2) |
| 6 | Skills gate passed with NO session id if any other session had a marker | 2026-09-23 | `_check_skills_loaded_marker()` no-session branch accepted any marker | Was FAIL-OPEN (now fixed: fails closed) |
| 7 | Domain/adversarial skill credit vanished after every deploy | 2026-09-23 | Loaded-skill set lived only in process memory; plugin reload wiped it | Yes (re-blocked mid-task) — fixed via the credit journal |
| 8 | "7/7 loaded ✅ but still blocked" after a deploy that changed no skill text | 2026-09-23 | `_skills_fingerprint()` hashed skill-file MTIMES, so a byte-identical redeploy moved the fingerprint, discarded the credit journal and invalidated the 7/7 marker | Yes — fixed: content-hash fingerprint + per-skill credit; the block message names the skills to reload |
| 9 | A lock opened from a non-git-repo cwd is tagged with the host-canonical repo, silently | 2026-10-13 (kustos) | `loop-gov.py`'s `"no-repo"` stamp returned without a word | No — **FIXED 2026-10-13**: names the cwd, the repo it will claim, and both ways out (detail below the table) |
| 10 | Every write gate blocked although governance is healthy: the CLI adapter exits 3 because the interpreter's `mcp` is too old for the 2.0 constructor API | 2026-10-20 (gisu) | `loop-gov-mcp.py` constructed `Server(...)` unguarded, so a version skew in a dependency the CLI never SERVES raised at module import | Yes (every write/edit in a Pi session) — **FIXED 2026-10-20**: the SDK guard probes the constructor API and an incompatible SDK degrades to the SDK-independent handlers, warning and naming the interpreter (detail below) |

---

## 9. A lock opened from a non-git-repo cwd is tagged with the host-canonical repo, SILENTLY

> **FIXED 2026-10-13.** Reported by kustos: his session's cwd `/home/app/mwi/koscap-mwi` is a
> working copy, not a repo (`git status` is fatal there), and its lock came out with
> `repo_slug: hermes-cortex` and an empty `repo_path`.

**Symptom.** The lock names a repo the session never touched, and nothing anywhere says so. The
only clue is the empty `repo_path`.

**What happens.** `_stamp_repo_into_payload()` (ops/scripts/loop-gov.py) resolves the cwd's git
root with `git rev-parse --show-toplevel` so the lock cannot claim another repo. When the cwd is
genuinely not a repo the call returns rc≠0 → status `"no-repo"` → **nothing is stamped** → the
server's `_derive_slug` falls to Priority 1, the host-canonical `~/hermes-cortex`, with
`repo_path` left empty. The `"unexpected"` case (git missing/hung) already failed closed for
`begin_change` (ADV-4479-1); the `"no-repo"` case printed **nothing at all**.

**Why it mattered.** Benign only while the session changes nothing in that tree — which is what
kustos reported, so nothing broke. But it is the wrong-repo bug (Titus cycle 5742) with the
signal removed: a CLOSE would compose review material from `~/hermes-cortex`, a tree that cannot
contain the work, and the cycle would be uncloseable — with no earlier indication why.

**Fix (FIXED 2026-10-13).** `_repo_identity_note()` decides what to say and whether to refuse,
and `main()` prints it: the `"no-repo"` note NAMES the cwd, the repo the lock will be tagged
with (asked of the server's own `_derive_slug`, so the warning cannot drift from the fallback),
and both ways out (`--repo <path>`, or run inside a repo). Non-fatal — the documented benign case
stays usable — and it goes to stderr so the tool's stdout contract is untouched. `"unexpected"`
still fails closed for `begin_change` (exit 1) and is now reported for every other tool too.
Evidence: `docs/evidence/lock-truth-2026-10-13.txt` (a real non-repo cwd, git's own "fatal: not a
git repository", and the note naming both the cwd and `'hermes-cortex'`). Tests:
`tests/test_lock_truth.py`.

---

## 10. A version skew in `mcp` killed the WRITE GATE, on a host whose governance was healthy

> **FIXED 2026-10-20.** Reported by the pi agent on gisu: every write/edit/non-readonly bash
> blocked — `cortex-governance.ts` → `loop-gov.py check_repo_lock` → rc=3 — with stderr
> `Server.__init__() got an unexpected keyword argument 'on_list_tools'`.

**Symptom.** `loop-gov.py: governance is unavailable: …` and exit 3 on every call, while the
loop-governance MCP tools keep working from that same agent. The gate looks dead; the store
looks fine.

**What happens.** `mcp-servers/loop-gov-mcp.py` guarded its SDK import with `except ImportError`
ONLY, and then constructed `Server("loop-governance", on_list_tools=…, on_call_tool=…)` at module
level. Those kwargs are the 2.0 constructor API, so an older SDK raises `TypeError` THERE — at
import. `ops/scripts/loop-gov.py` loads the module with `exec_module`, so the CLI adapter, which
never needs to SERVE MCP, died with it. The registered MCP server runs on a different interpreter
(`~/.hermes-cortex/venv/bin/python3`, mcp 2.0.0) and stayed healthy — which is why the same
agent's MCP calls succeeded while its write gate refused everything.

**Why the first diagnosis went the wrong way.** The message reads as "the SDK is NEWER than the
code" and means the opposite: `on_list_tools` IS the 2.0 API, and the decorator style it replaced
is the older one (`docs/older/reference/mcp-sdk-v2-migration.md`).

**Fix (FIXED 2026-10-20).** The guard now PROBES the API it needs — a throwaway
`Server("loop-governance/sdk-capability-probe", on_list_tools=None, on_call_tool=None)` inside the
same `try` — so an incompatible SDK takes the same fail-soft path as a missing one: the module
stays importable, the handlers stay drivable, and stderr carries a warning naming the interpreter
and the API required. It declines to serve rather than degrading in silence, because a gate that
quietly disables itself hides the wrong interpreter. The declared floor is `mcp>=2.0` (it was
`>=1.0`, which admitted exactly the version that breaks), and `fix-cortex-venv.py --check` probes
that capability rather than only importing — the check `cortex-update.sh` gates its repair on, so
without it a broken host was told `ok: … imports all 6 declared requirements` and repaired
nothing. Evidence: `docs/evidence/verify-mcp-sdk-guard.sh` beside its captured run (the pinned
baseline reproduces the reported `TypeError`; this tree imports, warns, and keeps the CLI
working). Tests: `tests/test_loop_gov_cli.py` (both SDK generations fabricated in-test),
`tests/test_fix_cortex_venv.py`.

---

## Self-check any host

`~/.hermes-cortex/scripts/probe-gate-logic.py` (repo:
`ops/scripts/quality/probe-gate-logic.py`) loads the ACTIVE enforcer module in a
throwaway state dir and asserts the gate behaviour end-to-end — marker timing,
block-message contents, the read-only classifier matrix, the credit journal, and
the no-session-id fail-closed path. Run it when an agent claims a gate is
"stuck", after a deploy, or when a peer host behaves differently:

```bash
python3 ~/.hermes-cortex/scripts/probe-gate-logic.py            # active copy
python3 ~/.hermes-cortex/scripts/probe-gate-logic.py --json     # machine-readable
```

Exit 0 = the enforcer on this host behaves as documented.

---

## Fixes / follow-ups

1. **`check_lock`** — scan all `.governance-*.json` and report every live lock (task, session,
   repo, age), not just this session's. Keep the session-scoped value but return the full picture.
   **(DONE 2026-10-13** — `_live_locks()`; session-scoped `active`/`lock` unchanged, `locks` +
   `live_lock_count` added to all three return shapes; evidence `docs/evidence/lock-truth-2026-10-13.txt`.)
2. **Liveness probe** — in `_purge_stale_locks()` / `_resolve_orphaned_pending_cycles()`, treat a
   lock whose owning session has no live process/marker as orphanable immediately, instead of
   waiting out the TTL. At minimum, surface the orphan (WARN) rather than silence it.
3. **GC stale PID markers** — add a routine in `_purge_stale_locks()` (or the cron auditor) to
   remove `.hermes-session-{PID}.id` files whose PID is no longer alive.
4. **Close-out gate breadth** — consider a fallback branch that resolves (MOVE_ON) a PENDING cycle
   whose owning session is dead, so RULE 2 holds across crashed sessions, not just live ones.
5. **No-session-id fail-closed** (DONE 2026-09-23) — the marker check no longer accepts another
   session's proof; the block message now diagnoses broken session-id plumbing instead.
6. **Skill-credit journal** (DONE 2026-09-23) — `state/skills-credit/<session_id>.json`,
   fingerprint-pinned, rehydrated on cold start, invalidated when the skills change.
7. **Content-hash fingerprint + per-skill invalidation** (DONE 2026-09-23) — `_skills_fingerprint()`
   now hashes skill CONTENT (`_skill_content_hash()`, memoized on mtime+size) instead of mtimes, and
   the credit journal stores a per-skill `hashes` map, so only a skill whose bytes actually changed
   loses credit. `_stale_skills(session_id)` names them, and the skills-gate block message prints
   `skill_view(name='<skill>')` for exactly those — a weak model reloads one skill, not seven.
   Legacy journals (no `hashes`) keep the old all-or-nothing rule, fail closed. Regression tests:
   `tests/test_runtime/test_skill_content_fingerprint.py` + the probe's
   "no-op deploy must not wipe credit" section.