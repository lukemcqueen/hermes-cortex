#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  install-pi-mcp.sh — Register the Hermes Cortex MCP servers in
#  Pi's USER-scope config so every Pi session gets governance.
#
#  Problem (2026-10-02, Luke/Titus): Pi gained an MCP client
#  (Pi >= 0.99 / 1.0), but a Pi agent had NO servers configured —
#  no begin_change / end_change / task / bus tools, so the
#  interactive governance ritual and the task model were
#  unreachable from Pi.
#
#  Fix: write ~/.pi/agent/mcp.json (user scope — Pi reads it in
#  EVERY project) with the same four governance servers Claude
#  Code gets from install-claude-governance.sh. Pi reads
#  user servers from ~/.pi/agent/mcp.json and project servers from
#  .pi/mcp.json (trusted project roots only); an entry there
#  overrides a user-level entry with the same name.
#
#  cortex-context IS registered here (2026-10-03). The earlier note said
#  Pi had no MCP client at the CONTEXT layer, so the memory/session tools
#  came from the extension's own registerTool calls — and when Pi moved
#  0.87.1 → 1.0.0 that hand-written tool surface broke SILENTLY (every call
#  failed with "definition.execute is not a function") while the store was
#  perfectly healthy. Pi 1.0.0 HAS an MCP client (`pi mcp list`), so the
#  tools now come from the SAME server Claude Code and Codex use: one
#  implementation, schemas DERIVED from the contract, and nothing
#  per-harness left to drift. The extension is kept ONLY for the lifecycle
#  triggers MCP cannot provide (turn_end checkpoint, before_agent_start
#  restore), so the TOOLS still have exactly one way in.
#
#  Requires a Pi build with MCP support. Verify after installing:
#    pi mcp list
#
#  Usage:
#    bash install-pi-mcp.sh            # add/update (idempotent)
#    bash install-pi-mcp.sh --check    # show current registration
#    bash install-pi-mcp.sh --remove   # remove our servers only
#
#  Supports macOS + Linux. Backs up the file first and preserves
#  every existing key and the user's own servers. Set AGENT_NAME to
#  attribute cycles (default: AGENT_NAME from
#  ~/.hermes-cortex/agent.env, else "pi").
# ─────────────────────────────────────────────────────────────
set -euo pipefail

PI_MCP="${PI_MCP_FILE:-${HOME}/.pi/agent/mcp.json}"
PYTHON="${PYTHON:-$(command -v python3)}"

# Deployed MCP server paths (cortex-update.sh deploys here on both macOS
# and Linux). Fall back to the repo source when not deployed.
LOOP_GOV="${HOME}/.hermes-cortex/tools/loop-governance/loop-gov-mcp.py"
TASK_MCP="${HOME}/.hermes-cortex/scripts/task-mcp.py"
EXECUTOR_MCP="${HOME}/.hermes-cortex/scripts/executor-mcp.py"
BUS_MCP="${HOME}/.hermes-cortex/scripts/cortex-bus-mcp.py"
CONTEXT_MCP="${HOME}/.hermes-cortex/scripts/cortex-context-mcp.py"

# Identity: the per-host agent name, so cycles are attributed to this host's
# agent (see AGENTS.md rule 21 — identity is host-derived, never guessed).
DEFAULT_AGENT=""
if [[ -f "${HOME}/.hermes-cortex/agent.env" ]]; then
  DEFAULT_AGENT="$(grep -E '^AGENT_NAME=' "${HOME}/.hermes-cortex/agent.env" 2>/dev/null | head -1 | cut -d= -f2- || true)"
fi
AGENT_NAME="${AGENT_NAME:-${DEFAULT_AGENT:-pi}}"

# Python that has the `mcp` package: prefer the cortex venv, fall back to PATH.
PY_CMD="${HOME}/.hermes-cortex/venv/bin/python3"
[[ -x "$PY_CMD" ]] || PY_CMD="${PYTHON}"

for f in "$LOOP_GOV" "$TASK_MCP" "$EXECUTOR_MCP" "$BUS_MCP" "$CONTEXT_MCP"; do
  if [[ ! -f "$f" ]]; then
    echo "Warning: cortex MCP server not found: $f"
    echo "  Run cortex-update.sh first, then this script."
  fi
