#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  request-skill-reports.sh — Moses-side: request skill reports
#                              from all registered agents.
#
#  Reads agent-registry.json and sends an inbox message to
#  each agent asking them to run collect-agent-skills.sh.
#
#  Designed to run as a cron job on Moses (e.g. daily at 2am).
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

# ── Config: source inbox credentials ──
INBOX_URL="https://your-domain.com:13004/send"
INBOX_AUTH=""

# Load config — try .env first, fallback to hermes-inbox.conf
CONFIG_FILE=""
if [[ -f "${HOME}/hermes-cortex/.env" ]]; then
    CONFIG_FILE="${HOME}/hermes-cortex/.env"
elif [[ -f "${HOME}/.hermes/hermes-inbox.conf" ]]; then
    CONFIG_FILE="${HOME}/.hermes/hermes-inbox.conf"
fi
if [[ -f "$CONFIG_FILE" ]]; then
    source "$CONFIG_FILE"
    INBOX_URL="${CORTEX_INBOX_URL:-$INBOX_URL}/send"
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

# Parse agents from registry JSON (extract keys at top level or under "agents")
AGENTS=()
if python3 -c "import json; d=json.load(open('$REGISTRY_FILE')); print(list(d.get('agents', d).keys()))" 2>/dev/null | grep -q '^\[.*\]$'; then
  AGENTS=($(python3 -c "
import json
d = json.load(open('$REGISTRY_FILE'))
agents = d.get('agents', d)
for name in agents:
    print(name)
" 2>/dev/null))
fi

if [[ ${#AGENTS[@]} -eq 0 ]]; then
  echo "WARN: No agents found in registry" >&2
  exit 0
fi

# ── Send request to each agent ───────────────────────────────
SENT=0
FAILED=0
REQUEST_ID="skill-req-${TIMESTAMP}"

# Build auth arg for curl
CURL_AUTH=()
[[ -n "$INBOX_AUTH" ]] && CURL_AUTH=(-u "$INBOX_AUTH")

for agent in "${AGENTS[@]}"; do
  # Skip self (Moses)
  [[ "$agent" == "moses" ]] && continue

  BODY="━━━ Skill Report Request — $REQUEST_ID ━━━
Hi all agents,
Please run collect-agent-skills.sh and share your custom skills.
This helps Moses discover and evaluate agent-developed skills
for potential incorporation into the hermes-cortex upstream.

Instructions:
  # Run once to report current skills:
  bash ~/.hermes-cortex/scripts/collect-agent-skills.sh

  # To set up automatic reporting (every 6h, no_agent):
  hermes cron create \
    name=collect-agent-skills \
    every 6h \
    script=~/.hermes-cortex/scripts/collect-agent-skills.sh \
    no_agent=true \
    deliver=local

  Then fill in ~/hermes-cortex/.env with your Moses
  inbox credentials (see .env.example in the repo).

Reply to this message with a summary of any custom skills found,
or with 'none' if you have nothing new to report.

- Moses
"

  if $DRY_RUN; then
    echo "[DRY RUN] Would send to $agent"
    continue
  fi

  if curl -sk -X POST "$INBOX_URL" \
    "${CURL_AUTH[@]}" \
    -d "from=moses" \
    -d "to=$agent" \
    -d "topic=operations" \
    -d "subject=📋 Skill Report Request" \
    -d "body=$BODY" \
    -d "priority=normal" \
    --connect-timeout 5 \
    --max-time 10 \
    -o /dev/null -w "%{http_code}" 2>/dev/null | grep -q "^\(200\|302\|303\)"; then
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
