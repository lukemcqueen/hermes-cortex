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
| Scan (any covering receipt) | `review-receipt-check.py --scan <state_dir> <slug> <tip> <base>` → prints `1 <path>` or `0` |

**Bound to the range, not the repo.** Tip *and* base must match, so a receipt
earned for range A can never authorise range B. That replay is the one failure
that would make this gate worse than no gate. An **empty range** (`tip == base`,
nothing to push) never authorises, even when a receipt names it exactly.

**Runtime-only.** Receipts never live inside a repo.

## The receipt also stands in for the LOCK (2026-10-10)

Closing a cycle **releases** the lock, and the lock gate demands an **active** one —
so every close needed a second, no-content `push-<what>` cycle purely to carry the
lock back (cycles 12009, 12010, 12021 in one session). That is the mis-framed-cycle
shape cycle 12012 was refused for.

A push whose unpushed range is covered by a receipt now passes the lock gate too:

| Layer | Where | Question |
|---|---|---|
| hook | `ops/scripts/pre-push-pull` | before refusing "no active governance lock", does a receipt cover this range? |
| enforcer | `plugins/governance-enforcer/__init__.py` → `_push_authorised_by_receipt()` | the same question, before the `git push` call is blocked |
| the rule | `review-receipt-check.py --scan` | ONE implementation, called by both |

Nothing is relaxed: with neither a lock nor a covering receipt the push is refused
exactly as before. The receipt is *tighter* than a lock — it is written by a permitted
close and bound to the reviewed content, so a commit made after the close stops
covering it, and a peer's commit riding in the range is not covered either.

**What qualifies:** a LONE `git push` (optionally `cd <dir> && …` or `git -C <dir>`).
`--no-verify` (it skips the hook), a pipe/redirection/backtick/substitution, a
backgrounded push, two pushes, or any compound carrying other work are all refused —
a shape the matcher cannot prove is a refusal (`_git_push_repo_hint`). With no repo
named, the enforcer resolves it from the tool args, then the session's repo hint, and
refuses when it cannot.

**When it goes live.** The hook half is immediate: `cortex-update.sh` (and the
pre-commit DOGFOOD) copy it, and git forks the hook on every push, so the deployed
file is what runs. The enforcer half must be IN FORCE in the running gateway, and
that is measurable rather than assumed — esther, 2026-10-10: with NO active lock the
running enforcer permitted the push and the hook's carve-out authorised it
(`docs/evidence/push-receipt-carve-out-2026-10-10/08-live-lock-free-push.txt`). The
mechanism that put it in force (a deploy-time plugin reload, or a restart) is not
part of that observation. The deploy prints `GATEWAY RESTART REQUIRED` when it cannot
determine the gateway's start time — a banner, not a verdict. Settle the question by
observation (a lock-free push of a covered range), never by assuming either way.

## The rule does NOT apply to

Ordinary commits. A change touching none of the always-review paths pushes with
no review and no receipt. Do not wait for one.

## Workflow

1. Do the work, commit.
2. Close the cycle. The receipt is written automatically when the **close is
   permitted** — not only when a review runs.
