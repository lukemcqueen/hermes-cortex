#!/usr/bin/env bash
# test-tasks-schema.sh — L1 hermetic AC battery for the tasks schema (v001–v005)
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
# A non-orchestrator profile role, so the tests can drive the WORKER side of the
# review gate (profile_of() → 'probe', and NOT a todos_fleet_writer member).
PROBE_ROLE="${TASKS_TEST_PROBE_ROLE:-mycortex_reader_probe}"

if [[ "$TEST_DB" == "mycortex" ]]; then
  echo "❌ REFUSING to run against the $TEST_DB database — hermeticity guard. Set TASKS_TEST_DB." >&2
  exit 1
fi

PSQL="docker exec ${CONTAINER} psql -U mycortex -d ${TEST_DB} -t -A"
PSQL_SUPER="docker exec ${CONTAINER} psql -U mycortex -d mycortex -t -A"
PSQL_READER="docker exec ${CONTAINER} psql -U mycortex_reader_esther -d ${TEST_DB} -t -A"
PSQL_PROBE="docker exec ${CONTAINER} psql -U ${PROBE_ROLE} -d ${TEST_DB} -t -A"

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
# Temp worker profile role — cluster-level, mimics a fleet worker's DB role
# (LOGIN so psql can connect as it; trust auth inside the container). It is a
# member of mycortex_reader for the table/function GRANTs, which does NOT make
# it a todos_fleet_writer member — so it is exactly the non-orchestrator case
# the v014 review gate must refuse.
$PSQL_SUPER -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='${PROBE_ROLE}') THEN CREATE ROLE ${PROBE_ROLE} LOGIN; END IF; END \$\$;" >/dev/null 2>&1
$PSQL_SUPER -c "GRANT mycortex_reader TO ${PROBE_ROLE};" >/dev/null 2>&1
echo "  created ${TEST_DB} + temp worker role ${PROBE_ROLE}"

echo ""
echo "═══ AC-L1-1: Fresh DB → migrate.py applies v001–v004; schema exists ═══"
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

# v005 transition matrix: pending → completed is ILLEGAL (must start first)
if $PSQL -c "SELECT tasks.task_upsert(p_id=>'${NEW_ID}', p_status=>'completed');" >/dev/null 2>&1; then
  fail "pending → completed accepted (v005 matrix)"
else
  pass "pending → completed rejected (v005 matrix — must start first)"
fi

# legal arc: in_progress → completed
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${NEW_ID}', p_status=>'in_progress');" >/dev/null 2>&1
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${NEW_ID}', p_status=>'completed');" >/dev/null 2>&1
COL_DONE=$($PSQL -c "SELECT \"column\" FROM tasks.tasks WHERE id='${NEW_ID}';" 2>/dev/null)
[ "$COL_DONE" = "done" ] && pass "completed → column='done' (derived)" || fail "completed column=$COL_DONE (expected 'done')"

DONE_AT=$($PSQL -c "SELECT completed_at IS NOT NULL FROM tasks.tasks WHERE id='${NEW_ID}';" 2>/dev/null)
[ "$DONE_AT" = "t" ] && pass "completed_at set on completion" || fail "completed_at not set (got: $DONE_AT)"

# v005 matrix: completed → cancelled is ILLEGAL
if $PSQL -c "SELECT tasks.task_upsert(p_id=>'${NEW_ID}', p_status=>'cancelled');" >/dev/null 2>&1; then
  fail "completed → cancelled accepted (v005 matrix)"
else
  pass "completed → cancelled rejected (v005 matrix)"
fi

# v005 matrix: reopen requires reason='reopen' (session GUC set by the CLI)
if $PSQL -c "SELECT tasks.task_upsert(p_id=>'${NEW_ID}', p_status=>'in_progress');" >/dev/null 2>&1; then
  fail "completed → in_progress accepted without reopen reason"
else
  pass "completed → in_progress rejected without reopen reason"
fi
$PSQL -c "SELECT set_config('tasks.transition_reason','reopen',false); SELECT tasks.task_upsert(p_id=>'${NEW_ID}', p_status=>'in_progress');" >/dev/null 2>&1
REOPENED=$($PSQL -c "SELECT status FROM tasks.tasks WHERE id='${NEW_ID}';" 2>/dev/null)
[ "$REOPENED" = "in_progress" ] && pass "completed → in_progress accepted with reason='reopen'" || fail "reopen failed (status=$REOPENED)"

# Regression (v003/v004): update an EXISTING row to cancelled must derive
# column=NULL, not carry over a stale column (v004: EXCLUDED."column").
NEW_ID2=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 cancel regression', p_created_by=>'esther');" 2>/dev/null | head -1)
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${NEW_ID2}', p_status=>'in_progress');" >/dev/null 2>&1
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${NEW_ID2}', p_status=>'cancelled');" >/dev/null 2>&1
COL_CANC=$($PSQL -c "SELECT \"column\" IS NULL FROM tasks.tasks WHERE id='${NEW_ID2}';" 2>/dev/null)
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
echo "═══ AC-L1-11: hierarchy — story/slice coherence + tenant checks ═══"
# story + slice under it (legal)
STORY_ID=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 story', p_created_by=>'esther', p_kind=>'story');" 2>/dev/null | head -1)
[ -n "$STORY_ID" ] && pass "story created (id=$STORY_ID)" || fail "story insert returned no id"
SLICE_ID=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 slice', p_created_by=>'esther', p_kind=>'slice', p_parent_id=>'${STORY_ID}');" 2>/dev/null | head -1)
[ -n "$SLICE_ID" ] && pass "slice under story created (id=$SLICE_ID)" || fail "slice insert returned no id"

# slice without a parent → coherence CHECK
if $PSQL -c "SELECT tasks.task_upsert(p_content=>'orphan slice', p_created_by=>'esther', p_kind=>'slice');" >/dev/null 2>&1; then
  fail "slice without parent accepted"
else
  pass "slice without parent rejected (coherence CHECK)"
fi
# story with a parent → coherence CHECK
if $PSQL -c "SELECT tasks.task_upsert(p_content=>'sub story', p_created_by=>'esther', p_kind=>'story', p_parent_id=>'${STORY_ID}');" >/dev/null 2>&1; then
  fail "story with parent accepted"
else
  pass "story with parent rejected (coherence CHECK)"
fi
# slice under a slice → tenant trigger (parent must be a story)
if $PSQL -c "SELECT tasks.task_upsert(p_content=>'sub slice', p_created_by=>'esther', p_kind=>'slice', p_parent_id=>'${SLICE_ID}');" >/dev/null 2>&1; then
  fail "slice under slice accepted"
else
  pass "slice under slice rejected (tenant trigger: parent must be story)"
fi
# deleting a story with slices → FK ON DELETE NO ACTION
if $PSQL -c "DELETE FROM tasks.tasks WHERE id='${STORY_ID}';" >/dev/null 2>&1; then
  fail "story deleted while slices exist"
else
  pass "story delete blocked while slices exist (FK NO ACTION)"
fi
# legacy flat rows (kind NULL, parent NULL) stay legal — backfill target
FLAT_OK=$($PSQL -c "SELECT count(*) FROM tasks.tasks WHERE kind IS NULL AND parent_id IS NULL AND status IN ('pending','in_progress');" 2>/dev/null)
[ "$FLAT_OK" -ge 1 ] && pass "legacy flat rows legal (kind NULL, n=$FLAT_OK)" || fail "no legacy flat rows found"

