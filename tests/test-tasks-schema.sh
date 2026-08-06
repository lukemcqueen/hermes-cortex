#!/usr/bin/env bash
# test-tasks-schema.sh — L1 hermetic AC battery for the tasks schema (v001+v002)
#
# From docs/design/task-workflow.md §8 (QA B-8 mandatory test plan):
#   hermetic scratch DB `tasks_test` (refuses `mycortex` DB with a guard),
#   schema-apply idempotency (run twice → no-op), function behavior,
#   RLS/GRANT assertions as `mycortex_reader`, task_upsert status→column
#   derivation, CHECK-constraint rejections, and the guarded bus.todos
#   migration (seed → migrate → count parity → scoped drop → re-run no-op).
#
# Mirrors tests/test-mycortex-schema.sh (same pass/fail pattern).
#
# Run: bash tests/test-tasks-schema.sh
set -eu
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MIGRATE_PY="${REPO_DIR}/ops/services/tasks/migrate.py"
MIGRATE_BUS_PY="${REPO_DIR}/ops/scripts/manage/migrate-bus-todos.py"
TEST_DB="${TASKS_TEST_DB:-tasks_test}"
CONTAINER="${TASKS_TEST_CONTAINER:-mycortex-postgres}"

if [[ "$TEST_DB" == "mycortex" || "$TEST_DB" == "gbrain" ]]; then
  echo "❌ REFUSING to run against the $TEST_DB database — hermeticity guard. Set TASKS_TEST_DB." >&2
  exit 1
fi

PSQL="docker exec ${CONTAINER} psql -U mycortex -d ${TEST_DB} -t -A"
PSQL_SUPER="docker exec ${CONTAINER} psql -U mycortex -d mycortex -t -A"

P=0; F=0
pass() { P=$((P+1)); echo "  ✅ $1"; }
fail() { F=$((F+1)); echo "  ❌ $1${2:+ — $2}"; }

cleanup() {
  $PSQL_SUPER -c "DROP DATABASE IF EXISTS ${TEST_DB};" >/dev/null 2>&1 || true
  if [[ -n "${TMP_DIR:-}" && -d "$TMP_DIR" ]]; then rm -rf "$TMP_DIR"; fi
}
trap cleanup EXIT

echo ""
echo "═══ Setup: scratch DB ${TEST_DB} ═══"
$PSQL_SUPER -c "DROP DATABASE IF EXISTS ${TEST_DB};" >/dev/null 2>&1 || true
$PSQL_SUPER -c "CREATE DATABASE ${TEST_DB};" >/dev/null 2>&1
echo "  created ${TEST_DB}"

echo ""
echo "═══ AC-L1-1: Fresh DB → migrate.py applies v001+v002; schema exists ═══"
if python3 "$MIGRATE_PY" --db-name "$TEST_DB" >/dev/null 2>&1; then
  pass "migrate.py applies migrations on fresh DB"
else
  fail "migrate.py failed on fresh DB"
fi

SCHEMA_EXISTS=$($PSQL -c "SELECT count(*) FROM information_schema.schemata WHERE schema_name='tasks';" 2>/dev/null)
[ "$SCHEMA_EXISTS" = "1" ] && pass "tasks schema exists" || fail "tasks schema missing (got: $SCHEMA_EXISTS)"

