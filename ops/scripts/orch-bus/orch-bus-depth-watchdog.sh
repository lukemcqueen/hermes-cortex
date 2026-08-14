#!/bin/bash
# orch-bus-depth-watchdog.sh — no_agent cron: checks bus inbox depth, silent when empty
# Returns "MAIL:N" if depth > 0, nothing otherwise (watchdog pattern)
# Schedule: */30 * * * * *  (every 30 seconds)

# ── Agent identity — fail loud, never hostname/USER/other agent ──
AGENT_NAME="${AGENT_NAME:-}"
if [[ -z "$AGENT_NAME" && -f "${HOME}/.hermes-cortex/agent.env" ]]; then
  AGENT_NAME=$(grep -E '^AGENT_NAME=' "${HOME}/.hermes-cortex/agent.env" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")
fi
if [[ -z "$AGENT_NAME" && -f "${HOME}/hermes-cortex/.env" ]]; then
  AGENT_NAME=$(grep -E '^AGENT_NAME=' "${HOME}/hermes-cortex/.env" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")
fi
if [[ -z "$AGENT_NAME" || "$AGENT_NAME" == "unknown" ]]; then
    echo "❌ AGENT_NAME not configured — set AGENT_NAME= in ~/.hermes-cortex/agent.env / ~/hermes-cortex/.env or export AGENT_NAME" >&2
    exit 1
fi
# Requires bus URL from config — no localhost fallback
if [[ -z "$BUS_URL" ]]; then
    echo "ERROR: BUS_URL not set — configure CORTEX_BUS_URL in env or cortex-bus.conf" >&2
    exit 1
fi

depth=$(curl -s -H "X-Forwarded-User: $AGENT_NAME" "$BUS_URL/api/pgmq/depth/inbox_$AGENT_NAME" 2>/dev/null | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    print(d.get('depth', 0))
except:
    print(0)
" 2>/dev/null)

if [ "$depth" -gt 0 ]; then
    echo "MAIL:$depth"
fi
