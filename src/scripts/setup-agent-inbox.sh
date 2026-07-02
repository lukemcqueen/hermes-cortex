#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  setup-agent-inbox.sh — One-time inbox-watch cron setup
#
#  Run ONCE on any machine to create an inbox-watch cron
#  that polls the agent inbox every 10 minutes.
#
#  Usage:
#    bash setup-agent-inbox.sh                    # auto-detect agent
#    bash setup-agent-inbox.sh --agent titus      # explicit agent
#    bash setup-agent-inbox.sh --dry-run           # preview only
#
#  Requires:
#    - Hermes CLI (bun hermes) with cron capability
#    - curl (for API calls)
#    - ~/.hermes/moses-inbox.conf with INBOX_AUTH (optional)
#
#  After setup, verify:
#    hermes cron list | grep inbox-watch
# ─────────────────────────────────────────────────────────────
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BOLD='\033[1m'; CYAN='\033[0;36m'; RESET='\033[0m'
info()  { echo -e "${GREEN}✓${RESET} $*"; }
warn()  { echo -e "${YELLOW}⚠${RESET} $*"; }

DRY_RUN=false
AGENT=""

# Parse args
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --agent=*) AGENT="${arg#--agent=}" ;;
    --agent) shift; AGENT="$1" ;;
  esac
done

# Resolve agent
if [ -z "$AGENT" ]; then
  AGENT="${AGENT_NAME:-${HERMES_AGENT:-}}"
fi
if [ -z "$AGENT" ] && [ -f "${HOME}/.hermes/agent-name" ]; then
  AGENT=$(tr -d '[:space:]' < "${HOME}/.hermes/agent-name")
fi
if [ -z "$AGENT" ]; then
  HOST=$(hostname -s 2>/dev/null || echo "unknown")
  case "$HOST" in
    orchestrator-1|moses*)   AGENT="moses" ;;
    worker-1|gisu*)          AGENT="gisu" ;;
    worker-2|joseph*)        AGENT="joseph" ;;
    worker-3|kustos*)        AGENT="kustos" ;;
    worker-5|esther*)        AGENT="esther" ;;
    LAM2|titus*)             AGENT="titus" ;;
    *) echo "Cannot detect agent. Use --agent=<name>"; exit 1 ;;
  esac
fi

echo ""
echo -e "${BOLD}━━━ Agent Inbox Watch Setup ━━━${RESET}"
echo -e "  Agent: ${CYAN}${AGENT}${RESET}"
echo ""

# Check prerequisites
if ! command -v curl &>/dev/null; then
  warn "curl not found — install it first"
  exit 1
fi

# Find Hermes CLI
HERMES=""
for cmd in "${HOME}/.bun/bin/hermes" "${HOME}/.local/bin/hermes" "$(command -v hermes 2>/dev/null || true)"; do
  if [ -x "$cmd" ]; then
    HERMES="$cmd"
    break
  fi
done

if [ -z "$HERMES" ]; then
  warn "Hermes CLI not found. Inbox-watch will run as a no_agent script."
  warn "Install Hermes first or create the cron manually:"
  warn "  hermes cron create name=inbox-watch schedule=\"*/10 * * * *\""
  warn "    script=inbox-watch.sh no_agent=true deliver=origin"
  echo ""
fi

# Test inbox connectivity
INBOX_URL="${INBOX_API_URL:-https://your-domain.com:13004}"
echo -n "  Testing inbox connectivity... "
AUTH=""
AUTH_FILE="${HOME}/.hermes/moses-inbox.conf"
if [ -f "$AUTH_FILE" ]; then
  # shellcheck disable=SC1090
  source "$AUTH_FILE" 2>/dev/null || true
  AUTH="${INBOX_AUTH:-${MOSES_INBOX_AUTH:-}}"
fi

if curl -sf --max-time 10 "${INBOX_URL}/health" >/dev/null 2>&1; then
  info "reachable"
else
  warn "cannot reach ${INBOX_URL}/health"
  warn "Check: is the server running? Is this machine connected to the internet?"
  echo ""
fi

# Create the cron job
echo ""
echo -e "  Creating inbox-watch cron for ${CYAN}${AGENT}${RESET}..."

# Save agent name for persistent identity
if [ ! -f "${HOME}/.hermes/agent-name" ]; then
  echo "$AGENT" > "${HOME}/.hermes/agent-name"
  info "Saved agent identity to ~/.hermes/agent-name"
fi

if $DRY_RUN; then
  info "[DRY RUN] Would create cron: inbox-watch (every 10m, no_agent, script=inbox-watch.sh)"
  exit 0
fi

if [ -n "$HERMES" ]; then
  # Check if already exists
  EXISTING=$("$HERMES" cron list 2>/dev/null | grep -c "inbox-watch" || true)
  if [ "$EXISTING" -gt 0 ]; then
    warn "inbox-watch cron already exists — skipping creation"
  else
    "$HERMES" cron create \
      name=inbox-watch \
      schedule="*/10 * * * *" \
      script=inbox-watch.sh \
      no_agent=true \
      deliver=origin 2>&1 | sed 's/^/    /'
    info "inbox-watch cron created (every 10 minutes)"
  fi
else
  warn "Hermes CLI not found — please create the cron manually:"
  echo "    hermes cron create name=inbox-watch schedule=\"*/10 * * * *\" \\"
  echo "      script=inbox-watch.sh no_agent=true deliver=origin"
fi

# Test: run once
echo ""
echo -n "  Testing inbox check... "
TEST_OUTPUT=$(bash "${BASH_SOURCE[0]/setup-agent-inbox.sh/inbox-watch.sh}" 2>/dev/null || true)
if [ -n "$TEST_OUTPUT" ]; then
  echo "found messages"
  echo ""
  echo "$TEST_OUTPUT"
else
  info "no new messages (run again later)"
fi

echo ""
info "Setup complete for ${AGENT}"
echo "  To verify: hermes cron list | grep inbox-watch"
echo "  Messages appear in your session automatically."
echo ""
