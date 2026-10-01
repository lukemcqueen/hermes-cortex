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
PSQL_ADMIN="docker exec ${CONTAINER} psql -U mycortex_mem_admin -d ${TEST_DB} -t -A"

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

# One schema_version row PER MIGRATION FILE — not "1". Asserting 1 broke the
# moment v002 shipped (3 files → 3 rows) and stayed broken, which is how a
# v003 that could not apply went unnoticed: this battery's AC1 should have
# caught it. Derive the expectation from the directory, never hardcode it.
EXPECTED_VERSIONS=$(ls -1 "${REPO_DIR}/ops/services/mycortex-mem/schema"/v*.sql 2>/dev/null | wc -l | tr -d ' ')
VER_AFTER=$($PSQL -c "SELECT count(*) FROM mycortex_mem.schema_version;" 2>/dev/null)
[ "$VER_AFTER" = "$EXPECTED_VERSIONS" ] && \
  pass "schema_version has one row per migration file (${VER_AFTER})" || \
  fail "schema_version has ${VER_AFTER} rows, expected ${EXPECTED_VERSIONS} (migration file count) — duplicate, or a migration applied without being recorded"

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
echo "═══ AC8: tool_events exists; session_id is UUID (FK to sessions.id) ═══"
TE_EXISTS=$($PSQL -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='mycortex_mem' AND table_name='tool_events';" 2>/dev/null)
[ "$TE_EXISTS" = "1" ] && pass "mycortex_mem.tool_events exists" || fail "mycortex_mem.tool_events missing (got: $TE_EXISTS)"

# The v003 first draft declared BIGINT here. That cannot reference sessions.id
# (UUID), so the migration died at APPLY time — no static check sees it, and
# both files read fine in isolation. Pin the type.
SID_TYPE=$($PSQL -c "SELECT data_type FROM information_schema.columns WHERE table_schema='mycortex_mem' AND table_name='tool_events' AND column_name='session_id';" 2>/dev/null)
[ "$SID_TYPE" = "uuid" ] && pass "session_id is uuid (matches sessions.id)" || fail "session_id is '${SID_TYPE}', expected uuid — a bigint FK cannot reference sessions.id"

TSV_TYPE=$($PSQL -c "SELECT data_type FROM information_schema.columns WHERE table_schema='mycortex_mem' AND table_name='tool_events' AND column_name='content_text_tsv';" 2>/dev/null)
[ "$TSV_TYPE" = "tsvector" ] && pass "generated content_text_tsv column present" || fail "content_text_tsv is '${TSV_TYPE}', expected tsvector"

echo ""
echo "═══ AC9: tool_events role split (a new table inherits NO grants) ═══"
$PSQL_WRITER -c "INSERT INTO mycortex_mem.tool_events (harness, tool_name, role, content) VALUES ('roleprobe','skill_view','tool','{\"name\":\"reflexion-check\"}'::jsonb);" >/dev/null 2>&1 && \
  pass "writer can INSERT into tool_events" || fail "writer cannot INSERT into tool_events"

W_COUNT=$($PSQL_READER -c "SELECT count(*) FROM mycortex_mem.tool_events;" 2>/dev/null)
[ "$W_COUNT" = "1" ] && pass "reader can SELECT from tool_events" || fail "reader cannot SELECT from tool_events (got: $W_COUNT)"

A_COUNT=$($PSQL_ADMIN -c "SELECT count(*) FROM mycortex_mem.tool_events;" 2>/dev/null)
[ "$A_COUNT" = "1" ] && pass "admin can SELECT from tool_events" || fail "admin cannot SELECT from tool_events (got: $A_COUNT)"

R_INS=$($PSQL_READER -c "INSERT INTO mycortex_mem.tool_events (harness, tool_name) VALUES ('x','y');" 2>&1 || true)
if echo "$R_INS" | grep -qi "permission denied"; then
  pass "reader INSERT denied (fail-closed role split)"
else
  fail "reader INSERT was NOT denied — role-split leak (got: ${R_INS})"
fi

echo ""
echo "═══ AC10/AC11/AC12: the gate's question, answered from a cold start ═══"
STORE_OUT=$(MYCORTEX_MEM_TEST_DB="$TEST_DB" python3 - "$REPO_DIR" <<'PYEOF'
import os, sys
repo = sys.argv[1]
sys.path.insert(0, os.path.join(repo, "ops", "services", "mycortex-mem"))
from store import Store, PgConnection

st = Store(PgConnection(db_name=os.environ["MYCORTEX_MEM_TEST_DB"]))
S = st.sessions
# A session key that has NEVER had a session row — the harness-first-write case.
S.record_tool_event("pi", "skill_view", {"name": "reflexion-check"}, repo="cold", branch="start")
print("loaded=%s" % S.loaded_skill("reflexion-check", "pi", repo="cold", branch="start"))
print("unloaded=%s" % S.loaded_skill("change-checklist", "pi", repo="cold", branch="start"))
print("nullrouted=%s" % st.pg.scalar("SELECT count(*) FROM mycortex_mem.tool_events WHERE session_id IS NULL AND harness='pi';"))
print("sessionrows=%s" % st.pg.scalar("SELECT count(*) FROM mycortex_mem.sessions WHERE session_key='pi:cold:start';"))
_LINKED = ("SELECT count(*) FROM mycortex_mem.tool_events e JOIN mycortex_mem.sessions s "
           "ON s.id = e.session_id WHERE s.session_key='pi:cold:start';")
print("linked_before=%s" % st.pg.scalar(_LINKED))
st.pg.run_sql("DELETE FROM mycortex_mem.sessions WHERE session_key='pi:cold:start';", role="mycortex_mem_admin")
print("linked_after=%s" % st.pg.scalar(_LINKED))
PYEOF
)
echo "$STORE_OUT" | grep -q "^loaded=True$" && \
  pass "cold-start event is routable — loaded_skill()=True with no prior session row" || \
  fail "cold-start event was NOT routable (loaded_skill=False) — written, but session_id NULL: $STORE_OUT"
echo "$STORE_OUT" | grep -q "^unloaded=False$" && \
  pass "loaded_skill() is False for a skill never loaded (no false positive)" || \
  fail "loaded_skill() false-positive — reported a skill that was never loaded: $STORE_OUT"
echo "$STORE_OUT" | grep -q "^nullrouted=0$" && \
  pass "zero unroutable events (no NULL session_id)" || \
  fail "events written with NULL session_id — invisible to the gate: $STORE_OUT"
echo "$STORE_OUT" | grep -q "^linked_before=1$" && \
  pass "event linked to the session before delete" || \
  fail "cold-start event not linked to its session (got: $STORE_OUT)"
echo "$STORE_OUT" | grep -q "^linked_after=0$" && \
  pass "deleting the session cascades its tool_events" || \
  fail "tool_events survived the session delete (FK cascade broken): $STORE_OUT"

echo ""
echo "═══ Summary ═══"
echo "  ${P} passed, ${F} failed"
if [ "$F" -gt 0 ]; then
  echo "  ❌ SOME TESTS FAILED"
  exit 1
fi
echo "  ✅ ALL TESTS PASSED"
