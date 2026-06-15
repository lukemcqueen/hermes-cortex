#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  check-agent-messages.sh — Poll agent message queue
#
#  Reads new messages from the agent inbox (root inbox/ dir).
#
#  Routing by topic:
#    luke, all, general, <agentname>  → broadcast to agents
#      Leaves file in inbox (unread) so agents' polling picks it up
#      Only shows to Moses once (tracked via .seen file)
#
#    other topics                     → agent→Moses messages
#      Moves to processed/ after showing to Moses
#
#  Silent when nothing new (watchdog pattern).
# ─────────────────────────────────────────────────────────────
set -euo pipefail

PRIVATE_REPO="${HOME}/hermes-cortex-private"
INBOX_DIR="${PRIVATE_REPO}/messages/inbox"
PROCESSED_DIR="${PRIVATE_REPO}/messages/processed"
STATE_DIR="${HOME}/.hermes/state"
SEEN_FILE="${STATE_DIR}/inbox-broadcast-seen"
STATE_FILE="${STATE_DIR}/last-message-check"

mkdir -p "$INBOX_DIR" "$PROCESSED_DIR" "$STATE_DIR"

# Save timestamp of this check
date -u +"%Y-%m-%dT%H:%M:%SZ" > "$STATE_FILE"

# Known agents (broadcast targets). Messages in these topics stay in inbox.
# Space-separated, used in a case statement below.

# Find new message files in root inbox (not subfolders)
shopt -s nullglob
INBOX_FILES=("$INBOX_DIR"/*.md)
shopt -u nullglob

[[ ${#INBOX_FILES[@]} -eq 0 ]] && exit 0

# Pull latest (agents may have pushed)
if cd "$PRIVATE_REPO" 2>/dev/null; then
  git pull --ff-only origin main >/dev/null 2>&1 || true
fi

shopt -s nullglob
INBOX_FILES=("$INBOX_DIR"/*.md)
shopt -u nullglob

[[ ${#INBOX_FILES[@]} -eq 0 ]] && exit 0

HAD_OUTPUT=false

for msg in "${INBOX_FILES[@]}"; do
  filename=$(basename "$msg")
  id="${filename%.md}"  # Strip .md for tracking

  # Extract frontmatter
  from=$(sed -n '/^from:/s/.*: *//p' "$msg" 2>/dev/null | head -1)
  subject=$(sed -n '/^subject:/s/.*: *//p' "$msg" 2>/dev/null | head -1)
  topic=$(sed -n '/^topic:/s/.*: *//p' "$msg" 2>/dev/null | head -1)
  from="${from:-unknown}"
  subject="${subject:-No subject}"
  topic="${topic:-general}"

  # ── Determine if this is a broadcast message (stays in inbox) ──
  IS_BROADCAST=false
  case "$topic" in
    luke|all|general|titus|joseph|kustos|gisu|moses)
      IS_BROADCAST=true
      ;;
  esac

  if $IS_BROADCAST; then
    # ── Broadcast: leave in inbox for agents, show to Moses once ──
    if ! grep -q "^${id}$" "$SEEN_FILE" 2>/dev/null; then
      $HAD_OUTPUT || { echo "━━━ 📬 Agent Inbox — Broadcast ━━━"; HAD_OUTPUT=true; }
      echo "  From: ${from}  |  Topic: #${topic}"
      echo "  Subject: ${subject}"
      echo "  (agents will pick this up on next poll)"
      echo ""
      # Show body
      body_start=$(grep -n '^---$' "$msg" 2>/dev/null | tail -1 | cut -d: -f1)
      body_start=$((body_start + 1))
      BODY=$(tail -n +"${body_start}" "$msg" 2>/dev/null || true)
      echo "${BODY}"
      echo ""
      echo "━━━ End Broadcast ━━━"

      # Detect if this message needs remediation (keywords in subject or body)
      NEEDS_FIX=false
      lower_subject=$(echo "${subject}" | tr '[:upper:]' '[:lower:]')
      lower_body=$(echo "${BODY}" | tr '[:upper:]' '[:lower:]')
      for keyword in "error" "failed" "crash" "down" "help" "broken" "stuck" "not working" "issue" "problem" "script failure"; do
        if echo "${lower_subject}" | grep -q "${keyword}" || echo "${lower_body}" | grep -q "${keyword}"; then
          NEEDS_FIX=true
          break
        fi
      done

      if $NEEDS_FIX; then
        # Write a remediation marker for the auto-remediation cron to pick up
        REMEDIATE_DIR="${HOME}/.hermes/state/remediate"
        mkdir -p "${REMEDIATE_DIR}"
        echo "from=${from}" > "${REMEDIATE_DIR}/inbox-$(date +%s).txt"
        echo "subject=${subject}" >> "${REMEDIATE_DIR}/inbox-$(date +%s).txt"
        echo "file=${msg}" >> "${REMEDIATE_DIR}/inbox-$(date +%s).txt"
        echo "  🔧 Flagged for auto-remediation"
      fi

      # Track as seen
      echo "$id" >> "$SEEN_FILE"
    fi
    # Leave file in inbox — agents need it
  else
    # ── Moses message: move to processed ──
    echo ""
    echo "━━━ 📬 Agent Message — ${filename} ━━━"
    echo "  From: ${from}"
    echo "  Subject: ${subject}"
    echo ""
    body_start=$(grep -n '^---$' "$msg" 2>/dev/null | tail -1 | cut -d: -f1)
    body_start=$((body_start + 1))
    tail -n +"${body_start}" "$msg" 2>/dev/null || true
    echo ""
    echo "━━━ End Message ━━━"

    mv "$msg" "${PROCESSED_DIR}/${filename}"
    HAD_OUTPUT=true
  fi
done

# Commit and push any changes
if cd "$PRIVATE_REPO" 2>/dev/null; then
  git add messages/ 2>/dev/null || true
  git diff --cached --quiet 2>/dev/null || {
    git commit -m "inbox: processed/broadcast check" >/dev/null 2>&1 || true
    git push >/dev/null 2>&1 || true
  }
fi
