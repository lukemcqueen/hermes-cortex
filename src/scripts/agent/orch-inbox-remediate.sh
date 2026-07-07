#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  orch-inbox-remediate.sh — Read pending remediation markers
#
#  Reads ~/.hermes-cortex/state/remediate/ for pending fix requests
#  left by check-agent-messages.sh. Outputs structured JSON.
#
#  Output: JSON array. Empty [] when nothing pending (silent).
#
#  Called by orch-process-agent-messages cron every 10 minutes.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

REMEDIATE_DIR="${HOME}/.hermes-cortex/state/remediate"
DONE_DIR="${REMEDIATE_DIR}/done"
PRIVATE_REPO="${HOME}/hermes-cortex-private"
INBOX_DIR="${PRIVATE_REPO}/messages/inbox"
PROCESSED_DIR="${PRIVATE_REPO}/messages/processed"

mkdir -p "$DONE_DIR"

shopt -s nullglob
MARKERS=("${REMEDIATE_DIR}"/inbox-*.txt)
shopt -u nullglob

if [ ${#MARKERS[@]} -eq 0 ]; then
  echo '[]'
  exit 0
fi

# Pull latest messages from git before reading
if cd "$PRIVATE_REPO" 2>/dev/null; then
  git pull --ff-only origin main >/dev/null 2>&1 || true
fi

FIRST=true
echo '['
for marker in "${MARKERS[@]}"; do
  $FIRST || echo ','
  FIRST=false

  # Read marker fields
  SENDER="$(grep '^from=' "$marker" 2>/dev/null | sed 's/^from=//')"
  SUBJECT="$(grep '^subject=' "$marker" 2>/dev/null | sed 's/^subject=//')"
  MSG_FILE="$(grep '^file=' "$marker" 2>/dev/null | sed 's/^file=//')"

  SENDER="${SENDER:-unknown}"
  SUBJECT="${SUBJECT:-No subject}"
  MSG_FILE="${MSG_FILE:-}"

  # Read original message body (works for both inbox/ and processed/ paths)
  BODY=''
  if [ -n "$MSG_FILE" ] && [ -f "$MSG_FILE" ]; then
    body_start=$(grep -n '^---$' "$MSG_FILE" 2>/dev/null | tail -1 | cut -d: -f1)
    body_start=$((body_start + 1))
    BODY=$(tail -n +"${body_start}" "$MSG_FILE" 2>/dev/null || echo '')
    # Escape JSON special chars
    BODY=$(echo "$BODY" | python3 -c "
import sys, json
text = sys.stdin.read()
print(json.dumps(text))
" 2>/dev/null || echo '""')
  fi

  # Also check processed dir
  if [ -z "$BODY" ] || [ "$BODY" = '""' ] && [ -n "$MSG_FILE" ]; then
    PROCESSED_FILE="${PROCESSED_DIR}/$(basename "$MSG_FILE")"
    if [ -f "$PROCESSED_FILE" ]; then
      body_start=$(grep -n '^---$' "$PROCESSED_FILE" 2>/dev/null | tail -1 | cut -d: -f1)
      body_start=$((body_start + 1))
      BODY=$(tail -n +"${body_start}" "$PROCESSED_FILE" 2>/dev/null || echo '')
      BODY=$(echo "$BODY" | python3 -c "
import sys, json
text = sys.stdin.read()
print(json.dumps(text))
" 2>/dev/null || echo '""')
    fi
  fi

  # Filename for done tracking
  FILENAME=$(basename "$marker")

  echo '  {'
  echo "    \"sender\": $(echo "$SENDER" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read().strip()))"),"
  echo "    \"subject\": $(echo "$SUBJECT" | python3 -c "import sys,json; print(json.dumps(sys.stdin.read().strip()))"),"
  echo "    \"body\": $BODY,"
  echo "    \"marker_file\": \"${marker}\","
  echo "    \"filename\": \"${FILENAME}\""
  echo '  }'
done
echo ']'