# ── AC-L1-11c: fleet slice under a personal orchestrator-owned story ──
# Regression (2026-10-18, backlog f0c6afbf): the pass protocol creates a path-citing
# fleet story + a PII-clean fleet slice. The path-citing STORY necessarily degrades to
# personal (B-5 scrub keeps PII out of fleet rows — correct, gate never weakened), so a
# fleet slice would then be refused by check_tenant ("slice scope (fleet) exceeds parent
# scope (personal)"). Fix (v013): relax check_tenant ONLY for orchestrator-owned
# personal parents (created_by IN moses/esther); the slice's OWN content is still
# enforced PII-clean by RLS WITH CHECK + fleet-writer role, so no leak.
ORCH_STORY=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 orchestrator story', p_created_by=>'esther', p_kind=>'story');" 2>/dev/null | head -1)
[ -n "$ORCH_STORY" ] && pass "orchestrator personal story created (id=$ORCH_STORY)" || fail "orchestrator story insert failed"
ORCH_SLICE=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 PII-clean fleet slice', p_created_by=>'esther', p_kind=>'slice', p_parent_id=>'${ORCH_STORY}', p_scope=>'fleet');" 2>/dev/null | head -1)
if [ -n "$ORCH_SLICE" ]; then
  ORCH_SLICE_SCOPE=$($PSQL -c "SELECT scope FROM tasks.tasks WHERE id='${ORCH_SLICE}';" 2>/dev/null)
  [ "$ORCH_SLICE_SCOPE" = "fleet" ] && pass "fleet slice under orchestrator personal story stored scope=fleet" || fail "fleet slice stored scope=$ORCH_SLICE_SCOPE (want fleet)"
else
  fail "fleet slice under orchestrator personal story refused — check_tenant over-strict"
