#!/usr/bin/env bash
# test-learning-ledger-cli.sh — hermetic AC battery for learning-ledger.py
# (F-006 orchestrator-only lifecycle client).
#
# Exercises the CLI against a scratch DB (not the live ledger):
#   list (default pending / --status / --route / --json), set-status with and
#   without --impact, stats, validation (bad uuid / bad status / bad impact /
#   bad route / bad limit), and RLS fail-closed (a temp un-granted role gets
#   permission denied on list).
#
# Mirrors tests/test-learnings-schema.sh (same pass/fail pattern, same
# scratch-DB hermeticity guard).
#
# Run: bash tests/test-learning-ledger-cli.sh
set -eu
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MIGRATE_PY="${REPO_DIR}/ops/services/learnings/migrate.py"
LEDGER_PY="python3 ${REPO_DIR}/ops/scripts/manage/learning-ledger.py"
TEST_DB="${LEARNING_TEST_DB:-learnings_cli_test}"
CONTAINER="${LEARNING_TEST_CONTAINER:-mycortex-postgres}"
TEST_WORKER_ROLE="learnings_cli_worker"   # temp role, dropped in cleanup

if [[ "$TEST_DB" == "mycortex" ]]; then
  echo "❌ REFUSING to run against the $TEST_DB database — hermeticity guard. Set LEARNING_TEST_DB." >&2
  exit 1
fi

PSQL="docker exec ${CONTAINER} psql -U mycortex -d ${TEST_DB} -t -A"
PSQL_SUPER="docker exec ${CONTAINER} psql -U mycortex -d mycortex -t -A"

P=0; F=0
pass() { P=$((P+1)); echo "  ✅ $1"; }
fail() { F=$((F+1)); echo "  ❌ $1${2:+ — $2}"; }

cleanup() {
  docker exec ${CONTAINER} psql -U mycortex -d mycortex -c \
    "DROP ROLE IF EXISTS ${TEST_WORKER_ROLE};" >/dev/null 2>&1 || true
  $PSQL_SUPER -c "DROP DATABASE IF EXISTS ${TEST_DB};" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# Hermetic env for the CLI under test: scratch DB + lifecycle profile role.
export LEARNING_DB="$TEST_DB"
export LEARNING_DB_ROLE="mycortex_reader_esther"

echo ""
echo "═══ Setup: scratch DB ${TEST_DB} ═══"
$PSQL_SUPER -c "DROP DATABASE IF EXISTS ${TEST_DB};" >/dev/null 2>&1 || true
$PSQL_SUPER -c "CREATE DATABASE ${TEST_DB};" >/dev/null 2>&1
$PSQL_SUPER -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='${TEST_WORKER_ROLE}') THEN CREATE ROLE ${TEST_WORKER_ROLE} LOGIN; END IF; END \$\$;" >/dev/null 2>&1
if ! python3 "$MIGRATE_PY" --db-name "$TEST_DB" >/dev/null 2>&1; then
  fail "migrate.py failed on scratch DB — cannot continue"
  echo "RESULTS: $P passed, $F failed"
  exit 1
fi
echo "  schema applied (v001+v002)"

echo ""
echo "═══ CLI-1: seed rows for list/set-status tests ═══"
# Owner-inserted via capture() (the only write path) — CLI must read them.
$PSQL -c "SELECT learnings.capture('remediation','worker-a','cli pending remediation one','fix',1,'src-cli-1');" >/dev/null 2>&1
$PSQL -c "SELECT learnings.capture('brain_lessons','worker-b','cli pending lesson two','lesson',0,'src-cli-2');" >/dev/null 2>&1
$PSQL -c "SELECT learnings.capture('cron_outputs','worker-c','cli applied watchdog three','watchdog',2,'src-cli-3');" >/dev/null 2>&1
$PSQL -c "SELECT learnings.set_status((SELECT id FROM learnings.learning WHERE source_ref='src-cli-3'),'applied');" >/dev/null 2>&1
echo "  seeded 3 rows (2 pending, 1 applied)"

echo ""
echo "═══ CLI-2: list defaults to pending ═══"
PENDING=$($LEDGER_PY list 2>/dev/null || true)
if echo "$PENDING" | grep -q "cli pending remediation one" \
  && echo "$PENDING" | grep -q "cli pending lesson two" \
  && ! echo "$PENDING" | grep -q "cli applied watchdog three"; then
  pass "list default shows only pending rows (2)"
else
  fail "list default wrong — got: $(echo "$PENDING" | head -3)"
fi

echo ""
echo "═══ CLI-3: list --status applied / --route filter ═══"
APPLIED=$($LEDGER_PY list --status applied 2>/dev/null || true)
if echo "$APPLIED" | grep -q "cli applied watchdog three"; then
  pass "list --status applied finds applied row"
else
  fail "list --status applied missed row — got: $(echo "$APPLIED" | head -3)"
