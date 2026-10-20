#!/usr/bin/env bash
# Re-runnable capture for the blob-verdict rules-revision fix (2026-10-20).
#
# Read-only with respect to the repo: it writes only under a temp dir, and the pre-fix half is
# built by EXTRACTING the pinned revision with `git show` (no worktree is added, nothing in the
# repo is modified). Every block prints the command's own rc, measured bare.
#
# Usage:  bash docs/evidence/blob-rules-rev-2026-10-20-capture.sh
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REPO_SHOWN="~${REPO#$HOME}"   # the repo is public: never print an absolute home path
PRE_FIX_SHA="fab9388b"          # the pushed tip before this change
NEW_TEST="tests/test_blob_rules_rev.py"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/rulesrev.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

echo "blob-verdict rules revision — capture"
echo "generated: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "repo:      $REPO_SHOWN"
echo "pre-fix:   $PRE_FIX_SHA"
echo

echo "=== 1. the new pin, at the working tree ==="
( cd "$REPO" && python3 "$NEW_TEST" ) > "$WORK/green.txt" 2>&1
rc=$?
grep -E "^  FAIL|^ALL PASS|^FAIL \(" "$WORK/green.txt" || true
echo "rc=$rc   checks passed=$(grep -c '  PASS' "$WORK/green.txt")  failed=$(grep -c '  FAIL' "$WORK/green.txt")"
echo

echo "=== 2. the same pin against the PRE-FIX module (extracted with git show) ==="
mkdir -p "$WORK/pre/mcp-servers" "$WORK/pre/tests"
( cd "$REPO" && git show "$PRE_FIX_SHA:mcp-servers/loop-gov-mcp.py" ) > "$WORK/pre/mcp-servers/loop-gov-mcp.py"
cp "$REPO/$NEW_TEST" "$WORK/pre/tests/"
( cd "$WORK/pre" && python3 tests/test_blob_rules_rev.py ) > "$WORK/red.txt" 2>&1
rc=$?
echo "decisive check (the reported deadlock):"
grep -E "the blob IS re-sent to the reviewer|the stored verdict is invisible|the revision changes with the rules text" "$WORK/red.txt" || true
echo "rc=$rc   checks passed=$(grep -c '  PASS' "$WORK/red.txt")  failed=$(grep -c '  FAIL' "$WORK/red.txt")"
echo "  (section G reports NOT RUN here: this temp tree has no git history to read)"
echo

echo "=== 3. the suites this change touches, at the working tree ==="
for f in tests/test_blob_coverage_semantics.py tests/test_blob_judged_not_retried.py \
         tests/test_review_guidance.py tests/test_blob_deleted_scope.py \
         tests/test_reviewer_model_default.py tests/test_blob_review_concurrency.py; do
  ( cd "$REPO" && python3 "$f" ) > "$WORK/s.txt" 2>&1
  rc=$?
  printf "  %-44s rc=%s fails=%s\n" "$(basename "$f")" "$rc" "$(grep -c '  FAIL' "$WORK/s.txt")"
done
echo

echo "=== 4. the two files that are red on BOTH sides (pre-existing, not this change) ==="
for f in tests/test_close_budget_bounds.py tests/test_review_per_blob.py; do
  ( cd "$REPO" && python3 "$f" ) > "$WORK/now.txt" 2>&1; now=$?
  cp "$REPO/$f" "$WORK/pre/tests/"
  ( cd "$WORK/pre" && python3 "$f" ) > "$WORK/base.txt" 2>&1; base=$?
  echo "  --- $(basename "$f"): rc now=$now  rc at $PRE_FIX_SHA=$base"
  echo "      now : $(grep -cE '^  FAIL' "$WORK/now.txt") named FAIL line(s); $(grep -c 'SKIP' "$WORK/now.txt") SKIP (NOT RUN is its own outcome, never a pass)"
  echo "      base: $(grep -cE '^  FAIL' "$WORK/base.txt") named FAIL line(s); $(grep -c 'SKIP' "$WORK/base.txt") SKIP"
  diff <(grep -E "^  FAIL" "$WORK/now.txt") <(grep -E "^  FAIL" "$WORK/base.txt") >/dev/null \
    && echo "      the named failures are IDENTICAL on both sides" \
    || echo "      the named failures DIFFER — investigate before shipping"
done
echo
echo "NOTES"
echo "  - Section 2 is the RED half: at $PRE_FIX_SHA the blob is NOT re-sent (calls=[]), which is"
echo "    the deadlock a peer host reported. Section 1 is the GREEN half at the same assertions."
echo "  - Nothing here writes to the repo, the deploy tree or any governance store."
