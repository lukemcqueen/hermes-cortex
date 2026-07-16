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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"

# Load config — try .env first, fallback to hermes-inbox.conf
CONFIG_FILE=""
if [[ -f "${HOME}/hermes-cortex/.env" ]]; then
    CONFIG_FILE="${HOME}/hermes-cortex/.env"
elif [[ -f "${HOME}/.hermes-cortex/hermes-inbox.conf" ]]; then
    CONFIG_FILE="${HOME}/.hermes-cortex/hermes-inbox.conf"
fi
ERROR_LOG="/tmp/com.hermes.health-push.err"

# ── Load failure state helpers ───────────────────────────────────
STATE_SCRIPT="${SCRIPT_DIR}/cron-failure-state.sh"
if [[ -f "$STATE_SCRIPT" ]]; then
    source "$STATE_SCRIPT"
else
    # Fallback when running from repo vs deployed
    STATE_SCRIPT2="${HOME}/.hermes-cortex/scripts/cron-failure-state.sh"
    [[ -f "$STATE_SCRIPT2" ]] && source "$STATE_SCRIPT2"
fi
CRON_STATE_SCRIPT="health-vector-push"

# ── Load config ────────────────────────────────────────────
if [[ -f "$CONFIG_FILE" ]]; then
    . "$CONFIG_FILE"
fi

: "${CORTEX_BUS_FALLBACK_URL:=${CORTEX_INBOX_URL:=}}"
: "${CORTEX_BUS_FALLBACK_AUTH:=${CORTEX_INBOX_AUTH:=}}"
: "${AGENT_NAME:=titus}"

if [[ -z "$CORTEX_BUS_FALLBACK_URL" ]]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] CORTEX_BUS_FALLBACK_URL not set" >> "$ERROR_LOG"
    exit 1
fi

# Use /api/send (JSON) endpoint — strip trailing /send if present, append /api/send
API_URL="${CORTEX_BUS_FALLBACK_URL}"
API_URL="${API_URL%/send}"
API_URL="${API_URL%/api/send}"
API_URL="${API_URL}/api/send"

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
command -v pgrep &>/dev/null && pgrep nginx >/dev/null 2>&1 && SVC_OK=1
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
    pgrep nginx >/dev/null 2>&1 || V_NGINX=-1
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

# ── POST to inbox API with fallback (primary remote → local agent inbox) ──
RESPONSE_FILE=$(mktemp /tmp/health-push-XXXXXX)
trap 'rm -f "$RESPONSE_FILE"' EXIT

CURL_ARGS=(-s -X POST -H "Content-Type: application/json" -d "$PAYLOAD" -w "\n%{http_code}" --max-time 10)
if [[ -n "$CORTEX_BUS_FALLBACK_AUTH" ]]; then
    CURL_ARGS=(-u "$CORTEX_BUS_FALLBACK_AUTH" "${CURL_ARGS[@]}")
fi

FALLBACK_URLS=(
    "http://127.0.0.1:8903/api/send"
    "http://127.0.0.1:8904/api/send"
)

PUSH_OK=0
for attempt_url in "$API_URL" "${FALLBACK_URLS[@]}"; do
    CURL_ATTEMPT_ARGS=("${CURL_ARGS[@]}")
    if [[ "$attempt_url" != "$API_URL" ]]; then
        # Local fallbacks — no auth needed
        CURL_ATTEMPT_ARGS=(-s -X POST -H "Content-Type: application/json" -d "$PAYLOAD" -w "\n%{http_code}" --max-time 10)
    fi

    curl "${CURL_ATTEMPT_ARGS[@]}" "$attempt_url" > "$RESPONSE_FILE" 2>/dev/null && {
        HTTP_CODE=$(tail -1 "$RESPONSE_FILE")
        case "$HTTP_CODE" in
            2*)
                PUSH_OK=1
                break
                ;;
            *)
                ERR_MSG="[$(date '+%Y-%m-%d %H:%M:%S')] HTTP $HTTP_CODE to $attempt_url"
                ;;
        esac
    } || {
        ERR_MSG="[$(date '+%Y-%m-%d %H:%M:%S')] curl failed to $attempt_url"
    }
done

if [[ "$PUSH_OK" -eq 0 ]]; then
    ERR_HASH=$(cron_error_hash "health-vector-push: push failed (all endpoints)")
    if cron_should_report "$CRON_STATE_SCRIPT" "$ERR_HASH" 30; then
        echo "$ERR_MSG" >> "$ERROR_LOG"
        cron_record_failure "$CRON_STATE_SCRIPT" "$ERR_HASH" 30
        exit 1
    fi
    exit 0
fi

# ── Record success ─────────────────────────────────────────
cron_record_success "$CRON_STATE_SCRIPT"

# Silent success
exit 0