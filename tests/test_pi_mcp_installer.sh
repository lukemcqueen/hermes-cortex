#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  test_pi_mcp_installer.sh — regression test for
#  ops/scripts/install/install-pi-mcp.sh
#
#  Proves:
#    1. Registers the 5 cortex MCP servers at USER scope
#       in ~/.pi/agent/mcp.json (Pi >= 1.0 MCP client).
#    2. Preserves every pre-existing key in the file (never clobbers).
#    3. Preserves the user's own non-governance mcpServers.
#    4. Derives AGENT_NAME from ~/.hermes-cortex/agent.env.
#    5. Is idempotent (second run = same server set).
#    6. --remove strips only the cortex servers.
#    7. KEEPS the interpreter an existing mcp.json already proves works, instead
#       of replacing it with a different one the resolver would have chosen.
#    8. REFUSES to write (exit 1, config left byte-identical) when nothing on the
#       host can `import mcp` — the old behaviour wrote the PATH python3 anyway,
#       so every cortex server started dead while the file looked perfect.
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

# The installer refuses to write an interpreter that cannot `import mcp`, so this
# test must hand it one that can — resolved the fleet's way (the component's own
# resolver), never `command -v python3`, which is the interpreter most likely to
# lack the module (measured on esther 2026-10-12: PATH python3 has NO mcp).
# exit 3 = COULD NOT VERIFY: fail loudly, never skip silently.
PY_MCP="$(bash "$REPO/ops/scripts/lib/python-with-module.sh" --print mcp)" || {
  echo "  FAIL  no interpreter on this host can import mcp — cannot exercise the installer"
  echo "        (fix: bash ~/.hermes-cortex/scripts/cortex-update.sh, or: python3 -m pip install mcp)"
  exit 3
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

export HOME="$HOME_T" PYTHON="$PY_MCP"
unset AGENT_NAME 2>/dev/null || true

bash "$SCRIPT" >/dev/null 2>&1
python3 - "$PJ" <<'EOF'
import json, sys
d = json.load(open(sys.argv[1]))
assert d["autoEnableCodemode"] is True, "existing key lost"
assert d["mcpServers"]["user-own-server"]["command"] == "uvx", "user server clobbered"
for n in ("loop-governance", "tasks", "executor", "agent-bus", "cortex-context"):
    assert n in d["mcpServers"], f"{n} missing"
s = d["mcpServers"]["loop-governance"]
assert s["env"]["AGENT_NAME"] == "tituspi", f"AGENT_NAME not derived: {s.get('env')}"
assert s["exposure"] == "direct", "governance tools must be declared to the model"
assert s["args"][0].endswith("tools/loop-governance/loop-gov-mcp.py"), s["args"]
EOF
check "run1: user keys preserved + 5 servers + derived AGENT_NAME + exposure" "$([ $? -eq 0 ] && echo 1 || echo 0)"

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
assert "cortex-context" not in d["mcpServers"], "cortex-context survived remove"
assert d["autoEnableCodemode"] is True, "remove dropped an unrelated key"
EOF
check "--remove strips cortex only, keeps user's own" "$([ $? -eq 0 ] && echo 1 || echo 0)"

echo
echo "B. an interpreter the existing mcp.json PROVES works is kept"
# Discriminating by construction: the registered command is a shim the resolver
# would never pick (it honours PYTHON first), so a regression that ignores the
# existing config shows up as a changed command string.
HOME_B="$TD/home_b"; mkdir -p "$HOME_B/.pi/agent" "$HOME_B/.hermes-cortex" "$TD/shim"
printf 'AGENT_NAME=tituspi\n' > "$HOME_B/.hermes-cortex/agent.env"
# A WRAPPER, not a symlink: a symlinked venv python loses its venv (no pyvenv.cfg
# beside the link) and cannot import mcp, which the installer then rightly refuses
# to preserve — the assertion would test the probe, not the preservation logic.
{ printf '#!/bin/sh\n'; printf 'exec "%s" "$@"\n' "$PY_MCP"; } > "$TD/shim/python3"
chmod +x "$TD/shim/python3"
PJB="$HOME_B/.pi/agent/mcp.json"
python3 - "$PJB" "$TD/shim/python3" <<'PY'
import json, sys
path, shim = sys.argv[1], sys.argv[2]
json.dump({"mcpServers": {"loop-governance": {
    "command": shim, "args": ["/x/loop-gov-mcp.py"], "env": {"AGENT_NAME": "tituspi"}}}},
    open(path, "w"))
PY
env HOME="$HOME_B" PYTHON="$PY_MCP" bash "$SCRIPT" >/dev/null 2>&1
GOT="$(python3 -c "import json;print(json.load(open('$PJB'))['mcpServers']['loop-governance']['command'])")"
check "B: kept the working shim interpreter (got: $GOT)" "$([ "$GOT" = "$TD/shim/python3" ] && echo 1 || echo 0)"

echo
echo "C. nothing can import mcp -> refuse loudly, leave the config untouched"
# Hermetic by construction: PATH holds ONLY the coreutils the installer needs plus
# a python3 that cannot import mcp, so the resolver finds no capable interpreter on
# ANY host. Waiting for a host that lacks the module would never test this branch.
# The five deployed servers DO exist here, so the "Run cortex-update.sh first"
# warning stays silent and a passing remediation assertion can only come from the
# interpreter error itself.
HOME_C="$TD/home_c"; mkdir -p "$HOME_C/.pi/agent" "$HOME_C/.hermes-cortex/scripts" \
  "$HOME_C/.hermes-cortex/tools/loop-governance"
for f in scripts/task-mcp.py scripts/executor-mcp.py scripts/cortex-bus-mcp.py \
         scripts/cortex-context-mcp.py tools/loop-governance/loop-gov-mcp.py; do
  printf '# mcp server\n' > "$HOME_C/.hermes-cortex/$f"
done
BIN_C="$TD/bin_c"; mkdir -p "$BIN_C"
for b in bash dirname grep cp mkdir cat sed head cut tr basename cmp; do
  ln -sf "$(command -v "$b")" "$BIN_C/$b" 2>/dev/null || true
done
printf '#!/bin/sh\nexit 1\n' > "$BIN_C/python3"; chmod +x "$BIN_C/python3"
printf 'AGENT_NAME=tituspi\n' > "$HOME_C/.hermes-cortex/agent.env"
PJC="$HOME_C/.pi/agent/mcp.json"
python3 - "$PJC" "$BIN_C/python3" <<'PY'
import json, sys
path, nopymcp = sys.argv[1], sys.argv[2]
json.dump({"mcpServers": {"loop-governance": {
    "command": nopymcp, "args": ["/x/loop-gov-mcp.py"], "env": {"AGENT_NAME": "tituspi"}}}},
    open(path, "w"))
PY
cp "$PJC" "$PJC.before"
OUT_C="$(env PATH="$BIN_C" HOME="$HOME_C" PYTHON="$BIN_C/python3" bash "$SCRIPT" 2>&1)"; RC_C=$?
check "C: exits non-zero instead of writing a dead config (rc=$RC_C)" "$([ "$RC_C" -ne 0 ] && echo 1 || echo 0)"
check "C: says the interpreter cannot import mcp" "$([[ "$OUT_C" == *"import mcp"* ]] && echo 1 || echo 0)"
check "C: names the remediation" "$([[ "$OUT_C" == *"cortex-update.sh"* ]] && echo 1 || echo 0)"
check "C: existing mcp.json left byte-identical" "$(cmp -s "$PJC" "$PJC.before" && echo 1 || echo 0)"

echo
echo "D. a malformed mcp.json is refused in one sentence, never a traceback"
HOME_D="$TD/home_d"; mkdir -p "$HOME_D/.pi/agent" "$HOME_D/.hermes-cortex/scripts" \
  "$HOME_D/.hermes-cortex/tools/loop-governance"
printf 'AGENT_NAME=tituspi\n' > "$HOME_D/.hermes-cortex/agent.env"
for f in scripts/task-mcp.py scripts/executor-mcp.py scripts/cortex-bus-mcp.py \
         scripts/cortex-context-mcp.py tools/loop-governance/loop-gov-mcp.py; do
  printf '# mcp server\n' > "$HOME_D/.hermes-cortex/$f"
done
PJD="$HOME_D/.pi/agent/mcp.json"
printf 'not json{\n' > "$PJD"; cp "$PJD" "$PJD.before"
OUT_D="$(env HOME="$HOME_D" PYTHON="$PY_MCP" bash "$SCRIPT" 2>&1)"; RC_D=$?
check "D: exits non-zero (rc=$RC_D)" "$([ "$RC_D" -ne 0 ] && echo 1 || echo 0)"
check "D: says the file is not valid JSON" "$([[ "$OUT_D" == *"not valid JSON"* ]] && echo 1 || echo 0)"
check "D: no raw Python traceback" "$([[ "$OUT_D" != *"Traceback"* ]] && echo 1 || echo 0)"
check "D: the unparseable file is left for its owner" "$(cmp -s "$PJD" "$PJD.before" && echo 1 || echo 0)"

echo
if [[ "$FAILS" -gt 0 ]]; then echo "$FAILS FAILED"; exit 1; fi
echo "ALL PASS"
