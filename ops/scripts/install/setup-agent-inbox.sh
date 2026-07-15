#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  setup-agent-inbox.sh — Full inbox pipeline setup
#
#  Run ONCE on any machine to create the complete inbox
#  monitoring pipeline:
#    1. inbox-watch (no_agent, every 10m) — detects messages
#    2. agent-inbox  (LLM-driven, every 30m) — reads + acts
#
#  Usage:
#    bash setup-agent-inbox.sh              # auto-detect agent
#    bash setup-agent-inbox.sh --agent titus
#    bash setup-agent-inbox.sh --dry-run
#
#  Requires:
#    - Hermes CLI (hermes cron create)
#    - ~/.hermes-cortex/hermes-inbox.conf with CORTEX_INBOX_AUTH
#    - curl (for API calls)
#    - Pulled hermes-cortex (for inbox-watch.sh)
#
#  After setup:
#    hermes cron list | grep -E 'inbox-watch|agent-inbox'
# ─────────────────────────────────────────────────────────────
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BOLD='\033[1m'; CYAN='\033[0;36m'; RESET='\033[0m'
info()  { echo -e "${GREEN}✓${RESET} $*"; }
warn()  { echo -e "${YELLOW}⚠${RESET} $*"; }

DRY_RUN=false
AGENT=""

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --agent=*) AGENT="${arg#--agent=}" ;;
    --agent) shift; AGENT="$1" ;;
  esac
done

# ── Resolve agent identity ──────────────────────────────
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
    *) echo "Cannot detect agent. Use --agent=<name> or set AGENT_NAME."; exit 1 ;;
  esac
fi

INBOX_URL="${CORTEX_INBOX_URL:-https://your-domain.com:13004}"

echo ""
echo -e "${BOLD}━━━ Agent Inbox Pipeline Setup ━━━${RESET}"
echo -e "  Agent: ${CYAN}${AGENT}${RESET}"
echo ""

# ── Prerequisites ───────────────────────────────────────────
if ! command -v curl &>/dev/null; then
  warn "curl not found — install it first"; exit 1
fi

# Check Hermes CLI
HERMES_CMD=""
for cmd in "${HOME}/.bun/bin/hermes" "${HOME}/.local/bin/hermes" "$(command -v hermes 2>/dev/null || true)"; do
  [ -x "$cmd" ] && HERMES_CMD="$cmd" && break
done

if [ -z "$HERMES_CMD" ]; then
  warn "Hermes CLI not found. Cannot create crons automatically."
  warn "Install Hermes first, then re-run this script."
  exit 1
fi

# Check inbox-watch.sh exists
WATCH_SCRIPT="${HOME}/.hermes-cortex/scripts/inbox-watch.sh"
if [ ! -f "$WATCH_SCRIPT" ]; then
  warn "inbox-watch.sh not found — running cortex-update.sh..."
  if [ -f "${HOME}/hermes-cortex/ops/scripts/cortex-update.sh" ]; then
    bash "${HOME}/hermes-cortex/ops/scripts/cortex-update.sh" --force-all 2>/dev/null || true
  fi
  if [ ! -f "$WATCH_SCRIPT" ]; then
    warn "Still not found. Run: cd ~/hermes-cortex && git pull && bash ops/scripts/cortex-update.sh --force-all"
    exit 1
  fi
fi

# Check auth config
AUTH_FILE="${HOME}/.hermes-cortex/hermes-inbox.conf"
AUTH_OK=false
if [ -f "$AUTH_FILE" ]; then
  # shellcheck disable=SC1090
  source "$AUTH_FILE" 2>/dev/null || true
  TEST_AUTH="${CORTEX_INBOX_AUTH:-}"
  if [ -n "$TEST_AUTH" ]; then
    AUTH_OK=true
  fi
fi
if ! $AUTH_OK; then
  warn "No auth credentials found in ~/.hermes-cortex/hermes-inbox.conf"
  warn "Create it with:"
  echo "    CORTEX_INBOX_URL=\"https://your-domain.com:13004\""
  echo "    CORTEX_INBOX_AUTH=\"user:pass\""
  echo "    AGENT_NAME=\"${AGENT}\""
fi

# ── Test connectivity ───────────────────────────────────────
echo -n "  Testing inbox API connectivity... "
if $AUTH_OK; then
  API_OK=$(curl -sf --max-time 10 \
    -u "$CORTEX_INBOX_AUTH" \
    "${INBOX_URL}/api/inbox?for=${AGENT}&limit=1" \
    >/dev/null 2>&1 && echo "true" || echo "false")
else
  API_OK=$(curl -sf --max-time 10 "${INBOX_URL}/health" >/dev/null 2>&1 && echo "true" || echo "false")
fi

if [ "$API_OK" = "true" ]; then
  info "reachable"
