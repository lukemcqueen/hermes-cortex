#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  bus-watch.sh — Poll Agent Bus via external API
#
#  Designed for no_agent cron (watchdog pattern).
#  Silent (exit 0, no output) when nothing new.
#  Outputs formatted message summaries when new messages found.
#
#  Reads agent identity from:
#    1. AGENT_NAME env var (set by Hermes session)
#    2. ~/.hermes-cortex/agent.env (canonical per-host identity)
#    NEVER hostname — a machine name is not an agent identity (Luke
#    directive 2026-08-14). Missing identity fails loudly.
#
#  Usage as no_agent cron (run once on any machine with curl):
#    hermes cron create name=bus-watch schedule="*/10 * * * *" \
#      script=bus-watch.sh no_agent=true deliver=origin
#
#  Or as context_source for an LLM cron:
#    hermes cron create name=cortex-bus schedule="0 */2 * * *" \
#      prompt="Process bus messages..." context_from=<job_id>
#
#  Auth: Uses ~/.hermes-cortex/cortex-bus.conf if present (BASIC auth).
#  Or set INBOX_AUTH env var to "user:pass".
# ─────────────────────────────────────────────────────────────
set -euo pipefail

# ── Resolve agent identity ────────────────────────────────
AGENT="${AGENT_NAME:-${HERMES_AGENT:-}}"

if [ -z "$AGENT" ] && [ -f "${HOME}/.hermes-cortex/agent.env" ]; then
  AGENT=$(grep -E '^AGENT_NAME=' "${HOME}/.hermes-cortex/agent.env" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'" | tr -d '[:space:]')
fi

if [ -z "$AGENT" ]; then
  echo "ERROR: Cannot determine agent name. Set AGENT_NAME env var or create ~/.hermes-cortex/agent.env (AGENT_NAME=<your-agent>)" >&2
  exit 1
fi

# ── Config ─────────────────────────────────────────────────
# Bus API base URL (PGMQ endpoints: /api/pgmq/queues, /api/pgmq/read)
BUS_URL="${CORTEX_BUS_URL:-https://your-domain.com:13004}"
AUTH=""

# Try loading auth from config file — check new name first, fall back to old
AUTH_FILE="${HOME}/.hermes-cortex/cortex-bus.conf"
if [ ! -f "$AUTH_FILE" ]; then
  AUTH_FILE="${HOME}/.hermes-cortex/moses-inbox.conf"
  if [ -f "$AUTH_FILE" ]; then
    echo "[deprecated] Rename ~/.hermes/moses-inbox.conf → ~/.hermes-cortex/cortex-bus.conf" >&2
  fi
fi
if [ -f "$AUTH_FILE" ]; then
  # shellcheck disable=SC1090
  source "$AUTH_FILE" 2>/dev/null || true
fi
# Support multiple auth var names (CORTEX_ preferred, old MOSES_ fallback)
AUTH="${INBOX_AUTH:-${CORTEX_INBOX_AUTH:-${MOSES_INBOX_AUTH:-}}}"

# ── Poll queue depth via bus API ────────────────────────────
URL="${BUS_URL}/api/pgmq/queues"

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
# Parse queue depths from bus API (/api/pgmq/queues)
OUTPUT=$(echo "$RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
except (json.JSONDecodeError, Exception):
    sys.exit(0)

agent = sys.argv[1] if len(sys.argv) > 1 else '?'
queues = data.get('queues', [])
inbox_queue = next((q for q in queues if q.get('name') == f'inbox_{agent}'), None)
if not inbox_queue:
    sys.exit(0)

depth = inbox_queue.get('depth', 0)
if depth == 0:
    sys.exit(0)

print(f'📬 {depth} unread message(s) in inbox_{agent}')
print(f'   (retrieve via bus_read or agent-message-handler)')
" "$AGENT" 2>/dev/null || true)

if [ -n "$OUTPUT" ]; then
  echo "$OUTPUT"
fi
