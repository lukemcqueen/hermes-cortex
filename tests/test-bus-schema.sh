#!/usr/bin/env bash
# test-bus-schema.sh — Comprehensive bus schema + DLQ chain tests
#
# Tests the SQL-level guards that prevent infinite DLQ-of-DLQ creation.
# Every test creates its own test data and cleans up after itself.
# Run via: bash test-bus-schema.sh
#
# Three code paths that could create DLQ-of-DLQ:
#   1. bus.requeue()   — called by SLA watchdog, bus clients
#   2. bus.recover_timeouts() — called every 5min by cron
#   3. bus.read() on main queue → auto-fallback to DLQ — called by bus consumers
#
set -eu
P=0; F=0
pass() { P=$((P+1)); echo "  ✅ $1"; }
fail() { F=$((F+1)); echo "  ❌ $1${2:+ — $2}"; }

PSQL="docker exec mycortex-postgres psql -U mycortex -d mycortex -t -A"
TEST_QUEUE="test_dlq_guard_$$"
TEST_DLQ="${TEST_QUEUE}_dlq"

cleanup() {
  $PSQL -c "DELETE FROM bus.messages WHERE queue_name LIKE '${TEST_QUEUE}%'" 2>/dev/null || true
  $PSQL -c "DELETE FROM bus.queues WHERE name LIKE '${TEST_QUEUE}%'" 2>/dev/null || true
}
trap cleanup EXIT

echo ""
echo "═══ 1. SQL Function Guard Exists ═══"

