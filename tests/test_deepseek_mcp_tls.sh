#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  test_deepseek_mcp_tls.sh — hermetic regression test for
#  ops/scripts/manage/check-deepseek-mcp-tls.sh
#
#  Proves, against a scratch HOME (never the real ~/.pi/agent/mcp.json):
#    1. Healthy   — a deepseek entry whose command imports mcp + certifi and
#                   resolves a real cacert.pem → rc=0, prints "deepseek TLS ok".
#    2. MISSING   — no ~/.pi/agent/mcp.json at all → rc=1, says MISSING.
#    3. NO ENTRY  — mcp.json exists but has no `deepseek` server → rc=1.
#    4. BAD INTERPRETER — deepseek.command names a non-executable path → rc=1.
#
#  The healthy branch needs an interpreter that imports BOTH mcp and certifi;
#  that is the capability the guard exists to assert, so it cannot be faked.
#  If no such interpreter answers on this host the branch is reported NOT RUN
#  (its own outcome — never a silent pass, never a false fail); the three
#  refusal branches run on any host.
#
#  Run:  bash tests/test_deepseek_mcp_tls.sh
# ─────────────────────────────────────────────────────────────
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$REPO/ops/scripts/manage/check-deepseek-mcp-tls.sh"
FAILS=0
NOTRUN=0

check() { # check <name> <0|1>
  if [[ "$2" == "1" ]]; then echo "  PASS  $1"; else echo "  FAIL  $1"; FAILS=$((FAILS+1)); fi
}

TD="$(mktemp -d)"
trap 'rm -rf "$TD"' EXIT

# A capable interpreter for the healthy branch — the fleet's way (capability,
# never a path), then confirm it also has certifi (the guard's whole point).
PY_CAP="$(bash "$REPO/ops/scripts/lib/python-with-module.sh" --print mcp 2>/dev/null || true)"
if [[ -n "$PY_CAP" ]] && env -u PYTHONPATH -u PYTHONHOME "$PY_CAP" -c 'import certifi' >/dev/null 2>&1; then
  CAP_OK=1
else
  CAP_OK=0
fi

echo "A. healthy — deepseek entry with a full, working TLS stack"
HA="$TD/home_a"; mkdir -p "$HA/.pi/agent"
if [[ "$CAP_OK" == "1" ]]; then
  printf '{"mcpServers":{"deepseek":{"command":"%s"}}}\n' "$PY_CAP" > "$HA/.pi/agent/mcp.json"
  OUT_A="$(env HOME="$HA" bash "$SCRIPT" 2>&1)"; RC_A=$?
  check "A: exits 0 (rc=$RC_A)" "$([ "$RC_A" -eq 0 ] && echo 1 || echo 0)"
  check "A: prints deepseek TLS ok" "$([[ "$OUT_A" == *"deepseek TLS ok"* ]] && echo 1 || echo 0)"
else
  NOTRUN=$((NOTRUN+1))
  echo "  NOT RUN  healthy branch (no interpreter on this host imports mcp + certifi)"
  echo "           fix: $REPO/ops/scripts/manage/fix-fleet-venv.py  (declared set now includes certifi)"
fi

echo "B. missing ~/.pi/agent/mcp.json — refuse"
HB="$TD/home_b"; mkdir -p "$HB"
OUT_B="$(env HOME="$HB" bash "$SCRIPT" 2>&1)"; RC_B=$?
check "B: exits 1 (rc=$RC_B)" "$([ "$RC_B" -eq 1 ] && echo 1 || echo 0)"
check "B: says MISSING" "$([[ "$OUT_B" == *"MISSING"* ]] && echo 1 || echo 0)"

echo "C. mcp.json present but no deepseek entry — refuse"
HC="$TD/home_c"; mkdir -p "$HC/.pi/agent"
printf '%s\n' '{"mcpServers":{"tasks":{"command":"/bin/true"}}}' > "$HC/.pi/agent/mcp.json"
OUT_C="$(env HOME="$HC" bash "$SCRIPT" 2>&1)"; RC_C=$?
check "C: exits 1 (rc=$RC_C)" "$([ "$RC_C" -eq 1 ] && echo 1 || echo 0)"
check "C: says entry unreadable" "$([[ "$OUT_C" == *"unreadable"* ]] && echo 1 || echo 0)"

echo "D. deepseek command is a non-executable path — refuse"
HD="$TD/home_d"; mkdir -p "$HD/.pi/agent"
printf '%s\n' '{"mcpServers":{"deepseek":{"command":"/nonexistent/venv/bin/python3"}}}' > "$HD/.pi/agent/mcp.json"
OUT_D="$(env HOME="$HD" bash "$SCRIPT" 2>&1)"; RC_D=$?
check "D: exits 1 (rc=$RC_D)" "$([ "$RC_D" -eq 1 ] && echo 1 || echo 0)"
check "D: says interpreter not executable" "$([[ "$OUT_D" == *"not executable"* ]] && echo 1 || echo 0)"

echo
if [[ "$FAILS" -gt 0 ]]; then echo "$FAILS FAILED"; exit 1; fi
if [[ "$NOTRUN" -gt 0 ]]; then echo "ALL PASS ($NOTRUN NOT RUN)"; exit 0; fi
echo "ALL PASS"