done

MODE="add"
case "${1:-}" in
  --check|--list) MODE="check" ;;
  --remove) MODE="remove" ;;
esac

if [[ "$MODE" == "check" ]]; then
  echo "$PI_MCP:"
  if [[ -f "$PI_MCP" ]]; then
    "$PYTHON" -c "
import json
d=json.load(open('$PI_MCP'))
for k,v in d.get('mcpServers',{}).items():
    print(f'  {k}: {v.get(\"command\",\"?\")} {\" \".join(v.get(\"args\",[]))} env={v.get(\"env\",{})}')
if not d.get('mcpServers'):
    print('  (no mcpServers registered)')
"
  else
    echo "  (no $PI_MCP)"
  fi
  exit 0
fi

# Back up existing config before touching it.
if [[ -f "$PI_MCP" ]]; then
  cp -p "$PI_MCP" "${PI_MCP}.bak.governance"
else
  mkdir -p "$(dirname "$PI_MCP")"
fi

"$PYTHON" - "$PI_MCP" "$LOOP_GOV" "$TASK_MCP" "$EXECUTOR_MCP" "$BUS_MCP" "$CONTEXT_MCP" "$AGENT_NAME" "$MODE" "$PY_CMD" <<'PYEOF'
import json, os, sys

(pi_mcp, loop_gov, task_mcp, executor_mcp, bus_mcp, context_mcp,
 agent_name, mode, py_cmd) = sys.argv[1:]


def server(path, description, env=None):
    return {
        "command": py_cmd,
        "args": [path],
        "env": env or {"AGENT_NAME": agent_name},
        # Governance is a ritual the model must reach without a discovery
        # step: declare the tools (Pi's default `codemode` exposure hides
        # them from the model and only makes them callable from scripts).
        "exposure": "direct",
        "description": description,
    }


GOVERNANCE = {
    "loop-governance": server(
        loop_gov,
        "Loop governance: begin_change, cache_search, cycle_query, "
        "feedback_accept/override, end_change — the interactive ritual."),
    "tasks": server(
        task_mcp,
        "Task model v3: claim, report, verify work slices."),
    "executor": server(
        executor_mcp,
        "Gated execution requests (governance lock + data tier enforced "
        "server-side)."),
    "agent-bus": server(
        bus_mcp,
        "Agent bus: inbox read/send and task dispatch."),
    # The memory/session TOOLS. Same server as Claude Code/Codex — Pi is not
    # special here. NOTE: no CORTEX_SESSION_* in `env` on purpose — Pi merges
    # this block over its own environment, so a session key the GATEWAY pinned
    # on the pi process (per chat) still reaches this server.
    "cortex-context": server(
        context_mcp,
        "Cortex context: mem_profile/search/context/conclude + "
        "session_checkpoint/restore/list/search/note/close."),
}

data = {}
if os.path.exists(pi_mcp):
    with open(pi_mcp) as f:
        data = json.load(f)
if not isinstance(data, dict):
    data = {}

servers = data.setdefault("mcpServers", {})
if not isinstance(servers, dict):
    servers = {}
    data["mcpServers"] = servers

if mode == "remove":
    removed = [n for n in GOVERNANCE if n in servers]
    for n in removed:
        del servers[n]
    print("Removed cortex MCP servers:", ", ".join(removed) if removed else "(none present)")
else:
    prior = set(servers) & set(GOVERNANCE)
    servers.update(GOVERNANCE)
    added = [n for n in GOVERNANCE if n not in prior]
    print("Registered cortex MCP servers (user scope):", ", ".join(GOVERNANCE))
    if added:
        print("  newly added:", ", ".join(added))
    else:
        print("  (all already present — updated in place)")

with open(pi_mcp, "w") as f:
    json.dump(data, f, indent=2)
    f.write("\n")
print(f"Wrote {pi_mcp}")
PYEOF
echo "Done. Run 'pi mcp list' to connect and check, or /reload in a session."
echo "Verify: bash $(cd "$(dirname "$0")" && pwd)/install-pi-mcp.sh --check"
