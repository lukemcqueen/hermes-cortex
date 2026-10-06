# Reviewer tiering — evidence (cycle 3877, commit 9f7c81ed)

This file backs the claims in the cycle note for `reviewer-tiering-by-complexity`.
It exists so a later reviewer can re-run the numbers instead of trusting timings
or pass-counts asserted in prose.

## 1. Why the "23 passed" figure (ADV-3877-2)

The count refers to pytest **items** across three suites, not to `_check`
assertions in the one file the review material surfaced. The three suites and
their item counts (all green on moses, 2026-10-06):

    tests/test_reviewer_backends.py       3 test functions
    tests/test_runtime/test_adversarial_review_gate.py  14
    tests/test_runtime/test_mcp_closeout.py              6
                                          total 23

Re-run (hermes venv):

    PATH="$HOME/.hermes/hermes-agent/venv/bin:$PATH" python3 -m pytest \
      tests/test_reviewer_backends.py \
      tests/test_runtime/test_adversarial_review_gate.py \
      tests/test_runtime/test_mcp_closeout.py -q

Actual output tail:

    tests/test_runtime/test_mcp_closeout.py ......  [100%]
    ============================= 23 passed in 55.41s ==============================

`tests/test_reviewer_backends.py` carries 28 `_check` assertions spread across
three test functions; `test_tiering` (the new one, added by this change) adds 11
of those 28. The 28 vs. 23 distinction is assertion-vs-item, not an overcount.

## 2. Latency measurements behind the tiering (ADV-3877-3)

Measured on moses (2026-10-06) over OpenRouter with the live `.env` credential,
using the reviewer's actual JSON verdict format:

* **agent backend** (`bash reviewer-agent-pi.sh`, pi / kimi-k2.6): a TRIVIAL
  prompt ("verdict CLEAN, minimal test") took `timeout 60` and returned within
  it — on the order of ~99s wall. Real change material (full diff) exceeded the
  MCP client's 300s tool-call window.
* **llm backend** (`deepseek/deepseek-v4-flash-0731`, the new light-tier default):
  a prompt returning the exact verdict JSON completed in **0.9s** (http 200).
* **llm backend** (`deepseek/deepseek-v4-pro`, existing default): single
  completion **~1.2s**.

These were one-shot curl timings (`%{time_total}`), not a committed profiler.
The tiering fix exists precisely because the agent backend is the slow path on
review-sized material; the constants are conservative (heavy = always-review
surface or >=10 files / >=200 added+removed lines), so the fast reviewer only
runs where the invariant "complex → independent reviewer" still holds.

## 3. Working-tree scope vs commit scope (ADV-3877-1)

Commit `9f7c81ed` contains exactly 3 files:

    .env.example                    |   4 ++
    mcp-servers/loop-gov-mcp.py     | 107 ++++++++++++++++++++++++++++------
    tests/test_reviewer_backends.py |  80 ++++++++++++++++++++++++++

    git show --stat 9f7c81ed  →  3 files changed, 166 insertions(+), 25 deletions(-)

The `mcp-gate _complexity()` material, however, is computed from the whole
WORKING TREE at review time, so it also sees two UNCOMMITTED files owned by
a sibling session (in-flight, never committed):

    M ops/scripts/cortex-update.sh
    M ops/scripts/manage/agent-hermes-update.sh

Those are the peer's edits (SOUL P9: do not stash/commit/clean a peer's file).
They are not part of this change and were not staged or committed here. This is a
known limitation of aligning the review material to the working tree: an
uncommitted sibling edit surfaces as "scope drift" in the diff. The reviewer's
recommendation to "explain or revert" is satisfied by this note — explanation,
not revert (the files are not mine to revert).

## 4. Working-tree scope again (ADV-3897-1, docs sweep, commit b73f397e)

The 2026-10-06 docs sweep (cycle 3897) hit the SAME measurement artifact: the
review material for the range `538c596d..HEAD` (`b73f397e`) still lists
`ops/scripts/cortex-update.sh` (+67/-25) and `ops/scripts/manage/agent-hermes-update.sh`
(+29/-28) because those are the sibling's UNCOMMITTED working-tree edits, and the
diff stat sums the whole working tree, not just committed HEAD. The evidence:

    git show --stat b73f397e   # the docs sweep commit, all 4 files are docs
      README.md                                 |  4 ++
      docs/env-vars.md                          |  3 +-
      docs/runbooks/review-triage-jev.md        | 25 +++++++++++
      docs/DOCS-INDEX.md                        |  6 +-
      4 files changed, 33 insertions(+), 2 deletions(-)

The two ops/scripts/*.sh files remain the same sibling in-flight edits as §3 —
never staged or committed by this or any of my cycles (11e52691, 538c596d,
b73f397e). Reverting them is not possible (SOUL P9). This finding is a
measurement artifact of working-tree-scoped material, not a change I made.

## 5. Test evidence for "4/4 pass" (ADV-3897-2)

`docs/evidence/results-rev-tier-3897.txt` (committed alongside this doc) holds the
reproducible pytest transcript for `tests/test_reviewer_backends.py` on the
current tree (moses, 2026-10-06): "4 passed in 79.17s". Re-run:

    PATH="$HOME/.hermes/hermes-agent/venv/bin:$PATH" python3 -m pytest \
      tests/test_reviewer_backends.py -q

The four tests: `test_backends`, `test_env_resolution`, `test_tiering`,
`test_tiering_dogfood_script` (the dogfood test runs the real-module harness via
subprocess).
