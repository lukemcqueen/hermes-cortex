#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  post-commit-notify.sh — Notify all agents after a commit
#
#  Runs after every git commit to hermes-cortex. Extracts
#  commit details and sends an inbox broadcast to all agents
#  via the agent inbox API.
#
#  Uses the SAME config loading pattern as inbox-mcp.py:
#    1. CORTEX_INBOX_* environment variables
#    2. ~/.hermes/hermes-inbox.conf (KEY=VALUE format, parsed line-by-line)
#    3. URL fallback chain: primary → fallback → third → localhost:8903
#
#  Silent when:
#    - Repo dir doesn't exist
#    - Inbox server is unreachable (all URLs in chain fail)
#    - State file says we already notified for this commit
#
#  Install as git post-commit hook:
#    cp src/scripts/post-commit-notify.sh ~/.hermes-cortex/hooks/post-commit
#    chmod +x ~/.hermes-cortex/hooks/post-commit
# ─────────────────────────────────────────────────────────────
set -euo pipefail

# ── Paths ──
STATE_FILE="${HOME}/.hermes/state/post-commit-notify"
LOG_FILE="${STATE_FILE}.log"
CONFIG_FILE="${HOME}/.hermes/hermes-inbox.conf"

# ── Helpers ──
log()  { echo "[notify] $*" >> "$LOG_FILE"; }

# ── Step 1: Resolve repo root from cwd (post-commit runs in repo) ──
if ! git rev-parse --git-dir >/dev/null 2>&1; then
  exit 0
fi
REPO_DIR=$(git rev-parse --show-toplevel 2>/dev/null || true)

# ── Step 2: Get commit info ──
SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
SUBJECT=$(git log -1 --format=%s 2>/dev/null || echo "unknown update")
FILES=$(git diff-tree --no-commit-id -r --name-only HEAD 2>/dev/null | head -20 || echo "")
FILE_COUNT=$(echo "$FILES" | grep -c . || true)
AUTHOR=$(git log -1 --format=%an 2>/dev/null || echo "Moses")

# ── Step 3: Dedup — skip if we already notified for this SHA ──
if [ -f "$STATE_FILE" ]; then
  LAST_SHA=$(cat "$STATE_FILE" 2>/dev/null || echo "")
  if [ "$LAST_SHA" = "$SHA" ]; then
    exit 0
  fi
fi

# ── Step 4: Load inbox config (same pattern as inbox-mcp.py) ──
# Priority: env var > config file
# Note: Python-style inline comment stripping (value%%\#*) must use
# CLEAN pattern syntax — no backslash-escaped characters that bash
# misinterprets inside double-quoted patterns with #-containing URLs.
INBOX_URL="${CORTEX_INBOX_URL:-}"
INBOX_FALLBACK_URL="${CORTEX_INBOX_FALLBACK_URL:-}"
INBOX_THIRD_URL="${CORTEX_INBOX_THIRD_URL:-}"
INBOX_AUTH="${CORTEX_INBOX_AUTH:-}"
AGENT_NAME="${AGENT_NAME:-}"

# Parse config file line-by-line using process substitution to avoid subshell
while IFS='=' read -r key value || [ -n "$key" ]; do
    # Trim whitespace from key
    key="${key//[[:space:]]/}"
    # Skip comments and blank lines
    case "$key" in ''|'#'*) continue ;; esac
    # Strip inline comments from value (hash preceded by space)
    value="${value%% #*}"
    # Trim leading/trailing whitespace from value
    value="${value#${value%%[![:space:]]*}}"
    value="${value%${value##*[![:space:]]}}"
    # Strip surrounding quotes (same pattern as inbox-mcp.py)
    value="${value%\'}"; value="${value#\'}"
    value="${value%\"}"; value="${value#\"}"

    case "$key" in
      CORTEX_INBOX_URL|MOSES_INBOX_URL)
        [ -z "$INBOX_URL" ] && INBOX_URL="$value"
        ;;
      CORTEX_INBOX_FALLBACK_URL|MOSES_INBOX_FALLBACK_URL)
        [ -z "$INBOX_FALLBACK_URL" ] && INBOX_FALLBACK_URL="$value"
        ;;
      CORTEX_INBOX_THIRD_URL|MOSES_INBOX_THIRD_URL)
        [ -z "$INBOX_THIRD_URL" ] && INBOX_THIRD_URL="$value"
        ;;
      CORTEX_INBOX_AUTH|MOSES_INBOX_AUTH)
        [ -z "$INBOX_AUTH" ] && INBOX_AUTH="$value"
        ;;
      AGENT_NAME)
        [ -z "$AGENT_NAME" ] && AGENT_NAME="$value"
        ;;
    esac
done < <(grep -E '^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*=' "$CONFIG_FILE" 2>/dev/null || true)

# Resolve AGENT_NAME if still empty
if [ -z "$AGENT_NAME" ]; then
  if [ -n "$INBOX_AUTH" ] && [[ "$INBOX_AUTH" == *:* ]]; then
    AGENT_NAME="${INBOX_AUTH%%:*}"
  else
    AGENT_NAME="${USER:-moses}"
  fi
fi

# ── Step 5: Build URL chain (same as inbox-mcp.py) ──
# Build the send URLs from base URLs (strip trailing /, then add /send)
declare -a URL_CHAIN=()
[ -n "$INBOX_URL" ] && URL_CHAIN+=("${INBOX_URL%/}/send")
[ -n "$INBOX_FALLBACK_URL" ] && URL_CHAIN+=("${INBOX_FALLBACK_URL%/}/send")
[ -n "$INBOX_THIRD_URL" ] && URL_CHAIN+=("${INBOX_THIRD_URL%/}/send")
# Always append the localhost fallback
URL_CHAIN+=("http://127.0.0.1:8903/send")

# ── Step 6: Build auth header ──
CURL_AUTH=()
[ -n "$INBOX_AUTH" ] && CURL_AUTH=(-u "$INBOX_AUTH")

# ── Step 7: Build message body ──
BODY="Committed by ${AUTHOR}
SHA: ${SHA}
Subject: ${SUBJECT}
Files: ${FILE_COUNT} changed

${FILES}"

# ── Step 8: Send broadcast — try each URL in the chain ──
SENT=false
for URL in "${URL_CHAIN[@]}"; do
  if curl -sf -X POST "$URL" "${CURL_AUTH[@]}" \
    -d "from=${AGENT_NAME}" \
    -d "to=all" \
    -d "topic=general" \
    -d "subject=📦 hermes-cortex update: ${SUBJECT}" \
    -d "body=${BODY}" \
    -d "priority=normal" \
    -d "status=read" \
    >/dev/null 2>&1; then
    SENT=true
    log "notified all agents via ${URL} for ${SHA}"
    break
  fi
  log "failed to reach ${URL} for ${SHA}"
done

if [ "$SENT" = false ]; then
  log "all inbox endpoints unreachable for ${SHA}"
  # Exit silently — watchdog pattern
  exit 0
fi

# ── Step 9: Save state ──
echo "$SHA" > "$STATE_FILE"
