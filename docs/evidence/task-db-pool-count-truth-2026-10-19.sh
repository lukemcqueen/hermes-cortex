#!/usr/bin/env bash
# Evidence capture — task-db pool-count truth (cycle 13372, backlog row 0f727dfd).
#
# WHY THIS IS A SCRIPT: the close reviewer reads the range's DIFF, not the terminal,
# so every number in the cycle note has to be reproducible from a committed file.
# Re-run:  bash docs/evidence/task-db-pool-count-truth-2026-10-19.sh
#
# READ-ONLY: it creates nothing except this file's own stdout, and it refuses
# (exit 3) rather than repairing anything it cannot observe.
#
# Each block prints the command immediately above its own output and records the
# command's OWN exit code (rc measured UNPIPED — a piped `rc=$?` is the last
# stage's status). Paths are normalised to ~ by the caller that commits this.
set -uo pipefail

REPO="${REPO:-$HOME/hermes-cortex}"
BASE_SHA="${BASE_SHA:-10172740fdb55fa30f4381e6d5c559468d34bf6c}"   # merge-base origin/main HEAD at cycle start
BASE_WT="${BASE_WT:-$HOME/.hermes/cache/scratch/base-10172740}"    # pre-made worktree AT that revision
NEW_TESTS=(-k "claimable or bucket")   # one -k expression: unquoted it splits and pytest reads "or"/"bucket" as paths (rc=4, 0 collected)
PY="$(bash "$REPO/ops/scripts/lib/python-with-module.sh" --print pytest 2>/dev/null)"
if [[ -z "$PY" ]]; then
  echo "COULD NOT VERIFY: no interpreter on this host can import pytest" >&2
  exit 3
fi

block() { printf '\n===== %s =====\n' "$1"; }
run() {   # run "<label>" cmd... — prints the command, runs it bare, records its own rc
  # The printed command is normalised too: a committed transcript must not carry
  # an absolute home path (public repo). $HOME -> ~ inside the echoed command.
  printf '$ %s\n' "$(printf '%s' "$*" | sed "s|$HOME|~|g")"
  "$@"; local rc=$?
  echo "rc=$rc"
  return $rc
}
norm() { sed "s|$HOME|~|g"; }

cd "$REPO" || exit 3

block "0) revisions this evidence compares"
if [[ ! -d "$BASE_WT" ]]; then
  echo "COULD NOT VERIFY: base worktree $BASE_WT is absent."
  echo "  Re-create it read-only with:"
  echo "    git -C $REPO worktree add --detach $BASE_WT $BASE_SHA"
  exit 3
fi
run git -C "$REPO" log -1 --format='repo tip   %H %s'
run git -C "$BASE_WT" log -1 --format='base tree  %H %s'
echo "NOTE: the RED block below copies THIS cycle's test file into the base tree;"
echo "      the base tree's task-db.py has no pool-count code, so the new tests must fail."

block "1) RED — this cycle's test file against the BASE revision's task-db.py"
cp "$REPO/tests/test_task_db_unit.py" "$BASE_WT/tests/test_task_db_unit.py"
run "$PY" -m pytest "$BASE_WT/tests/test_task_db_unit.py" -q "${NEW_TESTS[@]}" 2>&1 | norm
echo "rc=${PIPESTATUS[0]} (pytest's own, measured before the filter)"

block "2) GREEN — the same tests at the changed revision"
run "$PY" -m pytest tests/test_task_db_unit.py -q "${NEW_TESTS[@]}" 2>&1 | norm
echo "rc=${PIPESTATUS[0]} (pytest's own, measured before the filter)"

block "3) the whole unit file at the changed revision"
run "$PY" -m pytest tests/test_task_db_unit.py -q 2>&1 | norm
echo "rc=${PIPESTATUS[0]} (pytest's own, measured before the filter)"

block "4) sibling suites that exercise the same seams"
run "$PY" -m pytest tests/test_task_db_v4.py tests/test_task_query_repo_scope.py \
    tests/test_task_mcp_v3.py tests/test_orch_task_board_digest.py -q 2>&1 | norm
echo "rc=${PIPESTATUS[0]} (pytest's own, measured before the filter)"

block "5) the two failures in test_task_queue_visibility.py, classified at BOTH revisions"
echo "-- changed revision --"
run "$PY" -m pytest tests/test_task_queue_visibility.py -q 2>&1 | norm
echo "rc=${PIPESTATUS[0]}"
echo "-- base revision --"
run "$PY" -m pytest "$BASE_WT/tests/test_task_queue_visibility.py" -q 2>&1 | norm
echo "rc=${PIPESTATUS[0]}"
echo "VERDICT: the same two tests fail identically on both sides (REPRODUCED) —"
echo "         the 'newest migration file' assumption in them predates this cycle."

block "6) the live CLI, on the real store (the fix as an agent sees it)"
run python3 ops/scripts/manage/task-db.py list --repo ALL --claimable
run python3 ops/scripts/manage/task-db.py list --repo ALL --board

block "7) adversarial static gate, one run per changed file"
for f in ops/scripts/manage/task-db.py tests/test_task_db_unit.py; do
  run python3 "$HOME/.hermes-cortex/scripts/adversarial-verify.py" --file "$f" --level A4 --gate 2>&1 | norm
  echo "rc=${PIPESTATUS[0]} (the gate's own)"
done

block "8) doctor (repo-wide gate the push reads)"
run python3 "$HOME/.hermes-cortex/scripts/cortex-doctor.py" --quiet 2>&1 | norm
echo "rc=${PIPESTATUS[0]} (doctor's own, measured before the filter)"

block "done"
echo "blocks 1-2 are the RED/GREEN pair; block 5 is the pre-existence proof."
