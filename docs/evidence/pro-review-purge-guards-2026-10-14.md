> `provenance: advisory`

> Provenance: an OPERATOR-REQUESTED advisory review of this session's work on the TTL sweep, not the
> close gate. The reviewer is the fleet's heavy model, called through the same cortex config the
> governance reviewer uses (key resolved by the module's own helper, never seen or passed here).
> The material was the changed functions extracted from BOTH files with `ast` — never retyped.
> The model's response below is VERBATIM; my accept/reject judgement follows it, separated by a
> marker, so a reader can always tell which words are the reviewer's.

# DeepSeek Pro gap review — the TTL sweep's guards (#124, #125)

model: deepseek/deepseek-v4-pro
endpoint: https://openrouter.ai/api/v1
usage: {"prompt_tokens": 7101, "completion_tokens": 2212, "total_tokens": 9313, "cost": 0.02203487, "is_byok": false, "prompt_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0, "audio_tokens": 0, "video_tokens": 0}, "cost_details": {"upstream_inference_cost": 0.02203487, "upstream_inference_prompt_cost": 0.01356291, "upstream_inference_completions_cost": 0.00847196}, "completion_tokens_details": {"reasoning_tokens": 0, "image_tokens": 0, "audio_tokens": 0}}
material: 29326 chars (functions extracted with ast from the committed revision)
temperature: 0 (a sampling reviewer is not a reviewer)

---

Excellent. I will review the provided code extracts against the stated questions and context. My findings are ranked by severity and concreteness.

### 1. FAIL CLOSED IN THE SWEEP — Missing Alert on Permanent Store Failure (Question B)

*   **Function:** `ops/scripts/manage/purge-stale-governance-locks.py` → `_close_pending_cycle`
*   **Finding:** The "fail closed" strategy is sound: if the cycle cannot be resolved, keeping the lock prevents a host-wide deadlock. However, the code's stated claim—that a kept lock is harmless because "the next sweep retries it"—creates a dangerous silent-failure mode if the database is permanently damaged or inaccessible. Every cron run will fail to read the DB, keep the lock, and print a line to `sys.stderr`. Over weeks, these stale locks will accumulate, no push-blocking leak occurs, but **no operator is alerted** that a fundamental error is persisting. The stdout line is lost in cron logs. This transforms a critical infrastructure failure into background noise.
*   **Change:** The `except sqlite3.Error` or `if-not-DB_PATH.exists()` paths must increment a distinct metric or fire a specific, high-severity alert on *consecutive* failures, not merely print to stderr. The `RETURNING FALSE` direction is correct; the observability of *why* it continues to be false is the gap.

### 2. THE WIDENED RESCUE — Indefinite Lock Retention via a Peer's Work (Question A)

*   **Function:** `mcp-servers/loop-gov-mcp.py` → `_session_worked_anywhere_since`
*   **Finding:** The claim is that widening the git-author check to any repo is safe because `LIVENESS_MAX_RENEWALS = 1` provides a bound. This bound is an *acquisition* bound, not a session-lifetime bound. The comment in `_refresh_lock_heartbeat` itself acknowledges the attack vector: "a commit by the lock's own agent proves activity, but it is also INFINITELY renewable by anything that keeps committing as that agent... At most ONE renewal per acquisition...". The crucial question is: what resets the `liveness_renewals` counter? From the provided extracts, there is no code shown that resets it on a new acquisition. If the counter is stored in the lock file and a new acquisition overwrites the file, this is safe. If the counter persists or is not atomically reset with the new session_id in the lock file under `_STATE_LOCK`, a sequence of `acquire -> work -> release -> acquire` in the same repo by the same author could keep the counter at 1 indefinitely, making the bound a one-time gate, not a per-session limit.
*   **Change:** **Would check** the lock acquisition path (likely `_acquire_lock` or similar, not provided) to confirm that `liveness_renewals` is unconditionally reset to 0 when writing a new lock file. The comment in `_refresh_lock_heartbeat` should explicitly state this dependency: "This budget is per-acquisition; a new acquisition must zero the counter."

### 3. THE WIDENED RESCUE — Commit Authorship is Not Proof of Holding the Lock (Question A)

*   **Function:** `mcp-servers/loop-gov-mcp.py` → `_is_lock_stale`, `_session_worked_anywhere_since`
*   **Finding:** The fundamental equivalence being drawn is `recent commit by agent ANYWHERE == lock holder is alive`. This is logically unsound and the code's own comments concede this. A CI/CD pipeline, a background sync daemon, or even a manual `git commit --author="Hermes <hermes@ai>"` run by an operator will all be treated as proof-of-life for *every single lock* held by that agent on the host. The worst case if the rescue is wrong in this direction (false-positive: keeping a truly dead lock alive) is exactly what you are designing against: a lock is never purged, and the session's task remains PENDING indefinitely, blocking future acquisitions by the *same* agent on the same task. You are trading a host-wide push block for a per-session soft-lock.
*   **Change:** The docstring should explicitly acknowledge this trade-off. The "renewal budget" is the only backstop. To strengthen it, consider scoping the rescue to commits in repos that share the same `remote.origin.url` as the lock's own repo, a stronger signal of "the same project context." Without this, a single automated process committing as a user can keep all of that user's stale locks alive across all of their random projects.

### 4. THE TWO CLOSERS — Token Parity Test is a False Comfort (Question C)

*   **Functions:** `mcp-servers/loop-gov-mcp.py` → `_close_cycle_unscored`, `ops/scripts/manage/purge-stale-governance-locks.py` → `_close_pending_cycle`
*   **Finding:** The test pins them by comparing SQL TOKENS. This is a dangerously weak assertion. The two functions have already drifted in critical behavioral semantics that a tokenizer cannot see:
    1.  **Resolution Scope:** `_close_cycle_unscored` resolves via `cycle_id` first, with a fallback to `task_id` that selects only the *single most recent* PENDING cycle (`ORDER BY id DESC LIMIT 1`). `_close_pending_cycle` resolves by `task_id` and updates *all* matching rows. If a task has multiple PENDING cycles (a real possibility with rapid concurrent acquisitions or bugs), the MCP closer leaves them behind as leaks, while the sweep closer correctly resolves them.
    2.  **Success Reporting:** `_close_pending_cycle` returns `True` if, after its update, `COUNT(*) WHERE task_id=? AND decision='PENDING'` is zero. This is robust. `_close_cycle_unscored` returns `True` if its `UPDATE ... WHERE id=?` has `rowcount > 0`. As noted in #1, if a `cycle_id` is provided but the row is already non-PENDING, it returns `False`. This is correct but fragile. A token parity test would pass both.
*   **Change:** The token parity test must be replaced with a behavioral parity test that validates against a DB fixture with multiple PENDING rows for one task, already-scored rows, and overridden rows. The token test is indeed a false comfort and will silently pass over the multi-PENDING-row leak.

### 5. REMAINING LEAK PATH — Lock Removal by MCP Server (Question D)

*   **Function:** Not in extract, but implied by `mcp-servers/loop-gov-mcp.py`'s `_close_cycle_unscored`'s docstring.
*   **Finding:** The docstring states `_close_cycle_unscored` is for "every release-first path (metadata refusal, work refusal, blocked transition)." This strongly implies there are MCP-internal code paths that release/remove a lock file and then call `_close_cycle_unscored`. If any of these paths calls the closer, gets a `FALSE` return (e.g., cycle already scored, DB error), and **proceeds to unlink the lock file anyway**, that is a remaining path that creates a lockless PENDING cycle. The `_close_cycle_unscored` function correctly fails open on error, but its callers might not enforce the contract.
*   **Change:** **Would check** all callers of `_close_cycle_unscored` in `loop-gov-mcp.py` (not provided) to confirm that a `FALSE` return value **blocks** the subsequent `os.unlink()` on the lock file, exactly as the purge script does. The function's error handling is correct; the caller integration is the vulnerability.

### 6. `_candidate_repos` Reuse Couples Distinct Guarding Decisions (Question F)

*   **Function:** `mcp-servers/loop-gov-mcp.py` → `_candidate_repos`
*   **Finding:** Sharing the function is acceptable, but the **cap** `LIVENESS_SCAN_MAX_REPOS` is a critical coupling that should stay independent. If the wrong-repo guard logic changes and requires a larger list, or if performance dictates a smaller one, the liveness rescue's correctness will be inadvertently and silently changed. The rescue's logic wants "all plausible repos, bounded by a safety cap." The guard wants "any evidence to prevent a false positive." These are divergent requirements.
*   **Change:** The `_session_worked_anywhere_since` function should manage its own cap using its own constant, independent of what `_candidate_repos` returns. The slice `[...][:LIVENESS_SCAN_MAX_REPOS]` decouples this perfectly and should remain.

### 7. Error Handling Misleading Operators (Question E)

*   **Function:** `ops/scripts/manage/purge-stale-governance-locks.py` → `purge`
*   **Finding:** The `P1-A` rule states "NEVER delete unparseable files — an unparseable lock is a lock being written right now." This is a wise fail-safe. However, the log message `print(f"skipping unparseable lock file (mid-write?): {lock_file.name}", file=sys.stderr)` is excessively vague. A file can be permanently unparseable due to disk corruption or a bug in the lock writer that outputs invalid JSON. The operator will see this message once per cron run, forever, with no guidance on how to distinguish a millisecond transient race from a permanent disk error.
*   **Change:** After a file remains unparseable and its mtime is older than the TTL, the script should escalate the log message. A file that is both unparseable and 2xTTL old is no longer "mid-write"; it is a corrupted artifact that requires manual operator intervention. The current logic will keep it and its PENDING cycle forever, which is a leak by a different name.
---

## What I did with it (the reviewer's advice is CLAIMS, not conclusions)

Seven findings. One of them was a real behavioural defect in code I had already shipped and
"tested", and the reviewer was right in a way my own test could not see — which is the whole reason
this review was worth running.

### Accepted and FIXED — 3

| Finding | What was actually wrong | Fix |
|---|---|---|
| **4** (the two closers) | Not a style point: **the two closers genuinely behaved differently.** `_close_cycle_unscored` resolved ONE PENDING row per task (`ORDER BY id DESC LIMIT 1`), the sweep's `_close_pending_cycle` resolved them ALL. A task carrying two PENDING rows kept one behind — the exact doctor leak both functions exist to remove. My earlier "parity" test compared SQL tokens and passed, because the queries are token-identical. | The MCP closer now resolves **every** still-PENDING, non-overridden row for the task and returns "this task has nothing pending" rather than "an UPDATE matched a row". The token test is demoted and explicitly labelled a drift smoke test; `tests/test_closer_parity_and_escalation.py` drives **both** implementations against the same fixtures (multiple PENDING rows, nothing pending, an overridden row). |
| **1** (silence on a broken store) | Fail-closed was right; the *observability* was not. "The next sweep retries it" is true and useless if the store is permanently broken: every run keeps the locks, prints a line, and exits 0 — an operator never learns. | The sweep now returns a `SweepResult` (`removed`, `kept_busy`, `kept_unresolved`, `corrupt`) and **exits 2** with an explicit `OPERATOR ACTION` message when it could not do its job. A cron that only ever exits 0 turns a repairable host into a permanent one. |
| **7** (unparseable file skipped forever) | Correct: an unparseable lock is protected as a "mid-write race" — but a file unparseable *and* untouched for hours is corrupt, and it can never be aged, so it and its cycle sit forever. | The sweep distinguishes the two by age (`> 2x TTL`): corrupt files are collected, reported with their age and an `OPERATOR ACTION`, and exit 2. Deliberately **not** deleted — a corrupt lock is still somebody's lock, and deleting it cannot resolve the cycle behind it. Both directions tested (a fresh unparseable file must stay a race and exit 0). |

### Verified, then DOCUMENTED — 2

- **2** (what resets `liveness_renewals`?) — the reviewer was right to refuse this on trust, and the
  answer holds: `begin_change` builds a **fresh** lock state dict, so a new acquisition carries no
  counter and the budget is per-acquisition. Documented as a load-bearing dependency in
  `_refresh_lock_heartbeat`, and **asserted** (`test_a_new_acquisition_starts_the_renewal_budget_over`)
  rather than merely claimed — writing that test is what made the docstring's claim true instead of
  an overclaim.
- **5** (callers that unlink after a `False`) — checked: the sweep *keeps* the lock on failure; the
  MCP's callers *release anyway*, and that is deliberate. Refusing to release would re-create the
  original bug (a live session dead-ended by a broken store, `force=True` the only exit). The two
  dispositions differ because what each alternative costs differs, and that reasoning is now written
  into the closer's docstring instead of being implicit.

### No change — 1

- **6** (the shared `_candidate_repos` couples two decisions) — the reviewer's own conclusion was
  that the slice `[:LIVENESS_SCAN_MAX_REPOS]` is the right decoupling and "should remain". It does;
  the cap constant already belongs to the rescue, not to the shared walk. Noted rather than changed.

### Declined, with reasons — 1

- **3** (tighten the rescue to repos sharing the lock's `remote.origin.url`) — rejected as proposed:
  it would re-narrow exactly the case #124 exists for, because a session doing a long stretch in a
  different project has a different remote **by definition**. The underlying criticism is sound and
  was accepted in the form that helps: the trade-off is now stated plainly (authorship is not
  identity — a cron committing as that agent, or `--author=`, reads as proof of life), the renewal
  budget is named as the backstop that makes it tolerable, and a per-session token from the enforcer
  is recorded as the stronger signal worth having.

### Not implemented from the review

- Per-finding "distinct metric / consecutive-failure counter" (finding 1). A non-zero exit on every
  affected run is the alert, and cron failure surfacing already reaches the operator. A consecutive
  counter needs durable state for a case the exit code already covers; recorded here so the choice is
  visible rather than silently dropped.
