#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  test_claude_governance_installer.sh — regression test for
#  ops/scripts/install/install-claude-governance.sh
#
#  Proves (2026-09-29, governance-agnostic-claude):
#    1. Registers the 4 governance MCP servers at USER scope.
#    2. Preserves every pre-existing ~/.claude.json key (never clobbers).
#    3. Preserves the user's own non-governance mcpServers.
#    4. Is idempotent (second run = same server set).
#    5. --remove strips only the governance servers.
#  Runs against a temp HOME — never touches the real ~/.claude.json.
#
#  Run:  bash tests/test_claude_governance_installer.sh
# ─────────────────────────────────────────────────────────────
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$REPO/ops/scripts/install/install-claude-governance.sh"
FAILS=0

check() { # check <name> <0|1>
  if [[ "$2" == "1" ]]; then echo "  PASS  $1"; else echo "  FAIL  $1"; FAILS=$((FAILS+1)); fi
}

TD="$(mktemp -d)"
trap 'rm -rf "$TD"' EXIT
HOME_T="$TD/home"; mkdir -p "$HOME_T"
CJ="$HOME_T/.claude.json"

# A pre-existing config with user state + a user-owned server.
cat > "$CJ" <<'EOF'
{
  "firstStartTime": "2026-08-30T07:49:17.307Z",
  "machineID": "abc123",
  "migrationVersion": 13,
  "mcpServers": {"user-own-server": {"command": "uvx", "args": ["x"]}}
}
EOF

export HOME="$HOME_T" PYTHON="$(command -v python3)"
unset AGENT_NAME 2>/dev/null || true

bash "$SCRIPT" >/dev/null 2>&1
python3 - "$CJ" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
assert d["machineID"] == "abc123", "existing key lost"
assert d["mcpServers"]["user-own-server"]["command"] == "uvx", "user server clobbered"
for n in ("review", "tasks", "executor", "agent-bus"):
    assert n in d["mcpServers"], f"{n} missing"
assert d["mcpServers"]["review"]["env"]["AGENT_NAME"] == "titusclaude"
EOF
check "run1: user keys preserved + 4 governance servers + AGENT_NAME" "$([ $? -eq 0 ] && echo 1 || echo 0)"

BEFORE="$(python3 -c "import json;print(sorted(json.load(open('$CJ'))['mcpServers']))")"
bash "$SCRIPT" >/dev/null 2>&1
AFTER="$(python3 -c "import json;print(sorted(json.load(open('$CJ'))['mcpServers']))")"
check "run2: idempotent (same server set)" "$([ "$BEFORE" = "$AFTER" ] && echo 1 || echo 0)"

bash "$SCRIPT" --check >/dev/null 2>&1; RC=$?
check "--check exits 0" "$([ $RC -eq 0 ] && echo 1 || echo 0)"

bash "$SCRIPT" --remove >/dev/null 2>&1
python3 - "$CJ" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
assert "user-own-server" in d["mcpServers"], "remove took the user's server"
assert "review" not in d["mcpServers"], "governance server survived remove"
EOF
check "--remove strips governance only, keeps user's own" "$([ $? -eq 0 ] && echo 1 || echo 0)"

# 6. A PRE-RENAME host carries the legacy "loop-governance" key pointing at the SAME
#    binary. A run must RENAME it, never duplicate it — one process under two names is
#    the exact fragmentation the one-name rule (review) exists to kill, and the doctor
#    FAILs it.
python3 - "$CJ" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
# After --remove no governance server is left to clone: build the legacy entry standalone,
# with the args that identify the probe binary (the drop condition matches on args).
d["mcpServers"]["loop-governance"] = {
    "command": "python3",
    "args": ["~/.hermes-cortex/tools/loop-governance/loop-gov-mcp.py"],
}
json.dump(d, open(sys.argv[1], "w"))
EOF
grep -q '"loop-governance"' "$CJ" || { echo "  FAIL  rename: legacy seed itself did not land"; FAILS=$((FAILS+1)); }
bash "$SCRIPT" >/dev/null 2>&1
python3 - "$CJ" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
assert "review" in d["mcpServers"], "review missing"
assert "loop-governance" not in d["mcpServers"], "legacy entry survived the rename"
print("legacy renamed to review; single registration")
EOF
check "rename: legacy loop-governance entry becomes review, never duplicated" "$([ $? -eq 0 ] && echo 1 || echo 0)"

echo
if [[ "$FAILS" -gt 0 ]]; then echo "$FAILS FAILED"; exit 1; fi
echo "ALL PASS"
