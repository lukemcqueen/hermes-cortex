# Per-blob close pass: five defects and the fix plan

**Status:** plan, submitted to the governed reviewer before any code is written.
**Cycle:** 13843 (`fix-perblob-close-deadlock`).
**Scope:** `mcp-servers/loop-gov-mcp.py` plus tests. Nothing here credits coverage a
verdict did not earn; every change moves toward "judge again", never toward "authorise".

## The reported symptom

A close refused four times, quoting a state that reads as self-contradictory:

```
⏳ Cannot close yet: 1 blob(s) of the push range still carry no review verdict.

  reviewed this pass : 0 blob(s)
  CLEAN in the range : 0 blob(s)
  already judged, not clean: 1 blob(s) — re-reviewing identical content cannot
    change the verdict; fix the file and commit it (the fix is a new blob)
    instead of closing again
  unreviewed paths:
     - <path>
  judged and NOT clean — fix these, the fix is a NEW blob:
     - <path>
```

The same path appears as `unreviewed` and as `already judged`; the pass did no work
(`reviewed this pass : 0`); the range reports `CLEAN ... 0` while the cycle-level
re-review returned CLEAN. The agent action the message asks for does not change the
output, which is what makes it a one-way gate.

## Code map (`file:function:line`)

- `mcp-servers/loop-gov-mcp.py:_review_uncovered_blobs:1429` — the per-blob pass.
  `covered` (1460) and `recorded` (1465) decide eligibility; `room` (1501) and the
  `wave` guard (1502) decide how many are attempted:
  `wave = ([] if (time.monotonic() - started) > budget_s else eligible[:room])`.
  Every sha the wave misses is appended to `remaining` (1503) and reported as
  unreviewed work.
- `_blobs_with_recorded_verdict:1310` — any admissible non-UNJUDGED verdict puts a blob
  on the SKIP list; `already_judged` (1494) and `remaining` (1495) both receive that sha.
- `_complete_push_range_blobs:2290` — the close-side caller. `remaining` (2381) refuses
  the close, `calls` prints as `reviewed this pass` (2418), `clean_count` prints as
  `CLEAN in the range` (2410), `already_judged` prints as `judged and NOT clean` (2397)
  while `remaining_paths` prints as `unreviewed paths` (2411).
- `end_change` call site `7275-7281` — `cap=CLOSE_BLOBS_PER_WINDOW` (4) and
  `budget_s=_close_budget_left(close_started)`, where `close_started` (7261) is set
  BEFORE `_adversarial_review_gate` (7262). The blob pass therefore gets what the range
  call left of ONE 240s window (`CLOSE_TOTAL_BUDGET_S:1122`).
- `_adversarial_review_gate:7003` — `_call_reviewer(prompt, ...)`, the range call. The
  module's own record puts a reviewer call at 180-220s (`1105-1131`).
- `_rereview_change:6251` — replaces the CYCLE row in `adversarial_reviews` (6326) and
  nothing else; `blob_reviews` is untouched.
- `_extract_verdict:5631` — already guarantees a judge that returns no findings yields
  UNJUDGED, not FINDINGS-with-an-empty-list. That wedge was closed earlier; it is named
  here so the fix below is not confused with it.

## The five defects

### D1 — a starved pass reports blobs as pending work

`budget_s` arriving at the pass is `240 - (time spent in the range call)`. After a
180-220s range call the pass holds 20-60s, while one blob call needs 180-220s: every call
in the wave is cut at the deadline, `calls` stays 0, and every blob lands in `remaining`.
The close then prints `reviewed this pass : 0` beside a list of blobs presented as queued
work, though the pass attempted nothing.

The output cannot distinguish "judged some, left the rest" from "had no time to start".
Four identical refusals were produced this way.

Measured arithmetic: the guard at 1502 tests `elapsed > budget_s` where `elapsed` is
~0 and `budget_s` is the remainder — so a positive remainder ISSUES a wave that cannot
finish, and a zero/negative remainder issues none at all. Neither case is distinguishable
in the result dict.

### D2 — `rereview_change` CLEAN does not invalidate the per-blob verdict it judged

`_rereview_change` re-runs the reviewer live over the cycle's range and replaces the
`adversarial_reviews` row. A `blob_reviews` row that is recorded but not covered keeps the
blob on the skip list and in `remaining`, so the close stays refused on a verdict the
range-level review has already superseded — two stores describing one range and
disagreeing about whether a problem exists. The module already treats that disagreement
as a defect class on the other store (`2356-2371`, cycle 13253).

