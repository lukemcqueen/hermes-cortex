#!/usr/bin/env bash
# Re-runnable capture for the ADV-13116-1 fix (cycle 13253). READ-ONLY: it runs tests and reads
# git, and writes nothing into the repo (scratch files go to mktemp).
#
#   bash docs/evidence/adv-13116-1-capture.sh
#
# Every section prints its own exit status beside it. Nothing is piped into a tail, so no section
# can print a pass while an earlier command in the same section failed.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.." || exit 2
REPO="$PWD"
PRE_FIX="${PRE_FIX:-beeabecd}"          # the revision whose harness still carries the hardcoded path
SCRATCH="$(mktemp -d)" || exit 2
trap 'rm -rf "$SCRATCH"' EXIT

norm() { sed -e "s|$HOME|~|g" -e "s|$REPO|<repo>|g"; }

echo "### 1. the blobs under test (content-addressed) and the revision the FAILING half came from"
sha256sum tests/run_loop_gov_regression.py tests/test_run_loop_gov_regression_harness.py 2>/dev/null \
  || shasum -a 256 tests/run_loop_gov_regression.py tests/test_run_loop_gov_regression_harness.py
printf 'pre-fix half : %s (full sha of the revision whose harness carried the hardcoded venv path)\n' \
  "$(git rev-parse "$PRE_FIX")"
echo "the two sha256 lines above are the working-tree blobs this cycle commits; a reader verifies them"
echo "with: git show <tip>:<path> | sha256sum"

echo
echo "### 2. DISCRIMINATION — the guard must fail on the pre-fix harness and pass on the working copy"
git show "$PRE_FIX:tests/run_loop_gov_regression.py" > "$SCRATCH/harness.pre-fix.py" || exit 2
HARNESS_UNDER_TEST="$SCRATCH/harness.pre-fix.py" \
  python3 tests/test_run_loop_gov_regression_harness.py > "$SCRATCH/pre.log" 2>&1
rc_pre=$?
python3 tests/test_run_loop_gov_regression_harness.py > "$SCRATCH/post.log" 2>&1
rc_post=$?
printf 'pre-fix harness  rc=%s\n' "$rc_pre"
grep -E '^(FAIL|RESULT)' "$SCRATCH/pre.log" | norm
printf 'working copy     rc=%s\n' "$rc_post"
grep -E '^(FAIL|RESULT)' "$SCRATCH/post.log" | norm
if [ "$rc_pre" -eq 0 ]; then
  echo "ASSERTION FAILED: the guard PASSES on the pre-fix harness, so it proves nothing"
  exit 1
fi
if [ "$rc_post" -ne 0 ]; then
  echo "ASSERTION FAILED: the guard does not pass on the working copy"
  exit 1
fi
echo "asserted: rc=$rc_pre before the fix (non-zero), rc=$rc_post after"

echo
echo "### 3. the resolver a PEER runs — resolved through the repo, never a host-local path"
RESOLVED="$(bash ops/scripts/lib/python-with-module.sh --print pytest)"
rc_res=$?
printf 'python-with-module.sh --print pytest -> rc=%s  %s\n' "$rc_res" "$RESOLVED" | norm
if [ "$rc_res" -eq 0 ]; then
  "$RESOLVED" -m pytest --version | head -1
  "$RESOLVED" -c "import pytest, sys; print('pytest', pytest.__version__, 'for', sys.executable)" | norm
fi

echo
echo "### 4. CONSTRUCTED no-pytest host — the branch is exercised, not waited for"
env -i PATH=/nonexistent HOME="$HOME" "$(command -v bash)" \
  ops/scripts/lib/python-with-module.sh --print pytest > "$SCRATCH/none.log" 2>&1
rc_none=$?
printf 'with nothing on PATH -> rc=%s (3 = COULD NOT VERIFY, never a pass)\n' "$rc_none"
head -3 "$SCRATCH/none.log" | norm

echo
echo "### 5. the repair the harness names is committed, and pytest is DECLARED for it"
ls ops/scripts/manage/fix-cortex-venv.py ops/install/requirements.txt >/dev/null 2>&1
printf 'repair + declared set present: rc=%s\n' "$?"
grep -n '^pytest' ops/install/requirements.txt

echo
echo "### 6. deployment: tests/ is not in the deploy map, so this change needs no deploy step"
n_registered="$(grep -c 'register.*tests/' ops/scripts/cortex-update.sh)"
printf 'register() lines matching tests/ : %s\n' "$n_registered"
echo "(tests/ and docs/evidence/ are not deploy-map files; only the repo tree changes)"
