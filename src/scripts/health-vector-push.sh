#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# health-vector-push.sh — Push health vector to Moses inbox
#
# Compact 8-bit health vector POSTed to Moses every 10 min.
# Silent on success — no_agent watchdog stays quiet.
# Errors → /tmp/com.hermes.health-push.err
#
# Bit layout (Titus — peer agent):
#   0: ollama     — LLM inference server
#   1: gbrain     — Knowledge brain service
#   2: gateway    — Hermes agent gateway
#   3: inbox      — Agent inbox API (8903 reachable)
#   4-6: unused  — always 0
#   7: heartbeat  — always 1 (agent is alive)
#
# Usage:
#   AGENT_NAME=titus bash health-vector-push.sh
# ─────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${HOME}/.hermes/moses-inbox.conf"
ERROR_LOG="/tmp/com.hermes.health-push.err"

# ── Load config ────────────────────────────────────────────
if [[ -f "$CONFIG_FILE" ]]; then
    . "$CONFIG_FILE"
fi

: "${MOSES_INBOX_URL:=}"
: "${MOSES_INBOX_AUTH:=}"
: "${AGENT_NAME:=titus}"

if [[ -z "$MOSES_INBOX_URL" ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] MOSES_INBOX_URL not set" >> "$ERROR_LOG"
    exit 1
fi

# Derive API endpoint from the inbox URL (strip /send → /api/send)
API_URL="${MOSES_INBOX_URL%/send}/api/send"

# ── Health checks ──────────────────────────────────────────
OLLAMA=0
GBRAIN=0
GATEWAY=0
INBOX=0
ALWAYS_1=1

# ollama
if command -v curl &>/dev/null; then
    timeout 5 curl -sf http://localhost:11434/api/tags -o /dev/null 2>/dev/null && OLLAMA=1
fi

# gbrain sync daemon
if command -v pgrep &>/dev/null; then
    pgrep -f gbrain >/dev/null 2>&1 && GBRAIN=1
fi

# Hermes gateway
if command -v pgrep &>/dev/null; then
    pgrep -f 'hermes.*gateway' >/dev/null 2>&1 && GATEWAY=1
fi

# Agent inbox (port 8903 reachable)
if command -v curl &>/dev/null; then
    timeout 3 curl -sf http://127.0.0.1:8903/api/inbox -o /dev/null 2>/dev/null && INBOX=1
fi

HEALTH_VECTOR="[$OLLAMA,$GBRAIN,$GATEWAY,$INBOX,0,0,0,$ALWAYS_1]"

# ── Build inbox message ────────────────────────────────────
TIMESTAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
BODY="health vector: $HEALTH_VECTOR"
PAYLOAD="{\"from\":\"$AGENT_NAME\",\"subject\":\"health\",\"body\":\"$BODY\"}"

# ── POST to inbox API ──────────────────────────────────────
RESPONSE_FILE=$(mktemp /tmp/health-push-XXXXXX)
trap 'rm -f "$RESPONSE_FILE"' EXIT

CURL_ARGS=(-s -X POST -H "Content-Type: application/json" -d "$PAYLOAD" -w "\n%{http_code}" --max-time 10)
if [[ -n "$MOSES_INBOX_AUTH" ]]; then
    CURL_ARGS=(-u "$MOSES_INBOX_AUTH" "${CURL_ARGS[@]}")
fi

curl "${CURL_ARGS[@]}" "$API_URL" > "$RESPONSE_FILE" 2>/dev/null || {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] curl failed" >> "$ERROR_LOG"
    exit 1
}

HTTP_CODE=$(tail -1 "$RESPONSE_FILE")

case "$HTTP_CODE" in
    2*) ;;
    *)
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] HTTP $HTTP_CODE to $API_URL" >> "$ERROR_LOG"
        exit 1
        ;;
esac

# Silent success
exit 0