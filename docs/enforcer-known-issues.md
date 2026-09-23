# Enforcer Known Issues

> **Status:** Verified live on moses 2026-09-17 (session id ends `0aa33802`).
> This document catalogues defects in the governance enforcer / loop-governance
> lock machinery — what the symptom is, what actually happens on disk, and the
> root cause. It records problems found during investigation; code fixes are
> tracked separately.

---

## 1. `check_lock` reports "no active lock" while a valid, non-stale lock exists on disk

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
| 1 | `check_lock` false "no lock" when another session holds a live lock | 2026-09-17 | `_check_lock` reads only this session's lock file | No (read-only diag) |
| 2 | Fresh orphan (dead session lock + PENDING cycle) invisible for full TTL | 2026-09-17 | Staleness = heartbeat age only; no liveness probe | Partially (silent leak ≥1h) |
| 3 | Stale PID marker files never GC'd | 2026-09-17 | Legacy bridge written forever, never cleaned | No |
| 4 | No single tool shows complete lock truth | 2026-09-17 | Observability layer not extended with session-scoped model | No |
| 5 | `begin_change` close-out ignores PENDING cycles from dead sessions | 2026-09-17 | Close-out gate filters only `this session_id` | No (but weakens RULE 2) |

---

## Fixes / follow-ups

1. **`check_lock`** — scan all `.governance-*.json` and report every live lock (task, session,
   repo, age), not just this session's. Keep the session-scoped value but return the full picture.
2. **Liveness probe** — in `_purge_stale_locks()` / `_resolve_orphaned_pending_cycles()`, treat a
   lock whose owning session has no live process/marker as orphanable immediately, instead of
   waiting out the TTL. At minimum, surface the orphan (WARN) rather than silence it.
3. **GC stale PID markers** — add a routine in `_purge_stale_locks()` (or the cron auditor) to
   remove `.hermes-session-{PID}.id` files whose PID is no longer alive.
4. **Close-out gate breadth** — consider a fallback branch that resolves (MOVE_ON) a PENDING cycle
   whose owning session is dead, so RULE 2 holds across crashed sessions, not just live ones.