else
  warn "cannot reach ${INBOX_URL}/api/inbox"
  warn "Check connectivity and credentials."
fi

# ── Save agent identity ─────────────────────────────────────
if [ ! -f "${HOME}/.hermes/agent-name" ]; then
  mkdir -p "${HOME}/.hermes"
  echo "$AGENT" > "${HOME}/.hermes/agent-name"
  info "Saved agent identity to ~/.hermes/agent-name"
fi

if $DRY_RUN; then
  echo ""
  echo -e "${YELLOW}[DRY RUN] Would create:${RESET}"
  echo "  1. inbox-watch  (no_agent, every 10m, deliver=local)"
  echo "  2. agent-inbox  (LLM, every 30m, context_from=inbox-watch)"
  echo ""
  exit 0
fi

# ── Step 1: Create inbox-watch cron ─────────────────────────
echo ""
echo -e "  ${BOLD}Step 1/2: Creating inbox-watch detector...${RESET}"
EXISTING=$("$HERMES_CMD" cron list 2>/dev/null | grep -c "inbox-watch" || true)
if [ "$EXISTING" -gt 0 ]; then
  warn "inbox-watch cron already exists — skipping"
else
  "$HERMES_CMD" cron create \
    name=inbox-watch \
    schedule="*/10 * * * *" \
    script=inbox-watch.sh \
    no_agent=true \
    deliver=local 2>&1 | sed 's/^/    /'
  info "inbox-watch cron created (every 10 minutes)"
fi

# ── Get inbox-watch job ID ──────────────────────────────────
WATCH_JOB_ID=$("$HERMES_CMD" cron list 2>/dev/null | grep "inbox-watch" | head -1 | awk '{print $1}')
if [ -z "$WATCH_JOB_ID" ]; then
  warn "Could not find inbox-watch job ID — will need manual fix"
  WATCH_JOB_ID="REPLACE_ME"
fi

# ── Step 2: Create agent-inbox processor cron ───────────────
echo ""
echo -e "  ${BOLD}Step 2/2: Creating agent-inbox processor...${RESET}"
EXISTING=$("$HERMES_CMD" cron list 2>/dev/null | grep -c "agent-inbox" || true)
if [ "$EXISTING" -gt 0 ]; then
  warn "agent-inbox cron already exists — skipping"
else
  # Build prompt with agent-specific values substituted
  PROMPT="Process inbox messages for ${AGENT} using the Inbox Message Decision Framework.
Read the context from inbox-watch (lists unread message subjects and senders).

For each unread message:

1. Fetch the full message via the inbox API:
   \`\`\`bash
   source ~/.hermes-cortex/hermes-inbox.conf
   curl -s -u \"\$CORTEX_INBOX_AUTH\" \
     \"${INBOX_URL}/api/inbox?for=${AGENT}&unread_only=true\"
   \`\`\`

2. Apply the Decision Framework:
   - Priority: critical→act now, urgent→this tick, normal→this tick
   - Can you fix it yourself? → AUTO-ACT using terminal/web/file tools. Fix it, verify it, report it.
   - Needs another agent? → Use curl POST to /api/send to delegate, CC the user
   - Needs human judgment? → Output a clear escalation summary with options
   - FYI only? → Acknowledge and move on

3. Report what you did in a clear summary.

IMPORTANT: Use https://your-domain.com:13004 for API calls (not localhost).
The inbox MCP tool does not work from this machine."

  "$HERMES_CMD" cron create \
    name=agent-inbox \
    schedule="*/30 * * * *" \
    context_from="${WATCH_JOB_ID}" \
    enabled_toolsets="web,terminal,file" \
    prompt="${PROMPT}" \
    deliver=origin 2>&1 | sed 's/^/    /'
  info "agent-inbox cron created (every 30 minutes, reads context from inbox-watch)"
fi

# ── Test ────────────────────────────────────────────────────
echo ""
echo -n "  Testing inbox-watch... "
TEST_OUTPUT=$(AGENT_NAME="$AGENT" bash "$WATCH_SCRIPT" 2>/dev/null || true)
if [ -n "$TEST_OUTPUT" ]; then
  echo "found messages"
  echo ""
  echo "$TEST_OUTPUT" | head -12
  echo "  (...)"
else
  info "no new messages (check back later)"
fi

# ── Summary ─────────────────────────────────────────────────
echo ""
echo -e "${GREEN}━━━ Pipeline setup complete for ${AGENT} ━━━${RESET}"
echo "  Detector:  inbox-watch  (every 10m, silent unless new)"
echo "  Processor: agent-inbox (every 30m, reads + acts)"
echo ""
echo "  Verify with:"
echo "    hermes cron list | grep -E 'inbox-watch|agent-inbox'"
echo ""