3. Push. **No second cycle is needed to carry the lock** — the receipt the close
   just wrote also satisfies the lock gate (see above).

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
python3 tests/test_push_receipt_authorises.py # the lock carve-out: hook, enforcer, rule
python3 tests/test_push_receipt_boundaries.py # boundaries + differential vs the deployed enforcer
python3 tests/test_push_receipt_hook_live.py  # the SHIPPED hook on the real unpushed range
PUSH_RECEIPT_E2E=1 python3 tests/test_push_receipt_hook_live.py  # + the allow direction
python3 tests/test_review_receipt_writer.py   # the receipt producer
python3 tests/test_review_material_consistency.py  # Diff stat ⊆ diff body
python3 tests/test_review_material_scope.py   # working-tree scope of the measurement
python3 ops/scripts/lib/review-receipt-check.py <receipt.json> <tip> <base>
python3 ops/scripts/lib/review-receipt-check.py --scan <state_dir> <slug> <tip> <base>
```

`test_push_receipt_hook_live.py` asserts the refusal direction by default and the
allow direction only under `PUSH_RECEIPT_E2E=1`, because passing the lock gate lets
the hook run into its doctor gate and the mandatory dogfood — a real redeploy of the
host. Both directions skip (and say so) when nothing is unpushed.

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

---

## Whose work does the reviewer see? — the cycle's, not the checkout's

The material is built from the **commits in the cycle's window** (`base..HEAD`, scoped to the
authoring agent). A shared checkout does not change that: a peer's commits appear only as
labelled context, and a peer's *uncommitted* files are not in the material at all.

The complexity measurement, though, folds in the working tree — deliberately, so a worker
cannot dodge the gate by leaving risky edits uncommitted. In a **shared** checkout that used
to count every dirty path, including a peer's. So a simple change was measured as complex,
and the peer's paths appeared in the `Diff stat` the reviewer reads while their diff was
nowhere in the material — the reviewer reported material it could not see, and the close was
refused for work the cycle never did.

The rule now: **the working tree counts only for paths whose content changed since the cycle
began.** `begin_change` snapshots the dirty paths it finds (`path -> content hash`, capped at
300); at close, a path whose hash is unchanged belongs to whoever left it dirty, not to this
cycle. The anti-dodge property is intact — a worker's own edits change the file *during* the
cycle, so they are still counted. No snapshot at all (an older lock, or a tree over the cap —
logged) keeps the previous whole-tree behaviour: the fallback is stricter, never looser.

### The material keeps the same rule — plus one invariant

Scoping the *measurement* was only half the job. The `Diff stat` the reviewer reads was still
built from that wider set, so it named paths whose diff the material never showed. Cycle 10877
was charged as **fabrication** for exactly that:

> "The diff stat header claims 11 files changed with 578 lines of changes, but the worker
> simultaneously asserts no repository edits were made... A diff stat of non-zero changes
> with an unchanged HEAD is a contradiction." (ADV-10877-1, critical)

It fired two ways: a lock with **no snapshot** (every dirty path, a peer's included), and —
even with a correct snapshot — the cycle's **own** uncommitted edits, which the measurement
counts but a commit-built diff body cannot show.

The invariant: **a path is never named in the material without its diff being present.** The
`Diff stat` is built from the same range as the diff body (`base..HEAD`, the audited commit
range), and any working-tree path the measurement counted but the material does not show is
disclosed as `...[OUT OF SCOPE: ...]` — reported, never silently dropped, never named as
though its diff were there. The header counts are read back from the same rows that are
printed, so header, stat and diff cannot disagree.

With a clean commit the material is exactly the committed range and the disclosure is empty.
Leave work uncommitted and the reviewer sees an empty stat plus the disclosure — the honest,
fail-closed answer, because the commit is the artifact under review.

`tests/test_review_material_consistency.py` asserts the invariant in all three states (peer
dirt, own uncommitted edit, committed work); the committed case is the positive control, so a
"fix" that merely blanks the stat cannot pass.

## Why a repo-local `.hermes-cortex/` can reappear — and what catches it

Removing the directory is not the end of the job, because **two processes can
recreate it**, and for a while they did.

**The writers.** `loop-gov-mcp.py` (`_write_lock` → `_secondary_lock_path`) and
the governance enforcer each wrote `<repo>/.hermes-cortex/.governance-lock`. Both
are now disabled and both deployed copies are clean — but their *deployed files*
were fixed while the *running processes* still held the old revision. That is
**deploy ≠ load**: every `begin_change()` in that window wrote the marker again,
and once the marker file was cleaned by hand, an **empty directory shell** was
left behind. That empty shell is what reappeared.

**Why nothing reported it.** Two reasons, both now fixed:
1. `.gitignore` rules ignored paths inside `.hermes-cortex/`, so a recurrence was
   invisible to `git status`. Those rules are removed on purpose — unignored, a
   recurrence surfaces as untracked.
2. Nothing asserted the directory's *absence*. Now something does.

**The check.** `cortex-doctor` reports `Repo-local .hermes-cortex`:

| Situation | Result |
|---|---|
| absent | `PASS — absent — correct for the Cortex repo` |
| present (empty) | `FAIL`, names the path and its entries |
| present with `.governance-lock` | `FAIL`, and says governance state is being written inside the repo |

A `FAIL` here is the correct severity, not an over-reaction: the directory's
presence means a process is writing repo-local governance state, which is exactly
what removing it was for. If it fires, **restart the gateway** before deleting
anything — otherwise a stale process writes it straight back.

**Why it matters beyond tidiness.** Inside `~/hermes-cortex`, the name
`.hermes-cortex` shadows the *runtime* directory `~/.hermes-cortex`, so a marker
written there is indistinguishable from legitimate repo state — and it makes the
repo a consumer of the deploy it is meant to be the source of.

`tests/test_repo_local_cortex_dir_check.py` asserts the check fails on presence
and names the marker, so the guard cannot silently rot.
