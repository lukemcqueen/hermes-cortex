#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  inbox-watch.sh — Poll agent inbox via external API
#
#  Designed for no_agent cron (watchdog pattern).
#  Silent (exit 0, no output) when nothing new.
#  Outputs formatted message summaries when new messages found.
#
#  Reads agent identity from:
#    1. AGENT_NAME env var (set by Hermes session)
#    2. ~/.hermes/agent-name file (if set manually)
#    3. hostname → agent-registry.json mapping
#
#  Usage as no_agent cron (run once on any machine with curl):
#    hermes cron create name=inbox-watch schedule="*/10 * * * *" \
#      script=inbox-watch.sh no_agent=true deliver=origin
#
#  Or as context_source for an LLM cron:
#    hermes cron create name=agent-inbox schedule="0 */2 * * *" \
#      prompt="Process inbox messages..." context_from=<job_id>
#
#  Auth: Uses ~/.hermes/moses-inbox.conf if present (BASIC auth).
#  Or set INBOX_AUTH env var to "user:pass".
# ─────────────────────────────────────────────────────────────
set -euo pipefail

# ── Resolve agent identity ────────────────────────────────
AGENT="${AGENT_NAME:-${HERMES_AGENT:-}}"

if [ -z "$AGENT" ] && [ -f "${HOME}/.hermes/agent-name" ]; then
  AGENT=$(cat "${HOME}/.hermes/agent-name" | tr -d '[:space:]')
fi

if [ -z "$AGENT" ]; then
  # Fallback: try hostname → agent registry mapping
  HOST=$(hostname -s 2>/dev/null || hostname 2>/dev/null || echo "unknown")
  case "$HOST" in
    orchestrator-1|moses*)   AGENT="moses" ;;
    worker-1|gisu*)          AGENT="gisu" ;;
    worker-2|joseph*)        AGENT="joseph" ;;
    worker-3|kustos*)        AGENT="kustos" ;;
    worker-5|esther*)        AGENT="esther" ;;
    LAM2|titus*)             AGENT="titus" ;;
    *)                       AGENT="" ;;
  esac
fi

if [ -z "$AGENT" ]; then
  echo "ERROR: Cannot determine agent name. Set AGENT_NAME env var or create ~/.hermes/agent-name" >&2
  exit 1
fi

# ── Config ─────────────────────────────────────────────────
INBOX_URL="${INBOX_API_URL:-https://your-domain.com:13004/api/inbox}"
AUTH=""

# Try loading auth from config file
AUTH_FILE="${HOME}/.hermes/moses-inbox.conf"
if [ -f "$AUTH_FILE" ]; then
  # shellcheck disable=SC1090
  source "$AUTH_FILE" 2>/dev/null || true
fi
# Support multiple auth var names (legacy compatibility)
AUTH="${INBOX_AUTH:-${MOSES_INBOX_AUTH:-}}"

# ── Poll ───────────────────────────────────────────────────
URL="${INBOX_URL}?for=${AGENT}&unread_only=true"

if [ -n "$AUTH" ]; then
  RESPONSE=$(curl -sf --max-time 15 -u "$AUTH" "$URL" 2>/dev/null || echo "")
else
  RESPONSE=$(curl -sf --max-time 15 "$URL" 2>/dev/null || echo "")
fi

if [ -z "$RESPONSE" ]; then
  # Connection failure — silent (let system-alert-watchdog handle it)
  exit 0
fi

# ── Parse and deliver ──────────────────────────────────────
# Use python3 to safely parse JSON
OUTPUT=$(echo "$RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
except (json.JSONDecodeError, Exception):
    sys.exit(0)

# Try both response shapes: {messages: [...]} or direct list
msgs = data.get('messages') or data.get('inbox_msgs') or (data if isinstance(data, list) else [])
if not msgs:
    sys.exit(0)

count = len(msgs)
print(f'📬 {count} new message(s) for {sys.argv[1]}:')
print()
for m in msgs:
    pri = m.get('priority', 'normal')
    icon = '🔴' if pri == 'critical' else ('🟡' if pri == 'urgent' else '📩')
    frm = m.get('from', '?')
    subj = m.get('subject', '(no subject)')
    print(f'  {icon} From: {frm} | {subj}')
    body = m.get('body', '')
    if len(body) > 300:
        body = body[:300] + '...'
    # Indent body for readability
    for line in body.split('\\n'):
        print(f'    {line}')
    print()
" "$AGENT" 2>/dev/null || true)

if [ -n "$OUTPUT" ]; then
  echo "$OUTPUT"
fi
