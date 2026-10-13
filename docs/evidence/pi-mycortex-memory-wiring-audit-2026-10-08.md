# Evidence: Pi ↔ mycortex memory integration investigation

Date: 2026-10-08
Agent: titus (LAM2)
Task: mycortex-memory-integration

## Finding: integration EXISTS but was not wired on this host

The hermes-cortex repo already contains a complete Pi + mycortex memory integration:
- `plugins/mycortex-mem/__init__.py` — MemoryProvider for Hermes
- `mcp-servers/cortex-context-mcp.py` — MCP server exposing 12 memory/session tools
- `ops/install/harnesses/pi/extensions/cortex-context.ts` — Pi lifecycle extension
- Runbooks: `ops/install/harnesses/pi/IMPLEMENT.md`, `docs/runbooks/context-integration.md`

However, `~/.pi/agent/mcp.json` on this host was dated 2026-10-02 and had ONLY 4 of the 5 expected cortex MCP servers. The `cortex-context` server was missing entirely.

## Immediate fix applied

Ran `install-pi-mcp.sh` to add the missing server. It added `cortex-context` but simultaneously broke the python interpreter path: it replaced `/Users/luke/.hermes/hermes-agent/venv/bin/python3` (which has the `mcp` package) with `/Users/luke/.local/bin/python3` (which does NOT).

Manually corrected `~/.pi/agent/mcp.json` to restore the working interpreter for all 5 server entries.

## Verification

```
$ ~/.pi/agent/bin/pi mcp list
loop-governance:    connected, 17 tools
agent-bus:          connected, 10 tools
tasks:              connected, 14 tools
executor:           connected, 6 tools
cortex-context:     connected, 12 tools   ← newly visible
```

Memory read path verified:
```
$ python3 ~/.hermes-cortex/scripts/cortex-context.py mem_context '{}'
→ returns peer card with 6 standing facts + 3 persistent conclusions + recent messages
```

## Installer bug discovered

`ops/scripts/install/install-pi-mcp.sh` selects `PY_CMD` like this:
```bash
PY_CMD="${HOME}/.hermes-cortex/venv/bin/python3"
[[ -x "$PY_CMD" ]] || PY_CMD="${PYTHON}"
```

When the cortex venv does not exist (common on macOS), it falls back to the PATH python3. On this host that resolves to Homebrew python3 without the `mcp` package. The script then silently overwrites mcp.json with the broken path, causing ALL 5 MCP servers to fail with "mcp package not found".

## Proposal sent

A bus PROPOSAL (subject PROPOSAL) was sent to Moses/Esther with the fix:
1. Try `~/.hermes/hermes-agent/venv/bin/python3` as a second candidate
2. Preserve an existing working interpreter from mcp.json
3. Warn loudly before falling back to a system python that lacks `mcp`
4. Update audit script to expect 5 servers instead of 4
5. Update unit test to create synthetic `cortex-context-mcp.py`

## What the user needs to do

Start a NEW Pi session (or `/reload`) so Pi picks up the newly registered `cortex-context` MCP server. The current running session was started before the fix and does not have the memory tools in its tool list.
