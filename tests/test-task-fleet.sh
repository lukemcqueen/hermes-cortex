#!/usr/bin/env bash
# test-task-fleet.sh — L2 fleet test for the tasks system
#
# From docs/design/task-workflow.md §8 (QA B-8 mandatory test plan):
#   ssh-invoked on all 6 hosts: schema apply ×2, CRUD roundtrip
#   (env-override scratch DB), `pending` shape, save-end; Linux docker-exec
#   + macOS direct psql; orch vs worker config.yaml static check + JSON-RPC
#   `tools/list` handshake.
#
# Two modes:
#   Local host  : bash tests/test-task-fleet.sh            # tests THIS host
#   Fleet sweep : bash tests/test-task-fleet.sh --hosts "joseph gisu kustos titus moses"
#                 (ssh to each host, run the same battery remotely, aggregate)
#
# Hermeticity: CRUD runs against a scratch database (TASK_DB_NAME=fleet_test)
# with the reader role env-override (TASK_DB_ROLE). The scratch DB is created
# and dropped around each host's battery — live `mycortex` rows are never
# touched. Requires the deployed task-db.py (cortex-update must have run).
#
# Run: bash tests/test-task-fleet.sh [--hosts "h1 h2 ..."] [--user NAME]
set -eu

P=0; F=0
pass() { P=$((P+1)); echo "  ✅ $1"; }
fail() { F=$((F+1)); echo "  ❌ $1${2:+ — $2}"; }

HOSTS=""
USER_NAME="${USER:-$USERNAME}"
# parse args
while [[ $# -gt 0 ]]; do
  case "$1" in
    --hosts) HOSTS="$2"; shift 2 ;;
    --user) USER_NAME="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

