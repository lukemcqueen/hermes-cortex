#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  request-skill-reports.sh — Moses-side: request skill reports
#                              from all registered agents.
#
#  Reads agent-registry.json and sends an inbox message to
#  each agent asking them to run collect-agent-skills.sh.
#
#  Designed to run as a cron job on Moses (e.g. weekly).
#  Silent when sent successfully — errors only on failure.
#
#  Usage:
#    bash request-skill-reports.sh              # send to all agents
#    bash request-skill-reports.sh --dry-run    # show what would send
#    bash request-skill-reports.sh --status     # show last request time
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
  INBOX_URL="${CORTEX_INBOX_URL:-}"
  INBOX_AUTH="${CORTEX_INBOX_AUTH:-}"
elif [[ -f "${HOME}/.hermes/hermes-inbox.conf" ]]; then
  source "${HOME}/.hermes/hermes-inbox.conf"
  INBOX_URL="${CORTEX_INBOX_URL:-}"
  INBOX_AUTH="${CORTEX_INBOX_AUTH:-}"
fi

LAST_RUN_FILE="$STATE_DIR/last-skill-report-request.txt"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

DRY_RUN=false
STATUS_ONLY=false

parse_args() {
  for arg in "$@"; do
    case "$arg" in
      --dry-run) DRY_RUN=true ;;
      --status)  STATUS_ONLY=true ;;
      --help|-h)
        echo "Usage: bash request-skill-reports.sh [--dry-run|--status]"
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
  echo "WARN: CORTEX_INBOX_URL not set — cannot send requests" >&2
  exit 1
fi

for agent in "${AGENTS[@]}"; do
  # Skip self (Moses)
  [[ "$agent" == "moses" ]] && continue

  BODY="━━━ Skill Report Request — $REQUEST_ID ━━━

Hi $agent,

Please run collect-agent-skills.sh and share your custom skills.
This helps Moses discover and evaluate agent-developed skills
for potential incorporation into the hermes-cortex upstream.

Instructions:
  # Run once to report current skills:
  bash ~/hermes-cortex/ops/scripts/manage/collect-agent-skills.sh

  # To set up automatic reporting (every 6h, no_agent):
  hermes cron create \
    name=collect-agent-skills \
    every 6h \
    script=~/.hermes-cortex/scripts/collect-agent-skills.sh \
    no_agent=true \
    deliver=local

  Then fill in ~/hermes-cortex/.env with your Moses
  inbox credentials (see install.sh for setup).

Reply to this message with a summary of any custom skills found,
or with 'none' if you have nothing new to report.

- Moses
"

  if $DRY_RUN; then
    echo "[DRY RUN] Would send to $agent"
    continue
  fi

  # Send via JSON POST to inbox API
  if python3 -c "
import json, urllib.request, base64, sys

payload = {
    'from': 'moses',
    'to': '$agent',
    'subject': '📋 Skill Report Request ($REQUEST_ID)',
    'body': '''$BODY''',
    'topic': 'operations',
    'priority': 'normal',
}

url = '$INBOX_URL'.rstrip('/') + '/api/send'
req = urllib.request.Request(url,
    data=json.dumps(payload).encode('utf-8'),
    headers={'Content-Type': 'application/json'},
    method='POST')

auth = '$INBOX_AUTH'
if auth and ':' in auth:
    encoded = base64.b64encode(auth.encode()).decode()
    req.add_header('Authorization', f'Basic {encoded}')

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
