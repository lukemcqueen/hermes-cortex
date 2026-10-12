#!/usr/bin/env bash
# Re-runnable, NON-DESTRUCTIVE evidence for the 2026-10-12 orchestrator morning
# task pass (orch-task-morning-pass cron, job f6694d02d29c).
#
# It proves, from committed material, the three load-bearing claims of this
# pass — why 0 slices were dispatched today:
#
#   1. the two pr-2 TASK_REQUESTs sent on 2026-10-11 (ca282975, 72dc920b) were
#      CONSUMED by joseph (live bus: inbox_joseph depth 0), and
#   2. BOTH fleet slice rows are STILL pending on esther -> the dispatch left
#      no closure path back to the orchestrator's row (cross-host task rows are
#      local-only: task-db.py header, "Honest fleet semantics" B-3), and
#   3. the send-side dedup gate is PENDING-scoped (hc.py cmd_send), so once a
#      worker drains its queue the identical slice send is no longer refused --
#      the exact mechanism behind the >=5-morning repeat-dispatch thrash
#      (loop-governance issue #86). There is also no supported path to mark an
#      existing slice as handed-out, so it stays in the claimable pool.
#
# Read-only: no sends, no writes, no probes (nothing is queued anywhere).
# Run: bash docs/evidence/morning-task-pass-2026-10-12/verify-consumption.sh
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
TD="python3 ${HOME}/.hermes-cortex/scripts/task-db.py"
MOSES="mosesaaron"
RHC='python3 ~/.hermes-cortex/scripts/hc.py'
rc=0

echo "### 1. live bus: joseph's queue was drained (messages consumed) ###"
depth=$(ssh -o ConnectTimeout=10 -o BatchMode=yes "$MOSES" "$RHC status" 2>&1 | awk '/inbox_joseph/{print $NF}')
echo "inbox_joseph $depth"
case "$depth" in
  depth=0) echo "PASS: inbox_joseph empty -> 2026-10-11 dispatches consumed" ;;
  *)       echo "FAIL: inbox_joseph=$depth (still queued, or bus unreachable)"; rc=1 ;;
esac

echo
echo "### 2. ...but both fleet slice rows are still pending on esther ###"
rows=$($TD list --status pending 2>&1); td_rc=$?
if [ "$td_rc" -ne 0 ]; then
  echo "COULD NOT VERIFY: task-db.py list failed (rc=$td_rc) -> cannot count the pending rows"
  rc=1
else
  slices=$(printf '%s' "$rows" | grep -cE 'ca282975|72dc920b')
  echo "pending orchestrator rows matching ca282975/72dc920b: $slices"
  [ "$slices" -eq 2 ] && echo "PASS: both slices still pending -> no return path (issue #86)" \
                      || { echo "FAIL: expected 2 pending rows, got $slices"; rc=1; }
fi

echo
echo "### 3. claimable pool unchanged (frozen, not draining) ###"
# `task-db.py list --claimable` truncates its display at 10 rows, so count the
# pool the same way task_list_claimable does: pending AND unassigned.
claim=$(docker exec -i mycortex-postgres psql -U "mycortex_reader_${HERMES_PROFILE:-esther}" \
        -d "${TASK_DB_NAME:-mycortex}" -v ON_ERROR_STOP=1 -t -A \
        -c "SELECT count(*) FROM tasks.tasks WHERE status='pending' AND assignee IS NULL AND (kind IS NULL OR kind <> 'story')" 2>&1)
if ! [[ "$claim" =~ ^[0-9]+$ ]]; then
  # A failed/noisy psql used to leave this empty and let `[ "" -eq 16 ]` print a bash
  # arithmetic error — a check that cannot run must say so, not look like a count of 0.
  echo "COULD NOT VERIFY: claimable count unreadable (psql/docker unavailable): ${claim%%$'\n'*}"
  rc=1
else
  echo "claimable rows (pending, unassigned): $claim"
  [ "$claim" -eq 16 ] && echo "PASS: 16 claimable (same as 2026-10-10 and 2026-10-11)" \
                      || echo "NOTE: claimable=$claim (was 16 on 10-10/10-11)"
fi

echo
echo "### 4. dedup gate is PENDING-scoped (mechanism of the thrash) ###"
if grep -q 'identical message already pending in inbox_' "$HOME/.hermes-cortex/scripts/hc.py"; then
  echo "PASS: hc.py cmd_send refuses only on an ALREADY-PENDING duplicate"
  grep -n 'pending = bus_peek' "$HOME/.hermes-cortex/scripts/hc.py"
else
  echo "FAIL: dedup string not found in hc.py"; rc=1
fi

echo
echo "### 5. no supported path to mark an existing slice handed-out ###"
td_help=$($TD 2>&1)
if [ -z "$td_help" ]; then
  # task-db.py called bare PRINTS ITS USAGE AND EXITS 1 (measured 2026-10-12: rc=1 with
  # 3273 bytes of help), so the exit code cannot separate "dumped usage" from "crashed".
  # Empty output is the signal that it did not run at all — and without this guard an
  # unrunnable CLI fell through to the else-branch below and printed PASS.
  echo "COULD NOT VERIFY: task-db.py produced no output -> cannot inspect its 'update' verbs"
  rc=1
elif printf '%s' "$td_help" | grep -A3 'task-db.py update' | grep -q 'assignee'; then
  echo "NOTE: update now supports --assignee (hand-out path exists; re-check the method)"
else
  echo "PASS: 'update' exposes only --status/--reason -> no post-hoc assignee write"
fi
# grep's exit code separates "searched, no match" (1 = the PASS case) from "could not
# search" (2+). The old `2>/dev/null` form reported the latter as a PASS — a false PASS
# in a script whose whole purpose is evidence.
grep -rq 'handout_slice\|assign_slice' "$REPO/ops/services/tasks/schema"
g_rc=$?
if [ "$g_rc" -eq 0 ]; then
  echo "NOTE: a handout function now exists in the tasks schema"
elif [ "$g_rc" -eq 1 ]; then
  echo "PASS: no handout/assign function in ops/services/tasks/schema -> slices stay claimable"
else
  echo "COULD NOT VERIFY: could not search ops/services/tasks/schema (grep rc=$g_rc)"
  rc=1
fi

echo
echo "VERDICT: $([ $rc -eq 0 ] && echo PASS || echo FAIL)"
exit $rc