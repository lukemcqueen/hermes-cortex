#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  orch-team-messages.sh — Poll agent message queue
#
#  ⚠️  ORCHESTRATOR ONLY — This script is designed exclusively
#     for the Moses orchestrator server. Do NOT install on
#     worker agents (Titus, Gisu, Joseph, Kustos, Esther).
#     The install-crons.sh skips this on non-orchestrators.
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
STATE_DIR="${HOME}/.hermes-cortex/state"
SEEN_FILE="${STATE_DIR}/inbox-broadcast-seen"
STATE_FILE="${STATE_DIR}/last-message-check"

mkdir -p "$INBOX_DIR" "$PROCESSED_DIR" "$STATE_DIR"

# Save timestamp of this check
date -u +"%Y-%m-%dT%H:%M:%SZ" > "$STATE_FILE"

# Read agent registry for routing targets
AGENT_REGISTRY="${HOME}/.hermes-cortex/state/agent-registry.json"
BROADCAST_TOPICS="luke|all|general"
if [ -f "$AGENT_REGISTRY" ]; then
  # Extract broadcast topics + all agent names from registry
  REGISTRY_TOPICS=$(python3 -c "
import json
with open('${AGENT_REGISTRY}') as f:
    data = json.load(f)
topics = data.get('routing', {}).get('broadcast_topics', ['luke', 'all', 'general'])
if data.get('routing', {}).get('agent_prefix_topics', True):
    topics.extend(data.get('agents', {}).keys())
print('|'.join(topics))
" 2>/dev/null || echo "luke|all|general|moses|titus|joseph|kustos|gisu")
  if [ -n "$REGISTRY_TOPICS" ]; then
    BROADCAST_TOPICS="$REGISTRY_TOPICS"
  fi
fi

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
  status=$(sed -n '/^status:/s/.*: *//p' "$msg" 2>/dev/null | head -1)
  from="${from:-unknown}"
  subject="${subject:-No subject}"
  topic="${topic:-general}"
  status="${status:-unread}"

  # Skip messages already marked as read — prevents duplicate reporting
  if [ "$status" = "read" ]; then
    if ! grep -q "^${id}$" "$SEEN_FILE" 2>/dev/null; then
      echo "$id" >> "$SEEN_FILE" 2>/dev/null || true
    fi
    continue
  fi

  # ── Determine if this is a broadcast message (stays in inbox) ──
  IS_BROADCAST=false
  if echo "$BROADCAST_TOPICS" | grep -Eq "(^|\|)$topic(\||$)"; then
    IS_BROADCAST=true
  fi

  if $IS_BROADCAST; then
    # ── Broadcast: leave in inbox for agents, show to Moses once ──
    if ! grep -q "^${id}$" "$SEEN_FILE" 2>/dev/null; then
      # ── Health-status filter: suppress broadcast of health-ping JSON ──
      #   Agents sometimes broadcast health-online notices to #luke. These are
      #   programmatic, not human-readable messages Luke needs to see.
      body_start=$(grep -n '^---$' "$msg" 2>/dev/null | tail -1 | cut -d: -f1)
      body_start=$((body_start + 1))
      BODY=$(tail -n +"${body_start}" "$msg" 2>/dev/null || true)
      HEALTH_PING=false
      lower_subject=$(echo "${subject}" | tr '[:upper:]' '[:lower:]')
      # Check 1: subject matches health-online patterns
      if echo "${lower_subject}" | grep -Eq "(online.*health|health.*online|health reporting|status.*online)"; then
        HEALTH_PING=true
      fi
      # Check 2: body is a JSON object (programmatic health data, not human message)
      if echo "${BODY}" | grep -Eq '^\s*\{' 2>/dev/null; then
        HEALTH_PING=true
      fi
      if $HEALTH_PING; then
        # Track as seen so we don't re-evaluate, but don't broadcast
        echo "$id" >> "$SEEN_FILE"
        continue
      fi
      TS=$(TZ="Asia/Seoul" date +"%Y-%m-%d %H:%M KST")
      $HAD_OUTPUT || { echo "━━━ 📬 Agent Inbox — Broadcast ━━━ [${TS}]"; HAD_OUTPUT=true; }
      echo "  From: ${from}  |  Topic: #${topic}"
      echo "  Subject: ${subject}"
      echo "  (agents will pick this up on next poll)"
      echo ""
      echo "${BODY}"
      echo ""
      echo "━━━ End Broadcast ━━━"

      # Detect priority from frontmatter
      priority=$(sed -n '/^priority:/s/.*: *//p' "$msg" 2>/dev/null | head -1)
      priority="${priority:-normal}"

      if [ "$priority" = "critical" ] || [ "$priority" = "urgent" ]; then
        echo "  ⚠ Priority: $priority"
      fi

      # Detect if this message needs remediation (keywords in subject or body, or urgent/critical priority)
      NEEDS_FIX=false
      if [ "$priority" = "critical" ] || [ "$priority" = "urgent" ]; then
        NEEDS_FIX=true
      fi
      if ! $NEEDS_FIX; then
        lower_subject=$(echo "${subject}" | tr '[:upper:]' '[:lower:]')
        lower_body=$(echo "${BODY}" | tr '[:upper:]' '[:lower:]')
        for keyword in "error" "failed" "crash" "down" "help" "broken" "stuck" "not working" "issue" "problem" "script failure"; do
          if echo "${lower_subject}" | grep -q "${keyword}" || echo "${lower_body}" | grep -q "${keyword}"; then
            NEEDS_FIX=true
            break
          fi
        done
      fi

      if $NEEDS_FIX; then
        # Write a remediation marker
        REMEDIATE_DIR="${HOME}/.hermes-cortex/state/remediate"
        mkdir -p "${REMEDIATE_DIR}"
        echo "from=${from}" > "${REMEDIATE_DIR}/inbox-$(date +%s).txt"
        echo "subject=${subject}" >> "${REMEDIATE_DIR}/inbox-$(date +%s).txt"
        echo "file=${msg}" >> "${REMEDIATE_DIR}/inbox-$(date +%s).txt"
        echo "priority=${priority}" >> "${REMEDIATE_DIR}/inbox-$(date +%s).txt"
        echo "  🔧 Flagged for auto-remediation"
      fi

      # Track as seen
      echo "$id" >> "$SEEN_FILE"
    fi
    # Leave file in inbox — agents need it
  else
    # ── Moses message: move to processed ──
    TS=$(TZ="Asia/Seoul" date +"%Y-%m-%d %H:%M KST")
    echo ""
    echo "━━━ 📬 Agent Message — ${filename} ━━━ [${TS}]"
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
