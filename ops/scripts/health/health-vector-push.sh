#!/usr/bin/env bash
# health-vector-push.sh — Push health vector to Moses via Agent Bus.
# Runs via launchd on client-only agents (every 10m — see
# docs/templates/com.hermes.health-push.plist). Silent when healthy.
set -euo pipefail

# ── Config ──
HOME="${HOME:-/home/$(whoami)}"
CONFIG_FILE="$HOME/.hermes-cortex/cortex-bus.conf"
ENV_FILE="$HOME/hermes-cortex/.env"
ERROR_LOG="$HOME/.hermes-cortex/logs/health-push-errors.log"
mkdir -p "$(dirname "$ERROR_LOG")"

# ── Load config from env, then config files ──
load_var() {
  local key="$1"
  local val="${!key:-}"
  if [[ -n "$val" ]]; then echo "$val"; return; fi
  for f in "$CONFIG_FILE" "$ENV_FILE"; do
    [[ -f "$f" ]] || continue
    local line
    while IFS= read -r line; do
      line="${line%%#*}"  # strip comments
      [[ "$line" == "$key="* ]] || continue
      echo "${line#*=}" | tr -d "'\""
      return
    done < "$f"
  done
  echo ""
}

CORTEX_BUS_URL="$(load_var CORTEX_BUS_URL)"
CORTEX_BUS_FALLBACK_URL="$(load_var CORTEX_BUS_FALLBACK_URL)"
CORTEX_BUS_TOKEN="$(load_var CORTEX_BUS_TOKEN)"
CORTEX_BASIC_AUTH="$(load_var CORTEX_BASIC_AUTH)"
AGENT_NAME="${AGENT_NAME:-$(load_var AGENT_NAME)}"
# NEVER fall back to a hardcoded/other agent or hostname — a missing
# identity must fail loudly, not impersonate another agent (Luke
# directive 2026-08-14).
if [[ -z "$AGENT_NAME" || "$AGENT_NAME" == "unknown" ]]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] AGENT_NAME not configured — set AGENT_NAME= in cortex-bus.conf / hermes-cortex/.env or export AGENT_NAME" >> "$ERROR_LOG"
  exit 1
fi

# ── Resolve URL: primary, then fallback, then fail ──
BUS_URL="${CORTEX_BUS_URL:-${CORTEX_BUS_FALLBACK_URL:-}}"
if [[ -z "$BUS_URL" ]]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] CORTEX_BUS_URL not set — cannot push health" >> "$ERROR_LOG"
  exit 1
fi

# Auth: localhost → Bearer, remote → Basic
is_local() {
  local host="${1#*://}"; host="${host%%/*}"; host="${host%%:*}"
  [[ "$host" == "127.0.0.1" || "$host" == "localhost" ]]
}

AUTH_ARGS=()
if is_local "$BUS_URL"; then
  [[ -n "$CORTEX_BUS_TOKEN" ]] && AUTH_ARGS=(-H "Authorization: Bearer $CORTEX_BUS_TOKEN")
else
  [[ -n "$CORTEX_BASIC_AUTH" ]] && AUTH_ARGS=(-u "$CORTEX_BASIC_AUTH")
fi

# Endpoint
API_URL="${BUS_URL%/}/api/pgmq/send"

# ── Vector: default all-1 healthy ──
V_RESOURCES=1     # [0]
V_SERVICES=1      # [1]
V_NO_ERR_CRONS=1  # [2]
V_NO_STALE=1      # [3]
V_NGINX=1         # [4]
V_OLLAMA=1        # [5]
V_MYCORTEX=1      # [6]
V_DISK_OK=1       # [7]
V_MYCORTEX_SRC=1  # [8]

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
command -v test &>/dev/null && test -x "${HOME}/.hermes-cortex/scripts/mycortex" && SVC_OK=1
[[ "$SVC_OK" -eq 0 ]] && V_SERVICES=-1

# [2] no_errored_crons — check push error log for RECENT failures (6h).
# Pre-2026-08-12: `[[ -s ... ]]` flagged -1 on ANY historical error forever —
# one stale push failure (e.g. a wrong token or URL during a change) poisoned
# the health vector for days. Now requires the log to have been modified
# within the last 6h; once pushes succeed for 6h straight the flag clears.
if [[ -s "$ERROR_LOG" ]] && find "$ERROR_LOG" -mmin -360 2>/dev/null | grep -q .; then
    V_NO_ERR_CRONS=-1