TABLE_EXISTS=$($PSQL -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='tasks' AND table_name='tasks';" 2>/dev/null)
[ "$TABLE_EXISTS" = "1" ] && pass "tasks.tasks table exists" || fail "tasks.tasks missing (got: $TABLE_EXISTS)"

VER=$($PSQL -c "SELECT max(version) FROM tasks.schema_version;" 2>/dev/null)
EXPECTED_VER=$(ls "${REPO_DIR}/ops/services/tasks/schema/"v*.sql 2>/dev/null | wc -l | tr -d ' ')
[ "$VER" = "$EXPECTED_VER" ] && pass "schema_version = $EXPECTED_VER" || fail "schema_version = $VER (expected $EXPECTED_VER)"

echo ""
echo "═══ AC-L1-2: Re-run is a no-op (version-gated) ═══"
if python3 "$MIGRATE_PY" --db-name "$TEST_DB" 2>/dev/null | grep -q "no-op"; then
  pass "re-run reports no-op"
else
  fail "re-run did not report no-op"
fi

echo ""
echo "═══ AC-L1-3: RLS enabled + policies exist ═══"
# ENABLE (not FORCE) is deliberate: the migration runs as owner mycortex to
# move cross-tenant rows, which FORCE would break. CRUD never runs as owner
# (B-2: mycortex_reader_<profile>), so RLS applies to every CRUD connection.
RLS_ON=$($PSQL -c "SELECT relrowsecurity FROM pg_class WHERE oid='tasks.tasks'::regclass;" 2>/dev/null)
[ "$RLS_ON" = "t" ] && pass "RLS ENABLED on tasks.tasks" || fail "RLS not enabled (got: $RLS_ON)"

POLICY_COUNT=$($PSQL -c "SELECT count(*) FROM pg_policy p JOIN pg_class c ON p.polrelid=c.oid JOIN pg_namespace n ON c.relnamespace=n.oid WHERE n.nspname='tasks';" 2>/dev/null)
[ "$POLICY_COUNT" -ge 1 ] && pass "${POLICY_COUNT} RLS policy exists" || fail "expected ≥1 policy, got $POLICY_COUNT"

echo ""
echo "═══ AC-L1-4: Roles + grants — mycortex_reader has schema usage ═══"
FW_ROLE=$($PSQL -c "SELECT count(*) FROM pg_roles WHERE rolname='todos_fleet_writer';" 2>/dev/null)
[ "$FW_ROLE" = "1" ] && pass "todos_fleet_writer role exists" || fail "todos_fleet_writer missing (got: $FW_ROLE)"

USAGE_OK=$($PSQL -c "SELECT has_schema_privilege('mycortex_reader','tasks','USAGE');" 2>/dev/null)
[ "$USAGE_OK" = "t" ] && pass "mycortex_reader has USAGE on tasks schema" || fail "mycortex_reader lacks USAGE (got: $USAGE_OK)"

DML_OK=$($PSQL -c "SELECT has_table_privilege('mycortex_reader','tasks.tasks','SELECT,INSERT,UPDATE,DELETE');" 2>/dev/null)
[ "$DML_OK" = "t" ] && pass "mycortex_reader has DML on tasks.tasks" || fail "mycortex_reader lacks DML (got: $DML_OK)"

echo ""
echo "═══ AC-L1-5: task_upsert — status→column derivation + completed_at ═══"
# seed via the upsert function (single write path)
NEW_ID=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 test task', p_created_by=>'esther', p_source=>'manual');" 2>/dev/null | head -1)
[ -n "$NEW_ID" ] && pass "task_upsert inserts (id=$NEW_ID)" || fail "task_upsert insert returned no id"

COL_PENDING=$($PSQL -c "SELECT \"column\" FROM tasks.tasks WHERE id='${NEW_ID}';" 2>/dev/null)
[ "$COL_PENDING" = "todo" ] && pass "pending → column='todo' (derived)" || fail "pending column=$COL_PENDING (expected 'todo')"

$PSQL -c "SELECT tasks.task_upsert(p_id=>'${NEW_ID}', p_status=>'completed');" >/dev/null 2>&1
COL_DONE=$($PSQL -c "SELECT \"column\" FROM tasks.tasks WHERE id='${NEW_ID}';" 2>/dev/null)
[ "$COL_DONE" = "done" ] && pass "completed → column='done' (derived)" || fail "completed column=$COL_DONE (expected 'done')"

DONE_AT=$($PSQL -c "SELECT completed_at IS NOT NULL FROM tasks.tasks WHERE id='${NEW_ID}';" 2>/dev/null)
[ "$DONE_AT" = "t" ] && pass "completed_at set on completion" || fail "completed_at not set (got: $DONE_AT)"

# Regression (v003/v004): update an EXISTING row to cancelled must derive
# column=NULL, not carry over the stale column (v004: EXCLUDED."column").
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${NEW_ID}', p_status=>'cancelled');" >/dev/null 2>&1
COL_CANC=$($PSQL -c "SELECT \"column\" IS NULL FROM tasks.tasks WHERE id='${NEW_ID}';" 2>/dev/null)
[ "$COL_CANC" = "t" ] && pass "update→cancelled derives column=NULL (regression v004)" || fail "cancelled column not NULL (got: $COL_CANC — v004 regression)"

echo ""
echo "═══ AC-L1-6: CHECK constraints reject incoherent state ═══"
if $PSQL -c "SELECT tasks.task_upsert(p_content=>'bad status', p_created_by=>'esther', p_status=>'nonsense');" >/dev/null 2>&1; then
  fail "invalid status accepted"
else
  pass "invalid status rejected by CHECK"
fi

if $PSQL -c "SELECT tasks.task_upsert(p_content=>'bad scope', p_created_by=>'esther', p_scope=>'global');" >/dev/null 2>&1; then
  fail "invalid scope accepted"
else
  pass "invalid scope rejected by CHECK"
fi

if $PSQL -c "SELECT tasks.task_upsert(p_content=>'incoherent', p_created_by=>'esther', p_status=>'pending', p_column=>'done');" >/dev/null 2>&1; then
  fail "incoherent column/status accepted"
else
  pass "incoherent column/status rejected by CHECK (B-4)"
fi

echo ""
echo "═══ AC-L1-7: RLS isolation — reader cannot see esther's personal rows ═══"
# esther's row was seeded above as mycortex (superuser) — RLS applies to the
# reader regardless of who inserted. Plain mycortex_reader must see zero rows.
READER_PSQL="docker exec ${CONTAINER} psql -U mycortex_reader -d ${TEST_DB} -t -A"
READER_SEES=$($READER_PSQL -c "SELECT count(*) FROM tasks.tasks;" 2>/dev/null)
[ "$READER_SEES" = "0" ] && pass "mycortex_reader sees zero personal rows (isolation)" || fail "ISOLATION LEAK: reader saw $READER_SEES rows"

echo ""
echo "═══ AC-L1-8: Fleet writes — writer CAN, plain reader CANNOT ═══"
# plain reader must NOT be able to insert scope=fleet (not a fleet writer)
if $READER_PSQL -c "SELECT tasks.task_upsert(p_content=>'fleet attempt', p_created_by=>'mycortex_reader', p_scope=>'fleet');" >/dev/null 2>&1; then
  fail "plain reader inserted scope=fleet — WITH CHECK broken"
else
  pass "plain reader scope=fleet insert rejected (WITH CHECK)"
fi

# fleet writer (esther) CAN insert fleet with clean content — find her role
FW_CONNECT=""
for cand in mycortex_reader_esther mycortex_reader_moses; do
  if $PSQL_SUPER -c "SELECT 1 FROM pg_roles WHERE rolname='${cand}';" 2>/dev/null | grep -q 1; then
    FW_CONNECT="$cand"; break
  fi
done
if [[ -n "$FW_CONNECT" ]]; then
  FW_PSQL="docker exec ${CONTAINER} psql -U ${FW_CONNECT} -d ${TEST_DB} -t -A"
  if $FW_PSQL -c "SELECT tasks.task_upsert(p_content=>'fleet ok', p_created_by=>'esther', p_scope=>'fleet', p_project=>'hermes-cortex');" >/dev/null 2>&1; then
    pass "${FW_CONNECT} inserted scope=fleet (fleet writer)"
  else
    fail "${FW_CONNECT} could not insert fleet row — grant broken"
  fi
  # fleet × client-project banned (B-5)
  if $FW_PSQL -c "SELECT tasks.task_upsert(p_content=>'client leak', p_created_by=>'esther', p_scope=>'fleet', p_project=>'client-works');" >/dev/null 2>&1; then
    fail "fleet × client- project accepted — PII gate broken"
  else
    pass "fleet × client- project rejected (B-5 PII gate)"
  fi
  # content scrub gate (B-5): abs path, user@host, IPv4
  if $FW_PSQL -c "SELECT tasks.task_upsert(p_content=>'fix /var/lib/thing now', p_created_by=>'esther', p_scope=>'fleet');" >/dev/null 2>&1; then
    fail "fleet content with abs path accepted — scrub gate broken"
  else
    pass "fleet content abs path rejected (scrub gate)"
  fi
  if $FW_PSQL -c "SELECT tasks.task_upsert(p_content=>'mail user@example.org', p_created_by=>'esther', p_scope=>'fleet');" >/dev/null 2>&1; then
    fail "fleet content with email accepted — scrub gate broken"
  else
    pass "fleet content email rejected (scrub gate)"
  fi
  # fleet row is visible to plain reader (union semantics, B-3)
  FW_SEES=$($READER_PSQL -c "SELECT count(*) FROM tasks.tasks WHERE scope='fleet';" 2>/dev/null)
  [ "$FW_SEES" = "1" ] && pass "plain reader sees fleet row (got $FW_SEES)" || fail "reader sees $FW_SEES fleet rows (expected 1)"
else
  echo "  ⚠ no orchestrator profile role found — skipping fleet-writer battery (worker host)"
fi

echo ""
echo "═══ AC-L1-9: archive + prune behave ═══"
# archive esther's completed rows
ARCHIVED=$($PSQL -c "SELECT tasks.task_archive_old(p_created_by=>'esther');" 2>/dev/null)
[ "$ARCHIVED" -ge 1 ] && pass "task_archive_old archived $ARCHIVED row(s)" || fail "archive returned $ARCHIVED (expected ≥1)"

ARCH_COUNT=$($PSQL -c "SELECT count(*) FROM tasks.task_archive;" 2>/dev/null)
[ "$ARCH_COUNT" -ge 1 ] && pass "archive table has $ARCH_COUNT row(s)" || fail "archive empty after archive_old"

# prune with a NEGATIVE interval forces removal of the just-archived rows
PRUNED=$($PSQL -c "SELECT tasks.task_prune(interval '-1 day');" 2>/dev/null)
[ "$PRUNED" -ge 1 ] && pass "task_prune removed $PRUNED archived row(s)" || fail "prune returned $PRUNED (expected ≥1)"

echo ""
echo "═══ AC-L1-10: Guarded migration — seed bus.todos → migrate → parity → drop ═══"
# Hermetic: redirect the migration's backup + marker dirs into a temp dir.
TMP_DIR="$(mktemp -d)"
$PSQL -c "CREATE SCHEMA bus;" >/dev/null 2>&1
$PSQL -c "CREATE TABLE bus.todos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    priority INT NOT NULL DEFAULT 0,
    session_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);" >/dev/null 2>&1
