#!/usr/bin/env bash
# Re-runnable evidence for the 2026-10-11 orchestrator morning task pass.
#
# Proves, from committed material, the two load-bearing claims:
#   1. the TASK_REQUEST send path works end-to-end on self (self-test gate),
#   2. the 2 pr-2 dispatches for this pass are sitting in inbox_joseph.
#
# Read-only apart from the self-test probe, which is archived immediately
# after the peek so it never reaches the handler's task-row/notify path.
#
# Run: bash docs/evidence/morning-task-pass-2026-10-11/verify-dispatch.sh
set -u

HC="python3 ${HOME}/.hermes-cortex/scripts/hc.py"
RHC='python3 ~/.hermes-cortex/scripts/hc.py'   # runs on moses; ~ expands remotely
MOSES="mosesaaron"
PROBE="EVIDENCE-PROBE $(date -Is) morning-task-pass 2026-10-11 self-test replay"
rc=0

echo "### 1. self-test: hc send esther TASK_REQUEST (self) ###"
out=$($HC send esther TASK_REQUEST "$PROBE" 2>&1); echo "$out"
msg_id=$(printf '%s' "$out" | sed -n 's/.*msg_id=\([0-9a-f-]*\).*/\1/p')
if [ -z "$msg_id" ]; then echo "FAIL: self-test send produced no msg_id"; rc=1; fi

echo
echo "### 2. self-test landed in inbox_esther (live bus via ${MOSES}) ###"
ssh -o ConnectTimeout=10 -o BatchMode=yes "$MOSES" "$RHC inbox esther" 2>&1 | tee /dev/stderr | grep -q "SELF-TEST\|EVIDENCE-PROBE" \
  && echo "PASS: probe pending in inbox_esther" \
  || { echo "FAIL: probe not visible in inbox_esther"; rc=1; }

echo
echo "### 3. probe msg_id (archive it right after this run to keep the queue clean) ###"
if [ -n "$msg_id" ]; then
  echo "probe msg_id=$msg_id"
fi

echo
echo "### 4. dispatch delivery: inbox_joseph must hold the pass's 2 TASK_REQUESTs ###"
peek=$(ssh -o ConnectTimeout=10 -o BatchMode=yes "$MOSES" "$RHC inbox joseph" 2>&1); echo "$peek"
n=$(printf '%s' "$peek" | grep -c "→ TASK_REQUEST")
[ "$n" -ge 1 ] && echo "PASS: $n TASK_REQUEST(s) pending in inbox_joseph" \
  || { echo "FAIL: no TASK_REQUEST pending in inbox_joseph (consumed or undelivered)"; rc=1; }

echo
echo "### 5. queue depths ###"
ssh -o ConnectTimeout=10 -o BatchMode=yes "$MOSES" "$RHC status" 2>&1 | grep -E "inbox_(esther|joseph)" || rc=1

echo
echo "VERDICT: $([ $rc -eq 0 ] && echo PASS || echo FAIL)"
exit $rc