### D3 — `CLEAN in the range` always reads 0

`2410` calls `_blobs_with_covered_verdict(blobs)` with no `rules_rev`; `_admissible:1263`
returns False for an empty revision. The counter is therefore 0 on every close regardless
of the store: a diagnostic that cannot state the truth, printed directly above the counts
that justify the refusal.

### D4 — one path printed as both `unreviewed` and `already judged`

`already_judged` is a subset of `remaining` by design (a skipped blob is not covered, so
the receipt must not name it — pinned by `tests/test_blob_judged_not_retried.py`). The
refusal prints `remaining` under `unreviewed paths:` and `already_judged` under
`judged and NOT clean`, so any path in both prints twice with contradictory labels. The
data contract is right; the presentation is not.

### D5 — the close cannot tell "nothing eligible" from "nothing attempted"

Both give `calls == 0`, and the remedies differ: the first means the CONTENT must change
(its verdict is stored, and re-sending identical bytes cannot produce a different answer),
the second means the close needs another attempt.

## The fix

### F1 — the pass reports what it ATTEMPTED (`_review_uncovered_blobs`)

Two new keys beside the existing ones:

- `eligible` — count of blobs with no admissible verdict, i.e. this pass's candidates;
- `budget_starved` — True iff `eligible > 0` and the wave was empty because the clock
  left no room for one measured call, i.e. the pass attempted NOTHING.

Existing keys keep their exact meaning (`remaining` still holds every uncovered sha,
`already_judged` the skipped ones, `calls` the judged count), so
`test_blob_judged_not_retried.py` and `test_blob_review_concurrency.py` stay true.

A floor makes the decision explicit instead of incidental:
`BLOB_REVIEW_MIN_CALL_S = 180.0`, the low end of the measured 180-220s band. A wave is
issued only when the remaining budget can fit one measured call. Below the floor, starting
calls can only produce timeouts that are never credited.

### F2 — a zero-work pass is an ENGINE condition (`_complete_push_range_blobs`)

Three outcomes, three names, no two states sharing one:

| condition | verdict marker | what the message states |
|---|---|---|
| `calls == 0` and `budget_starved` | `REVIEW_WINDOW_SPENT` (new) | the range review spent the close's window; ZERO blob calls were attempted, so the count is the engine's limit and not blob work; retry `end_change` now — the range verdict is stored, so the next close reaches the blob pass with a full window |
| `calls == 0` and `eligible == 0` | `REVIEW_PENDING` (unchanged) | every outstanding blob already carries a not-clean verdict for its EXACT content; only a content change moves it |
| `calls > 0` | `REVIEW_PENDING` (unchanged) | the pass judged N and reports what is left |

`REVIEW_WINDOW_SPENT` is not satisfiable by editing files, so it must not be presented as
if it were.

### F3 — one path, one label (the refusal text)

- `never judged — still need a verdict:` lists `remaining` MINUS `already_judged`;
- `judged and NOT clean — their content must change:` lists `already_judged`;
- both counts are printed, so the two sets are visibly disjoint and sum to `remaining`.

### F4 — the range counter asks the question the close asks

`clean_count` passes `rules_rev=_rules_rev(template)`, the same revision the pass and the
coverage set use, so `CLEAN in the range` reports the store rather than a constant.

### F5 — a `rereview_change` CLEAN invalidates the per-blob verdicts it judged

After `_adversarial_review_gate(..., force=True)` returns None (CLEAN), `_rereview_change`
deletes the `blob_reviews` rows for blobs inside the range that re-review judged, and
reports the count in its reply and its log line.

The direction is one-way by construction: rows are DELETED, so those blobs are re-judged
live on the next close and are never marked covered. A rereview can cost a review; it can
never buy coverage. The range comes from ONE implementation — the gate's own base
expression (`6831-6834`) is extracted to `_review_window_base(repo, lock)` and called by
both, so the rows cleared are exactly the blobs that were judged.

## Rejected options