$PSQL -c "INSERT INTO bus.todos (content, agent_name, status, priority, session_id)
          VALUES ('old task 1','esther','pending',2,'sess-1'),
                 ('old task 2','esther','completed',1,NULL),
                 ('old task 3','esther','cancelled',0,'sess-3');" >/dev/null 2>&1
echo "  seeded 3 bus.todos rows (incl. completed + NULL-session_id)"

BEFORE_COUNT=$($PSQL -c "SELECT count(*) FROM bus.todos;" 2>/dev/null)
[ "$BEFORE_COUNT" = "3" ] && pass "seed present (3 rows)" || fail "seed count = $BEFORE_COUNT (expected 3)"

MIGRATE_OUT=$(MIGRATE_BACKUP_DIR="$TMP_DIR" MIGRATE_MARKER_DIR="$TMP_DIR" \
  python3 "$MIGRATE_BUS_PY" --db-name "$TEST_DB" 2>&1) && MIG_RC=0 || MIG_RC=1
[ "$MIG_RC" = "0" ] && pass "migrate-bus-todos.py ran clean" || fail "migration failed: $(echo "$MIGRATE_OUT" | tail -3)"

# Count parity against the 3 seeded rows — filter by fixture content so the
# fleet row from AC-L1-8 (also created_by=esther) doesn't pollute the count.
TASKS_COUNT=$($PSQL -c "SELECT count(*) FROM tasks.tasks WHERE content LIKE 'old task %';" 2>/dev/null)
[ "$TASKS_COUNT" = "3" ] && pass "count parity: 3 rows in tasks.tasks" || fail "tasks.tasks has $TASKS_COUNT (expected 3)"

