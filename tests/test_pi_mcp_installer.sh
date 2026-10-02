#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  test_pi_mcp_installer.sh — regression test for
#  ops/scripts/install/install-pi-mcp.sh
#
#  Proves:
#    1. Registers the 4 cortex governance MCP servers at USER scope
#       in ~/.pi/agent/mcp.json (Pi >= 1.0 MCP client).
#    2. Preserves every pre-existing key in the file (never clobbers).
#    3. Preserves the user's own non-governance mcpServers.
#    4. Derives AGENT_NAME from ~/.hermes-cortex/agent.env.
#    5. Is idempotent (second run = same server set).
#    6. --remove strips only the cortex servers.
#  Runs against a temp HOME — never touches the real ~/.pi/agent/mcp.json.
#
#  Run:  bash tests/test_pi_mcp_installer.sh
# ─────────────────────────────────────────────────────────────
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$REPO/ops/scripts/install/install-pi-mcp.sh"
FAILS=0

check() { # check <name> <0|1>
  if [[ "$2" == "1" ]]; then echo "  PASS  $1"; else echo "  FAIL  $1"; FAILS=$((FAILS+1)); fi
}

TD="$(mktemp -d)"
trap 'rm -rf "$TD"' EXIT
HOME_T="$TD/home"; mkdir -p "$HOME_T/.pi/agent" "$HOME_T/.hermes-cortex"
PJ="$HOME_T/.pi/agent/mcp.json"

# Per-host identity file — the installer must use this name, not a guess.
python3 - "$HOME_T/.hermes-cortex/agent.env" <<'PY'
import pathlib, sys
pathlib.Path(sys.argv[1]).write_text("AGENT_NAME=tituspi\n")
PY

# A pre-existing Pi config with user state + a user-owned server.
cat > "$PJ" <<'EOF'
{
  "autoEnableCodemode": true,
  "mcpServers": {"user-own-server": {"command": "uvx", "args": ["x"]}}
}
EOF

export HOME="$HOME_T" PYTHON="$(command -v python3)"
unset AGENT_NAME 2>/dev/null || true

bash "$SCRIPT" >/dev/null 2>&1
python3 - "$PJ" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
assert d["autoEnableCodemode"] is True, "existing key lost"
assert d["mcpServers"]["user-own-server"]["command"] == "uvx", "user server clobbered"
for n in ("loop-governance", "tasks", "executor", "agent-bus"):
    assert n in d["mcpServers"], f"{n} missing"
s = d["mcpServers"]["loop-governance"]
assert s["env"]["AGENT_NAME"] == "tituspi", f"AGENT_NAME not derived: {s.get('env')}"
assert s["exposure"] == "direct", "governance tools must be declared to the model"
assert s["args"][0].endswith("tools/loop-governance/loop-gov-mcp.py"), s["args"]
EOF
check "run1: user keys preserved + 4 servers + derived AGENT_NAME + exposure" "$([ $? -eq 0 ] && echo 1 || echo 0)"

BEFORE="$(python3 -c "import json;print(sorted(json.load(open('$PJ'))['mcpServers']))")"
bash "$SCRIPT" >/dev/null 2>&1
AFTER="$(python3 -c "import json;print(sorted(json.load(open('$PJ'))['mcpServers']))")"
check "run2: idempotent (same server set)" "$([ "$BEFORE" = "$AFTER" ] && echo 1 || echo 0)"

bash "$SCRIPT" --check >/dev/null 2>&1; RC=$?
check "--check exits 0" "$([ $RC -eq 0 ] && echo 1 || echo 0)"

bash "$SCRIPT" --remove >/dev/null 2>&1
python3 - "$PJ" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
assert "user-own-server" in d["mcpServers"], "remove took the user's server"
assert "loop-governance" not in d["mcpServers"], "governance server survived remove"
assert d["autoEnableCodemode"] is True, "remove dropped an unrelated key"
EOF
check "--remove strips cortex only, keeps user's own" "$([ $? -eq 0 ] && echo 1 || echo 0)"

echo
if [[ "$FAILS" -gt 0 ]]; then echo "$FAILS FAILED"; exit 1; fi
echo "ALL PASS"
