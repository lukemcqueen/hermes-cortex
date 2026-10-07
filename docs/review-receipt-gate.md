# Review Receipt Gate

**What it does:** `pre-push` refuses to push a range that touches an
**always-review path** unless a **CLEAN review receipt** exists for that exact
range. Review before push, enforced by construction rather than by discipline.

---

## The problem it solves

The self-adversarial review ran at **close**, and closing is what releases the
lock a push requires. So the review structurally landed *after* the push, and
every finding arrived too late to change what shipped. Nothing but discipline
could order them correctly, and discipline is not a mechanism.

## The rule

| Thing | Where / value |
|---|---|
| Always-review paths | `ops/scripts/lib/always-review-paths.txt` — **single source**, read by both the hook and `loop-gov-mcp.py` |
| Receipt file | `~/.hermes-cortex/state/.reviewed-<repo_slug>-<tip_sha>.json` |
| Must say | `verdict: CLEAN`, and `tip_sha` **and** `base_sha` both matching the range being pushed |
| Checker | `ops/scripts/lib/review-receipt-check.py <receipt> <tip> <base>` → prints `1` or `0` |

**Bound to the range, not the repo.** Tip *and* base must match, so a receipt
earned for range A can never authorise range B. That replay is the one failure
that would make this gate worse than no gate.

**Runtime-only.** Receipts never live inside a repo.

## The rule does NOT apply to

Ordinary commits. A change touching none of the always-review paths pushes with
no review and no receipt. Do not wait for one.

## Workflow

1. Do the work, commit.
2. Close the cycle. The receipt is written automatically when the **close is
   permitted** — not only when a review runs.
3. Push.

**One trap, by design:** every new commit moves the tip and **invalidates the
receipt**. Push immediately after closing; if you commit again, re-review.

## Why a "simple" cycle still writes a receipt

Cycles that change no code have their review **skipped** (`simple (0 lines, 0
files) — skip`). The receipt is therefore written at the point the review gate
**stops objecting**, before the lock is released — covering all three ways a
close succeeds: review CLEAN, review skipped as simple, and all-LOW findings.

> The close being *permitted* is the authorisation event. A CLEAN review is one
> route to it, not the only one.

## Verify it yourself

```bash
python3 tests/test_review_receipt_gate.py     # gate logic + deployed hook refusal
python3 tests/test_review_receipt_writer.py   # the receipt producer
python3 ops/scripts/lib/review-receipt-check.py <receipt.json> <tip> <base>
```

## Pitfalls — all of them cost real time

**1. deploy ≠ load: the writer lives in the MCP server.**
The receipt is written by `loop-gov-mcp.py`. A running MCP child that started
before that file changed **cannot write receipts** — it holds the old revision
in memory. After deploying `loop-gov-mcp.py`, the gateway must restart.
`cortex-update.sh` watches this file (`_restart_pending`, commit `a19dcd8c`) and
prints a loud banner when a restart is pending. **Agents cannot restart the
gateway** (lifecycle guard) — if the banner fires, the operator restarts it.

**2. The lock is resolved from tool-call args.**
`_write_review_receipt` must resolve this session's lock the way the close path
does — from the args. An early version called `_read_lock(None)`, which cannot
identify a session, returned `None`, and bailed: the receipt was *never* written
and the gate was unsatisfiable while every code path looked correct. If you
touch this code, run `tests/test_review_receipt_writer.py`.

**3. A silent bail is a deadlock that looks like correctness.**
Both "no repo identity" and "HEAD unresolvable" returned without logging. The
failure presented as "the gate refuses and nothing says why". Both paths log
their exact values now — keep it that way.

**4. The gate and the producer ship together.**
Shipping the receiver without its producer means every always-review push is
refused fleet-wide, fail-closed and silent. If you change one, check the other.

## Related

- `ops/scripts/pre-push-pull` — the gate
- `ops/scripts/lib/always-review-paths.txt` — scope
- `ops/scripts/lib/review-receipt-check.py` — one validator, shared by hook and test
- `docs/pre-commit-scoring.md`, `docs/git-enforcement.md` — the wider hook chain

---

## Review material budget — and why docs get more

The reviewer sees a **bounded** window of the diff, disclosed when it is cut.
Two budgets exist:

| Range | Budget | Constant |
|---|---|---|
| Standard | 12,000 chars | `DIFF_CHAR_BUDGET` |
| **Docs-only** | **60,000 chars** | `DIFF_CHAR_BUDGET_DOCS` |

**Why docs differ.** For code, a head+tail window is a workable review — a
reviewer can still judge structure and notice a missing test. For docs the diff
*is* the artifact: truncating a docs diff is not a smaller review, it is **no**
review, because the reviewer cannot see the prose it is being asked to judge. A
39 KB docs range against the 12 KB budget put both the document and its evidence
in the omitted middle, and the cycle could not close.

**It is computed, never claimed.** `_range_is_docs_only()` reads the
`diff --git a/...` headers itself. A note saying "this is docs only" buys
nothing. The range qualifies only when **every** path ends `.md`/`.txt`/`.rst`
**and** no path is an always-review path — so `ops/install/hooks/README.md`
disqualifies the whole range despite being markdown. One non-doc path reverts
everything to the standard budget. A self-declared relaxation would be a bypass;
a computed one is a scope decision.

Docs-only ranges carry a `REVIEW MATERIAL POLICY` header naming the budget
applied, so a reviewer is never left inferring it.

**Still too big?** The notice says so plainly and tells you to **split the cycle**
rather than re-submitting prose. Raising a budget cannot make an unbounded diff
reviewable — splitting is the only honest answer past that point.

**The notice never instructs the reviewer.** An earlier marker said the content
was "readable with read_file", which read as a directive and was flagged as
injection. It now states the limit and stops.