BUS_GONE=$($PSQL -c "SELECT count(*) FROM pg_tables WHERE schemaname='bus' AND tablename='todos';" 2>/dev/null)
[ "$BUS_GONE" = "0" ] && pass "bus.todos dropped (table-scoped)" || fail "bus.todos still present (got: $BUS_GONE)"

BUS_ALIVE=$($PSQL -c "SELECT count(*) FROM pg_namespace WHERE nspname='bus';" 2>/dev/null)
[ "$BUS_ALIVE" = "1" ] && pass "bus schema intact (never DROP SCHEMA)" || fail "bus schema missing (got: $BUS_ALIVE)"

MARKER_WRITTEN=$([ -f "$TMP_DIR/bus-todos-migrated.json" ] && echo yes || echo no)
[ "$MARKER_WRITTEN" = "yes" ] && pass "marker written to redirected dir (no real-state pollution)" || fail "marker missing in TMP_DIR"

NOOP_OUT=$(MIGRATE_BACKUP_DIR="$TMP_DIR" MIGRATE_MARKER_DIR="$TMP_DIR" \
  python3 "$MIGRATE_BUS_PY" --db-name "$TEST_DB" 2>&1) && NOOP_RC=0 || NOOP_RC=1
if [ "$NOOP_RC" = "0" ] && echo "$NOOP_OUT" | grep -q "does not exist"; then
  pass "migration re-run is an idempotent no-op"
else
  fail "re-run not a no-op: $(echo "$NOOP_OUT" | tail -2)"
fi

echo ""
echo "═══ Summary ═══"
echo "  ${P} passed, ${F} failed"
[ "$F" -eq 0 ] || echo "  ❌ SOME TESTS FAILED — investigate before shipping"
exit $F
