#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  orch-skill-report-request.sh — Orchestrator-side: request skill reports
#                              from all registered agents.
#
#  Reads agent-registry.json and sends an inbox message to
#  each agent asking them to run agent-collect-skills.sh.
#
#  Designed to run as a cron job on Moses (e.g. weekly).
#  Silent when sent successfully — errors only on failure.
#
#  Usage:
#    bash orch-skill-report-request.sh              # send to all agents
#    bash orch-skill-report-request.sh --dry-run    # show what would send
#    bash orch-skill-report-request.sh --status     # show last request time
# ─────────────────────────────────────────────────────────────
set -euo pipefail

CORTEX_DEPLOY_HOME="${CORTEX_DEPLOY_HOME:-$HOME/.hermes-cortex}"
STATE_DIR="$CORTEX_DEPLOY_HOME/state"
REGISTRY_FILE="$STATE_DIR/agent-registry.json"

# ── Source config ───────────────────────────────────────────
INBOX_URL=""
INBOX_AUTH=""
if [[ -f "${HOME}/hermes-cortex/.env" ]]; then
  set -a; source "${HOME}/hermes-cortex/.env"; set +a
  INBOX_URL="${CORTEX_BUS_URL:-${CORTEX_BUS_FALLBACK_URL:-${CORTEX_INBOX_URL:-}}}"
  INBOX_AUTH="${CORTEX_BASIC_AUTH:-${CORTEX_BUS_AUTH:-${CORTEX_INBOX_AUTH:-}}}"
  BUS_TOKEN="${CORTEX_BUS_TOKEN:-}"
elif [[ -f "${HOME}/.hermes-cortex/cortex-bus.conf" ]]; then
  source "${HOME}/.hermes-cortex/cortex-bus.conf"
  INBOX_URL="${CORTEX_BUS_URL:-${CORTEX_BUS_FALLBACK_URL:-${CORTEX_INBOX_URL:-}}}"
  INBOX_AUTH="${CORTEX_BASIC_AUTH:-${CORTEX_BUS_AUTH:-${CORTEX_INBOX_AUTH:-}}}"
  BUS_TOKEN="${CORTEX_BUS_TOKEN:-}"
fi

LAST_RUN_FILE="$STATE_DIR/last-orch-skill-report-request.txt"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

DRY_RUN=false
STATUS_ONLY=false

parse_args() {
  for arg in "$@"; do
    case "$arg" in
      --dry-run) DRY_RUN=true ;;
      --status)  STATUS_ONLY=true ;;
      --help|-h)
        echo "Usage: bash orch-skill-report-request.sh [--dry-run|--status]"
        echo "  --dry-run    Show what would be sent without sending"
        echo "  --status     Show last request time"
        exit 0
        ;;
    esac
  done
}

parse_args "$@"

if $STATUS_ONLY; then
  if [[ -f "$LAST_RUN_FILE" ]]; then
    echo "Last skill report request: $(cat "$LAST_RUN_FILE")"
  else
    echo "No skill report requests sent yet"
  fi
  exit 0
fi

# ── Read agent registry ──────────────────────────────────────
if [[ ! -f "$REGISTRY_FILE" ]]; then
  echo "ERROR: Agent registry not found at $REGISTRY_FILE" >&2
  exit 1
fi

# Parse agents from registry JSON
AGENTS=()
while IFS= read -r name; do
  AGENTS+=("$name")
done < <(python3 -c "
import json
with open('$REGISTRY_FILE') as f:
    d = json.load(f)
agents = d.get('agents', d)
for name in sorted(agents.keys()):
    print(name)
" 2>/dev/null)

if [[ ${#AGENTS[@]} -eq 0 ]]; then
  echo "WARN: No agents found in registry" >&2
  exit 0
fi

# ── Send request to each agent via inbox JSON API ──────────────
SENT=0
FAILED=0
REQUEST_ID="skill-req-${TIMESTAMP}"

# Skip if inbox URL not configured
if [[ -z "$INBOX_URL" ]]; then
  echo "WARN: CORTEX_BUS_FALLBACK_URL (or CORTEX_INBOX_URL) not set — cannot send requests" >&2
  exit 1
fi

for agent in "${AGENTS[@]}"; do
  # Skip orchestrators + self — skill-report requests are for workers only
  [[ "$agent" == "moses" || "$agent" == "esther" || "$agent" == "$(hostname -s)" ]] && continue

  BODY="━━━ Skill Report Request — $REQUEST_ID ━━━

Hi $agent,

Please run agent-collect-skills.sh and share your custom skills.
This helps the orchestrator discover and evaluate agent-developed skills
for potential incorporation into the hermes-cortex upstream.

Instructions:
  # Run once to report current skills:
  bash ~/hermes-cortex/ops/scripts/manage/agent-collect-skills.sh

  # To set up automatic reporting (every 6h, no_agent):
  hermes cron create \
    name=agent-collect-skills \
    every 6h \
    script=~/.hermes-cortex/scripts/agent-collect-skills.sh \
    no_agent=true \
    deliver=local

  Then fill in ~/hermes-cortex/.env with your bus
  inbox credentials (see install.sh for setup).

Reply to this message with a summary of any custom skills found,
or with 'none' if you have nothing new to report.

- Orchestrator
"

  if $DRY_RUN; then
    echo "[DRY RUN] Would send to $agent"
    continue
  fi

  # Send via PGMQ Agent Bus
  if python3 -c "
import json, urllib.request, base64, sys

bus_url = '$INBOX_URL'.rstrip('/')

# Auth: localhost → Bearer, remote → Basic
host = bus_url.split('://')[-1].split('/')[0].split(':')[0]
if host in ('127.0.0.1', 'localhost', '::1'):
    token = '$BUS_TOKEN'
    header = f'Bearer {token}' if token else ''
else:
    auth_creds = '$INBOX_AUTH'
    if auth_creds and ':' in auth_creds:
        encoded = base64.b64encode(auth_creds.encode()).decode()
        header = f'Basic {encoded}'
    else:
        header = ''

headers = {'Content-Type': 'application/json'}
if header:
    headers['Authorization'] = header

payload = {
    'queue': 'inbox_$agent',
    'message': {
        'from': '$(hostname -s)',
        'subject': '📋 Skill Report Request ($REQUEST_ID)',
        'body': '''$BODY''',
        'topic': 'operations',
        'priority': 'normal',
    },
}

url = bus_url + '/api/pgmq/send'
req = urllib.request.Request(url,
    data=json.dumps(payload).encode('utf-8'),
    headers=headers,
    method='POST')

try:
    resp = urllib.request.urlopen(req, timeout=15)
    sys.exit(0)
except Exception as e:
    print(f'ERROR: {e}', file=sys.stderr)
    sys.exit(1)
" 2>/dev/null; then
    SENT=$((SENT + 1))
  else
    echo "ERROR: Failed to send to $agent" >&2
    FAILED=$((FAILED + 1))
  fi
done

# ── Record last run ──────────────────────────────────────────
echo "$TIMESTAMP ($SENT sent, $FAILED failed, ${#AGENTS[@]} total)" > "$LAST_RUN_FILE"

# ── Summary ──────────────────────────────────────────────────
if [[ $FAILED -eq 0 ]]; then
  echo "Sent skill report requests to $SENT agents"
else
  echo "Sent to $SENT agents, $FAILED failed" >&2
fi
