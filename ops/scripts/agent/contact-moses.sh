#!/bin/bash
# contact-moses.sh — send a question/message to Moses via the bus
# Usage: contact-moses.sh "subject" "body" [priority]
#   priority: normal (default), urgent, critical
#
# Requires CORTEX_BASIC_AUTH or CORTEX_INBOX_AUTH in environment.

set -euo pipefail

AGENT_NAME="${AGENT_NAME:-${USER:-unknown}}"
SUBJECT="${1:-}"
BODY="${2:-}"
PRIORITY="${3:-normal}"

AUTH="${CORTEX_BASIC_AUTH:-${CORTEX_INBOX_AUTH:-}}"
BUS_URL="${BUS_URL:-${CORTEX_BUS_URL:-http://127.0.0.1:13004}}"

if [ -z "$SUBJECT" ] || [ -z "$BODY" ]; then
  echo "Usage: contact-moses.sh \"subject\" \"body\" [priority]"
  echo "  priority: normal (default), urgent, critical"
  exit 1
fi

if [ -z "$AUTH" ]; then
  echo "ERROR: CORTEX_BASIC_AUTH or CORTEX_INBOX_AUTH not set."
  exit 1
fi

PAYLOAD=$(cat <<EOF | jq -c .
{
  "queue": "inbox_moses",
  "message": {
    "from": "${AGENT_NAME}",
    "to": "moses",
    "subject": "${SUBJECT}",
    "body": "${BODY}",
    "priority": "${PRIORITY}"
  }
}
EOF
)

echo "📤 Sending to Moses..."
RESULT=$(curl -s -u "$AUTH" -X POST \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" \
  "${BUS_URL}/api/pgmq/send" 2>&1)

if echo "$RESULT" | grep -q '"msg_id"'; then
  echo "✅ Delivered. Message ID: $(echo "$RESULT" | jq -r '.msg_id 2>/dev/null || echo "?"')"
else
  echo "❌ Failed: $RESULT"
  exit 1
fi
