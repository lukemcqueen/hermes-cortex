#!/usr/bin/env bash
# [72b2c69b] RED -> GREEN for tests/test_doctor_no_ddl_schema_probe.py.
#
# RED is not "the test file before it was written" — it is the NEW test file run
# against the PRE-CHANGE revision, materialised in a throwaway worktree so the
# failures are reproducible from the committed tree alone:
#   bash docs/evidence/doctor-ddl-leak/red-green.sh
set -u
cd "$(dirname "$0")/../../.." || exit 1
REPO=$PWD
PY="$HOME/.hermes-cortex/venv/bin/python"
WT="$(mktemp -d "$HOME/.hermes/cache/scratch/ddl-red-XXXXXX")"
BASE="${BASE_REV:-HEAD~0}"

echo "# [72b2c69b] RED then GREEN — raw pytest output"
echo "# repo HEAD: $(git rev-parse --short HEAD)  ($(git log -1 --format=%cI))"
echo

echo "── 1. materialise the PRE-CHANGE tree at the parent of this commit ──"
git worktree add --detach "$WT" "$BASE" >/dev/null 2>&1
echo "worktree: $WT  HEAD=$(git -C "$WT" rev-parse --short HEAD)"
echo "pre-change call site present? $(grep -c -- '--apply-schema' "$WT/ops/scripts/manage/cortex_doctor/checks.py") occurrence(s)"
echo "pre-change _migrate_candidates present? $(grep -c '_migrate_candidates' "$WT/ops/scripts/manage/task-db.py") occurrence(s)"
echo

echo "── 2. RED — the new tests against the PRE-CHANGE files ──"
cp "$REPO/tests/test_doctor_no_ddl_schema_probe.py" "$WT/tests/"
( cd "$WT" && "$PY" -m pytest tests/test_doctor_no_ddl_schema_probe.py -q 2>&1 | tail -14 )
echo "  ^ each failure IS the report: the property the test pins does not hold"
echo "    on the pre-change tree, which is what makes the test a test."
echo

echo "── 3. GREEN — the same tests at this tip ──"
"$PY" -m pytest tests/test_doctor_no_ddl_schema_probe.py -q 2>&1 | tail -4
echo

echo "── 4. regression: the pre-existing task-db suites still pass ──"
"$PY" -m pytest tests/test_task_db_unit.py tests/test_task_db_v4.py -q 2>&1 | tail -4
echo

echo "── 5. cleanup ──"
git worktree remove --force "$WT" && echo "worktree removed rc=0"
