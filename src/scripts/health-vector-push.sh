#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# health-vector-push.sh — Push health vector to Moses inbox
#
# Designed for client-only agents (Titus/macOS) that cannot
# host an HTTP health endpoint. Runs on a cron/launchd schedule
# and POSTs the current health vector to Moses' inbox API.
#
# Usage:
#   ./health-vector-push.sh
#
# Requires:
#   - ~/health-vector.py or hermes-cortex/src/scripts/health-vector.py
#     (provide the path via HEALTH_VECTOR env var if nonstandard)
#   - MOSES_INBOX_URL and MOSES_INBOX_AUTH environment variables,
#     or ~/.hermes/moses-inbox.conf
#
# Returns silently on success; errors go to stderr.
# ──────────────────────────────────────────────────────────────
set -euo pipefail

# ── Config ──
HEALTH_VECTOR="${HEALTH_VECTOR:-$HOME/health-vector.py}"
CONF_FILE="${HOME}/.hermes/moses-inbox.conf"

# ── Resolve inbox URL + auth ──
INBOX_URL="${MOSES_INBOX_URL:-}"
INBOX_AUTH="${MOSES_INBOX_AUTH:-}"

if [[ -z "$INBOX_URL" && -f "$CONF_FILE" ]]; then
    while IFS='=' read -r key value; do
        key="${key// /}"
        value="${value//\"/}"
        value="${value//\'/}"
        case "$key" in
            MOSES_INBOX_URL) INBOX_URL="$value" ;;
            MOSES_INBOX_AUTH) INBOX_AUTH="$value" ;;
        esac
    done < "$CONF_FILE"
fi

if [[ -z "$INBOX_URL" || -z "$INBOX_AUTH" ]]; then
    echo "ERROR: MOSES_INBOX_URL and MOSES_INBOX_AUTH required" >&2
    exit 1
fi

# ── Determine hostname ──
HOSTNAME="${HOSTNAME:-$(hostname -s 2>/dev/null || hostname)}"

# ── Find health-vector.py ──
HV="$HEALTH_VECTOR"
if [[ ! -f "$HV" ]]; then
    # Try common locations
    for candidate in \
        "$HOME/hermes-cortex/src/scripts/health-vector.py" \
        "$HOME/.hermes/scripts/health-vector.py" \
        "$HOME/health-vector.py"; do
        if [[ -f "$candidate" ]]; then
            HV="$candidate"
            break
        fi
    done
fi

if [[ ! -f "$HV" ]]; then
    echo "ERROR: health-vector.py not found" >&2
    exit 1
fi

# ── Generate health vector ──
VECTOR_JSON=$(python3 "$HV" 2>/dev/null) || {
    echo "ERROR: health-vector.py failed" >&2
    exit 1
}

# ── Push to inbox ──
curl -sf -u "$INBOX_AUTH" \
    -d "from=${AGENT_NAME:-$(whoami)}" \
    -d "to=moses" \
    -d "topic=health" \
    -d "subject=health-vector" \
    -d "body=$VECTOR_JSON" \
    "$INBOX_URL/send" >/dev/null 2>&1 || {
    echo "ERROR: failed to push health vector to inbox" >&2
    exit 1
}

# Silent exit = success (watchdog pattern)