# Design request to the reviewer — reduce close-review friction without weakening review

**Provenance:** operator (Luke) asked for this review, 2026-10-18, after six `end_change`
calls in one session each hit the 300 s ceiling with no verdict. Cycle 12799. This file is
the reviewed material; the question below is the SUBJECT of the review, stated once, and is
not an attempt to steer your verdict.

## The question

Propose a concrete design for the close-time adversarial review that (a) keeps a real
independent verdict on every complex change, and (b) cannot stall the calling agent. Give
the specific edits — file, function, constant — and say what could break.

## Measured facts (one session, 2026-10-18, host esther)

| Cycle | Change | Result |
|---|---|---|
| 12777 | read-only fan/temp sampling, empty diff | refused: "prose-only claim" |
| 12779 | 79-line evidence transcript, 1 file | refused: 3 findings, all on a PEER's commit |
| 12782 | re-close of the same 1 file | 300 s timeout, no verdict, lock stranded |
| 12792 | 3-file docs plan, 153 lines, no code | 300 s timeout, no verdict |
| 12795 | 1-file docs commit, 41 lines | 300 s timeout, no verdict |
| 12797 | 1-file docs commit, 52 lines | 300 s timeout, no verdict |

Six stalls, the last three on documentation-only commits. A `force=True` was needed each
time to clear the resulting lock; the operator authorized that.

## The arithmetic (why it stalls)

`mcp-servers/loop-gov-mcp.py`:

- `REVIEWER_TIMEOUT_CEILING = 240` (line ~3333) — per-call ceiling, deliberately under the
  300 s Hermes MCP client window.
- `BLOB_REVIEW_BUDGET_S = 600.0` (line ~1069) — wall-clock budget for the PER-BLOB pass,
  which the close runs when the whole-range call cannot finish (`_review_or_refuse`, the
  `except` at ~5548 sets `REVIEW_INCOMPLETE` and re-routes; `_review_uncovered_blobs` at
  ~1149 does the work, reporting what it did not reach in `remaining`).
- A close can therefore spend 240 s on the range call AND THEN start a per-blob pass with a
  600 s budget. The caller stops waiting at 300 s and reports a timeout; the server is still
  working. Neither CLEAN, nor FINDINGS, nor an error reaches the agent.
- The module's own measurement (comment at ~1071): **blob calls ran 180–220 s**. So the
  per-call ceiling cannot simply be lowered — any budget under ~220 s cuts every heavy call,
  the per-blob pass then judges nothing, and a heavy change could never close at all.

## Constraints that must hold

1. The 300 s client window is fixed. Operator: *"the reviews should be shorter than 300s"* —
   raising a timeout is rejected.
2. Enforcement is unchanged: a complex change needs an independent CLEAN verdict before its
   cycle closes and before its content can be pushed. `ALWAYS_REVIEW_PATHS` (~3129) forces
   review for enforcement/security surface at any size.
3. Fail closed. A reviewer that cannot run, or material that cannot be judged, must refuse —
   never pass silently.
4. The reviewer must stay independent: fixed committed prompt, distinct model, a process the
   worker cannot reach.

## Secondary problem (same review path)

The review window is `lock-start..HEAD` (~5395). Every session on this host commits under ONE
git author (`esther-agent` — verified with `git log --format='%h %an %s'`), so a peer's
concurrent commit enters the window, is labelled only by an advisory provenance block
(~5410–5415 appends their diffs as context), and the always-review check at ~5424 runs over
that same window. Result measured in cycle 12779: a peer's `docs/cron-schedules.md` and
`skills/.../soul-refinement` produced scope-drift findings against this session, and this
session's own note ("no file, config or state changed") was filed as fabrication against
their 11 changed files. Author-based partitioning cannot fix it here, because the identity is
shared. A lock-derived commit trailer (`Cortex-Session: <session_id>`) is the candidate
discriminator; the question is whether that is the right seam, and what it costs.

## Options already tried or rejected

- **Lower `REVIEWER_TIMEOUT_CEILING` (240 → 120) and `BLOB_REVIEW_BUDGET_S` (600 → 120)** so
  the two budgets sum under 300 s. Written, then REVERTED unshipped: it cuts every blob call
  below its measured 180–220 s, so heavy reviews would never complete. This is the shortcut
  the design must avoid.
- **Raise the client/provider ceiling** — rejected by the operator.
- **Keep a lock-carrier cycle per push** — rejected (Rule 27): a lock-free push covered by a
  CLEAN receipt is legitimate, and re-gating it adds a content-free cycle per push.
- **A parallel review path or an agent-side bypass** — forbidden (`change-checklist`).

## What a good answer decides

1. Where the single clock lives, and how each pass is handed what REMAINS of it.
2. What the agent receives when the window closes with work unjudged — the exact shape, so a
   retry can continue instead of re-doing (the per-blob verdict cache exists: `_blobs_with_clean_verdict`).
3. Whether one heavy call per window is enough, or whether the range must be SPLIT before the
   first call so each piece fits.
4. How a docs-only or trivial change avoids paying the close-time review cost at all, without
   letting a code change hide behind that predicated on a self-declared class.
5. Whether the session discriminator above is worth its cost, or whether coverage-by-receipt
   already makes peer blobs harmless.
