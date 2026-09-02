#!/usr/bin/env bash
# test-learnings-schema.sh — L1 hermetic AC battery for the learnings schema
# (F-001 fleet learning ledger).
#
# From docs/design/learning-ledger.md §testing (party L-1..L-6):
#   hermetic scratch DB `learnings_test` (refuses `mycortex` with a
#   guard), schema-apply idempotency (run twice → no-op), capture() dedup
#   (same route+content → same id, deduped=true), scrub hook (email/IPv4/
#   home-path → placeholders), INSERT-only enforcement (reader can EXECUTE
#   capture but has NO table DML), set_status gate, RLS fail-closed (a
#   temp un-granted worker role sees zero rows; the granted lifecycle role
#   reads), bus schema untouched after apply.
# v002 (F-006): set_status(id, status, impact) — 3-arg revises impact_score,
#   2-arg keeps it, out-of-range impact rejected, reader EXECUTE re-granted.
#
# Mirrors tests/test-tasks-schema.sh (same pass/fail pattern).
#
# Run: bash tests/test-learnings-schema.sh
set -eu
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MIGRATE_PY="${REPO_DIR}/ops/services/learnings/migrate.py"
TEST_DB="${LEARNINGS_TEST_DB:-learnings_test}"
CONTAINER="${LEARNINGS_TEST_CONTAINER:-mycortex-postgres}"
TEST_WORKER_ROLE="learnings_test_worker"   # temp role, dropped in cleanup

if [[ "$TEST_DB" == "mycortex" ]]; then
  echo "❌ REFUSING to run against the $TEST_DB database — hermeticity guard. Set LEARNINGS_TEST_DB." >&2
  exit 1
fi

PSQL="docker exec ${CONTAINER} psql -U mycortex -d ${TEST_DB} -t -A"
PSQL_SUPER="docker exec ${CONTAINER} psql -U mycortex -d mycortex -t -A"

P=0; F=0
pass() { P=$((P+1)); echo "  ✅ $1"; }
fail() { F=$((F+1)); echo "  ❌ $1${2:+ — $2}"; }

cleanup() {
  # Drop the temp worker role (cluster-level — must drop from any DB)
  docker exec ${CONTAINER} psql -U mycortex -d mycortex -c \
    "DROP ROLE IF EXISTS ${TEST_WORKER_ROLE};" >/dev/null 2>&1 || true
  $PSQL_SUPER -c "DROP DATABASE IF EXISTS ${TEST_DB};" >/dev/null 2>&1 || true
  if [[ -n "${TMP_DIR:-}" && -d "$TMP_DIR" ]]; then rm -rf "$TMP_DIR"; fi
}
trap cleanup EXIT

echo ""
echo "═══ Setup: scratch DB ${TEST_DB} ═══"
$PSQL_SUPER -c "DROP DATABASE IF EXISTS ${TEST_DB};" >/dev/null 2>&1 || true
$PSQL_SUPER -c "CREATE DATABASE ${TEST_DB};" >/dev/null 2>&1
# Live-DB condition (regression guard, 2026-09-03): the real mycortex DB has
# an EXISTING `mycortex` schema, so role mycortex's search_path "\$user", public
# resolves \$user → mycortex. A bare CREATE EXTENSION then installs into the
# mycortex schema and capture() (search_path learnings,public) 400s forever.
# Pre-creating the schema here makes the battery reproduce that failure mode.
$PSQL -c "CREATE SCHEMA mycortex;" >/dev/null 2>&1
# Temp worker profile role — cluster-level, mimics a fleet worker's DB role.
# LOGIN so the psql client can connect as it (trust auth inside the container).
$PSQL_SUPER -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='${TEST_WORKER_ROLE}') THEN CREATE ROLE ${TEST_WORKER_ROLE} LOGIN; END IF; END \$\$;" >/dev/null 2>&1
echo "  created ${TEST_DB} + temp role ${TEST_WORKER_ROLE}"

echo ""
echo "═══ AC-L1: Fresh DB → migrate.py applies v001; schema exists ═══"
if python3 "$MIGRATE_PY" --db-name "$TEST_DB" >/dev/null 2>&1; then
  pass "migrate.py applies migrations on fresh DB"
else
  fail "migrate.py failed on fresh DB"
fi

SCHEMA_EXISTS=$($PSQL -c "SELECT count(*) FROM information_schema.schemata WHERE schema_name='learnings';" 2>/dev/null)
[ "$SCHEMA_EXISTS" = "1" ] && pass "learnings schema exists" || fail "learnings schema missing (got: $SCHEMA_EXISTS)"

