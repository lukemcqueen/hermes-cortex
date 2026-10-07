#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  install-claude-governance.sh — Register loop-governance MCP
#  servers at USER scope so Claude Code gets them in EVERY repo.
#
#  Problem (2026-09-29, Luke): the repo-root .mcp.json is PROJECT
#  scope — Claude Code loads it only in the hermes-cortex checkout.
#  In a separate repo Claude had NO loop-governance tools (no
#  begin_change / end_change), so governance silently didn't exist
#  there. Fix: register the same governance servers at USER scope
#  (~/.claude.json "mcpServers"), matching how core.hooksPath is
#  already global. The per-repo .mcp.json overrides for anyone who
#  wants a different set without touching the user defaults.
#
#  Usage:
#    bash install-claude-governance.sh            # add/update (idempotent)
#    bash install-claude-governance.sh --check    # show current registration
#    bash install-claude-governance.sh --remove   # remove our servers only
#
#  Supports macOS + Linux. Writes ~/.claude.json, preserving every
#  existing key (it backs up the file first). Set AGENT_NAME to
#  attribute cycles to the right agent (default: titusclaude).
# ─────────────────────────────────────────────────────────────
set -euo pipefail

CLAUDE_JSON="${HOME}/.claude.json"
PYTHON="${PYTHON:-$(command -v python3)}"
# Resolve deployed MCP server paths (cortex-update.sh deploys here on both
# macOS and Linux). Fall back to the repo source when not deployed.
LOOP_GOV="${HOME}/.hermes-cortex/tools/loop-governance/loop-gov-mcp.py"
TASK_MCP="${HOME}/.hermes-cortex/scripts/task-mcp.py"
EXECUTOR_MCP="${HOME}/.hermes-cortex/scripts/executor-mcp.py"
BUS_MCP="${HOME}/.hermes-cortex/scripts/cortex-bus-mcp.py"
AGENT_NAME="${AGENT_NAME:-titusclaude}"
# Python that has the `mcp` package: prefer the cortex venv, fall back to PATH.
PY_CMD="${HOME}/.hermes-cortex/venv/bin/python3"
[[ -x "$PY_CMD" ]] || PY_CMD="${PYTHON}"

for f in "$LOOP_GOV" "$TASK_MCP" "$EXECUTOR_MCP" "$BUS_MCP"; do
  if [[ ! -f "$f" ]]; then
    echo "Warning: governance MCP server not found: $f"
    echo "  Run cortex-update.sh first, then this script."
  fi
done

MODE="add"
case "${1:-}" in
  --check|--list) MODE="check" ;;
  --remove) MODE="remove" ;;
esac

if [[ "$MODE" == "check" ]]; then
  echo "~/.claude.json:"
  if [[ -f "$CLAUDE_JSON" ]]; then
    "$PYTHON" -c "
import json,sys
d=json.load(open('$CLAUDE_JSON'))
for k,v in d.get('mcpServers',{}).items():
    print(f'  {k}: {v.get(\"command\",\"?\")} {\" \".join(v.get(\"args\",[]))} env={v.get(\"env\",{})}')
if not d.get('mcpServers'):
    print('  (no mcpServers registered)')
"
  else
    echo "  (no $CLAUDE_JSON)"
  fi
  exit 0
fi

# Back up existing config before touching it.
if [[ -f "$CLAUDE_JSON" ]]; then
  cp -p "$CLAUDE_JSON" "${CLAUDE_JSON}.bak.governance"
fi

"$PYTHON" - "$CLAUDE_JSON" "$LOOP_GOV" "$TASK_MCP" "$EXECUTOR_MCP" "$BUS_MCP" "$AGENT_NAME" "$MODE" "$PY_CMD" <<'PYEOF'
import json, os, sys

claude_json, loop_gov, task_mcp, executor_mcp, bus_mcp, agent_name, mode, py_cmd = sys.argv[1:]

# Merge our governance servers into the user-scope mcpServers map,
# preserving everything else the user already has.
def server(command, args, env=None):
    s = {"command": command, "args": list(args)}
    if env:
        s["env"] = env
    return s

GOVERNANCE = {
    "loop-governance": server(py_cmd,
                              ["~/.hermes-cortex/tools/loop-governance/loop-gov-mcp.py"],
                              {"AGENT_NAME": "{{AGENT_NAME}}"}),
    "tasks": server(py_cmd,
                    ["~/.hermes-cortex/scripts/task-mcp.py"],
                    {"AGENT_NAME": "{{AGENT_NAME}}"}),
    "executor": server(py_cmd,
                       ["~/.hermes-cortex/scripts/executor-mcp.py"],
                       {"AGENT_NAME": "{{AGENT_NAME}}"}),
    "agent-bus": server(py_cmd,
                        ["~/.hermes-cortex/scripts/cortex-bus-mcp.py"],
                        {"AGENT_NAME": "{{AGENT_NAME}}"}),
}

# Replace the placeholder with the real agent name.
for name in GOVERNANCE:
    GOVERNANCE[name]["env"]["AGENT_NAME"] = agent_name

data = {}
if os.path.exists(claude_json):
    with open(claude_json) as f:
        data = json.load(f)
if not isinstance(data, dict):
    data = {}

servers = data.setdefault("mcpServers", {})
if mode == "remove":
    removed = [n for n in GOVERNANCE if n in servers]
    for n in removed:
        del servers[n]
    print("Removed governance servers:", ", ".join(removed) if removed else "(none present)")
else:
    prior = set(servers) & set(GOVERNANCE)
    servers.update(GOVERNANCE)
    data["mcpServers"] = servers
    added = [n for n in GOVERNANCE if n not in prior]
    print("Registered governance servers (user scope):", ", ".join(GOVERNANCE))
    if added:
        print("  newly added:", ", ".join(added))
    else:
        print("  (all already present — updated in place)")

with open(claude_json, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
print(f"Wrote {claude_json}")
PYEOF
echo "Done. Restart the Claude Code session to load the new servers."
echo "Verify: bash $(cd "$(dirname "$0")" && pwd)/install-claude-governance.sh --check"