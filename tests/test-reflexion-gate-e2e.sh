#!/usr/bin/env bash
# test-reflexion-gate-e2e.sh — the WHOLE reflexion path, live, in one runnable test:
#
#     enforcer writer  ->  real store (mycortex_mem.tool_events)  ->  real verifier
#
# tests/test-reflexion-gate-repoint.sh proves the gate BLOCK's contract with a stub
# verifier (hermetic, no store). This proves the other half — that the writer and
# the verifier actually agree through the real database — so the claim is
# reproducible from the repo rather than resting on a terminal transcript in a note.
#
# It uses a UNIQUE probe session id and deletes its own rows, so it can run beside a
# live session. If the store is unreachable it SKIPS (exit 0) with a clear notice:
# failing here would report a broken gate when the truth is "no database on this box".
#
# Run: bash tests/test-reflexion-gate-e2e.sh
set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECKER="$REPO_DIR/ops/scripts/hc-reflexion-check.py"
ENFORCER="$REPO_DIR/plugins/governance-enforcer/__init__.py"
STORE="$REPO_DIR/ops/services/mycortex-mem/store.py"
SID="probe-e2e-$$"

P=0; F=0
pass() { P=$((P + 1)); echo "  ✅ $1"; }
fail() { F=$((F + 1)); echo "  ❌ $1${2:+ — $2}"; }

cleanup() {
  # Report a failed cleanup rather than hiding it: silenced cleanup means probe rows
  # persist and nobody knows. The rows are session-scoped to probe-e2e-* so they are
  # harmless, but "harmless" is a claim the next reader should be able to check.
  local rc=0
  python3 - "$STORE" <<'PY' >/dev/null || rc=$?
import importlib.util, sys
spec = importlib.util.spec_from_file_location("s", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
try:
    m.Store().pg.run_sql(
        "DELETE FROM mycortex_mem.sessions WHERE session_key LIKE 'probe-e2e-%';",
        role="mycortex_mem_admin")
except Exception as exc:
    print(f"cleanup failed: {exc}", file=sys.stderr)
    sys.exit(1)
PY
  if [[ "$rc" -ne 0 ]]; then
    echo "  ⚠️  cleanup could not remove probe-e2e-* rows (rc=$rc) — they persist until" >&2
    echo "      the store is reachable again; they are session-scoped and do not affect" >&2
    echo "      a real session's evidence." >&2
  fi
}
trap cleanup EXIT

echo ""
echo "═══ Setup: is the store reachable? ═══"
if ! python3 - "$STORE" <<'PY'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("s", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
sys.exit(0 if m.Store().available() else 1)
PY
then
  echo "  ⏭  SKIP — HC store unreachable (mycortex-postgres not running on this host)."
  echo "     This test verifies the live writer→store→verifier path; with no store"
  echo "     there is nothing honest to assert. Not a failure."
  exit 0
fi
echo "  store reachable"

echo ""
echo "═══ AC1: the ENFORCER WRITER records a real row (no manual insert) ═══"
python3 - "$ENFORCER" "$SID" <<'PY'
import importlib.util, sys, time
spec = importlib.util.spec_from_file_location("enf", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m._record_tool_event(sys.argv[2], "reflexion-check")   # the writer path, as on skill_view
time.sleep(6)                                          # it records off-thread
PY
ROW=$(python3 - "$STORE" "$SID" <<'PY'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("s", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
pg = m.Store().pg
rows = pg.query(
    "SELECT e.harness, e.tool_name, e.role, e.content::text "
    "FROM mycortex_mem.tool_events e JOIN mycortex_mem.sessions s ON s.id = e.session_id "
    f"WHERE s.session_key = '{sys.argv[2]}';")
print("|".join(rows[0]) if rows else "")
PY
)
if [[ "$ROW" == "hermes|skill_view|tool|{\"name\": \"reflexion-check\"}" ]]; then
  pass "writer produced the expected row: $ROW"
else
  fail "writer did not produce the expected row" "got: ${ROW:-<none>}"
fi

echo ""
echo "═══ AC2: the verifier reads that row (store, not a journal) ═══"
python3 "$CHECKER" --session "$SID" --skill reflexion-check >/dev/null 2>&1
[[ "$?" == "0" ]] && pass "verifier returns LOADED for the recorded session" \
                  || fail "verifier did not see the recorded row"

echo ""
echo "═══ AC3: per-skill discrimination — loaded True, never-loaded False ═══"
python3 "$CHECKER" --session "$SID" --skill shell-scripting >/dev/null 2>&1
[[ "$?" == "1" ]] && pass "a skill this session never loaded is NOT-LOADED" \
                  || fail "verifier reported a skill that was never loaded"

echo ""
echo "═══ AC4: a session with no rows at all is refused ═══"
python3 "$CHECKER" --session "probe-e2e-absent-$$" >/dev/null 2>&1
[[ "$?" == "1" ]] && pass "absent session is refused" || fail "absent session was not refused"

echo ""
echo "═══ Summary ═══"
echo "  ${P} passed, ${F} failed"
if [ "$F" -gt 0 ]; then
  echo "  ❌ SOME TESTS FAILED"
  exit 1
fi
echo "  ✅ ALL TESTS PASSED"
