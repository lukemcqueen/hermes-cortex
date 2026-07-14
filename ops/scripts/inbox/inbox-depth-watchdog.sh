#!/bin/bash
# inbox-depth-watchdog.sh — no_agent cron: checks bus inbox depth, silent when empty
# Returns "MAIL:N" if depth > 0, nothing otherwise (watchdog pattern)
# Schedule: */30 * * * * *  (every 30 seconds)

AGENT_NAME="${AGENT_NAME:-${USER:-moses}}"
BUS_URL="${BUS_URL:-http://127.0.0.1:8905}"

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
