#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  post-commit-notify.sh — Notify all agents after a commit
#
#  Runs after every git commit to hermes-cortex. Extracts
#  commit details and sends an inbox broadcast to all agents
#  via the agent inbox API (localhost:8903).
#
#  Silent when:
#    - Repo dir doesn't exist
#    - Inbox server is unreachable
#    - State file says we already notified for this commit
#
#  Install as git post-commit hook:
#    scripts/install-post-commit-hook.sh
# ─────────────────────────────────────────────────────────────
set -euo pipefail

# ── Paths ──
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_FILE="${HOME}/.hermes/state/post-commit-notify"
INBOX_URL="http://127.0.0.1:8903/send"

# ── Helpers ──
log()  { echo "[notify] $*" >> "$STATE_FILE.log"; }

# ── Step 1: Check we're in a git repo ──
cd "$REPO_DIR" || exit 0
if ! git rev-parse --git-dir >/dev/null 2>&1; then
  exit 0
fi

# ── Step 2: Get commit info ──
SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "unknown")
SUBJECT=$(git log -1 --format=%s 2>/dev/null || echo "unknown update")
FILES=$(git diff-tree --no-commit-id -r --name-only HEAD 2>/dev/null | head -20 || echo "")
FILE_COUNT=$(echo "$FILES" | grep -c . || true)
AUTHOR=$(git log -1 --format=%an 2>/dev/null || echo "Moses")

# ── Step 3: Dedup — skip if we already notified for this SHA ──
if [ -f "$STATE_FILE" ]; then
  LAST_SHA=$(cat "$STATE_FILE" 2>/dev/null || echo "")
  if [ "$LAST_SHA" = "$SHA" ]; then
    exit 0
  fi
fi

# ── Step 4: Check inbox is reachable ──
if ! curl -sf -o /dev/null --connect-timeout 2 "http://127.0.0.1:8903/health" 2>/dev/null; then
  log "inbox unreachable — skipping notification"
  exit 0
fi

# ── Step 5: Build message body ──
BODY="Commited by ${AUTHOR}
SHA: ${SHA}
Subject: ${SUBJECT}
Files: ${FILE_COUNT} changed

${FILES}
"

# ── Step 6: Send broadcast to all agents ──
curl -sf -X POST "$INBOX_URL" \
  -d "from=Moses" \
  -d "topic=all" \
  -d "subject=📦 hermes-cortex update: ${SUBJECT}" \
  -d "body=${BODY}" \
  -d "priority=normal" \
  >/dev/null 2>&1 && log "notified all agents for ${SHA}" || log "failed to notify for ${SHA}"

# ── Step 7: Save state ──
echo "$SHA" > "$STATE_FILE"