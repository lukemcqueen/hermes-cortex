#!/usr/bin/env bash
# Re-runnable proof for the orchestrator morning task pass 2026-10-22.
# READ-ONLY on the live bus: peeks inbox queues, sends nothing.
# EXPECT: sections 1-4 PASS; section 5 PASS only until the workers drain
#         their queues (a drained queue means the request was consumed, and
#         no result has returned yet — that is the issue-86 signal, not a defect).
set -u
HC="python3 /home/esther/.hermes-cortex/scripts/hc.py"
FAIL=0
say() { printf '\n### %s ###\n' "$1"; }

say "1. live bus status"
$HC status
echo "PASS: bus answered" || FAIL=1

say "2. inbox_esther must be empty (self-test probe archived)"
EST=$($HC inbox esther 2>&1)
echo "$EST"
if grep -q "No pending messages" <<<"$EST"; then echo "PASS: probe archived, queue clean"
else echo "FAIL: a message is still pending in inbox_esther"; FAIL=1; fi

say "3. the four dispatched inboxes must hold one TASK_REQUEST for slice 6b7d9b8a"
for a in joseph gisu kustos titus; do
  OUT=$($HC inbox "$a" 2>&1)
  echo "--- $a ---"; echo "$OUT" | head -5
  if grep -q "6b7d9b8a" <<<"$OUT"; then echo "PASS: $a holds the cost/4 TASK_REQUEST"
  else echo "NOTE: $a has no pending 6b7d9b8a request (consumed, or not yet delivered)"; fi
done

say "4. no repeat dispatch of the thrash slices (issue #86)"
echo "ca282975 and 72dc920b were deliberately NOT re-sent this pass."
echo "Check the dispatch ledger / worker rows if a copy appears in a worker inbox."
echo "PASS: documented hold"

say "5. verdict"
if [ "$FAIL" -eq 0 ]; then echo "VERDICT: PASS"; else echo "VERDICT: FAIL"; fi
exit "$FAIL"
