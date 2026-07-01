#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# health-vector-push.sh — Push 9-item health vector to Moses inbox
#
# Compact 9-bit health vector POSTed to Moses every 10 min.
# Silent on success — no_agent watchdog stays quiet.
# Errors → /tmp/com.hermes.health-push.err
#
# Vector layout (from agent-registry.json):
#   [0] resources           — system resources OK
#   [1] services            — core services running
#   [2] no_errored_crons    — no cron jobs with recent errors
#   [3] no_stale_crons      — no cron jobs gone stale
#   [4] nginx               — nginx process running
#   [5] ollama              — Ollama running
#   [6] gbrain              — gbrain running
#   [7] disk_ok             — disk space sufficient
#   [8] gbrain_sources_ok   — gbrain source dirs exist
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

# Derive API endpoint from the inbox URL
API_URL="${MOSES_INBOX_URL%/send}/api/send"

# ── Vector: default all-1 healthy ──────────────────────────
# Each check sets its slot to 0=n/a, -1=fail, or leaves 1=pass
V_RESOURCES=1     # [0]
V_SERVICES=1      # [1]
V_NO_ERR_CRONS=1  # [2]
V_NO_STALE=1      # [3]
V_NGINX=1         # [4]
V_OLLAMA=1        # [5]
V_GBRAIN=1        # [6]
V_DISK_OK=1       # [7]
V_GBRAIN_SRC=1    # [8]

# [0] resources — CPU load < 4x cores
if command -v sysctl &>/dev/null; then
    LOAD=$(sysctl -n vm.loadavg 2>/dev/null | awk '{print $2}')
    if [[ -n "$LOAD" ]]; then
        LOAD_INT=${LOAD%.*}
        [[ "$LOAD_INT" -gt 40 ]] && V_RESOURCES=-1  # 4×10 cores = 40
    fi
fi

# [1] services — at least one core service running
SVC_OK=0
command -v pgrep &>/dev/null && pgrep -x ollama >/dev/null 2>&1 && SVC_OK=1
command -v pgrep &>/dev/null && pgrep -x nginx >/dev/null 2>&1 && SVC_OK=1
command -v pgrep &>/dev/null && pgrep -f gbrain >/dev/null 2>&1 && SVC_OK=1
[[ "$SVC_OK" -eq 0 ]] && V_SERVICES=-1

# [2] no_errored_crons — check push error log
if [[ -s "$ERROR_LOG" ]]; then
    V_NO_ERR_CRONS=-1
fi

# [3] no_stale_crons — best-effort (delegated to orchestrator)
# Currently always 1; actual stale detection is Moses' job.

# [4] nginx
if command -v pgrep &>/dev/null; then
    pgrep -x nginx >/dev/null 2>&1 || V_NGINX=-1
else
    V_NGINX=0
fi

# [5] ollama
if command -v curl &>/dev/null; then
    timeout 5 curl -sf http://localhost:11434/api/tags -o /dev/null 2>/dev/null || V_OLLAMA=-1
else
    V_OLLAMA=0
fi

# [6] gbrain
if command -v pgrep &>/dev/null; then
    pgrep -f gbrain >/dev/null 2>&1 || V_GBRAIN=-1
else
    V_GBRAIN=0
fi

# [7] disk_ok — root partition < 90% used
DF_OUTPUT=$(df / 2>/dev/null | tail -1)
if [[ -n "$DF_OUTPUT" ]]; then
    PCT=$(echo "$DF_OUTPUT" | awk '{print $5}' | tr -d '%')
    if [[ -n "$PCT" ]] && [[ "$PCT" -ge 90 ]]; then
        V_DISK_OK=-1
    fi
fi

# [8] gbrain_sources_ok — ~/brain has at least one non-empty subdirectory
BRAIN_HOME="${HOME}/brain"
if [[ -d "$BRAIN_HOME" ]]; then
    HAS_SOURCE=0
    for d in "$BRAIN_HOME"/*/; do
        if [[ -d "$d" ]] && [[ -n "$(ls -A "$d" 2>/dev/null)" ]]; then
            HAS_SOURCE=1
            break
        fi
    done
    [[ "$HAS_SOURCE" -eq 0 ]] && V_GBRAIN_SRC=-1
else
    V_GBRAIN_SRC=-1
fi

# ── Build inbox message (JSON format Moses can parse) ──────
NOW_TS=$(date +%s)
HNAME='t'
# Build health vector payload via Python for proper JSON encoding
PAYLOAD=$(python3 -c "
import json
body = json.dumps({'v': [$V_RESOURCES,$V_SERVICES,$V_NO_ERR_CRONS,$V_NO_STALE,$V_NGINX,$V_OLLAMA,$V_GBRAIN,$V_DISK_OK,$V_GBRAIN_SRC], 'h': '$HNAME', 't': $NOW_TS})
msg = {'from': '$AGENT_NAME', 'subject': 'health', 'body': body}
print(json.dumps(msg))
" 2>/dev/null || echo '{}')

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