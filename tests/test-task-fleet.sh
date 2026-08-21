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

  # ── Regression 2026-08-21: multiline content must survive list output ──
  # (content with \\n used to split the ||-delimited psql row → parse_row
  # dropped it; the row "vanished". SELECT_COLS now flattens display.)
  local multi_id
  multi_id=$(TASK_DB_NAME="$scratch_db" TASK_DB_ROLE="mycortex_reader" \
             HERMES_PROFILE="mycortex_reader" \
             python3 "$TASK_DB" add "multiline regression $$ line1
line2 still content" --source manual 2>&1 | grep -oE "[0-9a-f]{8}\.\.\." | head -1 || true)
  local multi_listed
  multi_listed=$(TASK_DB_NAME="$scratch_db" TASK_DB_ROLE="mycortex_reader" \
                 HERMES_PROFILE="mycortex_reader" \
                 python3 "$TASK_DB" list --status pending 2>/dev/null | grep -c "multiline regression $$" || true)
  if [ -n "$multi_id" ] && [ "$multi_listed" -ge 1 ]; then
    pass "multiline content round-trips through list (id=${multi_id}, listed=${multi_listed})"
  else
    fail "multiline content dropped/garbled in list (id=${multi_id:-none}, listed=${multi_listed})"
  fi

  # ── Regression 2026-08-21: fleet + pathy content degrades to personal ──
  # (B-5 scrub gate: fleet content with abs-path/email/IP smell used to die
  # with a raw RLS error; cmd_add now degrades to scope=personal + warning.)
  local deg_out deg_row
  deg_out=$(TASK_DB_NAME="$scratch_db" TASK_DB_ROLE="mycortex_reader" \
            HERMES_PROFILE="mycortex_reader" \
            python3 "$TASK_DB" add "degrade probe $$ ~/.hermes/skills/devops/x" \
              --scope fleet --source manual 2>&1 || true)
  if echo "$deg_out" | grep -q "B-5 scrub gate"; then
    pass "fleet pathy content degraded with B-5 warning"
  else
    fail "fleet pathy content did not degrade: $(echo "$deg_out" | head -c 160)"
  fi
  deg_row=$(TASK_DB_NAME="$scratch_db" TASK_DB_ROLE="mycortex_reader" \
            HERMES_PROFILE="mycortex_reader" \
            python3 "$TASK_DB" list --status pending 2>/dev/null | grep "degrade probe $$" || true)
  if echo "$deg_row" | grep -q "personal"; then
    pass "degraded task stored with scope=personal"
  else
    fail "degraded task scope wrong: $(echo "$deg_row" | head -c 120)"
  fi

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

  # update → in_progress → completed (status canonical; v005 matrix
  # requires starting before completing)
  if [ -n "$rid" ]; then
    local full_id
    full_id=$(TASK_DB_NAME="$scratch_db" TASK_DB_ROLE="mycortex_reader" \
              HERMES_PROFILE="mycortex_reader" \
              python3 "$TASK_DB" list --status pending 2>/dev/null \
              | grep "fleet-probe $$" | head -1 | awk '{print $1}')
    if [ -n "$full_id" ] && \
       TASK_DB_NAME="$scratch_db" TASK_DB_ROLE="mycortex_reader" \
         HERMES_PROFILE="mycortex_reader" \
         python3 "$TASK_DB" update "$full_id" --status in_progress >/dev/null 2>&1; then
      pass "update → in_progress (v005 matrix)"
    else
      fail "update to in_progress failed on ${host}"
    fi
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

  # ── 4. v2 battery (TL-v2 S3/S4 — schema v5+ required) ─────────────
  # Hermetic: scratch DB + TASKS_NOTIFY_MUTE + dummy notify env file →
  # zero real Telegram (design L2 row). Skips gracefully on old schema.
  echo ""
  echo "═══ 4. v2 lifecycle battery (scratch DB, zero Telegram) ═══"
  local notify_dir notify_env
  notify_dir="$(mktemp -d)"
  notify_env="${notify_dir}/notify.env"
  printf 'TELEGRAM_BOT_TOKEN=dummy\nTELEGRAM_HOME_CHANNEL=0\n' > "$notify_env"
  chmod 600 "$notify_env"
  # Section 2 dropped its scratch DB — recreate a fresh one for the v2
  # battery (same hermetic guard: never the live mycortex DB).
  local v2_db="fleet_v2_test"
  if [ "$(uname)" = "Darwin" ]; then
    psql -h 127.0.0.1 -p 15432 -U mycortex -d mycortex -t -A \
      -c "DROP DATABASE IF EXISTS ${v2_db};" >/dev/null 2>&1 || true
    psql -h 127.0.0.1 -p 15432 -U mycortex -d mycortex -t -A \
      -c "CREATE DATABASE ${v2_db};" >/dev/null 2>&1 || true
  else
    docker exec mycortex-postgres psql -U mycortex -d mycortex -t -A \
      -c "DROP DATABASE IF EXISTS ${v2_db};" >/dev/null 2>&1 || true
    docker exec mycortex-postgres psql -U mycortex -d mycortex -t -A \
      -c "CREATE DATABASE ${v2_db};" >/dev/null 2>&1 || true
  fi
  if [ -n "$MIGRATE_PY" ]; then
    python3 "$MIGRATE_PY" --db-name "$v2_db" >/dev/null 2>&1 || true
  fi
  local V2ENV=(TASK_DB_NAME="$v2_db" TASK_DB_ROLE="mycortex_reader"
               HERMES_PROFILE="mycortex_reader"
               TASKS_NOTIFY_MUTE="pending,in_progress,completed,cancelled,paused"
               TELEGRAM_NOTIFY_ENV_FILE="$notify_env"
               TELEGRAM_NOTIFY_STATE_DIR="$notify_dir/state")

  local v2ver
  v2ver=$(env "${V2ENV[@]}" python3 -c "
import importlib.util
spec = importlib.util.spec_from_file_location('tdb', '$TASK_DB')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print(m.schema_version())
" 2>/dev/null || echo "0")
  if [ -z "$v2ver" ] || [ "$v2ver" -lt 5 ]; then
    echo "  ⚠ tasks schema v<5 on ${host} (found v${v2ver:-?}) — v2 battery skipped"
    rm -rf "$notify_dir"
    return 0
  fi
  pass "schema v${v2ver} ≥ 5 (v2 available)"

  # 4a. by-correlation lifecycle: add (inbox) → in_progress → completed
  local corr="l2-${host}-$$"
  local cid
  cid=$(env "${V2ENV[@]}" python3 "$TASK_DB" add "L2 corr probe $$" \
        --source inbox --correlation-id "$corr" --no-notify 2>/dev/null \
        | grep -oE "[0-9a-f]{8}\.\.\." | head -1 || true)
  [ -n "$cid" ] && pass "add with --correlation-id (${cid})" \
    || fail "add --correlation-id failed on ${host}"

  # v007 preservation: status-only update must keep source=inbox
  env "${V2ENV[@]}" python3 "$TASK_DB" update --by-correlation "$corr" \
    --status in_progress --no-notify >/dev/null 2>&1
  # verify source via pending JSON (inbox rows carry 'untrusted': true)
  local src_json
  src_json=$(env "${V2ENV[@]}" python3 "$TASK_DB" pending 2>/dev/null \
             | python3 -c "
import json, sys
try:
    items = json.load(sys.stdin)
except Exception:
    print(0); raise SystemExit
print(sum(1 for it in items
          if it.get('content', '').startswith('L2 corr probe')
          and it.get('untrusted') is True))
")
  [ "$src_json" -ge 1 ] && pass "inbox row marked untrusted in pending JSON (v007 preservation)" \
    || fail "source lost on status update (v007 regression)"

  if env "${V2ENV[@]}" python3 "$TASK_DB" update --by-correlation "$corr" \
       --status completed --no-notify >/dev/null 2>&1; then
    pass "by-correlation → completed (S4 Result-receipt path)"
  else
    fail "by-correlation → completed failed on ${host}"
  fi

  # duplicate correlation rejected (partial unique index)
  if env "${V2ENV[@]}" python3 "$TASK_DB" add "L2 dup $$" --source inbox \
       --correlation-id "$corr" --no-notify >/dev/null 2>&1; then
    fail "duplicate correlation accepted (idempotency broken)"
  else
    pass "duplicate correlation rejected (partial unique)"
  fi

  # 4b. story/slice hierarchy + switch
  local story_id slice_id
  story_id=$(env "${V2ENV[@]}" python3 "$TASK_DB" add "L2 story $$" \
             --kind story --no-notify 2>/dev/null \
             | grep -oE "[0-9a-f]{8}\.\.\." | head -1 || true)
  [ -n "$story_id" ] && pass "story created (${story_id})" \
    || fail "story create failed on ${host}"
  slice_id=$(env "${V2ENV[@]}" python3 "$TASK_DB" add "L2 slice $$" \
             --kind slice --parent "$(env "${V2ENV[@]}" python3 "$TASK_DB" \
             list --status pending 2>/dev/null | grep "L2 story $$" \
             | head -1 | awk '{print $1}')" --no-notify 2>/dev/null \
             | grep -oE "[0-9a-f]{8}\.\.\." | head -1 || true)
  [ -n "$slice_id" ] && pass "slice under story created (${slice_id})" \
    || fail "slice create failed on ${host}"

  # 4c. stale-sweep query: seed an OLD in_progress inbox row, verify the
  # handler's sweep predicate finds it (design L2: stale-sweep L1-seeded)
  local stale_corr="l2-stale-${host}-$$"
  env "${V2ENV[@]}" python3 "$TASK_DB" add "L2 stale probe $$" \
    --source inbox --correlation-id "$stale_corr" --no-notify >/dev/null 2>&1
  env "${V2ENV[@]}" python3 "$TASK_DB" update --by-correlation "$stale_corr" \
    --status in_progress --no-notify >/dev/null 2>&1
  # age the row past the 1h threshold (update status_changed_at directly;
  # task_events no-op gate makes this safe)
  docker exec mycortex-postgres psql -U mycortex -d "$v2_db" -t -A \
    -c "UPDATE tasks.tasks SET status_changed_at = now() - interval '2 hours'
        WHERE correlation_id = '${stale_corr}';" >/dev/null 2>&1 || true
  local swept
  swept=$(env "${V2ENV[@]}" python3 -c "
import importlib.util, sys
spec = importlib.util.spec_from_file_location('tdb', '$TASK_DB')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
sql = (\"SELECT correlation_id FROM tasks.tasks WHERE source='inbox' AND \"
       \"status='in_progress' AND status_changed_at < now() - \"
       \"make_interval(hours => 1) LIMIT 50;\")
raw = m.psql(m.build_query(sql, []))
print(len([l for l in raw.splitlines() if l.strip()]))
" 2>/dev/null || echo "0")
  [ "$swept" -ge 1 ] && pass "stale-sweep predicate finds aged row (n=$swept)" \
    || fail "stale-sweep predicate missed the aged row (n=$swept)"
  env "${V2ENV[@]}" python3 "$TASK_DB" update --by-correlation "$stale_corr" \
    --status cancelled --no-notify >/dev/null 2>&1

  # 4d. no_agent identity resolution: no HERMES_PROFILE/AGENT_NAME env →
  # task-db resolves from ~/.hermes-cortex/agent.env (Luke 2026-08-10), and
  # the DEFAULT role (mycortex_reader_<profile>) must satisfy RLS WITH
  # CHECK (created_by == profile_of(current_user)) — no role override.
  local na_out na_rid
  na_out=$(TASK_DB_NAME="$v2_db" \
           TASKS_NOTIFY_MUTE="pending" TELEGRAM_NOTIFY_ENV_FILE="$notify_env" \
           TELEGRAM_NOTIFY_STATE_DIR="$notify_dir/state" \
           env -u HERMES_PROFILE -u AGENT_NAME \
           python3 "$TASK_DB" add "L2 noagent probe $$" --no-notify 2>&1) \
           && na_rid=$(echo "$na_out" | grep -oE "[0-9a-f]{8}\.\.\." | head -1) || na_rid=""
  if [ -n "$na_rid" ]; then
    pass "no_agent identity resolves from .env (${na_rid})"
  else
    fail "no_agent identity resolution failed: $(echo "$na_out" | grep -E "ERROR" | head -1)"
  fi

  # v2 scratch DB cleanup (best-effort — the live mycortex DB is untouched)
  if [ "$(uname)" = "Darwin" ]; then
    psql -h 127.0.0.1 -p 15432 -U mycortex -d mycortex -t -A \
      -c "DROP DATABASE IF EXISTS ${v2_db};" >/dev/null 2>&1 || true
  else
    docker exec mycortex-postgres psql -U mycortex -d mycortex -t -A \
      -c "DROP DATABASE IF EXISTS ${v2_db};" >/dev/null 2>&1 || true
  fi
  rm -rf "$notify_dir"
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
