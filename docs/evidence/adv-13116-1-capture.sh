#!/usr/bin/env bash
# Re-runnable capture for the ADV-13116-1 / ADV-13253-1 fix. READ-ONLY against the repo: it runs
# tests and reads git, and writes nothing inside the tree (scratch goes to mktemp).
#
#   bash docs/evidence/adv-13116-1-capture.sh
#
# Every section prints its own exit status beside it, captured BARE (never a pipe's), so no section
# can print a pass while an earlier command in the same section failed.
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/../.." || exit 2
REPO="$PWD"
PRE_FIX="${PRE_FIX:-beeabecd}"          # the revision whose harness carried the hardcoded venv path
SCRATCH="$(mktemp -d)" || exit 2
trap 'rm -rf "$SCRATCH"' EXIT

norm() { sed -e "s|$HOME|~|g" -e "s|$REPO|<repo>|g"; }

echo "### 1. the blobs under test (content-addressed) and the revision the FAILING half came from"
sha256sum tests/run_loop_gov_regression.py tests/test_run_loop_gov_regression_harness.py \
          tests/test_ensure_pytest.py ops/scripts/lib/ensure-pytest.sh 2>/dev/null \
  || shasum -a 256 tests/run_loop_gov_regression.py tests/test_run_loop_gov_regression_harness.py \
                 tests/test_ensure_pytest.py ops/scripts/lib/ensure-pytest.sh
printf 'pre-fix half : %s (the revision whose harness carried the hardcoded venv path)\n' \
  "$(git rev-parse "$PRE_FIX")"
echo "the sha256 lines above are the blobs this change carries; verify with:"
echo "  git show <tip>:<path> | sha256sum"

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
echo "### 3. the CREATE step is committed, and pytest is DECLARED for it (ADV-13253-1)"
git ls-tree -r HEAD -- ops/scripts/lib/ensure-pytest.sh \
                       ops/scripts/health/check-package-age.py \
                       ops/scripts/manage/fix-cortex-venv.py \
                       ops/install/requirements.txt \
                       ops/scripts/cortex-update.sh
rc_tree=$?
printf 'git ls-tree rc=%s (each row above is a blob at the reviewed tip)\n' "$rc_tree"
grep -n '^pytest' ops/install/requirements.txt
grep -n 'scripts/lib/ensure-pytest.sh' ops/scripts/cortex-update.sh

echo
echo "### 4. the age gate is real — it queries the registry for pytest TODAY"
python3 ops/scripts/health/check-package-age.py --min-days 14 pip pytest > "$SCRATCH/age.log" 2>&1
rc_age=$?
printf 'check-package-age.py pip pytest -> rc=%s\n' "$rc_age"
tail -3 "$SCRATCH/age.log" | norm

echo
echo "### 5. the CREATE step, run for real on this host and run AGAIN (idempotent by import)"
out_a="$(bash ops/scripts/lib/ensure-pytest.sh 2>"$SCRATCH/a.err")"; rc_a=$?
out_b="$(bash ops/scripts/lib/ensure-pytest.sh 2>"$SCRATCH/b.err")"; rc_b=$?
printf 'run 1 rc=%s -> %s\n' "$rc_a" "$(printf '%s' "$out_a" | norm)"
printf 'run 2 rc=%s -> %s\n' "$rc_b" "$(printf '%s' "$out_b" | norm)"
printf 'stderr (run 1, must be empty when pytest is already present): %s\n' "$(norm < "$SCRATCH/a.err")"
if [ "$rc_a" -ne 0 ] || [ "$rc_b" -ne 0 ]; then
  echo "ASSERTION FAILED: ensure-pytest.sh did not reach a usable pytest (rc=$rc_a, rc=$rc_b)"
  exit 1
fi
if [ "$out_a" != "$out_b" ]; then
  echo "ASSERTION FAILED: two runs disagreed — $out_a vs $out_b"
  exit 1
fi
echo "asserted: same interpreter on both runs, rc=0"

echo
echo "### 6. the CREATE step's branches, CONSTRUCTED (never waited for) against a fabricated repo"
python3 tests/test_ensure_pytest.py > "$SCRATCH/ensure.log" 2>&1
rc_ensure=$?
printf 'tests/test_ensure_pytest.py rc=%s\n' "$rc_ensure"
grep -E '^(FAIL|RESULT)|^  ' "$SCRATCH/ensure.log" | norm
if [ "$rc_ensure" -ne 0 ]; then
  echo "ASSERTION FAILED: the branch matrix does not pass"
  exit 1
fi

echo
echo "### 7. the resolver finds pytest through the fleet venv the create step provisions"
RESOLVED="$(bash ops/scripts/lib/python-with-module.sh --print pytest)"
rc_res=$?
printf 'python-with-module.sh --print pytest -> rc=%s  %s\n' "$rc_res" "$RESOLVED" | norm
if [ "$rc_res" -eq 0 ]; then
  "$RESOLVED" -m pytest --version | head -1
  "$RESOLVED" -c "import pytest, sys; print('pytest', pytest.__version__, 'for', sys.executable)" | norm
fi

echo
echo "### 8. CONSTRUCTED no-pytest host — the branch is exercised, not waited for"
env -i PATH=/nonexistent HOME="$HOME" "$(command -v bash)" \
  ops/scripts/lib/python-with-module.sh --print pytest > "$SCRATCH/none.log" 2>&1
rc_none=$?
printf 'with nothing on PATH -> rc=%s (3 = COULD NOT VERIFY, never a pass)\n' "$rc_none"
grep -m1 'COULD NOT VERIFY' "$SCRATCH/none.log" | norm
