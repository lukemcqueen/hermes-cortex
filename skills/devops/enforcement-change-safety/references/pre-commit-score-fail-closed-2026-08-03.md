# Incident: pre-commit-score fail-closed fix (2026-08-03)

## The misread that deleted scoring

Request: "Remove the stale score-cycle search/warn block from pre-commit-score so
the warning stops printing on every commit" (issue #16).

WRONG interpretation (what happened): "stale score-cycle block" was read as the
ENTIRE "Score the current commit" section — search loop, warn block, scoring
machinery, decision check. A python line-range deletion removed ~156 lines of
scoring (STAGED_FILES collection, PARENT_COMMIT, PASS_PCT pytest run,
ALL_CODE_FILE/PREV_FILE assembly, PYTHON_BIN selection, TASK_ID/CYCLE_NUM DB
query, the `timeout 30 "$SCORE_CYCLE"` invocation, the 2026-08-02 hard-block on
failure, and the DECISION echo/ERROR gate).

User reaction (verbatim signal): "DO NOT REMOVE SCORING. ARE YOU SERIOUS?",
"NEVER DECREASE SECURITY TO ENFORCER!!!!!!", "The entire function of loops is
eliminated without scoring", "The entire point of the fix needed was to INCREASE
SECURITY", "Instead of 'skipping', have the logic be FAIL IMMEDIATELY (if binary
is gone, etc.)".

CORRECT interpretation: the "stale block" is ONLY the PATH search loop + the
`if [[ -z "$SCORE_CYCLE" ]]; then echo warn; exit 0; fi`. The bug is the
`exit 0` — on hosts without the deprecated CLI it short-circuits the hook,
skipping the orchestrator-only paths guard, self-test, and adversarial scan that
run after the scoring section. Fix = keep ALL scoring, change the branch to
`exit 1` with a fail-closed message.

## The correct diff (what shipped)

```diff
-# If score-cycle doesn't exist, warn once per install
+# If score-cycle doesn't exist, HARD BLOCK — fail closed.
 if [[ -z "$SCORE_CYCLE" ]]; then
-  echo "⚠  score-cycle not found — skipping old scoring"
-  echo "   Current governance is MCP-based (begin_change → cycle_query → feedback_accept → end_change)"
-  exit 0
+  echo "❌  score-cycle not found — cannot record governance cycle."
+  echo "    Install it via the sanctioned path: bash ~/hermes-cortex/ops/scripts/cortex-update.sh"
+  echo "    No bypass flags — do NOT use --no-verify."
+  exit 1
 fi
```

One block changed, `exit 0` → `exit 1`, zero lines of scoring removed.

## The revert that nearly destroyed another session's work

After the bad deletion, a `git checkout -- ops/scripts/pre-commit-score` was the
correct selective revert (only my file). But then the commit sweep happened
(Rule 2 in SKILL.md): a plain `git commit` took 6 files another session had
staged (their PII scrub edits). Recovery sequence that worked:

```bash
# 1. Backup worktree FIRST — proof of no data loss
mkdir -p /tmp/safety-backup && for f in <files>; do cp "$f" "/tmp/safety-backup/$(echo $f | tr '/' '_')"; done
# 2. Undo the bad commit, keep index+worktree
git reset --soft HEAD~1
# 3. Separate foreign files back to unstaged (index-only, worktree untouched)
git restore --staged <foreign-file-1> <foreign-file-2> ...
# 4. Re-verify worktree == backup (sha256sum), commit ONLY your file
```

The sibling session then absorbed the commit into its own push (origin/main =
11d7eddd, same content) — the right move was to verify the final pushed state,
not fight it.

## Enforcer lock-test contamination proof

Failures: `TestHasGovernanceLock::test_corrupted_lock_file_returns_false` and
`test_deleted_lock_file_returns_false` (assert True is False).

Cause: `_has_governance_lock()` Phase 3 reads `_secondary_lock_path()` → repo
marker `.hermes-cortex/.governance-lock`, written by the ACTIVE lock of the
session running pytest. The test fixture only redirects Phase 1/2
(GOVERNANCE_STATE_DIR), not the repo-located Phase 3 marker.

Proof:
```bash
mv .hermes-cortex/.governance-lock /tmp/governance-lock.bak
pytest tests/test_runtime/test_governance_bypass.py::TestHasGovernanceLock -q   # 5 passed
mv /tmp/governance-lock.bak .hermes-cortex/.governance-lock
```

## Verification recipe for hook changes

```bash
bash -n ops/scripts/pre-commit-score && bash -n ~/.hermes-cortex/scripts/pre-commit-score
# fail-closed branch: run the extracted search+warn block with empty HOME + stripped PATH → expect exit 1
# scoring branch: run with scorer present → expect SCORER-PATH resolved, no early exit
# scoring machinery anchors: grep -cE 'SCORE_OUTPUT=\$\(timeout|ALL_CODE_FILE=\$\(mktemp|PREV_FILE=\$\(mktemp|SCORE_STDERR=\$\(mktemp|Hard block \(2026-08-02\)' <hook>
# deployed == repo: diff <(sed '1,2d' deployed) <(sed '1,2d' repo)   (strip SOURCE header)
# pytest: python3 -m pytest tests/ (2 lock tests will false-fail mid-lock — see Rule 3)
```
