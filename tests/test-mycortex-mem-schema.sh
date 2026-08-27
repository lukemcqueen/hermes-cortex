#!/usr/bin/env bash
# test-mycortex-mem-schema.sh — L1 hermetic AC battery
#
# Covers:
#   AC1  Fresh DB → migrate.py → schema + tables + roles exist; re-run = no-op
#   AC2  mycortex_mem_reader role exists
#   AC3  mycortex_mem_writer role exists
#   AC4  mycortex_mem_admin role exists
#   AC5  Idempotency: re-run migrate.py succeeds with no errors
#   AC6  peers UNIQUE constraint (workspace, peer_name)
#   AC7  Writer can INSERT, Reader can SELECT (role split)
#
# Run: bash tests/test-mycortex-mem-schema.sh
set -eu

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MIGRATE_PY="${REPO_DIR}/ops/services/mycortex-mem/migrate.py"
TEST_DB="${MYCORTEX_MEM_TEST_DB:-mycortex_mem_test}"
CONTAINER="${MYCORTEX_MEM_TEST_CONTAINER:-mycortex-postgres}"

if [[ "$TEST_DB" == "mycortex" ]]; then
  echo "❌ REFUSING to run against the mycortex DB — hermeticity guard. Set MYCORTEX_MEM_TEST_DB." >&2
  exit 1
fi

PSQL="docker exec ${CONTAINER} psql -U mycortex -d ${TEST_DB} -t -A"
PSQL_SUPER="docker exec ${CONTAINER} psql -U mycortex -d mycortex -t -A"
PSQL_READER="docker exec ${CONTAINER} psql -U mycortex_mem_reader -d ${TEST_DB} -t -A"
PSQL_WRITER="docker exec ${CONTAINER} psql -U mycortex_mem_writer -d ${TEST_DB} -t -A"

P=0; F=0
pass() { P=$((P+1)); echo "  ✅ $1"; }
fail() { F=$((F+1)); echo "  ❌ $1${2:+ — $2}"; }

cleanup() {
  $PSQL_SUPER -c "DROP DATABASE IF EXISTS ${TEST_DB};" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo ""
echo "═══ Setup: scratch DB ${TEST_DB} ═══"
$PSQL_SUPER -c "DROP DATABASE IF EXISTS ${TEST_DB};" >/dev/null 2>&1 || true
$PSQL_SUPER -c "CREATE DATABASE ${TEST_DB};" >/dev/null 2>&1
echo "  created ${TEST_DB}"

echo ""
echo "═══ AC1: Fresh DB → migrate.py creates schema + tables + roles; re-run no-op ═══"
if python3 "$MIGRATE_PY" --db-name "$TEST_DB" >/dev/null 2>&1; then
  pass "migrate.py applies v001 on fresh DB"
else
  fail "migrate.py failed on fresh DB"
fi

SCHEMA_EXISTS=$($PSQL -c "SELECT count(*) FROM information_schema.schemata WHERE schema_name='mycortex_mem';" 2>/dev/null)
[ "$SCHEMA_EXISTS" = "1" ] && pass "mycortex_mem schema exists" || fail "mycortex_mem schema missing (got: $SCHEMA_EXISTS)"

for TABLE in peers profiles sessions messages conclusions interceptor_log schema_version; do
  COUNT=$($PSQL -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='mycortex_mem' AND table_name='${TABLE}';" 2>/dev/null)
  [ "$COUNT" = "1" ] && pass "mycortex_mem.${TABLE} table exists" || fail "mycortex_mem.${TABLE} missing (got: $COUNT)"
done

echo ""
echo "═══ AC2: Role exists — mycortex_mem_reader ═══"
READER_ROLE=$($PSQL_SUPER -c "SELECT count(*) FROM pg_roles WHERE rolname='mycortex_mem_reader';" 2>/dev/null)
[ "$READER_ROLE" = "1" ] && pass "mycortex_mem_reader role exists" || fail "mycortex_mem_reader role missing (got: $READER_ROLE)"

echo ""
echo "═══ AC3: Role exists — mycortex_mem_writer ═══"
WRITER_ROLE=$($PSQL_SUPER -c "SELECT count(*) FROM pg_roles WHERE rolname='mycortex_mem_writer';" 2>/dev/null)
[ "$WRITER_ROLE" = "1" ] && pass "mycortex_mem_writer role exists" || fail "mycortex_mem_writer role missing (got: $WRITER_ROLE)"

echo ""
echo "═══ AC4: Role exists — mycortex_mem_admin ═══"
ADMIN_ROLE=$($PSQL_SUPER -c "SELECT count(*) FROM pg_roles WHERE rolname='mycortex_mem_admin';" 2>/dev/null)
[ "$ADMIN_ROLE" = "1" ] && pass "mycortex_mem_admin role exists" || fail "mycortex_mem_admin role missing (got: $ADMIN_ROLE)"

echo ""
echo "═══ AC5: Idempotency — re-run migrate.py is no-op ═══"
if python3 "$MIGRATE_PY" --db-name "$TEST_DB" >/dev/null 2>&1; then
  pass "migrate.py re-run succeeds (idempotent)"
else
  fail "migrate.py re-run failed"
fi

VER_AFTER=$($PSQL -c "SELECT count(*) FROM mycortex_mem.schema_version;" 2>/dev/null)
[ "$VER_AFTER" = "1" ] && pass "schema_version has exactly 1 row (no duplicate)" || fail "schema_version has ${VER_AFTER} rows (expected 1) — re-run duplicated"

echo ""
echo "═══ AC6: peers UNIQUE constraint (workspace, peer_name) ═══"
$PSQL -c "INSERT INTO mycortex_mem.peers (workspace, peer_name, peer_type) VALUES ('test', 'user1', 'user');" >/dev/null 2>&1
DUP_RESULT=$($PSQL -c "INSERT INTO mycortex_mem.peers (workspace, peer_name, peer_type) VALUES ('test', 'user1', 'user');" 2>&1 || true)
if echo "$DUP_RESULT" | grep -q "duplicate key"; then
  pass "UNIQUE constraint on (workspace, peer_name) enforced"
else
  fail "UNIQUE constraint not enforced — duplicate insert succeeded"
fi

echo ""
echo "═══ AC7: Writer can INSERT, Reader can SELECT ═══"
$PSQL_WRITER -c "INSERT INTO mycortex_mem.peers (workspace, peer_name, peer_type) VALUES ('test2', 'writer_peer', 'user');" >/dev/null 2>&1 && \
  pass "mycortex_mem_writer can INSERT into peers" || \
  fail "mycortex_mem_writer cannot INSERT into peers"

READER_COUNT=$($PSQL_READER -c "SELECT count(*) FROM mycortex_mem.peers WHERE workspace='test2';" 2>/dev/null)
[ "$READER_COUNT" = "1" ] && pass "mycortex_mem_reader can SELECT from peers" || fail "mycortex_mem_reader cannot SELECT from peers (got: $READER_COUNT)"

echo ""
echo "═══ Summary ═══"
echo "  ${P} passed, ${F} failed"
if [ "$F" -gt 0 ]; then
  echo "  ❌ SOME TESTS FAILED"
  exit 1
fi
echo "  ✅ ALL TESTS PASSED"