TABLE_EXISTS=$($PSQL -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='learnings' AND table_name='learning';" 2>/dev/null)
[ "$TABLE_EXISTS" = "1" ] && pass "learnings.learning table exists" || fail "learnings.learning missing (got: $TABLE_EXISTS)"

echo ""
echo "═══ AC-L1.1: Idempotent re-run → no-op ═══"
RE_RUN=$(python3 "$MIGRATE_PY" --db-name "$TEST_DB" 2>&1)
if echo "$RE_RUN" | grep -q "no-op"; then
  pass "re-run reports no-op"
else
  fail "re-run did not report no-op: $(echo "$RE_RUN" | head -2)"
fi

echo ""
echo "═══ AC-L3: capture() dedup — same route+content → same id ═══"
FIRST=$($PSQL -c "SELECT id FROM learnings.capture('remediation','test-agent','first dedup test','fix',2,'src-1');" 2>/dev/null | head -1)
SECOND=$($PSQL -c "SELECT id FROM learnings.capture('remediation','test-agent','first dedup test','fix',2,'src-1');" 2>/dev/null | head -1)
[ -n "$FIRST" ] && [ "$FIRST" = "$SECOND" ] && pass "dedup returns same id ($FIRST)" || fail "dedup mismatch: $FIRST vs $SECOND"

COUNT=$($PSQL -c "SELECT count(*) FROM learnings.learning WHERE content='first dedup test';" 2>/dev/null)
[ "$COUNT" = "1" ] && pass "only 1 row for deduped content" || fail "expected 1 row, got $COUNT"

echo ""
echo "═══ AC-L3b: Different content, same route → distinct rows ═══"
THIRD=$($PSQL -c "SELECT id FROM learnings.capture('remediation','test-agent','second dedup test','fix',1,NULL);" 2>/dev/null | head -1)
[ -n "$THIRD" ] && [ "$THIRD" != "$FIRST" ] && pass "different content → different id" || fail "distinct-content rows collided: $FIRST vs $THIRD"

echo ""
echo "═══ AC-L2: Scrub hook — email / IPv4 / home-path → placeholders ═══"
$PSQL -c "SELECT learnings.capture('cron_outputs','test-agent','contact dev@example.com at 10.1.2.3 under /home/admin/logs','watchdog',0,'src-2');" >/dev/null 2>&1
SCRUBBED=$($PSQL -c "SELECT content FROM learnings.learning WHERE source_ref='src-2';" 2>/dev/null | head -1)
if echo "$SCRUBBED" | grep -q "user@client-domain.com" \
  && echo "$SCRUBBED" | grep -q "x.x.x.x" \
  && echo "$SCRUBBED" | grep -q "~/"; then
  pass "scrubbed: $SCRUBBED"
else
  fail "scrub missed patterns: $SCRUBBED"
fi

echo ""
echo "═══ AC-L1: INSERT-only — reader can EXECUTE capture, no table DML ═══"
PSQL_READER="docker exec ${CONTAINER} psql -U mycortex_reader -d ${TEST_DB} -t -A"
READER_CAPTURE=$($PSQL_READER -c "SELECT count(*) FROM learnings.capture('brain_lessons','worker-agent','reader can capture','lesson',0,NULL);" 2>/dev/null | head -1)
[ "$READER_CAPTURE" = "1" ] && pass "reader role can EXECUTE capture()" || fail "reader capture failed (got: $READER_CAPTURE)"

INSERT_DENIED=$(docker exec ${CONTAINER} psql -U mycortex_reader -d ${TEST_DB} -t -A -c "INSERT INTO learnings.learning (route, agent, content, content_hash) VALUES ('brain_lessons','x','y','z');" 2>&1 | grep -ci "permission denied" || true)
[ "$INSERT_DENIED" -ge 1 ] && pass "reader INSERT denied (permission denied)" || fail "reader INSERT was NOT denied"

echo ""
echo "═══ AC-L1: set_status gate — transitions work, invalid rejected ═══"
CAPTURED_ID=$($PSQL -c "SELECT id FROM learnings.capture('governance_cycles','test-agent','status transition test','insight',1,'src-3');" 2>/dev/null | head -1)
SET_OK=$($PSQL -c "SELECT learnings.set_status('${CAPTURED_ID}','applied');" 2>/dev/null | head -1)
[ "$SET_OK" = "t" ] && pass "set_status applied" || fail "set_status failed (got: $SET_OK)"

STATUS=$($PSQL -c "SELECT status FROM learnings.learning WHERE id='${CAPTURED_ID}';" 2>/dev/null | head -1)
[ "$STATUS" = "applied" ] && pass "status now applied" || fail "status wrong (got: $STATUS)"

BAD_STATUS=$(docker exec ${CONTAINER} psql -U mycortex -d ${TEST_DB} -t -A -c "SELECT learnings.set_status('${CAPTURED_ID}','nonsense');" 2>&1 | grep -ci "invalid status" || true)
[ "$BAD_STATUS" -ge 1 ] && pass "invalid status rejected" || fail "invalid status accepted"

echo ""
echo "═══ AC-L1/v002: set_status impact revision — 3-arg sets impact, 2-arg keeps it ═══"
# v002: set_status(id, status, impact) — lifecycle revises impact during eval.
CAPTURE_IMP=$($PSQL -c "SELECT id FROM learnings.capture('session_corrections','test-agent','impact revision test','correction',0,'src-v002');" 2>/dev/null | head -1)
SET_IMP=$($PSQL -c "SELECT learnings.set_status('${CAPTURE_IMP}','evaluated',2);" 2>/dev/null | head -1)
[ "$SET_IMP" = "t" ] && pass "set_status with impact returns t" || fail "set_status(3-arg) failed (got: $SET_IMP)"
IMP_AFTER=$($PSQL -c "SELECT impact_score FROM learnings.learning WHERE id='${CAPTURE_IMP}';" 2>/dev/null | head -1)
[ "$IMP_AFTER" = "2" ] && pass "impact revised to 2" || fail "impact not revised (got: $IMP_AFTER)"
# 2-arg call on the same row keeps the revised impact (COALESCE(p_impact, current))
SET_AGAIN=$($PSQL -c "SELECT learnings.set_status('${CAPTURE_IMP}','applied');" 2>/dev/null | head -1)
IMP_KEPT=$($PSQL -c "SELECT impact_score FROM learnings.learning WHERE id='${CAPTURE_IMP}';" 2>/dev/null | head -1)
[ "$SET_AGAIN" = "t" ] && [ "$IMP_KEPT" = "2" ] && pass "2-arg set_status keeps impact (got $IMP_KEPT)" || fail "2-arg call clobbered impact (got: $IMP_KEPT)"
# impact out of range → rejected
BAD_IMP=$(docker exec ${CONTAINER} psql -U mycortex -d ${TEST_DB} -t -A -c "SELECT learnings.set_status('${CAPTURE_IMP}','verified',9);" 2>&1 | grep -ci "between -3 and 3" || true)
[ "$BAD_IMP" -ge 1 ] && pass "impact out of range rejected" || fail "impact out of range accepted"
# reader role (mycortex_reader) can EXECUTE the 3-arg form via the DEFAULT grant
READER_SET=$(docker exec ${CONTAINER} psql -U mycortex_reader -d ${TEST_DB} -t -A -c "SELECT learnings.set_status('${CAPTURE_IMP}','verified',1);" 2>/dev/null | head -1)
[ "$READER_SET" = "t" ] && pass "reader can EXECUTE 3-arg set_status (grant re-affirmed)" || fail "reader 3-arg set_status denied (got: $READER_SET)"

echo ""
echo "═══ AC-L6: RLS fail-closed — un-granted worker sees nothing; lifecycle reads ═══"
PSQL_WORKER="docker exec ${CONTAINER} psql -U ${TEST_WORKER_ROLE} -d ${TEST_DB} -t -A"
# `|| true` — permission denied exits non-zero; set -e would abort the script
# before the check (shell-scripting pitfall: failed cmd-substitution in assignment)
WORKER_READ=$($PSQL_WORKER -c "SELECT count(*) FROM learnings.learning;" 2>&1 || true)
if echo "$WORKER_READ" | grep -q "permission denied"; then
  pass "un-granted worker role blocked (permission denied)"
elif [ "$WORKER_READ" = "0" ]; then
  pass "un-granted worker role sees 0 rows (RLS)"
else
  fail "un-granted worker role saw rows: $WORKER_READ"
fi

# Lifecycle reader role = the LOCAL orchestrator's profile reader
# (mycortex_reader_<AGENT_NAME>). Hardcoding esther's role here broke the
# battery on the moses host — same lesson as run-evals.py _task_db_identity
# (2026-08-09): each host provisions only its own reader role.
LOCAL_AGENT="${LEARNINGS_READER_AGENT:-$(grep -h '^AGENT_NAME=' "$HOME/.hermes-cortex/agent.env" "$HOME/hermes-cortex/.env" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d ' ')}"
PSQL_LIFECYCLE="docker exec ${CONTAINER} psql -U mycortex_reader_${LOCAL_AGENT} -d ${TEST_DB} -t -A"
LIFECYCLE_READ=$($PSQL_LIFECYCLE -c "SELECT count(*) FROM learnings.learning;" 2>/dev/null || true)
if [[ "$LIFECYCLE_READ" =~ ^[0-9]+$ ]] && [ "$LIFECYCLE_READ" -ge 1 ]; then
  pass "lifecycle role (mycortex_reader_${LOCAL_AGENT}) reads rows ($LIFECYCLE_READ)"
else
  fail "lifecycle role read failed (got: $LIFECYCLE_READ)"
fi

echo ""
echo "═══ AC-L7: bus schema untouched after learnings apply ═══"
# The learnings migration must NOT create or modify the bus schema. In the
# scratch DB, bus doesn't exist (it lives only in the real mycortex DB) —
# so the correct assertion is that the migration left it at 0 tables.
BUS_COUNT=$($PSQL -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='bus';" 2>/dev/null)
[ "$BUS_COUNT" = "0" ] && pass "bus schema not created/modified by learnings apply (0 tables)" || fail "learnings migration touched bus schema: $BUS_COUNT tables"

echo ""
echo "═══════════════════════════════════════════════"
echo "RESULTS: $P passed, $F failed"
[ "$F" -eq 0 ] || exit 1
exit 0
