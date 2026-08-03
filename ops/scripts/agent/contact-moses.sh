#!/bin/bash
# contact-moses.sh — send a question/message to Moses via the bus (HTTP client)
# Usage: contact-moses.sh "subject" "body" [priority]
#   priority: normal (default), urgent, critical
#
# Auth/URL resolution order:
#   1. Env vars: CORTEX_BUS_AUTH / CORTEX_BASIC_AUTH / CORTEX_INBOX_AUTH,
#      BUS_URL / CORTEX_BUS_URL
#   2. Fallback: ~/.hermes-cortex/cortex-bus.conf (KEY=value lines)
#
# NOTE: body should be a single line. Multi-line bodies are flattened by
# the JSON builder (python3 — guaranteed present in Hermes environments).

set -euo pipefail

AGENT_NAME="${AGENT_NAME:-${USER:-unknown}}"
SUBJECT="${1:-}"
BODY="${2:-}"
PRIORITY="${3:-normal}"

CONF="${CORTEX_BUS_CONF:-${HOME}/.hermes-cortex/cortex-bus.conf}"

_read_conf() {
  local key="$1"
  if [ -f "$CONF" ]; then
    sed -n "s/^${key}=//p" "$CONF" 2>/dev/null | head -1 | tr -d '"'
  fi
}

AUTH="${CORTEX_BUS_AUTH:-${CORTEX_BASIC_AUTH:-${CORTEX_INBOX_AUTH:-}}}"
if [ -z "$AUTH" ]; then
  AUTH="$(_read_conf "CORTEX_BASIC_AUTH")"
fi
if [ -z "$AUTH" ]; then
  AUTH="$(_read_conf "CORTEX_BUS_AUTH")"
fi

BUS_URL="${BUS_URL:-${CORTEX_BUS_URL:-}}"
if [ -z "$BUS_URL" ]; then
  BUS_URL="$(_read_conf "CORTEX_BUS_URL")"
fi
if [ -z "$BUS_URL" ]; then
  BUS_URL="http://127.0.0.1:13004"
fi

if [ -z "$SUBJECT" ] || [ -z "$BODY" ]; then
  echo "Usage: contact-moses.sh \"subject\" \"body\" [priority]"
  echo "  priority: normal (default), urgent, critical"
  exit 1
fi

if [ -z "$AUTH" ]; then
  echo "ERROR: CORTEX_BUS_AUTH, CORTEX_BASIC_AUTH, or CORTEX_INBOX_AUTH not set (env or ${CONF})." >&2
  exit 1
fi

# Build payload with python3 (guaranteed present in Hermes venv — jq is not)
# so multi-line bodies are safely JSON-encoded, not interpolated.
PAYLOAD=$(AGENT_NAME="$AGENT_NAME" SUBJECT="$SUBJECT" BODY="$BODY" PRIORITY="$PRIORITY" \
  python3 -c '
import json, os
print(json.dumps({
    "queue": "inbox_moses",
    "message": {
        "from": os.environ["AGENT_NAME"],
        "to": "moses",
        "subject": os.environ["SUBJECT"],
        "body": os.environ["BODY"],
        "priority": os.environ["PRIORITY"],
    },
}))')

echo "📤 Sending to Moses..."
RESULT=$(curl -s -u "$AUTH" -X POST \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" \
  "${BUS_URL}/api/pgmq/send" 2>&1 || true)

if echo "$RESULT" | grep -q '"msg_id"'; then
  MSG_ID=$(echo "$RESULT" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("msg_id","?"))' 2>/dev/null || echo "?")
  echo "✅ Delivered. Message ID: ${MSG_ID}"
else
  echo "❌ Failed: $RESULT"
  exit 1
fi
