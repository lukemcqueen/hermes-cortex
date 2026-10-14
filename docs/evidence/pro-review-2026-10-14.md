> `provenance: advisory`

> Provenance: an OPERATOR-REQUESTED advisory review of this session's governance work, not the
> close gate. The reviewer is the fleet's heavy model, called through the same cortex config the
> governance reviewer uses (key resolved by the module's own helper, never seen or passed here).
> The material was the functions extracted from the reviewed revision with `ast` — never retyped
> — plus the change summary; the reviewer never saw this host's terminal.
> The model's response below is VERBATIM. My accept/reject judgement follows it, separated by a
> marker, so a reader can always tell which words are the reviewer's.

# DeepSeek Pro gap review — governance release paths + reclaim_dead_locks

model: deepseek/deepseek-v4-pro
endpoint: https://openrouter.ai/api/v1
usage: {"prompt_tokens": 7560, "completion_tokens": 4039, "total_tokens": 11599, "cost": 0.02990897, "is_byok": false, "prompt_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0, "audio_tokens": 0, "video_tokens": 0}, "cost_details": {"upstream_inference_cost": 0.02990897, "upstream_inference_prompt_cost": 0.0144396, "upstream_inference_completions_cost": 0.01546937}, "completion_tokens_details": {"reasoning_tokens": 0, "image_tokens": 0, "audio_tokens": 0}}
material: 31637 chars (functions extracted with ast from the reviewed revision)
temperature: 0 (a sampling reviewer is not a reviewer)

---

## Independent Review — `loop-gov-mcp.py` governance lock cleanup

I’ll answer your four questions in priority order, with concrete findings ranked by severity.

---

### A. Release-path invariant: lock freed / cycle resolved

**What I can see in the extract and judge complete:**

1. **`_release_lock_after_metadata_refusal` (lines 1‑58)** — correct. `_close_cycle_unscored` is called *before* the chosen `session_id`-scoped `_release_lock`. The early return on missing `session_id` deliberately leaves the cycle PENDING, matching the comment’s stated intent. ✅

2. **`_release_after_refusal` (lines 1‑61)** — correct. Same order: close unscored (with `task_id` fallback), then release by `lock["session_id"]`. The early return on missing session id also leaves the cycle PENDING and does not attempt a release. ✅

3. **`_advance_task_state` `blocked` branch (excerpt)** — correct. `_close_cycle_unscored` is called first with `task_id` lookup, then `_release_lock(args)`. Note: `_release_lock(args)` is called with the whole `args` dict, not with a `session_id`-scoped owner. I cannot see the body of `_release_lock`; I must trust that `_release_lock` extracts `session_id` from `args` *reliably* and never falls back to a process‑scoped default. If `_release_lock` uses `get_session_id(None)` internally, this path could release a peer’s lock — you must verify that `_release_lock` honours the caller’s supplied `session_id` exactly. This is the one release path that does not use the `{"session_id": owner}` explicit form. **Gap: I cannot see whether `_release_lock` is safe here.** ⚠️

4. **`_reclaim_dead_locks` (apply path, lines 1‑102)** — correct relative to its own operation. It unlinks the lock file inside `_STATE_LOCK`, then calls `_resolve_orphaned_pending_cycles(task_ids)`. However, the unlink and the DB close are in two *separate* transactions (filesystem vs SQLite). If the process crashes after unlink but before the DB commit, a lockless PENDING cycle remains. The STARTUP sweep (`_resolve_orphaned_pending_cycles` called with `task_ids=None`) will eventually catch it, but it is subject to the TTL delay. This is not a *leak that blocks pushes forever*, but it is a window. **Gap: no atomicity between unlink and DB close in the reclaim path.** Medium severity if the startup sweep is reliable; high if the startup sweep can itself be skipped.

5. **Any other path?** I do not have the bodies of `end_change`, `feedback_accept`, `begin_change`, or the `unavailable`/outage path. I cannot enumerate every code path that calls `_release_lock` or writes to `loop_cycles`. The docstring in `_release_after_refusal` says the outage path deliberately keeps the lock. That must be the only other lock‑holding path, or there is a leak. **I cannot confirm from this extract alone.** You should grep for every caller of `_release_lock` and verify that every caller that does not call `_close_cycle_unscored` first is either (a) a path where the cycle has already been closed (e.g., scored in `feedback_accept`) or (b) the outage path that explicitly keeps both lock and PENDING cycle. Similarly, every caller of `_close_cycle_unscored` that is not paired with a release must be a deliberate leave-it-PENDING case (like the missing `session_id` refusal) — and those must eventually resolve (TTL purge or startup reaper). That is the full invariant check.

**Ranking for A:**

| # | Finding | Severity |
|---|---------|----------|
| A1 | `_advance_task_state` `blocked` calls `_release_lock(args)` — extraction of `session_id` inside `_release_lock` not visible in this extract; if it uses a process‑scoped fallback, a peer’s lock can be freed. | **High** until proven safe |
| A2 | `reclaim_dead_locks` unlinks the file and closes the DB cycle in separate transactions — a crash between them leaves a lockless PENDING cycle (resolved later by the startup sweep, but with a TTL delay window). | **Medium** |
| A3 | Other release paths (`end_change`, outage, `feedback_accept`, `begin_change` reaping) are not in the extract — I cannot judge whether any of them drops a lock without closing a cycle. | **High** (must be audited externally) |

---

### B. `reclaim_dead_locks` safety

I’ll walk through each concern you raised.

#### B1. Races: dead‑looking owner coming back
`_is_lock_stale` checks the heartbeat AND the commit history. A session that was idle past its TTL but has committed recently is renewed (the liveness rescue). The stale check is idempotent: a session that was alive the whole time will have recent commits, so it will never appear dead. The only race is a session that was genuinely dead, its lock reclaimed, and *then* it wakes up and tries to act — but that session’s lock file is gone, so its next governed call will fail with a lock‑missing error, which is correct (its session was terminated). No take‑over is attempted, so no conflict. ✅

#### B2. Concurrent `begin_change`
`reclaim_dead_locks` operates inside `_STATE_LOCK` for the unlink phase, but the stale check happens *before* acquiring the lock. If a dead‑looking owner issues a `begin_change` between the stale check and the `_STATE_LOCK` acquisition, the heartbeat could be refreshed (a new write to the lock file). The code then unlinks a file that is now live. However, the `begin_change` writer will have its own file descriptor; the unlink removes the *directory entry* but the writer’s inode is still there. The writer will fail its next read/write (ENOENT on the path). This is a race window of a few milliseconds. The probability is very low for a session that has been idle past its TTL. **Acceptable in practice, but the startup sweep should be the primary reaper; this tool is an explicit operator action.** Low severity. ⚠️

#### B3. Unlink vs atomic write
Unlinking a file is atomic on local filesystems when the path is a regular file. The code does a plain `Path.unlink()`. It does not rename-to-tombstone first. On NFS or network filesystems, this can be racy. Since `GOVERNANCE_STATE_DIR` is in `~/.hermes-cortex/state/` (likely local), this is acceptable. No symlink traversal risk because symlinks are skipped explicitly. ✅

#### B4. The renewal side effect inside a “report” read
`_is_lock_stale` may call `_refresh_lock_heartbeat(state)`, which writes to the lock file. The `apply=false` REPORT path reads every lock file and calls `_is_lock_stale`. The report is therefore NOT a pure read: it can renew a lock whose agent has committed. The report’s output can legitimately list *fewer* locks than there are old‑looking files, and this is documented in the docstring. The tool’s description to the agent should make this clear (“report may renew locks that are busy — list may be shorter than expected”). **The side effect is intentional and documented in the code, but the tool description visible to the agent may not communicate it.** Medium — could cause an operator to miss a lock that was renewed silently. ⚠️

#### B5. Symlink handling
`lock_file.is_symlink()` skips symlinks entirely. A symlink could be used to point to a lock file for a non‑local repo or to escape the directory. Skipping is safe (never reclaiming a symlink is correct). ✅

#### B6. The `only_task` filter
`only_task` is applied *after* reading and parsing every lock file. It filters the `dead` list. A lock that is live is also skipped by this filter (the stale check is done first). The filter is correct — it narrows the reclaim scope to a single task. ✅

#### B7. Closing the dead owner’s cycle — can it launder an unfinished review?
`_resolve_orphaned_pending_cycles` sets `decision='MOVE_ON'` with an `ORPHAN_REAPER_TAG` in `unscored_reason`. No review receipt is written. The doctor has a check that distinguishes reaped cycles from genuinely scored ones. The push gate requires a CLEAN review receipt, which does not exist for a reaped cycle. **The reaped cycle does not become pushable.** ✅

#### B8. Permissions surface for an agent‑facing tool
The tool can end another agent’s lock. In the current design, any agent on the same host can run it. If the host is shared by mutually distrusting agents, this is a privilege escalation (one agent can kill another’s lock). The tool has no ownership check beyond “not my own lock.” **If agents are in separate trust domains, this tool should require an explicit operator confirmation or be restricted to a human‑facing tool.** The docstring says “operator or an agent told to by an operator.” The code does not enforce any operator gate. **High** if multi‑agent isolation is required; **Low** if all agents on the host are in a single trust domain (as the file‑based mutex implies). I cannot determine the trust model from this extract. ⚠️

**Ranking for B:**

| # | Finding | Severity |
|---|---------|----------|
| B1 | `reclaim_dead_locks` has no ownership restriction — any agent on the host can end another agent’s lock. If agents are in separate trust domains, this is a vulnerability. | **High** (context‑dependent) |
| B2 | The REPORT path (`apply=false`) may silently renew a busy lock, reducing what is reported. The agent‑facing tool description may not communicate this side effect. | **Medium** |
| B3 | Race between stale check and `_STATE_LOCK` acquisition could unlink a lock that just became live. Probability is very low and the consequence is a terminated session, not data corruption. | **Low** |

---

### C. `_is_lock_stale` as a definition of “provably dead”

The definition is:

1. Heartbeat age > TTL **AND**
2. No commit by that agent in that repo since the heartbeat timestamp **AND**
3. Renewal budget exhausted (if commits exist but heartbeat is old)

**Failure mode it cannot see:**
An agent is alive and continuously working in a **different repo** from the one named in its lock. The lock’s `repo_slug` is fixed at `begin_change`. If the agent is doing work that produces commits in a *different* repo (e.g., side‑effect work), `_session_worked_since` checks commits in the lock’s own repo. Those commits won’t be there. The lock will age out and be declared dead even though the agent is still running. The liveness rescue only checks the lock’s own repo. **This is a false‑positive death declaration.** The session will lose its lock while still working, and its next governed call will fail.

The fix would require either (a) a heartbeat refresh on every governed call (which the docstring says was added but is not visible in this extract), or (b) a broader liveness check (presence of the agent’s PID or a process‑level signal). The docstring says “Every governed call now refreshes the heartbeat,” so this gap is partially closed — but if the agent makes *no* governed calls for a long stretch while working in a side repo, the gap remains. The TTL + renewal budget provides a cap; after the budget is spent, the lock ages out regardless of activity. **The definition is sound *given* frequent governed calls; the failure mode is a long gap in governed calls while working in a different repo.** Medium.

**Ranking for C:**

| # | Finding | Severity |
|---|---------|----------|
| C1 | `_is_lock_stale` checks commits only in the lock’s own repo. An agent active in a different repo will be declared dead after TTL + renewal budget, losing its lock. | **Medium** |

---

### D. Error handling / logging / return‑value semantics that could mislead

I found several concrete issues:

#### D1. `_close_cycle_unscored` returns `False` when no row matched.
But the caller `_release_lock_after_metadata_refusal` returns `resolved` (the bool from `_close_cycle_unscored`) to its own caller. If `_close_cycle_unscored` returned `False` because the row was already scored/overridden, the caller gets `False`, which *might* interpret that as a failure of the whole release path. In `_release_lock_after_metadata_refusal`, the return value is `resolved`, but the lock was still released (the `_release_lock` call comes after and is not guarded by `resolved`). The bool `False` means “the cycle was not closed by this call” — not “the lock was not released.” Callers that check the return value could be misled into thinking the release failed. **The docstring should clarify what `True`/`False` means for this function, and callers should not conflate cycle‑close outcome with lock‑release outcome.** Medium.

#### D2. `_release_lock_after_metadata_refusal` returns `False` when the lock carries no `session_id`.
But the cycle is *deliberately* left PENDING. The `False` return tells the caller “something failed.” A caller could retry the refusal, which would hit the same guard and return `False` again in an infinite loop. The function should return a distinct value or set a flag indicating “deliberately not released” vs “operation failed.” **Medium** — risk of retry storm.

#### D3. `_release_after_refusal` return string on missing `session_id`.
The string says “its cycle is left PENDING for the same reason — see the cycle note above.” But no cycle note is above in the return string — that text is only in the log. The agent sees a message referencing a “cycle note above” that does not exist in the returned content. **Minor** — confusing to the agent.

#### D4. `_reclaim_dead_locks` `apply=true` returns a success message even when `failed > 0`.
The message says “{failed} could not be removed — they will age out or need the operator.” This is fine — it’s honest. But the `CallToolResult` has no `isError=True`. If the caller treats any non‑error result as full success, they will miss the partial failure. The standard MCP convention is to set `isError=True` when the operation was partially unsuccessful. **Minor** — tool convention deviation.

#### D5. `_resolve_orphaned_pending_cycles` swallows all exceptions and returns 0.
If the DB is locked or the query fails for a transient reason, the caller gets 0 and no error propagation. The function returns an `int`, not a success/failure indicator, so the caller cannot distinguish “0 cycles to close” from “error occurred.” The log has a warning, but callers like `_reclaim_dead_locks` don’t check — they just print “closed 0 PENDING cycle(s).” **Medium** — silent failure masks problems.

#### D6. `_reclaim_dead_locks` `apply=true` does the unlink loop *then* calls `_resolve_orphaned_pending_cycles`. If `_resolve_orphaned_pending_cycles` fails (returns 0 due to DB error), the locks are already gone. The tool reports “closed 0 PENDING cycle(s)” but the doctor will later FAIL on those lockless PENDING cycles. The operator has no indication that a DB error occurred vs there were no cycles to close. **Medium** — same root as D5.

**Ranking for D:**

| # | Finding | Severity |
|---|---------|----------|
| D1 | `_release_lock_after_metadata_refusal` returns `_close_cycle_unscored`’s bool — `False` may be misread as “release failed” when the cycle was already scored/overridden. | **Medium** |
| D2 | Missing‑session‑id case returns `False` to caller with no distinction from operational failure — retry risk. | **Medium** |
| D3 | `_resolve_orphaned_pending_cycles` and its callers cannot distinguish “0 cycles” from “DB error” — silent failure. | **Medium** |
| D4 | `_release_after_refusal` message references a “cycle note above” that isn’t in the returned text. | **Minor** |
| D5 | `reclaim_dead_locks` `apply=true` does not set `isError=True` on partial failure. | **Minor** |

---

### Summary of what is fine

- The `_close_cycle_unscored` implementation with `PENDING` guard and `rowcount` check is correct and self‑defensive against rewriting scored/overridden cycles. ✅
- The liveness rescue in `_is_lock_stale` (commit‑based renewal with budget) is a strong defence against false‑positive death during active work, within the constraint of the lock’s own repo. ✅
- The P1‑A protection (skipping unparseable files, never deleting them) is correctly applied in both `_reclaim_dead_locks` and `_resolve_orphaned_pending_cycles`. ✅
- The explicit skip of symlinks in `_reclaim_dead_locks` is correct. ✅
- The order‑of‑operations (close cycle before drop lock) is correctly implemented in all visible release paths. ✅
- The orphan‑reaper tag and the honesty‑driven `unscored_reason` ensure that abandoned cycles are auditable and cannot be confused with judged closes. ✅
---

## What I did with it (the reviewer's advice is CLAIMS, not conclusions)

Recorded per finding; the reasoning matters more than the verdict, because a reviewer can be
right about the mechanism and wrong about the severity (or the reverse).

### Accepted and FIXED in this commit — 8 changes

| Finding | What was actually wrong | Fix |
|---|---|---|
| **A3** (high: "audit every release path") | Enumeration found **two more live instances** of the exact class: `_advance_task_state`'s TERMINAL branch released the lock (making the task terminal) with its cycle still PENDING — which the doctor counts as a leak, because a terminal lock is not a live lock — and `_check_lock`'s stale auto-release dropped a heartbeat-stale lock without touching its cycle. | Both now resolve the cycle in the shared closer before releasing. `tests/test_release_paths_sweep.py` pins the whole CLASS: every `_release_lock(` call site must call the closer or be declared in an explicit exemption list whose justifying gate is itself asserted against the source. |
| **A2** (medium: no atomicity between unlink and the DB close) | Real, and worse than it looked: closing *after* unlinking is exactly the leak window this thread exists to remove. | The reclaim now closes the cycles FIRST and removes the lock files after. A crash in between leaves a DEAD lock beside a MOVE_ON cycle, which the doctor ignores. |
| **A2 follow-on** (found by my own probe, not by the reviewer) | Reordering naively made the reclaim close **nothing**: the orphan resolver skips any task whose lock file still exists, and the dead locks are still on disk at that point. The probe caught it (0 cycles closed, `is_error=True`). | The reclaim calls the shared per-task closer instead of the resolver — the closer has no live-lock precondition. The contract test now forbids routing through the resolver here, so the trap cannot be walked back into. |
| **B3** (low: TOCTOU between the scan and the unlink) | Real: ownership and staleness were decided from a read taken *before* the state lock, so an owner that woke up and refreshed its heartbeat in the gap could lose a LIVE lock. | Both are re-checked inside `_STATE_LOCK` immediately before the unlink, and an unreadable file is skipped rather than removed (P1-A). |
| **D5/D6** (medium: a count cannot distinguish "nothing to close" from "the store is down") | Real, and it is the "two facts, one return value" defect class — the reclaim would report "closed 0" while the doctor was about to fail the host. | The outcome is now MEASURED (`_still_pending`), with the fleet's third outcome (-1 = could not verify) getting its own branch and its own message. |
| **D1/D2** (medium: the refusal helpers' return value can be misread; retry risk) | Real as a documentation defect: `False` means "the CYCLE was not resolved by this call", never "the release failed", and the callers must not retry on it. | Both docstrings now state the return semantics precisely, including the no-session case. |
| **D3** (minor: a message refers to "the cycle note above", which is not in the returned text) | Correct — the returned string has no such note. | Rewritten to be self-contained. |
| **D4** (minor: partial failure returned as success) | Correct against the MCP convention. | `is_error=True` when a lock could not be removed or a cycle is still PENDING — a count we could not verify is not a zero. |

### Accepted, DOCUMENTED, no code change — 2

- **B2** (medium: the REPORT path can silently renew a busy lock). The side effect is the
  documented liveness rescue and is deliberate, so removing it would undo a fix. What was
  genuinely missing is that the *agent-visible* output did not say it: the report now prints a
  NOTE that a lock can be renewed rather than declared dead, so a shorter list is not read as a
  miss.
- **B1** (high if agents are in separate trust domains: any agent can end another's lock). The
  severity depends on the trust model, and this fleet's model answers it: every agent on a host
  shares one unix user and one state directory, so the file mutex is one trust domain by
  construction — the tool cannot be more of an isolation boundary than the mutex it manages.
  Rather than add a `confirm=` flag that an agent could pass just as easily (friction without
  security), the tool description now states the trust assumption so a host that DOES isolate
  agents knows not to rely on it.

### Noted, not fixed — 1 (recorded as an issue)

- **C1** (medium: the predicate's blind spot). `_is_lock_stale` looks for commits in the LOCK'S
  OWN repo, so an agent working for a long stretch in a *different* repo can be declared dead
  after its TTL plus renewal budget. This is pre-existing behaviour that the purge already
  relies on — the reclaim did not introduce it, it inherits it — and the reclaim can never be
  more aggressive than the purge because it uses the same predicate. Closing it properly needs
  a liveness signal that survives a long governed-call gap in another repo (a process/session
  signal rather than commit archaeology), which is a design change of its own. Recorded as a
  governance issue with this reasoning.

### Rejected — 0 outright, but one severity corrected

- **A1** (high "until proven safe": the `blocked` path passes `args` rather than a named owner).
  The concern is right in shape and I closed it anyway — the blocked and terminal branches now
  name the resolved owner explicitly — but it was not a live defect: `_release_lock` resolves its
  session through the same `get_session_id(args)` contract that had just resolved the lock, so it
  could not have freed a peer's. Recorded that way rather than as a bug found, because "fix by
  inspection" and "fix a real defect" are different claims and only one of them is true.
