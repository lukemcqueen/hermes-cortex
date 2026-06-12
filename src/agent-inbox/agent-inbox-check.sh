#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  DEPRECATED — The agent inbox is now MCP-only.
#  Use inbox_send / inbox_read / inbox_watch MCP tools instead.
#  This script kept for legacy compatibility but no longer
#  works for external access.
# ─────────────────────────────────────────────────────────────
# Agent Inbox Check — silent when empty, output when messages arrive
# Usage:
#   agent-inbox-check.sh
#   agent-inbox-check.sh --mark-read   # mark messages as read after printing
#
# Config: set these in ~/.hermes/agent-inbox.conf or pass via env vars
#   AGENT_INBOX_URL   (default: https://your-domain.com:13004)
#   AGENT_INBOX_USER
#   AGENT_INBOX_PASS

set -euo pipefail

CONFIG="${HOME}/.hermes/agent-inbox.conf"
[ -f "$CONFIG" ] && source "$CONFIG"

URL="${AGENT_INBOX_URL:-https://your-domain.com:13004}"
USER="${AGENT_INBOX_USER:-}"
PASS="${AGENT_INBOX_PASS:-}"

if [ -z "$USER" ] || [ -z "$PASS" ]; then
  echo "ERROR: AGENT_INBOX_USER and AGENT_INBOX_PASS must be set" >&2
  exit 1
fi

# Fetch unread messages — silent on failure (network down, etc.)
DATA=$(curl -sk --connect-timeout 10 -u "${USER}:${PASS}" "${URL}/api/inbox?unread_only=true" 2>/dev/null || true)
[ -z "$DATA" ] && exit 0

COUNT=$(echo "$DATA" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('unread',0))" 2>/dev/null || echo "0")

[ "$COUNT" -eq 0 ] && exit 0  # Silent exit — no news is good news

echo "━━━ Agent Inbox — ${COUNT} unread ━━━"
python3 -c "
import sys, json
d = json.loads(sys.argv[1])
for m in d.get('messages', []):
    print()
    print('  From: %s  |  %s  |  %s' % (m['from'], m['topic'], m['timestamp'][:19]))
    print('  Re:  %s' % m['subject'])
    print('  ' + chr(0x2501) * 52)
    for line in m['body'].strip().split('\n'):
        print('  %s' % line.strip())
    print('  (id: %s)' % m['filename'])
" "$DATA"

# Mark as read if requested
if [ "${1:-}" = "--mark-read" ]; then
  echo "$DATA" | python3 -c "
import sys, json, subprocess
d = json.load(sys.stdin)
for m in d.get('messages', []):
    subprocess.run(['curl', '-sk', '--location-trusted', '--connect-timeout', '10',
        '-u', '${USER}:${PASS}',
        '${URL}/read/' + m['filename'] + '?for=${USER}'],
        capture_output=True, timeout=10)
" 2>/dev/null
fi
