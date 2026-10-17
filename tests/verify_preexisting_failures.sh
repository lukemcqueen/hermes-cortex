#!/usr/bin/env bash
# Reproducible PROOF that the failing loop-governance regression tests are PRE-EXISTING.
#
# Why this script is committed rather than described (adversarial finding ADV-12971-1 on
# docs/evidence/close-budget-bound-2026-10-18.txt): that file records
# `python3 tests/run_loop_gov_regression.py` as rc=1 with five failing files. A note that SAYS
# "these predate my change" is an unverifiable claim — a later reviewer has nothing to re-run.
#
# This script is the re-runnable form of that claim. It checks out the PARENT revision into a
# throwaway git worktree and runs the same five files at BOTH revisions, then reports per file
# whether the two exit codes AGREE. Agreement means the failure is not introduced by the change
# under test; a DIFFERENCE means this script exits non-zero so the regression is not waved away.
#
# Usage:  bash tests/verify_preexisting_failures.sh [parent-rev]     (default: HEAD~1)
# Exit:   0 = every failure reproduces identically on the parent revision
#         1 = at least one file behaves differently between the two revisions
#         2 = the harness itself could not run (bad revision, no git, worktree refused)
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PARENT="${1:-HEAD~1}"
PER_TEST_TIMEOUT="${PER_TEST_TIMEOUT:-200}"

# Exactly the files the runner reports as failing. Scope of the artifact must equal scope of
# the claim, so this list is the failing set and nothing else.
TESTS=(
  "tests/run_non_hermes_lock_release_repro.py"
  "tests/test_loop_gov_stale_purge.py"
  "tests/test_reviewer_backends.py"
  "tests/test_refused_close_visible.py"
  "tests/test_python_with_module.py"
)

tmp="$(mktemp -d)" || exit 2
cleanup() { git -C "$REPO" worktree remove --force "$tmp" >/dev/null 2>&1 || rm -rf "$tmp"; }
trap cleanup EXIT

git -C "$REPO" rev-parse --verify --quiet "$PARENT" >/dev/null || {
  echo "cannot resolve revision '$PARENT' in $REPO" >&2; exit 2; }
PARENT_SHA="$(git -C "$REPO" rev-parse --short "$PARENT")"
HEAD_SHA="$(git -C "$REPO" rev-parse --short HEAD)"

git -C "$REPO" worktree add -q "$tmp" "$PARENT" || {
  echo "could not create a worktree at $PARENT_SHA" >&2; exit 2; }

echo "parent revision : $PARENT_SHA   (worktree $tmp)"
echo "current         : $HEAD_SHA    (working tree $REPO)"
echo
printf '%-48s %-10s %-10s %s\n' "test file" "parent" "current" "verdict"

differ=0
for t in "${TESTS[@]}"; do
  ( cd "$REPO" && timeout "$PER_TEST_TIMEOUT" python3 "$t" >/dev/null 2>&1 ); cur=$?
  ( cd "$tmp"  && timeout "$PER_TEST_TIMEOUT" python3 "$t" >/dev/null 2>&1 ); par=$?
  if [ "$par" = "$cur" ]; then
    verdict="SAME (pre-existing)"
  else
    verdict="*** DIFFERENT — not pre-existing ***"
    differ=1
  fi
  printf '%-48s %-10s %-10s %s\n' "$t" "rc=$par" "rc=$cur" "$verdict"
done

echo
if [ "$differ" = "0" ]; then
  echo "RESULT: every listed failure reproduces identically on $PARENT_SHA before the change,"
  echo "        so none of them is a regression introduced by $HEAD_SHA."
else
  echo "RESULT: at least one file differs between $PARENT_SHA and $HEAD_SHA — the change is"
  echo "        implicated. Treat the differing file as a regression from this range."
fi
exit "$differ"