fi
ROUTE_ONLY=$($LEDGER_PY list --route remediation 2>/dev/null || true)
if echo "$ROUTE_ONLY" | grep -q "cli pending remediation one" \
  && ! echo "$ROUTE_ONLY" | grep -q "cli pending lesson two"; then
  pass "list --route remediation filters by route"
else
  fail "list --route remediation wrong — got: $(echo "$ROUTE_ONLY" | head -3)"
fi

echo ""
echo "═══ CLI-4: list --json output is parseable + has id/status ═══"
JSON_OUT=$($LEDGER_PY list --status applied --json 2>/dev/null || true)
if echo "$JSON_OUT" | python3 -c "import json,sys; d=json.load(sys.stdin); assert any(r['status']=='applied' for r in d), 'no applied row'; assert d[0]['id'], 'missing id'" 2>/dev/null; then
  pass "list --json is valid JSON with id+status"
else
  fail "list --json malformed — got: $(echo "$JSON_OUT" | head -3)"
fi

echo ""
echo "═══ CLI-5: set-status transitions + optional impact ═══"
TARGET_ID=$($PSQL -c "SELECT id FROM learnings.learning WHERE source_ref='src-cli-1';" 2>/dev/null | head -1)
SET1=$($LEDGER_PY set-status "$TARGET_ID" evaluated 2>&1 || true)
if echo "$SET1" | grep -q "evaluated"; then
  pass "set-status <id> evaluated"
else
  fail "set-status evaluated failed — got: $SET1"
fi
SET2=$($LEDGER_PY set-status "$TARGET_ID" applied --impact 3 2>&1 || true)
IMPACT_ROW=$($PSQL -c "SELECT status || '|' || impact_score FROM learnings.learning WHERE id='${TARGET_ID}';" 2>/dev/null | head -1)
if [ "$IMPACT_ROW" = "applied|3" ]; then
  pass "set-status applied --impact 3 → status=applied, impact=3 (got: $IMPACT_ROW)"
else
  fail "impact revision failed — got: $IMPACT_ROW"
fi

echo ""
echo "═══ CLI-6: validation — bad uuid / status / impact / route / limit ═══"
BAD_UUID=$($LEDGER_PY set-status not-a-uuid applied 2>&1 || true)
echo "$BAD_UUID" | grep -qi "not a valid learning UUID" && pass "bad uuid rejected" || fail "bad uuid accepted: $BAD_UUID"
BAD_STATUS=$($LEDGER_PY set-status "$TARGET_ID" nonsense 2>&1 || true)
echo "$BAD_STATUS" | grep -qi "not in" && pass "bad status rejected" || fail "bad status accepted: $BAD_STATUS"
BAD_IMPACT=$($LEDGER_PY set-status "$TARGET_ID" verified --impact 9 2>&1 || true)
echo "$BAD_IMPACT" | grep -qi "between -3 and 3" && pass "bad impact rejected" || fail "bad impact accepted: $BAD_IMPACT"
BAD_ROUTE=$($LEDGER_PY list --route bogus 2>&1 || true)
echo "$BAD_ROUTE" | grep -qi "not in" && pass "bad route rejected" || fail "bad route accepted: $BAD_ROUTE"
BAD_LIMIT=$($LEDGER_PY list --limit 0 2>&1 || true)
echo "$BAD_LIMIT" | grep -qi "1..500" && pass "bad limit rejected" || fail "bad limit accepted: $BAD_LIMIT"

echo ""
echo "═══ CLI-7: missing id → set-status fails cleanly ═══"
MISSING=$($LEDGER_PY set-status 00000000-0000-0000-0000-000000000000 retired 2>&1 || true)
if echo "$MISSING" | grep -qi "no such learning\|ERROR"; then
  pass "missing id errors cleanly"
else
  fail "missing id did not error — got: $MISSING"
fi

echo ""
echo "═══ CLI-8: stats reports status counts ═══"
STATS=$($LEDGER_PY stats 2>&1 || true)
if echo "$STATS" | grep -q "By status:" && echo "$STATS" | grep -q "applied"; then
  pass "stats prints status breakdown"
else
  fail "stats malformed — got: $(echo "$STATS" | head -5)"
fi

echo ""
echo "═══ CLI-9: RLS fail-closed — un-granted role cannot list ═══"
DENIED=$(LEARNING_DB_ROLE="$TEST_WORKER_ROLE" $LEDGER_PY list 2>&1 || true)
if echo "$DENIED" | grep -qi "permission denied"; then
  pass "un-granted worker role blocked (permission denied)"
else
  fail "un-granted role list did not fail — got: $(echo "$DENIED" | head -2)"
fi

echo ""
echo "═══════════════════════════════════════════════"
echo "RESULTS: $P passed, $F failed"
[ "$F" -eq 0 ] || exit 1
exit 0
