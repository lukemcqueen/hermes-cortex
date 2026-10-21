#!/usr/bin/env bash
# Capture for cycle 13457 (task a6bb2da4) — the evidence interpreter fix.
#
# Every block below is the actual output of the command shown, with the command's
# own rc measured unpiped (a piped rc is the LAST stage's status). Re-run with:
#   bash docs/evidence/task-queue-evidence-interpreter-2026-10-20-capture.sh
# The script writes nothing in the repo; it prints the transcript on stdout.
set -uo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BASE="$(git -C "$REPO" merge-base origin/main HEAD)"
TIP="$(git -C "$REPO" rev-parse --short HEAD)"
WT=/tmp/tq-evidence-base-wt

echo "# Task-queue evidence — interpreter capability, before/after (cycle 13457, task a6bb2da4)"
echo "# host: esther · range base: $(git -C "$REPO" rev-parse --short "$BASE") · tip: $TIP"
echo "# Every block is the actual output of the command above it; rc is measured unpiped."
echo

echo "## BEFORE — the report committed at the range base carries a NOT-RUN as its evidence"
echo '$ git show '"$BASE"':docs/evidence/task-queue-remediation.md | grep -e "test_hc_harness passes" -e "No module named"'
git -C "$REPO" show "$BASE:docs/evidence/task-queue-remediation.md" | grep -e "test_hc_harness passes" -e "No module named"
echo "[rc=$?]"
echo

echo "## BEFORE — the provenance test at the range base (worktree), run by the repo runner"
echo '$ git worktree add --detach '"$WT"' '"$BASE"' && cd '"$WT"' && bash tests/run-tests.sh tests/test_task_queue_evidence.py -q'
git -C "$REPO" worktree remove --force "$WT" >/dev/null 2>&1
git -C "$REPO" worktree add --detach "$WT" "$BASE" >/dev/null 2>&1
add_rc=$?
if [ "$add_rc" -eq 0 ]; then
  ( cd "$WT" && bash tests/run-tests.sh tests/test_task_queue_evidence.py -q )
  echo "[rc=$?]"
else
  echo "[COULD NOT VERIFY: worktree add rc=$add_rc]"
fi
echo

echo "## AFTER — same test at the tip, run by the repo runner"
echo '$ bash tests/run-tests.sh tests/test_task_queue_evidence.py -q'
( cd "$REPO" && bash tests/run-tests.sh tests/test_task_queue_evidence.py -q )
echo "[rc=$?]"
echo

echo "## AFTER — regenerating the report, and the report's own load-bearing rows"
echo '$ bash ops/scripts/manage/run-task-queue-evidence.sh'
( cd "$REPO" && bash ops/scripts/manage/run-task-queue-evidence.sh )
echo "[rc=$?]"
echo
echo '$ grep -n -e "test_hc_harness passes" -e "Verdict" docs/evidence/task-queue-remediation.md'
grep -n -e "test_hc_harness passes" -e "Verdict" "$REPO/docs/evidence/task-queue-remediation.md"
echo "[rc=$?]"
echo

echo "## COULD NOT VERIFY — constructed: no candidate interpreter can import pytest"
echo '# the stub below is created here so the block is re-runnable: a python3 that'
echo '# fails every import probe, on a PATH that has no venv, under a HOME with none.'
mkdir -p /tmp/fakebin /tmp/nohome
printf '#!/bin/sh\nexit 1\n' > /tmp/fakebin/python3
chmod +x /tmp/fakebin/python3
echo '$ PATH=/tmp/fakebin:/usr/bin:/bin HOME=/tmp/nohome bash ops/scripts/manage/run-task-queue-evidence.sh'
( cd "$REPO" && PATH=/tmp/fakebin:/usr/bin:/bin HOME=/tmp/nohome bash ops/scripts/manage/run-task-queue-evidence.sh )
echo "[rc=$? — 3 = refused to emit a report]"
echo
echo '$ wc -l docs/evidence/task-queue-remediation.md   # unchanged by the refusal'
wc -l < "$REPO/docs/evidence/task-queue-remediation.md"
echo "[rc=$?]"

git -C "$REPO" worktree remove --force "$WT" >/dev/null 2>&1