GUARD_EXISTS=$($PSQL -c "
  SELECT count(*) FROM pg_proc p
  JOIN pg_namespace n ON p.pronamespace = n.oid
  WHERE n.nspname = 'bus' AND p.proname = 'requeue'
    AND pg_get_functiondef(p.oid) LIKE '%v_is_dlq%';
" 2>/dev/null)
if [ "$GUARD_EXISTS" = "1" ] || [ "$GUARD_EXISTS" = "t" ]; then
  pass "bus.requeue() has v_is_dlq guard"
else
  fail "bus.requeue() MISSING v_is_dlq guard — DLQ-of-DLQ possible"
fi

echo ""
echo "═══ 2. Requeue on Main Queue → Moves to DLQ ═══"

# Create a test queue with message, max_retries=1 so one requeue triggers DLQ move
$PSQL -c "INSERT INTO bus.queues (name, max_retries) VALUES ('${TEST_QUEUE}', 1) ON CONFLICT DO NOTHING;" 2>/dev/null
MSG_ID=$($PSQL -c "INSERT INTO bus.messages (queue_name, body, retry_count, max_retries, state)
  VALUES ('${TEST_QUEUE}', '{\"test\":true}', 0, 1, 'pending')
  RETURNING msg_id::text;" 2>/dev/null | head -1)

# Requeue once (retry_count goes 0→1, 1>=1 so it moves to DLQ)
$PSQL -c "SELECT bus.requeue('${TEST_QUEUE}', '${MSG_ID}'::uuid, 'test requeue');" 2>/dev/null

# Verify message moved to DLQ
NEW_Q=$($PSQL -c "SELECT queue_name FROM bus.messages WHERE msg_id = '${MSG_ID}'::uuid;" 2>/dev/null | head -1)
if [ "$NEW_Q" = "${TEST_DLQ}" ]; then
  pass "Main queue message moved to DLQ after requeue (retries exhausted)"
else
  fail "Expected ${TEST_DLQ}, got ${NEW_Q}" "Main queue requeue failed"
fi

echo ""
echo "═══ 3. Requeue on DLQ → Stays in Place (Guard) ═══"

# Now requeue again on the DLQ message
$PSQL -c "SELECT bus.requeue('${TEST_DLQ}', '${MSG_ID}'::uuid, 'test DLQ requeue');" 2>/dev/null

# Verify message STAYED in same DLQ (no DLQ-of-DLQ)
STAY_Q=$($PSQL -c "SELECT queue_name FROM bus.messages WHERE msg_id = '${MSG_ID}'::uuid;" 2>/dev/null | head -1)
if [ "$STAY_Q" = "${TEST_DLQ}" ]; then
  pass "DLQ message stayed in ${TEST_DLQ} after requeue (guard works)"
else
  fail "DLQ message moved to ${STAY_Q}" "Guard FAILED — DLQ-of-DLQ created"
fi

# Verify no DLQ-of-DLQ queue was auto-created
CASCADE=$($PSQL -c "SELECT count(*) FROM bus.queues WHERE name LIKE '${TEST_DLQ}_dlq%';" 2>/dev/null | head -1)
if [ "$CASCADE" = "0" ]; then
  pass "No DLQ-of-DLQ queue created for ${TEST_DLQ}"
else
  fail "${CASCADE} cascade DLQ queues created" "Guard against DLQ-of-DLQ FAILED"
fi

# Verify the error message is set correctly
DLQ_ERROR=$($PSQL -c "SELECT error FROM bus.messages WHERE msg_id = '${MSG_ID}'::uuid;" 2>/dev/null | head -1)
if echo "$DLQ_ERROR" | grep -q "DLQ end-of-line"; then
  pass "DLQ message has correct end-of-line error marker"
else
  fail "Got error: ${DLQ_ERROR}" "Expected 'DLQ end-of-line'"
fi

echo ""
echo "═══ 4. Requeue on DLQ × 5 (Stress: No Chain Growth) ═══"

for i in $(seq 1 5); do
  $PSQL -c "SELECT bus.requeue('${TEST_DLQ}', '${MSG_ID}'::uuid, 'stress test ${i}');" 2>/dev/null
done

STAY_Q=$($PSQL -c "SELECT queue_name, retry_count FROM bus.messages WHERE msg_id = '${MSG_ID}'::uuid;" 2>/dev/null | head -1)
CASCADE_AFTER=$($PSQL -c "SELECT count(*) FROM bus.queues WHERE name LIKE '${TEST_DLQ}_dlq%';" 2>/dev/null | head -1)
if [ "$CASCADE_AFTER" = "0" ]; then
  pass "After 5 requeues on DLQ: 0 cascade queues (guard holds)"
else
  fail "${CASCADE_AFTER} cascade queues after 5 requeues" "Stress test FAILED"
fi

echo ""
echo "═══ 5. recover_timeouts() — DLQ Messages Not Re-Moved ═══"

# Create a message in a DLQ with max_retries=1 that's been in 'processing' past timeout
# This simulates what happens when a DLQ message times out
DLQ_MSG2=$($PSQL -c "INSERT INTO bus.messages (queue_name, body, retry_count, max_retries, state, timeout_at)
  VALUES ('${TEST_DLQ}', '{\"test\":true}', 1, 1, 'processing', now() - interval '1 minute')
  RETURNING msg_id::text;" 2>/dev/null | head -1)

# Run recover_timeouts
$PSQL -c "SELECT bus.recover_timeouts();" 2>/dev/null

# Verify message did NOT move to a deeper DLQ. Current behavior (queue.sql
# Step 2): exhausted DLQ processing messages (retry_count >= max_retries,
# past timeout) are DELETED — no deep-chain. So the message is either still
# in TEST_DLQ (retried) or GONE (deleted). Both are correct; a deeper DLQ
# is the failure.
DLQ2_Q=$($PSQL -c "SELECT queue_name FROM bus.messages WHERE msg_id = '${DLQ_MSG2}'::uuid;" 2>/dev/null | head -1)
if [ "$DLQ2_Q" = "${TEST_DLQ}" ] || [ -z "$DLQ2_Q" ]; then
  pass "recover_timeouts() kept DLQ message in same queue (or deleted exhausted — no deep-chain)"
else
  fail "recover_timeouts() moved DLQ message to ${DLQ2_Q}"
fi

CASCADE_2=$($PSQL -c "SELECT count(*) FROM bus.queues WHERE name LIKE '${TEST_DLQ}_dlq%';" 2>/dev/null | head -1)
if [ "$CASCADE_2" = "0" ]; then
  pass "recover_timeouts() created 0 DLQ-of-DLQ queues"
else
  fail "recover_timeouts() created ${CASCADE_2} cascade DLQs"
fi

echo ""
echo "═══ 6. bus.read() on Main Queue → DLQ Fallback (No Cascade) ═══"

# Create a message deep in a DLQ (simulating what read() auto-fallback might see)
DEEP_DLQ="${TEST_QUEUE}_deep_dlq"
$PSQL -c "INSERT INTO bus.queues (name, is_dlq, parent_queue) VALUES ('${DEEP_DLQ}', true, '${TEST_QUEUE}') ON CONFLICT DO NOTHING;" 2>/dev/null
DEEP_MSG=$($PSQL -c "INSERT INTO bus.messages (queue_name, body, retry_count, max_retries, state)
  VALUES ('${DEEP_DLQ}', '{\"test\":true}', 1, 1, 'pending')
  RETURNING msg_id::text;" 2>/dev/null | head -1)

# read() from the main queue should NOT cascade — the main queue has no DLQ fallback
# that creates deeper chains. The read() function checks is_dlq before falling back.
READ_RESULT=$($PSQL -c "SELECT bus.read('${TEST_QUEUE}', 1) IS NOT NULL;" 2>/dev/null | head -1)
# This reads from the DLQ fallback of the main queue, which is ${TEST_DLQ}
# The deep DLQ message shouldn't be visible here since ${TEST_DLQ} is the parent

NEW_CASCADE=$($PSQL -c "SELECT count(*) FROM bus.queues WHERE name LIKE '${TEST_QUEUE}_deep_dlq_dlq%';" 2>/dev/null | head -1)
if [ "$NEW_CASCADE" = "0" ]; then
  pass "bus.read() created 0 cascade DLQs (DLQ fallback is safe)"
else
  fail "bus.read() created ${NEW_CASCADE} cascade DLQs"
fi

echo ""
echo "═══ 7. End-to-End: SLA Watchdog Import (No Requeue on DLQs) ═══"

# Verify the sla_watchdog module's _check_dlqs() no longer calls requeue
WATCHDOG_CODE=$(python3 -c "
import ast, sys
with open('/home/moses/hermes-cortex/core/cortex_bus/workflow/sla_watchdog.py') as f:
    tree = ast.parse(f.read())
for node in ast.walk(tree):
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == 'requeue':
            print('FOUND requeue call at line', node.lineno)
            sys.exit(1)
print('No requeue calls found - CLEAN')
" 2>/dev/null)
if echo "$WATCHDOG_CODE" | grep -q "CLEAN"; then
  pass "sla_watchdog.py has zero bus.requeue() calls"
else
  fail "sla_watchdog.py still has bus.requeue() calls" "$WATCHDOG_CODE"
fi

echo ""
echo "═══ 8. Production: Verify No Cascade DLQs in Live Queues ═══"

CASCADE_LIVE=$($PSQL -c "
  SELECT count(*) FROM bus.queues
  WHERE is_dlq = true
    AND name LIKE 'inbox_%_dlq_dlq%';
" 2>/dev/null | head -1)
if [ "$CASCADE_LIVE" = "0" ]; then
  pass "Production queues: 0 cascade DLQs"
else
  fail "${CASCADE_LIVE} cascade DLQs in production" "Run cleanup: DELETE FROM bus.queues WHERE name LIKE '%_dlq_dlq%'"
fi

echo ""
echo "═══ Summary ═══"
echo "  ${P} passed, ${F} failed"
[ "$F" -eq 0 ] || echo "  ❌ SOME TESTS FAILED — investigate before shipping"
exit $F
