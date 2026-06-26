#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  send-agent-learning.sh — Send recent session/brain learnings
#  from this agent to Moses via the agent inbox.
#
#  Runs as a no_agent cron (default: every 6h).
#  Silent when no new learnings since last run.
#  Sends with status=read (informational, not actionable).
#
#  Schedule: cron name=agent-learning-sender schedule="0 */6 * * *"
#            script=send-agent-learning.sh no_agent=true deliver=local
# ─────────────────────────────────────────────────────────────
set -euo pipefail

# ── Config: source inbox credentials ──
INBOX_URL="https://your-domain.com:13004/send"
INBOX_AUTH=""
CONFIG_FILE="${HOME}/.hermes/moses-inbox.conf"
if [[ -f "$CONFIG_FILE" ]]; then
    source "$CONFIG_FILE"
    INBOX_URL="${MOSES_INBOX_URL:-$INBOX_URL}/send"
    INBOX_AUTH="${MOSES_INBOX_AUTH:-}"
fi

AGENT_NAME="${HOSTNAME%%.*}"
STATE_DIR="${HOME}/.hermes/state"
LAST_SENT_FILE="${STATE_DIR}/agent-learning-last-sent"
INTERVAL_SECONDS="${AGENT_LEARNING_INTERVAL:-21600}"  # default 6h
SESSION_DIR="${HOME}/.hermes-cortex/sessions"
BRAIN_LESSONS_DIR="${HOME}/brain/${AGENT_NAME}/lessons"

mkdir -p "${STATE_DIR}"

# ── Helpers ──
log() { echo "[$(date '+%H:%M:%S')] $*"; }

# ── Step 1: Rate limit ──
if [[ -f "${LAST_SENT_FILE}" ]]; then
    LAST_RUN=$(cat "${LAST_SENT_FILE}" 2>/dev/null || echo 0)
    NOW=$(date +%s)
    if [[ $((NOW - LAST_RUN)) -lt ${INTERVAL_SECONDS} ]]; then
        exit 0  # Too soon, skip silently
    fi
fi

# ── Step 2: Gather session takeaways ──
SNIPPETS=""

# From session DB (most recent session file)
LATEST_SESSION=$(find "${SESSION_DIR}" -name "*.md" -type f 2>/dev/null | head -1)
if [[ -n "${LATEST_SESSION}" && -f "${LATEST_SESSION}" ]]; then
    # Extract the last ~30 lines (summary/takeaways section)
    TAIL_OUT=$(tail -30 "${LATEST_SESSION}" 2>/dev/null || true)
    if [[ -n "${TAIL_OUT}" ]]; then
        SNIPPETS+="=== ${AGENT_NAME} — Recent session takeaways ===\n"
        SNIPPETS+="${TAIL_OUT}\n\n"
    fi
fi

# From brain lessons (new/modified since last run)
if [[ -d "${BRAIN_LESSONS_DIR}" ]]; then
    # Find lesson files newer than last run
    NEW_LESSONS=()
    while IFS= read -r -d '' f; do
        NEW_LESSONS+=("$f")
    done < <(find "${BRAIN_LESSONS_DIR}" -name "*.md" -type f -newermt "@${LAST_RUN:-0}" -print0 2>/dev/null)

    if [[ ${#NEW_LESSONS[@]} -gt 0 ]]; then
        SNIPPETS+="=== ${AGENT_NAME} — New lessons (${#NEW_LESSONS[@]}) ===\n"
        for f in "${NEW_LESSONS[@]}"; do
            TITLE=$(basename "${f}" .md)
            # First non-empty line as summary
            SUMMARY=$(grep -m1 -E '^[^#]' "${f}" 2>/dev/null | head -1 || head -1 "${f}")
            SNIPPETS+="• ${TITLE}: ${SUMMARY}\n"
        done
        SNIPPETS+="\n"
    fi
fi

# From script changes (if this agent runs install.sh/cortex-update.sh)
CUSTOM_SCRIPTS="${HOME}/.hermes-cortex/scripts"
if [[ -d "${CUSTOM_SCRIPTS}" ]]; then
    # Check for any custom scripts not from the repo
    REPO_SCRIPTS="${HOME}/hermes-cortex/src/scripts"
    CUSTOM_COUNT=0
    for f in "${CUSTOM_SCRIPTS}"/*.sh "${CUSTOM_SCRIPTS}"/*.py 2>/dev/null; do
        [[ -f "$f" ]] || continue
        BASENAME=$(basename "$f")
        if [[ ! -f "${REPO_SCRIPTS}/${BASENAME}" ]]; then
            ((CUSTOM_COUNT++))
        fi
    done
    if [[ ${CUSTOM_COUNT} -gt 0 ]]; then
        SNIPPETS+="=== ${AGENT_NAME} — Custom scripts (${CUSTOM_COUNT}) ===\n"
        SNIPPETS+="Found ${CUSTOM_COUNT} scripts not in hermes-cortex repo.\n\n"
    fi
fi

# ── Step 3: Exit if nothing to send ──
if [[ -z "${SNIPPETS}" ]]; then
    exit 0  # Silent — no new learnings
fi

# ── Step 4: Build message ──
BODY="Agent: ${AGENT_NAME}
Host: $(hostname)
Time: $(date -u '+%Y-%m-%d %H:%M:%S UTC')

${SNIPPETS}"

# ── Step 5: Send to Moses via inbox ──
CURL_AUTH=()
[[ -n "$INBOX_AUTH" ]] && CURL_AUTH=(-u "$INBOX_AUTH")
RESPONSE=$(curl -sf -X POST "${INBOX_URL}" \
    "${CURL_AUTH[@]}" \
    -d "from=${AGENT_NAME}" \
    -d "topic=moses" \
    -d "subject=📥 ${AGENT_NAME} learning summary" \
    -d "body=${BODY}" \
    -d "priority=normal" \
    -d "status=read" 2>&1) || {
    log "Failed to send to inbox: ${RESPONSE}"
    exit 1
}

# ── Step 6: Update timestamp ──
date +%s > "${LAST_SENT_FILE}"
log "Sent learning summary to Moses (topic=moses)"
