#!/usr/bin/env bash
# Re-runnable proof that the Jev decision model is SWAPPABLE, and that swapping it
# is safe. Everything here talks to a LOCAL stub that speaks the typed
# /v1/systemone wire format — the same contract a self-hosted von or a steadfaste
# model would speak — so the result is reproducible with no provider key and no
# network.
#
# Proves, in order:
#   1. the override is accepted and named by `jev doctor`
#   2. a real decision (`jev route`) is ANSWERED BY THE STUB
#   3. a raw typed call validates noul + choice + score from that endpoint
#   4. the real provider credential does NOT travel to the override
#   5. a dead endpoint FAILS OPEN (current model kept, exit 0)
#   6. plaintext to a non-loopback host is REFUSED
#
# Usage: bash run.sh            (needs the `jev` CLI installed; see the install step
#                               in docs/design/jev-decision-layer.md)
# Never writes live state: the stub and the report live in a temp dir.
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORK="$(mktemp -d)"
PORT=8799
STUB_LOG="$WORK/stub.log"
REPORT="$WORK/report.json"
FAILURES=0

command -v jev >/dev/null 2>&1 || { echo "SKIP: no \`jev\` CLI on this host"; exit 3; }
command -v python3 >/dev/null 2>&1 || { echo "SKIP: no python3"; exit 3; }

fail() { echo "  FAIL: $1"; FAILURES=$((FAILURES + 1)); }
pass() { echo "  ok: $1"; }

EXPECT_PROXY_KEY=stub-proxy-key STUB_REPORT="$REPORT" \
  python3 "$HERE/stub_systemone.py" "$PORT" >"$STUB_LOG" 2>&1 &
STUB_PID=$!
trap 'kill "$STUB_PID" 2>/dev/null; rm -rf "$WORK"' EXIT
sleep 2

BASE="http://127.0.0.1:$PORT"
PROMPT="refactor the governance enforcer lock gate and keep every refusal path identical"
CURRENT="openrouter:deepseek/deepseek-v4.1-flash"

echo "== 1. doctor names the override =="
DOCTOR="$(TYPESAFE_BASE_URL="$BASE" JEV_PROXY_API_KEY=stub-proxy-key jev doctor 2>&1)"
case "$DOCTOR" in
  *'"valid": true'*) pass "override accepted" ;;
  *) fail "doctor did not accept the override: $(echo "$DOCTOR" | head -5)" ;;
esac

echo "== 2. a real decision is answered by the stub =="
ROUTE="$(TYPESAFE_BASE_URL="$BASE" JEV_PROXY_API_KEY=stub-proxy-key \
         jev route --prompt "$PROMPT" --current "$CURRENT" 2>&1)"
case "$ROUTE" in
  *'"routed": true'*) pass "routed through the override" ;;
  *) fail "no routing decision from the override: $(echo "$ROUTE" | head -5)" ;;
esac

echo "== 3. typed noul + choice + score validate from that endpoint =="
ASK="$(TYPESAFE_BASE_URL="$BASE" JEV_PROXY_API_KEY=stub-proxy-key jev ask <"$HERE/questions.json" 2>&1)"
case "$ASK" in
  *'"type": "noul"'*) pass "noul validated" ;;
  *) fail "noul answer missing: $(echo "$ASK" | head -5)" ;;
esac
case "$ASK" in
  *'"type": "choice"'*) pass "choice validated" ;;
  *) fail "choice answer missing" ;;
esac
case "$ASK" in
  *'"type": "score"'*) pass "score validated" ;;
  *) fail "score answer missing" ;;
esac

echo "== 4. the real provider credential does not travel =="
if [ -s "$REPORT" ]; then
  python3 - "$REPORT" <<'PY'
import json, sys
rows = json.load(open(sys.argv[1]))
if not rows:
    print("  FAIL: the stub was never called"); raise SystemExit(1)
# Every request the stub saw, not just the first: `jev doctor` probes the endpoint
# too, so the first row is its health question, not the routing call.
for row in rows:
    assert row["path"] == "/v1/systemone", row["path"]
    print("  ok: POST /v1/systemone · model", row["model"],
          "· questions", row["questions"], "· types", row["question_types"])
if not all(row["bearer_is_expected_proxy_key"] for row in rows):
    print("  FAIL: the proxy key did not arrive on every call"); raise SystemExit(1)
print(f"  ok: the proxy key arrived on all {len(rows)} call(s)")
if any(row["bearer_equals_env_typesafe_key"] for row in rows):
    print("  FAIL: the REAL provider key was forwarded to the override"); raise SystemExit(1)
print("  ok: the real provider key was NOT forwarded on any call")
PY
  [ $? -eq 0 ] || FAILURES=$((FAILURES + 1))
else
  fail "no stub report — the endpoint was never reached"
fi

echo "== 5. a dead endpoint fails open =="
DEAD="$(TYPESAFE_BASE_URL=http://127.0.0.1:8798 JEV_PROXY_API_KEY=stub-proxy-key \
        jev route --prompt "fix the failing test" --current "$CURRENT" 2>&1)"
DEAD_RC=$?
case "$DEAD" in
  *'"routed": false'*) pass "kept the current model" ;;
  *) fail "a dead endpoint did not fail open: $(echo "$DEAD" | head -5)" ;;
esac
[ "$DEAD_RC" -eq 0 ] && pass "exit 0 (nothing blocked)" || fail "exit $DEAD_RC"

echo "== 6. plaintext to a non-loopback host is refused =="
BAD="$(TYPESAFE_BASE_URL=http://example.com JEV_PROXY_API_KEY=stub-proxy-key jev doctor 2>&1)"
case "$BAD" in
  *invalid_endpoint*) pass "refused with invalid_endpoint" ;;
  *) fail "plaintext to a public host was not refused" ;;
esac

echo
if [ "$FAILURES" -eq 0 ]; then
  echo "VERDICT: the decision model is swappable and the swap is safe (6/6)"
  exit 0
fi
echo "VERDICT: $FAILURES check(s) failed"
exit 1