- **Delete the whole `blob_reviews` cache on rereview.** Clears verdicts for content the
  re-review never saw (a peer's commits in the same push range). Authorising by erasure
  what was not judged.
- **Mark the cleared blobs COVERED rather than deleting the rows.** Range verdict
  authorising per-blob content nobody judged; turns `rereview_change` into a
  coverage-granting tool.
- **Raise the client window past 300s.** Operator requirement: reviews stay under 300s
  (`CLOSE_TOTAL_BUDGET_S:1122`).
- **Run the blob pass before the range gate.** Redistributes the window on every close,
  including the fast ones, and reverses the documented precedence (wide range → REQUIRED
  per-blob).
- **Re-send already-judged content when nothing else is eligible.** Identical bytes cannot
  produce a different verdict; it burns the window and reports progress that cannot come.
- **A new `--force`/skip flag.** No bypass is added; `REVIEW_WINDOW_SPENT` refuses exactly
  as `REVIEW_PENDING` does and writes no receipt.

## Evidence already in hand

- `_close_budget_left` (`1138-1144`) clamps at 0, and the guard at 1502 compares elapsed
  time against it — so a spent window yields an empty wave with no distinguishing signal.
- `_admissible:1263` returns False for an empty `rules_rev`, and the `clean_count` call at
  2410 passes none, so the counter is structurally 0.
- `_blobs_with_recorded_verdict:1310-1349` returns any admissible non-UNJUDGED verdict, and
  the pass puts that sha into BOTH lists (1494-1495), which is what prints one path twice.

## Tests (written first, watched RED before the code)

1. `tests/test_perblob_zero_work_is_engine_condition.py`
   - starved pass (budget below the floor, one candidate): `calls == 0`,
     `budget_starved is True`, `eligible == 1`, blob in `remaining`;
   - the close over that result refuses with `REVIEW_WINDOW_SPENT`, does not present the
     blob as queued blob work, and does not list the path under `never judged`;
   - all-already-judged (ample budget, one recorded non-clean blob): `budget_starved is
     False`, `eligible == 0`, and the message names the content change as the only remedy;
   - a pass with budget and work still reports `calls == 1` (no regression).
2. `tests/test_perblob_refusal_labels.py` — the rendered refusal lists any path in exactly
   one of the two lists, and `CLEAN in the range` reports the store's real count (non-zero
   for a stored CLEAN blob under the current revision).
3. `tests/test_rereview_clears_stale_blob_verdicts.py` — with an injected store and a
   stubbed gate, the rereview path deletes exactly the non-covered rows inside the
   re-reviewed range, leaves covered rows and out-of-range rows alone, reports the count,
   and the cleared blob is eligible (not covered) on the next pass.

Each test drives the real functions with an injected store: no live governance DB, no
network, and no call to `begin_change`/`feedback_accept` against the live store.

## As built (deltas from the plan above, recorded rather than backdated)

1. **The floor lives at the CLOSE, not inside the pass.** `BLOB_REVIEW_MIN_CALL_S` is enforced in
   `_complete_push_range_blobs` before it calls `_complete_blob_reviews`, so
   `_review_uncovered_blobs` keeps its contract ("attempt what the caller allows") and its existing
   tests keep their meaning. The window arithmetic being fixed is specific to the close that shares
   its window with the range gate; a sweep/CLI caller passes no budget and is untouched.
2. **No new pass-level result keys were needed.** `remaining`/`already_judged`/`calls` already
   carry everything the three-way message needs, so D5 is solved at the close with no signature
   change. Fewer moving parts, and no risk of a second definition of "eligible".
3. **The revision sweep grew to four call sites**, because reading the code for F4 turned up three
   more instances of the same defect: `_unreviewed_paths` (scope note), the SIBLING REVIEW STATUS
   block inside `_blob_material` (wrong information fed to the judge), and `_receipt_blobs` (every
   receipt this module wrote named only deletions, so the push gate lost content coverage). One
   class, one fix, one test file — `tests/test_coverage_readers_pass_rules_rev.py`.
4. **`require_full` now also accepts `REVIEW_WINDOW_SPENT`.** Without it the next close's early
   "not an always-review range" exit would skip the blob pass entirely — the engine-condition
   refusal would have turned into a way to close with no per-blob coverage at all.
5. **`tests/test_close_budget_bounds.py` was repaired, not just adjusted.** Two of its checks were
   already RED at the range base (`b2c2d25a`) — a cap-duration assertion that predates the
   concurrent wave, and an "unreached blobs are REPORTED" fixture whose sub-second budget could
   never leave anything unreached (the wave's deadline has a 1.0s floor). Both are now asserted
   against the behaviour that exists, and the forwarding value moved above the floor so it still
   measures the hand-off rather than the floor.