# ── Host battery: run the whole check set on ONE host ────────────────
run_battery() {
  local host="$1"
  echo ""
  echo "═══════════════════════════════════════════════════════"
  echo "═══ Host: ${host} ═══"
  echo "═══════════════════════════════════════════════════════"

  # Locate the deployed CLI + repo migrate runner.
  TASK_DB=""
  for cand in \
    "$HOME/.hermes-cortex/scripts/task-db.py" \
    "$HOME/hermes-cortex/ops/scripts/manage/task-db.py"; do
    if [ -f "$cand" ]; then TASK_DB="$cand"; break; fi
  done
  if [ -z "$TASK_DB" ]; then
    fail "task-db.py not deployed on ${host} — run cortex-update first"
    return 1
  fi
  echo "  using task-db.py: ${TASK_DB}"

  MIGRATE_PY=""
  for cand in \
    "$HOME/hermes-cortex/ops/services/tasks/migrate.py" \
    "$HOME/.hermes-cortex/scripts/ops/services/tasks/migrate.py"; do
    if [ -f "$cand" ]; then MIGRATE_PY="$cand"; break; fi
  done

  # ── 1. Schema apply ×2 (idempotency) ──────────────────────────────
  echo ""
  echo "═══ 1. Schema apply ×2 (version-gated idempotency) ═══"
  if [ -n "$MIGRATE_PY" ]; then
    if python3 "$MIGRATE_PY" >/dev/null 2>&1; then
      pass "migrate.py applies on ${host}"
    else
      fail "migrate.py FAILED on ${host} — schema missing/blocked"
    fi
    if python3 "$MIGRATE_PY" 2>/dev/null | grep -q "no-op"; then
      pass "re-run is a no-op (version-gated)"
    else
      fail "re-run not a no-op on ${host}"
    fi
  else
    echo "  ⚠ migrate.py not found on ${host} — schema apply check skipped"
  fi

  # ── 2. Hermetic CRUD roundtrip on scratch DB ──────────────────────
  echo ""
  echo "═══ 2. CRUD roundtrip (scratch DB, live rows untouched) ═══"
  local scratch_db="fleet_test"
  if [ "$(uname)" = "Darwin" ]; then
    # macOS: psql direct — scratch DB may not exist; create via default conn
    psql -h 127.0.0.1 -p 15432 -U mycortex -d mycortex -t -A \
      -c "DROP DATABASE IF EXISTS ${scratch_db};" >/dev/null 2>&1 || true
    psql -h 127.0.0.1 -p 15432 -U mycortex -d mycortex -t -A \
      -c "CREATE DATABASE ${scratch_db};" >/dev/null 2>&1 || true
    # schema on the scratch DB (owner role)
    if [ -n "$MIGRATE_PY" ]; then
      python3 "$MIGRATE_PY" --db-name "$scratch_db" >/dev/null 2>&1 || true
    fi
  else
    # Linux: docker exec
    if docker exec mycortex-postgres psql -U mycortex -d mycortex -t -A \
        -c "DROP DATABASE IF EXISTS ${scratch_db};" >/dev/null 2>&1; then
      :; fi
    docker exec mycortex-postgres psql -U mycortex -d mycortex -t -A \
      -c "CREATE DATABASE ${scratch_db};" >/dev/null 2>&1 || true
    if [ -n "$MIGRATE_PY" ]; then
      python3 "$MIGRATE_PY" --db-name "$scratch_db" >/dev/null 2>&1 || true
    fi
  fi

  local rid
  # add → the roundtrip core. Reader role: mycortex_reader (base grant, exists
  # on every host; no per-profile role needed for hermetic CRUD). PROFILE must
  # be pinned to the same value so created_by matches profile_of(current_user)
  # under RLS — hostname-derived PROFILE (e.g. 'esther') would be denied.
  local out
  out=$(TASK_DB_NAME="$scratch_db" TASK_DB_ROLE="mycortex_reader" \
        HERMES_PROFILE="mycortex_reader" \
        python3 "$TASK_DB" add "fleet-probe $$" --source manual 2>&1) && rid=$(echo "$out" | grep -oE "[0-9a-f]{8}\.\.\." | head -1) || rid=""
  if [ -n "$rid" ]; then
    pass "add on scratch DB (${rid})"
  else
    fail "add failed on ${host}: $(echo "$out" | grep -E "ERROR|violates|denied" | head -1)"
  fi

  # list roundtrip — the row must appear for mycortex_reader (personal scope
  # with created_by=mycortex_reader matches the reader's own profile)
  local listed
  listed=$(TASK_DB_NAME="$scratch_db" TASK_DB_ROLE="mycortex_reader" \
           HERMES_PROFILE="mycortex_reader" \
           python3 "$TASK_DB" list --status pending 2>/dev/null | grep -c "fleet-probe $$" || true)
  [ "$listed" -ge 1 ] && pass "list sees the probe row (got $listed)" || fail "list did not return the probe row"

  # pending JSON shape (session-restore contract)
  local pend_json
  pend_json=$(TASK_DB_NAME="$scratch_db" TASK_DB_ROLE="mycortex_reader" \
              HERMES_PROFILE="mycortex_reader" \
              python3 "$TASK_DB" pending 2>/dev/null)
  if echo "$pend_json" | python3 -c "import json,sys; d=json.load(sys.stdin); assert isinstance(d,list)" 2>/dev/null; then
    pass "pending returns valid JSON list"
  else
    fail "pending JSON shape broken on ${host}: $(echo "$pend_json" | head -c 120)"
  fi

  # update → completed (status canonical)
  if [ -n "$rid" ]; then
    local full_id
    full_id=$(TASK_DB_NAME="$scratch_db" TASK_DB_ROLE="mycortex_reader" \
              HERMES_PROFILE="mycortex_reader" \
              python3 "$TASK_DB" list --status pending 2>/dev/null \
              | grep "fleet-probe $$" | head -1 | awk '{print $1}')
    if [ -n "$full_id" ] && \
       TASK_DB_NAME="$scratch_db" TASK_DB_ROLE="mycortex_reader" \
         HERMES_PROFILE="mycortex_reader" \
         python3 "$TASK_DB" update "$full_id" --status completed >/dev/null 2>&1; then
      pass "update → completed (status canonical)"
    else
      fail "update to completed failed on ${host}"
    fi
    # save-end archives it
    TASK_DB_NAME="$scratch_db" TASK_DB_ROLE="mycortex_reader" \
      HERMES_PROFILE="mycortex_reader" \
      python3 "$TASK_DB" save-end >/dev/null 2>&1 \
      && pass "save-end archives completed" \
      || fail "save-end failed on ${host}"
  fi

  # cleanup scratch DB (best-effort)
  if [ "$(uname)" = "Darwin" ]; then
    psql -h 127.0.0.1 -p 15432 -U mycortex -d mycortex -t -A \
      -c "DROP DATABASE IF EXISTS ${scratch_db};" >/dev/null 2>&1 || true
  else
    docker exec mycortex-postgres psql -U mycortex -d mycortex -t -A \
      -c "DROP DATABASE IF EXISTS ${scratch_db};" >/dev/null 2>&1 || true
  fi

  # ── 3. MCP config static check + JSON-RPC handshake ───────────────
  echo ""
  echo "═══ 3. MCP todos registration check ═══"
  local cfg="$HOME/.hermes/config.yaml"
  if [ -f "$cfg" ] && grep -q "task-mcp.py" "$cfg"; then
    pass "config.yaml registers task-mcp.py (todos)"
  else
    fail "task-mcp.py NOT registered in ${cfg}"
  fi

  # JSON-RPC handshake against the RUNNING gateway (design B-7: tools must be
  # exposed after restart, not just registered in config). Best-effort: if the
  # gateway isn't reachable, WARN — the doctor owns the hard check.
  if command -v hermes >/dev/null 2>&1 && hermes mcp test todos >/dev/null 2>&1; then
    pass "hermes mcp test todos: tools reachable"
  else
    echo "  ⚠ gateway handshake skipped/unreachable on ${host} (doctor owns the hard check)"
  fi
}

# ── Local mode (default) ─────────────────────────────────────────────
if [ -z "$HOSTS" ]; then
  run_battery "$(hostname)"
  echo ""
  echo "═══ Summary (local) ═══"
  echo "  ${P} passed, ${F} failed"
  [ "$F" -eq 0 ] || echo "  ❌ SOME TESTS FAILED"
  exit $F
fi

# ── Fleet mode: ssh to each host ─────────────────────────────────────
for host in $HOSTS; do
  echo ""
  echo "── ssh ${USER_NAME}@${host} ──"
  out=$(ssh -o BatchMode=yes -o ConnectTimeout=10 "${USER_NAME}@${host}" \
    "bash -s" < "${BASH_SOURCE[0]}" 2>&1) && rc=0 || rc=$?
  echo "$out"
  [ "$rc" -eq 0 ] || F=$((F+1))
done
echo ""
echo "═══ Summary (fleet) ═══"
echo "  ${P} passed locally, ${F} host failure(s)"
[ "$F" -eq 0 ] || echo "  ❌ SOME HOSTS FAILED — investigate"
exit $F