fi

# [3] no_stale_crons — best-effort (delegated to orchestrator)
# Always 1; actual stale detection is Moses' job.

# [4] nginx
if command -v pgrep &>/dev/null; then
    pgrep nginx >/dev/null 2>&1 || V_NGINX=-1
else
    V_NGINX=0
fi

# [5] ollama
if command -v curl &>/dev/null; then
    # macOS has no `timeout` (gtimeout from coreutils); fall back to curl --max-time
    if command -v timeout &>/dev/null; then
        timeout 5 curl -sf http://localhost:11434/api/tags -o /dev/null 2>/dev/null || V_OLLAMA=-1
    else
        curl -sf --max-time 5 http://localhost:11434/api/tags -o /dev/null 2>/dev/null || V_OLLAMA=-1
    fi
else
    V_OLLAMA=0
fi

# [6] mycortex — mycortex CLI presence is the signal
if [[ -x "${HOME}/.hermes-cortex/scripts/mycortex" ]]; then
    V_MYCORTEX=1
else
    V_MYCORTEX=-1
fi

# [7] disk_ok — root partition < 90% used
DF_OUTPUT=$(df / 2>/dev/null | tail -1)
if [[ -n "$DF_OUTPUT" ]]; then
    PCT=$(echo "$DF_OUTPUT" | awk '{print $5}' | tr -d '%')
    [[ -n "$PCT" ]] && [[ "$PCT" -ge 90 ]] && V_DISK_OK=-1
fi

# [8] mycortex_sources_ok — ~/brain has at least one non-empty subdirectory
BRAIN_HOME="${HOME}/brain"
if [[ -d "$BRAIN_HOME" ]]; then
    HAS_SOURCE=0
    for d in "$BRAIN_HOME"/*/; do
        if [[ -d "$d" ]] && [[ -n "$(ls -A "$d" 2>/dev/null)" ]]; then
            HAS_SOURCE=1; break
        fi
    done
    [[ "$HAS_SOURCE" -eq 0 ]] && V_MYCORTEX_SRC=-1
else
    V_MYCORTEX_SRC=-1
fi

# ── Build PGMQ payload ──
NOW_TS=$(date +%s)
HNAME='t'
PAYLOAD=$(python3 -c "
import json
body = json.dumps({'v': [$V_RESOURCES,$V_SERVICES,$V_NO_ERR_CRONS,$V_NO_STALE,$V_NGINX,$V_OLLAMA,$V_MYCORTEX,$V_DISK_OK,$V_MYCORTEX_SRC], 'h': '$HNAME', 't': $NOW_TS})
msg = {'queue': 'inbox_health_check', 'message': {'from': '$AGENT_NAME', 'subject': 'health', 'body': body}}
print(json.dumps(msg))
" 2>/dev/null || echo '{"queue":"inbox_health_check","message":{"from":"'$AGENT_NAME'","subject":"health","body":"{}"}}')

# ── POST to PGMQ Agent Bus ──
RESPONSE_FILE=$(mktemp /tmp/health-push-XXXXXX)
trap 'rm -f "$RESPONSE_FILE"' EXIT

HTTP_CODE=$(curl -s -X POST "${AUTH_ARGS[@]}" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD" \
  -w "%{http_code}" \
  -o "$RESPONSE_FILE" \
  --max-time 10 "$API_URL" 2>/dev/null || echo "000")

PUSH_OK=0
case "$HTTP_CODE" in
    2*) PUSH_OK=1 ;;
    *)  [[ "$HTTP_CODE" != "000" ]] && echo "[$(date '+%Y-%m-%d %H:%M:%S')] HTTP $HTTP_CODE to $API_URL" >> "$ERROR_LOG"
        [[ "$HTTP_CODE" == "000" ]] && echo "[$(date '+%Y-%m-%d %H:%M:%S')] curl failed to $API_URL" >> "$ERROR_LOG" ;;
esac

if [[ "$PUSH_OK" -eq 0 ]]; then
    exit 1
fi

exit 0
