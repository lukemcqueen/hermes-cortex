#!/usr/bin/env bash
# Agent Bus Monitor — silent when empty, output when bus messages arrive
# Usage:
#   agent-bus-monitor.sh
#   agent-bus-monitor.sh --mark-read
#
# Config: AGENT_BUS_URL / AGENT_BUS_TOKEN (or ~/.hermes/agent-bus.env)
set -euo pipefail

ENV_FILE="${HOME}/.hermes/agent-bus.env"
[ -f "$ENV_FILE" ] && source "$ENV_FILE"

URL="${AGENT_BUS_URL:-http://localhost:8903}"
TOKEN="${AGENT_BUS_TOKEN:-}"
AGENT="${AGENT_NAME:-esther}"

if [ -z "$TOKEN" ]; then
  # Fall back to bus token file
  TOKEN_FILE="${HOME}/.hermes/state/bus.token"
  [ -f "$TOKEN_FILE" ] && TOKEN="$(cat "$TOKEN_FILE")"
fi

if [ -z "$TOKEN" ]; then
  echo "ERROR: AGENT_BUS_TOKEN not set" >&2
  exit 1
fi

# Fetch unread messages via bus health/status endpoint
DATA=$(curl -sk --connect-timeout 10 \
  -H "Authorization: Bearer ${TOKEN}" \
  "${URL}/api/inbox?unread_only=true&for=${AGENT}" 2>/dev/null || true)

COUNT=$(echo "$DATA" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('unread',0))" 2>/dev/null || echo "0")

[ "$COUNT" -eq 0 ] && exit 0  # Silent exit

echo "━━━ Agent Bus — ${COUNT} unread ━━━"
echo "$DATA" | python3 -c "
import sys, json
d = json.load(sys.stdin)
for m in d.get('messages', []):
    print()
    print(f\"  From: {m['from']}  |  {m['topic']}  |  {m['timestamp'][:19]}\")
    print(f\"  Re:  {m['subject']}\")
    print(\"  ─\" + \"─\" * 50)
    for line in m['body'].strip().split('\n'):
        print(f\"  {line.strip()}\")
    print(f\"  (id: {m['filename']})\")
" 2>/dev/null

if [ "${1:-}" = "--mark-read" ]; then
  echo "$DATA" | python3 -c "
import sys, json, subprocess
d = json.load(sys.stdin)
for m in d.get('messages', []):
    subprocess.run(['curl', '-sk', '--connect-timeout', '10',
        '-H', 'Authorization: Bearer ${TOKEN}',
        '${URL}/read/' + m['filename'] + '?for=${AGENT}'],
        capture_output=True, timeout=10)
" 2>/dev/null
fi