fi
# coherence preserved: a fleet slice under a NON-orchestrator personal story stays refused
USER_STORY=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 worker story', p_created_by=>'alice', p_kind=>'story');" 2>/dev/null | head -1)
[ -n "$USER_STORY" ] && pass "non-orchestrator personal story created (id=$USER_STORY)" || fail "worker story insert failed"
# Connectivity/health pre-check: if psql cannot reach the DB at all, the refusal
# branch below would pass for the WRONG reason. Prove psql answers first.
if $PSQL -c "SELECT 1;" >/dev/null 2>&1; then
  WRK_ERR=$( { $PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 worker fleet slice', p_created_by=>'alice', p_kind=>'slice', p_parent_id=>'${USER_STORY}', p_scope=>'fleet');"; } 2>&1 || true )
  if [ -z "$WRK_ERR" ]; then
    fail "fleet slice under non-orchestrator personal story accepted — relaxation too broad"
  elif echo "$WRK_ERR" | grep -q "exceeds parent scope"; then
    pass "fleet slice under non-orchestrator personal story still refused (coherence — 'exceeds parent scope')"
  else
    fail "non-orchestrator fleet slice refused for an UNEXPECTED reason (not scope coherence): $(echo "$WRK_ERR" | head -c 120)"
  fi
else
  fail "psql connectivity pre-check failed — cannot distinguish policy refusal from DB-down"
fi

echo ""
echo "═══ AC-L1-12: paused status + switching arc ═══"
PAUSED_ID=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 pause arc', p_created_by=>'esther');" 2>/dev/null | head -1)
# pending → paused is ILLEGAL (must start first)
if $PSQL -c "SELECT tasks.task_upsert(p_id=>'${PAUSED_ID}', p_status=>'paused');" >/dev/null 2>&1; then
  fail "pending → paused accepted (must start first)"
else
  pass "pending → paused rejected (matrix — must start first)"
fi
# in_progress → paused ✓, column derived NULL
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${PAUSED_ID}', p_status=>'in_progress');" >/dev/null 2>&1
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${PAUSED_ID}', p_status=>'paused');" >/dev/null 2>&1
PAUSED_COL=$($PSQL -c "SELECT \"column\" IS NULL FROM tasks.tasks WHERE id='${PAUSED_ID}';" 2>/dev/null)
[ "$PAUSED_COL" = "t" ] && pass "paused derives column=NULL" || fail "paused column not NULL (got: $PAUSED_COL)"
# resume paused → in_progress ✓; paused → completed ✓
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${PAUSED_ID}', p_status=>'in_progress');" >/dev/null 2>&1
RESUMED=$($PSQL -c "SELECT status FROM tasks.tasks WHERE id='${PAUSED_ID}';" 2>/dev/null)
[ "$RESUMED" = "in_progress" ] && pass "paused → in_progress resume ✓" || fail "resume failed (status=$RESUMED)"
# paused status is in the CHECK — verify accepted value set
PAUSED_CNT=$($PSQL -c "SELECT count(*) FROM tasks.tasks WHERE status='paused';" 2>/dev/null)
# (the in_progress above un-paused it; force one for the count)
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${PAUSED_ID}', p_status=>'paused');" >/dev/null 2>&1
PAUSED_CNT=$($PSQL -c "SELECT count(*) FROM tasks.tasks WHERE status='paused';" 2>/dev/null)
[ "$PAUSED_CNT" = "1" ] && pass "paused status persisted (n=$PAUSED_CNT)" || fail "paused count=$PAUSED_CNT (expected 1)"

echo ""
echo "═══ AC-L1-13: transition matrix — spot checks ═══"
# in_progress → pending LEGAL since v009 (unclaim feature); the check below
# asserts the unclaim arc is now admitted (was ILLEGAL pre-v009)
MAT_ID=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 matrix', p_created_by=>'esther');" 2>/dev/null | head -1)
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${MAT_ID}', p_status=>'in_progress');" >/dev/null 2>&1
if $PSQL -c "SELECT tasks.task_upsert(p_id=>'${MAT_ID}', p_status=>'pending');" >/dev/null 2>&1; then
  pass "in_progress → pending accepted (v009 unclaim arc)"
else
  fail "in_progress → pending rejected (v009 should admit it)"
fi
# cancelled is terminal
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${MAT_ID}', p_status=>'cancelled');" >/dev/null 2>&1
if $PSQL -c "SELECT tasks.task_upsert(p_id=>'${MAT_ID}', p_status=>'in_progress');" >/dev/null 2>&1; then
  fail "cancelled → in_progress accepted"
else
  pass "cancelled → in_progress rejected (terminal)"
fi
# paused → completed legal
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${PAUSED_ID}', p_status=>'completed');" >/dev/null 2>&1
PAUSED_DONE=$($PSQL -c "SELECT status FROM tasks.tasks WHERE id='${PAUSED_ID}';" 2>/dev/null)
[ "$PAUSED_DONE" = "completed" ] && pass "paused → completed legal" || fail "paused → completed failed (status=$PAUSED_DONE)"
# story gate (Domain R-3): story cannot complete while a slice is active;
# completes once all slices are done OR cancelled
GATE_STORY=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 gate story', p_created_by=>'esther', p_kind=>'story');" 2>/dev/null | head -1)
GATE_SLICE=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 gate slice', p_created_by=>'esther', p_kind=>'slice', p_parent_id=>'${GATE_STORY}');" 2>/dev/null | head -1)
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${GATE_STORY}', p_status=>'in_progress');" >/dev/null 2>&1
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${GATE_SLICE}', p_status=>'in_progress');" >/dev/null 2>&1
if $PSQL -c "SELECT tasks.task_upsert(p_id=>'${GATE_STORY}', p_status=>'completed');" >/dev/null 2>&1; then
  fail "story completed while slice active (gate broken)"
else
  pass "story with active slice rejected (gate)"
fi
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${GATE_SLICE}', p_status=>'completed');" >/dev/null 2>&1
if $PSQL -c "SELECT tasks.task_upsert(p_id=>'${GATE_STORY}', p_status=>'completed');" >/dev/null 2>&1; then
  pass "story completes when all slices done"
else
  fail "story blocked after slices done (gate false positive)"
fi
GATE_STORY2=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 gate story 2', p_created_by=>'esther', p_kind=>'story');" 2>/dev/null | head -1)
GATE_SLICE2=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 gate slice 2', p_created_by=>'esther', p_kind=>'slice', p_parent_id=>'${GATE_STORY2}');" 2>/dev/null | head -1)
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${GATE_STORY2}', p_status=>'in_progress');" >/dev/null 2>&1
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${GATE_SLICE2}', p_status=>'in_progress');" >/dev/null 2>&1
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${GATE_SLICE2}', p_status=>'cancelled');" >/dev/null 2>&1
if $PSQL -c "SELECT tasks.task_upsert(p_id=>'${GATE_STORY2}', p_status=>'completed');" >/dev/null 2>&1; then
  pass "story completes when slices cancelled"
else
  fail "story blocked with cancelled slices (gate false positive)"
fi

echo ""
echo "═══ AC-L1-14: task_events — capture, no-op gate, suppression, RLS ═══"
# created + status_changed events recorded for the story/slice
STORY_EVENTS=$($PSQL -c "SELECT count(*) FROM tasks.task_events WHERE task_id='${STORY_ID}';" 2>/dev/null)
[ "$STORY_EVENTS" = "1" ] && pass "story created event recorded" || fail "story events=$STORY_EVENTS (expected 1)"
SLICE_EVENTS=$($PSQL -c "SELECT count(*) FROM tasks.task_events WHERE task_id='${SLICE_ID}';" 2>/dev/null)
[ "$SLICE_EVENTS" = "1" ] && pass "slice created event recorded" || fail "slice events=$SLICE_EVENTS (expected 1)"
# no-op update (status unchanged) emits nothing
NOOP_ID=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 noop', p_created_by=>'esther');" 2>/dev/null | head -1)
N_BEFORE=$($PSQL -c "SELECT count(*) FROM tasks.task_events WHERE task_id='${NOOP_ID}';" 2>/dev/null)
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${NOOP_ID}', p_status=>'pending');" >/dev/null 2>&1
N_AFTER=$($PSQL -c "SELECT count(*) FROM tasks.task_events WHERE task_id='${NOOP_ID}';" 2>/dev/null)
[ "$N_BEFORE" = "$N_AFTER" ] && pass "no-op status update emits no event ($N_AFTER)" || fail "no-op gate broken: $N_BEFORE → $N_AFTER"
# doctor-probe rows emit nothing
PROBE_ID=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 probe', p_created_by=>'esther', p_source=>'doctor-probe');" 2>/dev/null | head -1)
N_PROBE=$($PSQL -c "SELECT count(*) FROM tasks.task_events WHERE task_id='${PROBE_ID}';" 2>/dev/null)
[ "$N_PROBE" = "0" ] && pass "doctor-probe creates no event (suppression M-5)" || fail "doctor-probe emitted $N_PROBE events"
# status_changed event carries from/to
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${NOOP_ID}', p_status=>'in_progress');" >/dev/null 2>&1
EVT_FROM_TO=$($PSQL -c "SELECT from_status||'->'||to_status FROM tasks.task_events WHERE task_id='${NOOP_ID}' AND event_type='status_changed';" 2>/dev/null)
[ "$EVT_FROM_TO" = "pending->in_progress" ] && pass "status_changed event records pending->in_progress" || fail "event from/to wrong (got: $EVT_FROM_TO)"
# RLS: plain reader sees zero events for personal tasks; sees fleet events
# (fleet row from AC-L1-8 has a created event) when an orchestrator profile
# exists on this host.
READER_PERSONAL=$($READER_PSQL -c "SELECT count(*) FROM tasks.task_events e JOIN tasks.tasks t ON t.id=e.task_id WHERE t.scope='personal';" 2>/dev/null)
[ "$READER_PERSONAL" = "0" ] && pass "reader sees zero personal events (isolation)" || fail "reader personal events=$READER_PERSONAL (isolation leak)"
if [[ -n "$FW_CONNECT" ]]; then
  FLEET_EVENTS=$($READER_PSQL -c "SELECT count(*) FROM tasks.task_events e JOIN tasks.tasks t ON t.id=e.task_id WHERE t.scope='fleet';" 2>/dev/null)
  [ "$FLEET_EVENTS" -ge 1 ] && pass "reader sees fleet events (n=$FLEET_EVENTS)" || fail "reader fleet events=$FLEET_EVENTS (expected ≥1)"
else
  echo "  ⚠ no orchestrator profile role — skipping fleet-event visibility assertion (worker host)"
fi
# no direct DML grants on task_events for readers (INSERT-only via task_log_event)
if $READER_PSQL -c "INSERT INTO tasks.task_events (task_id, event_type, by) VALUES ('${STORY_ID}', 'created', 'x');" >/dev/null 2>&1; then
  fail "reader direct INSERT into task_events accepted"
else
  pass "reader direct INSERT into task_events denied (no grant)"
fi
if $READER_PSQL -c "UPDATE tasks.task_events SET reason='x';" >/dev/null 2>&1; then
  fail "reader UPDATE task_events accepted"
else
  pass "reader UPDATE task_events denied (no grant)"
fi

echo ""
echo "═══ AC-L1-15: correlation_id — 1 task per inbox message ═══"
CORR_ID=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 corr', p_created_by=>'esther', p_source=>'inbox', p_correlation_id=>'msg-l1-1');" 2>/dev/null | head -1)
[ -n "$CORR_ID" ] && pass "inbox task created with correlation_id" || fail "correlation insert failed"
if $PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 corr dup', p_created_by=>'esther', p_source=>'inbox', p_correlation_id=>'msg-l1-1');" >/dev/null 2>&1; then
  fail "duplicate inbox correlation accepted"
else
  pass "duplicate inbox correlation rejected (partial unique)"
fi

echo ""
echo "═══ AC-L1-16: 17-arg task_upsert legacy compatibility ═══"
LEGACY_ID="00000000-0000-0000-0000-0000000000aa"
LEGACY_RET=$($PSQL -c "SELECT tasks.task_upsert('${LEGACY_ID}'::uuid, 'legacy 17-arg', 'esther', NULL, 'hermes-cortex', NULL, NULL, 'personal', 'pending', NULL, NULL, 1, NULL, NULL, 'manual', NULL, 'sess-legacy');" 2>/dev/null | head -1)
[ "$LEGACY_RET" = "$LEGACY_ID" ] && pass "17-arg positional call resolves via trailing defaults" || fail "17-arg call failed (got: $LEGACY_RET)"

echo ""
echo "═══ AC-L1-17: poisoned migration — single-transaction rollback ═══"
POISON_DIR="$(mktemp -d)"
cp "${REPO_DIR}"/ops/services/tasks/schema/v0*.sql "$POISON_DIR"/
echo "THIS IS NOT VALID SQL;" > "$POISON_DIR/v099__poison.sql"
if MIGRATE_POISON_OUT=$(python3 "$MIGRATE_PY" --db-name "$TEST_DB" --schema-dir "$POISON_DIR" 2>&1); then
  fail "poisoned migration succeeded (rc=0)"
else
  VER_AFTER_POISON=$($PSQL -c "SELECT max(version) FROM tasks.schema_version;" 2>/dev/null)
  [ "$VER_AFTER_POISON" = "$EXPECTED_VER" ] && pass "poisoned migration failed and version stayed $EXPECTED_VER (rollback)" || fail "version moved to $VER_AFTER_POISON after poison (expected $EXPECTED_VER)"
fi
rm "$POISON_DIR/v099__poison.sql"
if python3 "$MIGRATE_PY" --db-name "$TEST_DB" --schema-dir "$POISON_DIR" 2>/dev/null | grep -q "no-op"; then
  pass "migration re-run after poison removal is a no-op"
else
  fail "re-run after poison removal not a no-op"
fi
rm -rf "$POISON_DIR"

echo ""
echo "═══ AC-L1-18: v008 — blocked/waiting status (M-7) ═══"
# status CHECK accepts blocked/waiting; column derives NULL (paused class)
BLK_ID=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 blocked', p_created_by=>'esther', p_status=>'blocked');" 2>/dev/null | head -1)
[ -n "$BLK_ID" ] && pass "blocked status accepted" || fail "blocked insert returned no id"
BLK_COL=$($PSQL -c "SELECT \"column\" IS NULL FROM tasks.tasks WHERE id='${BLK_ID}';" 2>/dev/null)
[ "$BLK_COL" = "t" ] && pass "blocked derives column=NULL" || fail "blocked column not NULL (got: $BLK_COL)"
WAI_ID=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 waiting', p_created_by=>'esther', p_status=>'waiting');" 2>/dev/null | head -1)
[ -n "$WAI_ID" ] && pass "waiting status accepted" || fail "waiting insert returned no id"
WAI_COL=$($PSQL -c "SELECT \"column\" IS NULL FROM tasks.tasks WHERE id='${WAI_ID}';" 2>/dev/null)
[ "$WAI_COL" = "t" ] && pass "waiting derives column=NULL" || fail "waiting column not NULL (got: $WAI_COL)"
# transition matrix: pending→blocked, blocked→in_progress, waiting→in_progress,
# blocked→waiting, in_progress→blocked; blocked→pending is LEGAL since v012
# (a parked row must be able to rejoin the pull pool — the whole point of that
# migration; v009 had left every parked state with no arc back to `pending`).
# This assertion asserted the v009 rule and had been RED since v012 landed.
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${BLK_ID}', p_status=>'in_progress');" >/dev/null 2>&1
BLK_RES=$($PSQL -c "SELECT status FROM tasks.tasks WHERE id='${BLK_ID}';" 2>/dev/null)
[ "$BLK_RES" = "in_progress" ] && pass "blocked → in_progress resume ✓" || fail "blocked resume failed (status=$BLK_RES)"
# re-establish blocked (in_progress → blocked is legal) so the next check
# genuinely tests blocked → pending (not in_progress → pending, which v009
# admits via the unclaim arc)
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${BLK_ID}', p_status=>'blocked');" >/dev/null 2>&1
BLK_PEND=$($PSQL -c "SELECT tasks.task_upsert(p_id=>'${BLK_ID}', p_status=>'pending');" 2>/dev/null)
BLK_PEND_ST=$($PSQL -c "SELECT status FROM tasks.tasks WHERE id='${BLK_ID}';" 2>/dev/null)
[ -n "$BLK_PEND" ] && [ "$BLK_PEND_ST" = "pending" ] \
  && pass "blocked → pending accepted and lands (v012: parked rows rejoin the pool)" \
  || fail "blocked → pending failed (ret=$BLK_PEND status=$BLK_PEND_ST)"
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${WAI_ID}', p_status=>'blocked');" >/dev/null 2>&1
WAI_RES=$($PSQL -c "SELECT status FROM tasks.tasks WHERE id='${WAI_ID}';" 2>/dev/null)
[ "$WAI_RES" = "blocked" ] && pass "waiting → blocked ✓" || fail "waiting→blocked failed (status=$WAI_RES)"
# blocked → completed legal (resolved without further work)
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${WAI_ID}', p_status=>'completed');" >/dev/null 2>&1
WAI_DONE=$($PSQL -c "SELECT status FROM tasks.tasks WHERE id='${WAI_ID}';" 2>/dev/null)
[ "$WAI_DONE" = "completed" ] && pass "blocked → completed legal" || fail "blocked→completed failed (status=$WAI_DONE)"

echo ""
echo "═══ AC-L1-19: v008 — task_story_summary() (M-7 tooling) ═══"
SUMM_STORY=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 summary story', p_created_by=>'esther', p_kind=>'story');" 2>/dev/null | head -1)
S1=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 sum slice 1', p_created_by=>'esther', p_kind=>'slice', p_parent_id=>'${SUMM_STORY}');" 2>/dev/null | head -1)
S2=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 sum slice 2', p_created_by=>'esther', p_kind=>'slice', p_parent_id=>'${SUMM_STORY}');" 2>/dev/null | head -1)
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${S1}', p_status=>'in_progress');" >/dev/null 2>&1
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${S1}', p_status=>'completed');" >/dev/null 2>&1
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${S2}', p_status=>'blocked');" >/dev/null 2>&1
SUMM=$($PSQL -c "SELECT tasks.task_story_summary('${SUMM_STORY}');" 2>/dev/null)
echo "$SUMM" | grep -q '"total_slices": 2' && pass "summary total_slices=2" || fail "summary total wrong: $SUMM"
echo "$SUMM" | grep -q '"completed": 1' && pass "summary completed=1" || fail "summary completed wrong: $SUMM"
echo "$SUMM" | grep -q '"blocked": 1' && pass "summary blocked=1" || fail "summary blocked wrong: $SUMM"
echo "$SUMM" | grep -q '"active": 1' && pass "summary active=1" || fail "summary active wrong: $SUMM"
echo "$SUMM" | grep -q '"done_ratio": 50' && pass "summary done_ratio=50" || fail "summary ratio wrong: $SUMM"
# non-story / invisible id → NULL
SUMM_NULL=$($PSQL -c "SELECT tasks.task_story_summary('${S1}');" 2>/dev/null)
[ -z "$SUMM_NULL" ] && pass "summary on a slice returns NULL" || fail "summary on slice returned: $SUMM_NULL"

echo ""
echo "═══ AC-L1-20: v008 — story auto-complete (R-3 polish) ═══"
AC_STORY=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 auto story', p_created_by=>'esther', p_kind=>'story');" 2>/dev/null | head -1)
AC_S1=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 auto slice 1', p_created_by=>'esther', p_kind=>'slice', p_parent_id=>'${AC_STORY}');" 2>/dev/null | head -1)
AC_S2=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 auto slice 2', p_created_by=>'esther', p_kind=>'slice', p_parent_id=>'${AC_STORY}');" 2>/dev/null | head -1)
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${AC_S1}', p_status=>'in_progress');" >/dev/null 2>&1
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${AC_S2}', p_status=>'in_progress');" >/dev/null 2>&1
# first slice done — story must NOT auto-complete yet (sibling still active)
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${AC_S1}', p_status=>'completed');" >/dev/null 2>&1
AC_MID=$($PSQL -c "SELECT status FROM tasks.tasks WHERE id='${AC_STORY}';" 2>/dev/null)
[ "$AC_MID" = "pending" ] && pass "story stays pending after first slice done" || fail "story auto-completed too early (status=$AC_MID)"
# last slice done — story auto-completes with reason + event
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${AC_S2}', p_status=>'completed');" >/dev/null 2>&1
AC_DONE=$($PSQL -c "SELECT status FROM tasks.tasks WHERE id='${AC_STORY}';" 2>/dev/null)
[ "$AC_DONE" = "completed" ] && pass "story auto-completes when last slice done" || fail "story not auto-completed (status=$AC_DONE)"
AC_EVT=$($PSQL -c "SELECT count(*) FROM tasks.task_events WHERE task_id='${AC_STORY}' AND event_type='story_auto_complete';" 2>/dev/null)
[ "$AC_EVT" = "1" ] && pass "story_auto_complete event recorded (n=$AC_EVT)" || fail "story_auto_complete events=$AC_EVT (expected 1)"
# cancelled-last-slice path: story auto-completes too
AC2_STORY=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 auto story 2', p_created_by=>'esther', p_kind=>'story');" 2>/dev/null | head -1)
AC2_S1=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 auto slice 2a', p_created_by=>'esther', p_kind=>'slice', p_parent_id=>'${AC2_STORY}');" 2>/dev/null | head -1)
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${AC2_S1}', p_status=>'in_progress');" >/dev/null 2>&1
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${AC2_S1}', p_status=>'cancelled');" >/dev/null 2>&1
AC2_DONE=$($PSQL -c "SELECT status FROM tasks.tasks WHERE id='${AC2_STORY}';" 2>/dev/null)
[ "$AC2_DONE" = "completed" ] && pass "story auto-completes when last slice cancelled" || fail "cancelled-slice story not completed (status=$AC2_DONE)"
# manual story completion path unchanged: story with active slice still blocked
AC3_STORY=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 gate story 3', p_created_by=>'esther', p_kind=>'story');" 2>/dev/null | head -1)
AC3_S1=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 gate slice 3', p_created_by=>'esther', p_kind=>'slice', p_parent_id=>'${AC3_STORY}');" 2>/dev/null | head -1)
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${AC3_S1}', p_status=>'in_progress');" >/dev/null 2>&1
if $PSQL -c "SELECT tasks.task_upsert(p_id=>'${AC3_STORY}', p_status=>'completed');" >/dev/null 2>&1; then
  fail "manual story completion with active slice accepted (gate broken)"
else
  pass "manual story completion with active slice still rejected (gate)"
fi
# doctor-probe slice completion must NOT auto-complete its story (M-5)
AC4_STORY=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 probe story', p_created_by=>'esther', p_kind=>'story');" 2>/dev/null | head -1)
AC4_S1=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 probe slice', p_created_by=>'esther', p_kind=>'slice', p_parent_id=>'${AC4_STORY}', p_source=>'doctor-probe');" 2>/dev/null | head -1)
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${AC4_S1}', p_status=>'in_progress');" >/dev/null 2>&1
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${AC4_S1}', p_status=>'completed');" >/dev/null 2>&1
AC4_DONE=$($PSQL -c "SELECT status FROM tasks.tasks WHERE id='${AC4_STORY}';" 2>/dev/null)
[ "$AC4_DONE" = "pending" ] && pass "doctor-probe slice does not auto-complete story (M-5)" || fail "probe slice auto-completed story (status=$AC4_DONE)"

echo ""
echo "═══ AC-L1-21: v008 — archive children-first (M-4) ═══"
# completed story + completed slices → archive_old removes BOTH without FK error
AR_STORY=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 archive story', p_created_by=>'esther', p_kind=>'story');" 2>/dev/null | head -1)
AR_S1=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 archive slice', p_created_by=>'esther', p_kind=>'slice', p_parent_id=>'${AR_STORY}');" 2>/dev/null | head -1)
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${AR_S1}', p_status=>'in_progress');" >/dev/null 2>&1
# completing the last slice auto-completes the story (R-3) — both now done
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${AR_S1}', p_status=>'completed');" >/dev/null 2>&1
AR_REMAIN=$($PSQL -c "SELECT count(*) FROM tasks.tasks WHERE id IN ('${AR_STORY}','${AR_S1}');" 2>/dev/null)
[ "$AR_REMAIN" = "2" ] && pass "story + slice both terminal before archive (n=$AR_REMAIN)" || fail "pre-archive rows=$AR_REMAIN (expected 2)"
AR_ARCHIVED=$($PSQL -c "SELECT tasks.task_archive_old(p_created_by=>'esther');" 2>/dev/null)
[ "$AR_ARCHIVED" -ge 1 ] && pass "archive_old archived rows (n=$AR_ARCHIVED)" || fail "archive_old returned $AR_ARCHIVED (expected ≥1)"
AR_LEFT=$($PSQL -c "SELECT count(*) FROM tasks.tasks WHERE id IN ('${AR_STORY}','${AR_S1}');" 2>/dev/null)
[ "$AR_LEFT" = "0" ] && pass "story + slices archived children-first (no FK error)" || fail "rows remain after archive (n=$AR_LEFT) — FK blocked?"

echo ""
echo "═══ AC-L1-22: v009 — task model v3 (claim/report/verify) ═══"
# 1. plan column exists
PLAN_OK=$($PSQL -c "SELECT count(*) FROM information_schema.columns WHERE table_schema='tasks' AND table_name='tasks' AND column_name='plan';" 2>/dev/null)
[ "$PLAN_OK" = "1" ] && pass "plan column exists" || fail "plan column missing (n=$PLAN_OK)"
# 2. review status exists in CHECK
REVIEW_OK=$($PSQL -c "SELECT count(*) FROM pg_constraint WHERE conname='tasks_status_check';" 2>/dev/null)
[ "$REVIEW_OK" -ge 1 ] && pass "status CHECK constraint present" || fail "status check missing"
# 3. claim_slice via READER role (self-only guard means superuser must NOT claim)
V3_STORY=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 v3 story', p_created_by=>'esther', p_kind=>'story');" 2>/dev/null | head -1)
V3_S1=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 v3 slice', p_created_by=>'esther', p_kind=>'slice', p_parent_id=>'${V3_STORY}');" 2>/dev/null | head -1)
CLAIM_AS_SUPER=$($PSQL -c "SELECT tasks.claim_slice('${V3_S1}', 'esther');" 2>/dev/null)
[ "$CLAIM_AS_SUPER" = "f" ] && pass "superuser claim refused (self-only guard: profile=mycortex)" || fail "superuser claim accepted ($CLAIM_AS_SUPER)"
CLAIM_OK=$($PSQL_READER -c "SELECT tasks.claim_slice('${V3_S1}', 'esther');" 2>/dev/null)
[ "$CLAIM_OK" = "t" ] && pass "claim_slice succeeded via reader (pending→in_progress)" || fail "claim_slice failed (got $CLAIM_OK)"
CLAIM_ST=$($PSQL_READER -c "SELECT status||':'||COALESCE(assignee,'-') FROM tasks.tasks WHERE id='${V3_S1}';" 2>/dev/null)
[ "$CLAIM_ST" = "in_progress:esther" ] && pass "claimed slice is in_progress by esther" || fail "claim state wrong ($CLAIM_ST)"
# 4. double-claim fails (already in_progress)
CLAIM2=$($PSQL_READER -c "SELECT tasks.claim_slice('${V3_S1}', 'esther');" 2>/dev/null)
[ "$CLAIM2" = "f" ] && pass "double-claim refused" || fail "double-claim accepted ($CLAIM2)"
# 5. cross-agent claim refused (claiming as titus for titus on an esther slice: allowed by design — any agent may claim ANY pending slice; but a claimed one must not be re-claimed)
CLAIM_OTHER=$($PSQL_READER -c "SELECT tasks.claim_slice('${V3_S1}', 'titus');" 2>/dev/null)
[ "$CLAIM_OTHER" = "f" ] && pass "already-claimed slice cannot be re-claimed (single claimer)" || fail "re-claim accepted ($CLAIM_OTHER)"
# 6. unclaim: in_progress → pending, clears assignee (only own work — esther unclaims her own)
UNCLAIM_OK=$($PSQL_READER -c "SELECT tasks.unclaim_slice('${V3_S1}');" 2>/dev/null)
[ "$UNCLAIM_OK" = "t" ] && pass "unclaim succeeded" || fail "unclaim failed ($UNCLAIM_OK)"
UNCLAIM_ST=$($PSQL_READER -c "SELECT status||':'||COALESCE(assignee,'-') FROM tasks.tasks WHERE id='${V3_S1}';" 2>/dev/null)
[ "$UNCLAIM_ST" = "pending:-" ] && pass "unclaimed slice back to pending, assignee cleared" || fail "unclaim state wrong ($UNCLAIM_ST)"
# 7. report_done: in_progress → review (re-claim first)
$PSQL_READER -c "SELECT tasks.claim_slice('${V3_S1}', 'esther');" >/dev/null 2>&1
REPORT_OK=$($PSQL_READER -c "SELECT tasks.report_done('${V3_S1}', 'tests pass');" 2>/dev/null)
[ "$REPORT_OK" = "t" ] && pass "report_done succeeded (in_progress→review)" || fail "report_done failed ($REPORT_OK)"
REPORT_ST=$($PSQL_READER -c "SELECT status FROM tasks.tasks WHERE id='${V3_S1}';" 2>/dev/null)
[ "$REPORT_ST" = "review" ] && pass "slice in review status" || fail "review state wrong ($REPORT_ST)"
# 8. orchestrator verify: review → completed (esther is an orchestrator)
VERIFY_OK=$($PSQL_READER -c "SELECT tasks.verify_slice('${V3_S1}', true, 'approved');" 2>/dev/null)
[ "$VERIFY_OK" = "t" ] && pass "orchestrator verify_slice succeeded (review→completed)" || fail "verify_slice failed ($VERIFY_OK)"
VERIFY_ST=$($PSQL_READER -c "SELECT status FROM tasks.tasks WHERE id='${V3_S1}';" 2>/dev/null)
[ "$VERIFY_ST" = "completed" ] && pass "verified slice completed" || fail "verify state wrong ($VERIFY_ST)"
# 10. verify-failed path: re-open → report → verify(false) → in_progress
$PSQL_READER -c "SET tasks.transition_reason = 'reopen'; SELECT tasks.task_upsert(p_id=>'${V3_S1}', p_status=>'in_progress');" >/dev/null 2>&1
$PSQL_READER -c "SELECT tasks.report_done('${V3_S1}', 'second attempt');" >/dev/null 2>&1
VERIFY_NO=$($PSQL_READER -c "SELECT tasks.verify_slice('${V3_S1}', false, 'evidence incomplete');" 2>/dev/null)
[ "$VERIFY_NO" = "t" ] && pass "verify_slice(false) returns true (rejected path)" || fail "verify(false) failed ($VERIFY_NO)"
VERIFY_NO_ST=$($PSQL_READER -c "SELECT status FROM tasks.tasks WHERE id='${V3_S1}';" 2>/dev/null)
[ "$VERIFY_NO_ST" = "in_progress" ] && pass "failed verify returns slice to in_progress" || fail "verify-fail state wrong ($VERIFY_NO_ST)"

echo ""
echo "═══ AC-L1-24: v014 — review→completed is orchestrator-only on EVERY write path ═══"
# Titus Pi finding (verified against the live store): verify_slice is
# orchestrator-only, but the ARC it performs was legal on the generic write
# path, so the gate was advisory. These checks drive the WORKER side as
# ${PROBE_ROLE} (profile_of() → 'probe', not a todos_fleet_writer member).
#
# Mimic the worker-host GRANTS: v009 grants claim/unclaim/report BY NAME to
# every profile role, and verify_slice to moses/esther ONLY — so a real worker
# cannot call verify_slice at all, which is precisely why the generic update
# path was the only route it had to a self-completed slice.
$PSQL -c "GRANT EXECUTE ON FUNCTION tasks.claim_slice(uuid,text), tasks.unclaim_slice(uuid,text), tasks.report_done(uuid,text) TO ${PROBE_ROLE};" >/dev/null 2>&1
W_SLICE=$($PSQL_PROBE -c "SELECT tasks.task_upsert(p_content=>'L1 v14 self-graded slice', p_created_by=>'probe', p_scope=>'personal');" 2>/dev/null | head -1)
W_CLAIM=$($PSQL_PROBE -c "SELECT tasks.claim_slice('${W_SLICE}', 'probe');" 2>/dev/null)
W_REPORT=$($PSQL_PROBE -c "SELECT tasks.report_done('${W_SLICE}', 'probe self-reported evidence');" 2>/dev/null)
W_ST=$($PSQL_PROBE -c "SELECT status FROM tasks.tasks WHERE id='${W_SLICE}';" 2>/dev/null)
[ "$W_CLAIM" = "t" ] && [ "$W_REPORT" = "t" ] && [ "$W_ST" = "review" ] \
  && pass "worker reached review on its own slice (claim+report)" \
  || fail "worker could not reach review (claim=$W_CLAIM report=$W_REPORT status=$W_ST)"

# 1. THE DEFECT: the generic update path (task_update / task-db.py update) must
#    NOT let the slice's own creator complete it from review.
W_RC=0
W_OUT=$($PSQL_PROBE -v ON_ERROR_STOP=1 -c "SELECT tasks.task_upsert(p_id=>'${W_SLICE}', p_status=>'completed');" 2>&1) || W_RC=$?
if [ "$W_RC" -ne 0 ] && echo "$W_OUT" | grep -q orchestrator; then
  pass "worker refused review→completed via task_upsert (rc=$W_RC)"
else
  fail "worker COMPLETED its own review slice via task_upsert (rc=$W_RC)" "$W_OUT"
fi

# 2. A raw UPDATE (bypassing task_upsert entirely) is refused by the same trigger.
W_RC2=0
W_OUT2=$($PSQL_PROBE -v ON_ERROR_STOP=1 -c "UPDATE tasks.tasks SET status='completed', \"column\"='done' WHERE id='${W_SLICE}';" 2>&1) || W_RC2=$?
if [ "$W_RC2" -ne 0 ] && echo "$W_OUT2" | grep -q orchestrator; then
  pass "worker refused review→completed via raw UPDATE (rc=$W_RC2)"
else
  fail "worker COMPLETED its own review slice via raw UPDATE (rc=$W_RC2)" "$W_OUT2"
fi

W_ST2=$($PSQL_PROBE -c "SELECT status FROM tasks.tasks WHERE id='${W_SLICE}';" 2>/dev/null)
[ "$W_ST2" = "review" ] && pass "slice still in review after both refused attempts" \
  || fail "slice left review (status=$W_ST2) — a refused write changed the row"

# 3. Both layers of the function-level gate hold for a worker: (a) no EXECUTE
#    grant at all, and (b) even WITH the grant, the in-function allowlist refuses.
W_RC3=0
W_OUT3=$($PSQL_PROBE -v ON_ERROR_STOP=1 -c "SELECT tasks.verify_slice('${W_SLICE}', true, 'self-approve');" 2>&1) || W_RC3=$?
if [ "$W_RC3" -ne 0 ] && echo "$W_OUT3" | grep -q "permission denied"; then
  pass "worker holds no EXECUTE on verify_slice (permission denied)"
else
  fail "worker could call verify_slice (rc=$W_RC3)" "$W_OUT3"
fi
$PSQL -c "GRANT EXECUTE ON FUNCTION tasks.verify_slice(uuid,boolean,text) TO ${PROBE_ROLE};" >/dev/null 2>&1
W_VERIFY=$($PSQL_PROBE -c "SELECT tasks.verify_slice('${W_SLICE}', true, 'self-approve');" 2>/dev/null)
$PSQL -c "REVOKE EXECUTE ON FUNCTION tasks.verify_slice(uuid,boolean,text) FROM ${PROBE_ROLE};" >/dev/null 2>&1
[ "$W_VERIFY" = "f" ] && pass "worker verify_slice still returns false (in-function allowlist)" \
  || fail "worker verify_slice returned $W_VERIFY (expected f)"

# 4. The ARC stays legal in the matrix — only the identity is gated. A later
#    reader must not "fix" this by editing transition_allowed.
ARC_OK=$($PSQL -c "SELECT tasks.transition_allowed('review','completed',NULL);" 2>/dev/null)
[ "$ARC_OK" = "t" ] && pass "transition_allowed('review','completed') still true (identity-gated, not arc-gated)" \
  || fail "review→completed removed from the matrix (got $ARC_OK)"

# 5. The REAL verification path still works, end-to-end. The status is read back
#    AS THE PROBE: the row is personal to the probe, so RLS hides it from the
#    esther reader (USING: scope='fleet' OR created_by = me) — a reader-side
#    read returns empty and would read as a failure that is not one.
W_APPROVE=$($PSQL_READER -c "SELECT tasks.verify_slice('${W_SLICE}', true, 'verified by esther');" 2>/dev/null)
W_ST3=$($PSQL_PROBE -c "SELECT status FROM tasks.tasks WHERE id='${W_SLICE}';" 2>/dev/null)
[ "$W_APPROVE" = "t" ] && [ "$W_ST3" = "completed" ] \
  && pass "orchestrator verify_slice still approves review→completed" \
  || fail "orchestrator verify broken (returned $W_APPROVE, status=$W_ST3)"

# 6. Scoping: a worker's own in_progress→completed (no verification claim) and
#    the story auto-complete path (which completes a story from the slice's
#    trigger, possibly under a worker's session_user) must still work.
S_STORY=$($PSQL_PROBE -c "SELECT tasks.task_upsert(p_content=>'L1 v14 probe story', p_created_by=>'probe', p_kind=>'story');" 2>/dev/null | head -1)
S_SLICE=$($PSQL_PROBE -c "SELECT tasks.task_upsert(p_content=>'L1 v14 probe story slice', p_created_by=>'probe', p_kind=>'slice', p_parent_id=>'${S_STORY}');" 2>/dev/null | head -1)
$PSQL_PROBE -c "SELECT tasks.claim_slice('${S_SLICE}', 'probe');" >/dev/null 2>&1
S_RC=0
$PSQL_PROBE -v ON_ERROR_STOP=1 -c "SELECT tasks.task_upsert(p_id=>'${S_SLICE}', p_status=>'completed');" >/dev/null 2>&1 || S_RC=$?
S_SLICE_ST=$($PSQL_PROBE -c "SELECT status FROM tasks.tasks WHERE id='${S_SLICE}';" 2>/dev/null)
S_STORY_ST=$($PSQL_PROBE -c "SELECT status FROM tasks.tasks WHERE id='${S_STORY}';" 2>/dev/null)
[ "$S_RC" -eq 0 ] && [ "$S_SLICE_ST" = "completed" ] \
  && pass "worker in_progress→completed still allowed (not a verification claim)" \
  || fail "guard over-reached: worker slice completion refused (rc=$S_RC, status=$S_SLICE_ST)"
[ "$S_STORY_ST" = "completed" ] && pass "story auto-complete still fires under a worker session" \
  || fail "story auto-complete broken (story status=$S_STORY_ST)"

echo ""
echo "═══ AC-L1-25: v015 — the story gate is verified, not GUC-authorised ═══"
# v008 admitted story→completed by consulting tasks.transition_reason, and put that
# early return ABOVE the R-3 gate. The reason is written by the CALLER, so the gate
# was skippable by anyone who could write the row.
#
# The reachable form matters: task_upsert() PRE-CHECKS transition_allowed() and the
# matrix (v012) forbids pending→completed, so a caller must first move the story to
# in_progress (legal) — then the reason is the only thing standing between it and the
# gate. task-db.py --reason and MCP task_update(reason=...) both set that GUC.
V15_STORY=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 v15 story', p_created_by=>'esther', p_kind=>'story', p_status=>'in_progress');" 2>/dev/null | head -1)
V15_SLICE=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 v15 active slice', p_created_by=>'esther', p_kind=>'slice', p_parent_id=>'${V15_STORY}');" 2>/dev/null | head -1)
V15_ACTIVE=$($PSQL -c "SELECT count(*) FROM tasks.tasks WHERE parent_id='${V15_STORY}' AND status NOT IN ('completed','cancelled');" 2>/dev/null)
# 1. THE DEFECT, via the CLI/MCP path: forge the auto-complete reason on a story that
#    STILL has an active slice and complete it.
V15_RC=0
V15_OUT=$($PSQL -v ON_ERROR_STOP=1 -c "SELECT set_config('tasks.transition_reason','story_auto_complete',false); SELECT tasks.task_upsert(p_id=>'${V15_STORY}', p_status=>'completed');" 2>&1) || V15_RC=$?
V15_ST=$($PSQL -c "SELECT status FROM tasks.tasks WHERE id='${V15_STORY}';" 2>/dev/null)
if [ "$V15_ACTIVE" = "1" ] && [ "$V15_RC" -ne 0 ] && [ "$V15_ST" != "completed" ]; then
  pass "forged auto-complete reason refused while a slice is active (task_upsert, rc=$V15_RC, status=$V15_ST)"
else
  fail "story with an ACTIVE slice was completed via a forged reason (rc=$V15_RC, status=$V15_ST, active=$V15_ACTIVE)" "$V15_OUT"
fi
# 2. The RAW path: the early return is what admits a raw UPDATE, so a caller forging
#    the reason there must be refused too (RLS lets a profile role write its own row).
V15_RAW_RC=0
V15_RAW_OUT=$($PSQL -v ON_ERROR_STOP=1 -c "SELECT set_config('tasks.transition_reason','story_auto_complete',false); UPDATE tasks.tasks SET status='completed', \"column\"='done' WHERE id='${V15_STORY}';" 2>&1) || V15_RAW_RC=$?
V15_RAW_ST=$($PSQL -c "SELECT status FROM tasks.tasks WHERE id='${V15_STORY}';" 2>/dev/null)
if [ "$V15_RAW_RC" -ne 0 ] && [ "$V15_RAW_ST" != "completed" ]; then
  pass "forged auto-complete reason refused on a raw UPDATE (rc=$V15_RAW_RC, status=$V15_RAW_ST)"
else
  fail "raw UPDATE completed a story with an ACTIVE slice (rc=$V15_RAW_RC, status=$V15_RAW_ST)" "$V15_RAW_OUT"
fi
# 3. The genuine auto-complete path must still work: the last slice finishing
#    completes the story with no reason set by anyone.
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${V15_SLICE}', p_status=>'in_progress');" >/dev/null 2>&1
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${V15_SLICE}', p_status=>'completed');" >/dev/null 2>&1
V15_AUTO=$($PSQL -c "SELECT status FROM tasks.tasks WHERE id='${V15_STORY}';" 2>/dev/null)
[ "$V15_AUTO" = "completed" ] && pass "auto-complete still fires when the last slice finishes" \
  || fail "auto-complete broken (story status=$V15_AUTO)"
# 4. A story with NO active slice still completes on the raw path (the auto-complete
#    precondition), so the verified condition is not narrower than the legitimate use.
V15_FREE=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 v15 slice-free story', p_created_by=>'esther', p_kind=>'story', p_status=>'in_progress');" 2>/dev/null | head -1)
V15_FREE_RC=0
$PSQL -v ON_ERROR_STOP=1 -c "SELECT set_config('tasks.transition_reason','story_auto_complete',false); UPDATE tasks.tasks SET status='completed', \"column\"='done' WHERE id='${V15_FREE}';" >/dev/null 2>&1 || V15_FREE_RC=$?
V15_FREE_ST=$($PSQL -c "SELECT status FROM tasks.tasks WHERE id='${V15_FREE}';" 2>/dev/null)
[ "$V15_FREE_RC" -eq 0 ] && [ "$V15_FREE_ST" = "completed" ] \
  && pass "slice-free story still completes (verified precondition satisfied)" \
  || fail "slice-free story completion refused (rc=$V15_FREE_RC, status=$V15_FREE_ST)"
# 5. The gate itself is unchanged for the ordinary path: no reason set, active slice → refused.
V15_G=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 v15 gate story', p_created_by=>'esther', p_kind=>'story', p_status=>'in_progress');" 2>/dev/null | head -1)
$PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 v15 gate slice', p_created_by=>'esther', p_kind=>'slice', p_parent_id=>'${V15_G}');" >/dev/null 2>&1
V15_G_RC=0
$PSQL -v ON_ERROR_STOP=1 -c "SELECT tasks.task_upsert(p_id=>'${V15_G}', p_status=>'completed');" >/dev/null 2>&1 || V15_G_RC=$?
V15_G_ST=$($PSQL -c "SELECT status FROM tasks.tasks WHERE id='${V15_G}';" 2>/dev/null)
[ "$V15_G_RC" -ne 0 ] && [ "$V15_G_ST" != "completed" ] \
  && pass "story with an active slice still refused with no reason set (gate intact)" \
  || fail "gate regressed: story completed with an active slice (rc=$V15_G_RC, status=$V15_G_ST)"

echo ""
echo "═══ AC-L1-26: v016 — task_upsert carries p_plan (21-arg, ONE overload) ═══"
# The ADV-13847-1 regression guard. `CREATE OR REPLACE` cannot change a
# function's argument list: given one more parameter it ADDS a second overload
# and leaves the 20-arg function live, after which every name-based lookup below
# fails with `ERROR: more than one function named "tasks.task_upsert"`.
# Every probe below is `|| true`-guarded: a battery that ABORTS on the first
# failing read reports one failure and hides the rest (measured on this block's
# RED run — the empty id made the next lookup die and the script exited before
# the Summary). A check that cannot run is its own outcome, never an abort.
V16_OVERLOADS=$($PSQL -c "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='tasks' AND p.proname='task_upsert';" 2>/dev/null || true)
[ "$V16_OVERLOADS" = "1" ] \
  && pass "exactly one tasks.task_upsert exists (no overload left behind)" \
  || fail "tasks.task_upsert has $V16_OVERLOADS overloads — the 20-arg one was not dropped"

V16_ARGS=$($PSQL -c "SELECT pg_get_function_arguments('tasks.task_upsert'::regproc);" 2>&1 || true)
V16_N=$(printf '%s' "$V16_ARGS" | awk -F', ' '{print NF}')
[ "$V16_N" = "21" ] && printf '%s' "$V16_ARGS" | grep -q "p_plan text DEFAULT NULL::text$" \
  && pass "resolves by name to 21 parameters, p_plan appended last" \
  || fail "task_upsert resolves to $V16_N parameters / p_plan not last" "$V16_ARGS"

# Round trip through the write path itself.
V16_ID=$($PSQL -c "SELECT tasks.task_upsert(p_content=>'L1 v16 plan row', p_created_by=>'esther', p_plan=>'step one; step two');" 2>/dev/null | head -1 || true)
V16_PLAN=$($PSQL -c "SELECT plan FROM tasks.tasks WHERE id='${V16_ID}';" 2>/dev/null || true)
[ "$V16_PLAN" = "step one; step two" ] \
  && pass "p_plan is written on insert and reads back verbatim" \
  || fail "p_plan did not round-trip (got '${V16_PLAN}')"

# Metadata-only write on an in_progress row — the §3 trap. p_status must carry
# the row's CURRENT status (what task-db.py update does when --status is
# omitted); the write must succeed AND leave status/column coherent. Passing
# NULL instead derives column='todo' and dies with 23514, which is asserted
# separately below so this guard can never pass vacuously.
$PSQL -c "SELECT tasks.task_upsert(p_id=>'${V16_ID}', p_status=>'in_progress');" >/dev/null 2>&1 || true
V16_META_RC=0
$PSQL -v ON_ERROR_STOP=1 -c "SELECT tasks.task_upsert(p_id=>'${V16_ID}', p_status=>'in_progress', p_plan=>'revised plan');" >/dev/null 2>&1 || V16_META_RC=$?
V16_ST=$($PSQL -c "SELECT status || '/' || COALESCE(\"column\",'NULL') FROM tasks.tasks WHERE id='${V16_ID}';" 2>/dev/null || true)
V16_PLAN2=$($PSQL -c "SELECT plan FROM tasks.tasks WHERE id='${V16_ID}';" 2>/dev/null || true)
[ "$V16_META_RC" -eq 0 ] && [ "$V16_ST" = "in_progress/in_progress" ] && [ "$V16_PLAN2" = "revised plan" ] \
  && pass "metadata-only write keeps status/column coherent on an in_progress row (rc=0, ${V16_ST})" \
  || fail "metadata-only write broke coherence (rc=$V16_META_RC, ${V16_ST}, plan='${V16_PLAN2}')"

# ...and the trap it avoids is REAL (a check that cannot fail proves nothing).
V16_TRAP_RC=0
$PSQL -v ON_ERROR_STOP=1 -c "SELECT tasks.task_upsert(p_id=>'${V16_ID}', p_plan=>'from a null status');" >/dev/null 2>&1 || V16_TRAP_RC=$?
V16_TRAP_ST=$($PSQL -c "SELECT status FROM tasks.tasks WHERE id='${V16_ID}';" 2>/dev/null || true)
[ "$V16_TRAP_RC" -ne 0 ] && [ "$V16_TRAP_ST" = "in_progress" ] \
  && pass "p_status=NULL on a non-pending row is still refused (23514) — carrying the current status is load-bearing" \
  || fail "the §3 trap did not fire (rc=$V16_TRAP_RC, status=$V16_TRAP_ST)"

# Grant read-back on the NEW 21-arg signature (a DROP discards the ACL).
V16_GRANT=$($PSQL -c "SELECT has_function_privilege('mycortex_reader_esther', (SELECT p.oid FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='tasks' AND p.proname='task_upsert'), 'EXECUTE');" 2>/dev/null || true)
[ "$V16_GRANT" = "t" ] \
  && pass "mycortex_reader_esther still holds EXECUTE on the 21-arg task_upsert" \
  || fail "the reader role lost EXECUTE after the DROP+CREATE (got '$V16_GRANT')"

# The CRUD role can actually CALL it (the grant assertion above is not enough:
# a privilege that is never exercised is not proven usable).
V16_CALL=$($PSQL_READER -c "SELECT tasks.task_upsert(p_content=>'L1 v16 reader call', p_created_by=>'esther');" 2>/dev/null | head -1)
[ -n "$V16_CALL" ] \
  && pass "the reader role can call the 21-arg task_upsert" \
  || fail "the reader role cannot call task_upsert after v016"

echo ""
echo "═══ Summary ═══"
echo "  ${P} passed, ${F} failed"
[ "$F" -eq 0 ] || echo "  ❌ SOME TESTS FAILED — investigate before shipping"
exit $F
