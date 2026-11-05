#!/usr/bin/env bash
# check-deepseek-mcp-tls.sh — host-local TLS guard for the deepseek MCP entry.
#
# Scope: the `deepseek` entry in ~/.pi/agent/mcp.json ONLY (not the whole fleet).
# Asserts that the entry's own interpreter can `import mcp` and resolve a REAL
# certifi.where() cacert.pem — the failure class the hermes-cortex → steadfaste-fleet
# home-dir migration surfaced ("Could not find a suitable TLS CA certificate bundle,
# invalid path: <venv>/certifi/cacert.pem").
#
# A stale `command` path or a missing cacert exits 1 so whatever wires it (pi restart
# hook, doctor, cron) flags the entry before a review/LLM call dies on TLS.
#
# Exit codes: 0 = healthy, 1 = broken (missing entry / interpreter / mcp / cacert).
set -euo pipefail

MCP_JSON="${HOME}/.pi/agent/mcp.json"
if [ ! -f "$MCP_JSON" ]; then
    echo "deepseek MCP TLS: MISSING $MCP_JSON"
    exit 1
fi

PY="$(env -u PYTHONPATH -u PYTHONHOME python3 -c "
import json, sys
try:
    cfg = json.load(open('$MCP_JSON'))
    cmd = cfg['mcpServers']['deepseek']['command']
    print(cmd)
except Exception as e:
    sys.exit('deepseek entry unreadable: %s' % e)
")"
if [ -z "$PY" ] || [ ! -x "$PY" ]; then
    echo "deepseek MCP TLS: interpreter not executable: $PY"
    exit 1
fi

if ! env -u PYTHONPATH -u PYTHONHOME "$PY" -c "
import os, mcp, certifi
p = certifi.where()
assert os.path.exists(p), 'cacert.pem missing: %s' % p
print('deepseek TLS ok:', p)
" ; then
    echo "deepseek MCP TLS: BROKEN under $PY (import mcp or certifi.where() failed)"
    exit 1
fi

echo "deepseek MCP TLS: OK ($PY)"
exit 0