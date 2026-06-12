#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  check-agent-messages.sh — Poll agent message queue
#
#  Reads new messages from the private hermes-cortex-private
#  repo's messages/inbox/, delivers them via stdout (which the
#  cron sends to the operator's configured channel), then moves
#  processed messages to messages/processed/.
#
#  Silent when no new messages (watchdog pattern).
# ─────────────────────────────────────────────────────────────
set -euo pipefail

PRIVATE_REPO="${HOME}/hermes-cortex-private"
INBOX_DIR="${PRIVATE_REPO}/messages/inbox"
PROCESSED_DIR="${PRIVATE_REPO}/messages/processed"
STATE_FILE="${HOME}/.hermes/state/last-message-check"

mkdir -p "$INBOX_DIR" "$PROCESSED_DIR"

# Find new message files (not yet processed)
shopt -s nullglob
NEW_MESSAGES=("$INBOX_DIR"/*.md)
shopt -u nullglob

if [[ ${#NEW_MESSAGES[@]} -eq 0 ]]; then
  exit 0  # Silent — nothing new
fi

# Pull latest from private repo (agents may have pushed messages)
if cd "$PRIVATE_REPO" 2>/dev/null; then
  git pull --ff-only origin main 2>/dev/null || true
fi

# Re-check after pull (the pull may have brought in messages)
shopt -s nullglob
NEW_MESSAGES=("$INBOX_DIR"/*.md)
shopt -u nullglob

if [[ ${#NEW_MESSAGES[@]} -eq 0 ]]; then
  exit 0
fi

# Process each message
for msg in "${NEW_MESSAGES[@]}"; do
  filename=$(basename "$msg")

  echo ""
  echo "━━━ 📬 Agent Message — ${filename} ━━━"

  # Extract frontmatter
  from=$(sed -n '/^from:/s/.*: *//p' "$msg" 2>/dev/null | head -1)
  subject=$(sed -n '/^subject:/s/.*: *//p' "$msg" 2>/dev/null | head -1)
  from="${from:-unknown}"
  subject="${subject:-No subject}"

  echo "  From: ${from}"
  echo "  Subject: ${subject}"
  echo ""

  # Body (skip frontmatter)
  body_start=$(grep -n '^---$' "$msg" 2>/dev/null | tail -1 | cut -d: -f1)
  body_start=$((body_start + 1))
  tail -n +"${body_start}" "$msg" 2>/dev/null || true

  echo ""
  echo "━━━ End Message ━━━"

  # Move to processed
  mv "$msg" "${PROCESSED_DIR}/${filename}"
done

# Save timestamp
date -u +"%Y-%m-%dT%H:%M:%SZ" > "$STATE_FILE"

# Commit and push processed messages back
if cd "$PRIVATE_REPO" 2>/dev/null; then
  git add messages/ 2>/dev/null || true
  git diff --cached --quiet 2>/dev/null || {
    git commit -m "inbox: processed ${#NEW_MESSAGES[@]} message(s)" 2>/dev/null || true
    git push 2>/dev/null || true
  }
fi
