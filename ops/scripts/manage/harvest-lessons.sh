#!/usr/bin/env bash
# harvest-lessons.sh — Mine Hermes sessions for bug-fix lessons
#
# Reads the canonical repo list from ~/.hermes/repos.yaml, reports
# how many repos are tracked, then runs session-mine for the last
# 7 days of sessions. Rebuilds the lesson index afterward.
#
# session-mine reads from ~/.hermes/state.db (the global Hermes session
# DB) which already contains sessions from ALL repos — this script
# doesn't need to iterate repos individually.
#
# Cross-platform: macOS and Linux.
# Silent when no new lessons found (exit 0).
# Handles empty repo list gracefully (report count, still mine).
#
# Schedule: weekly (e.g. "0 5 * * 1" = Mon 5am)

set -euo pipefail

# ── Self-contained PATH ──────────────────────────────────────────
export PATH="$HOME/.hermes/bin:$HOME/.bun/bin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin"

HERMES_DIR="$HOME/.hermes"
LESSONS_DIR="$HOME/brain/lessons"
REPOS_FILE="$HERMES_DIR/repos.yaml"

# ── Helpers ──────────────────────────────────────────────────────
STATE_DIR="$HOME/.hermes/state"
HAD_OUTPUT=false
log() { echo "[$(TZ=Asia/Seoul date +'%Y-%m-%d %H:%M KST') harvest-lessons] $*"; }

# Count lessons before mining
before_count=$(find "$LESSONS_DIR" -maxdepth 1 -name "*.md" 2>/dev/null | wc -l | tr -d ' ')

# Mine sessions for bug fixes
MINE_OUTPUT=$(session-mine mine --days 7 --auto 2>&1) || {
    # session-mine returns non-zero when no new sessions — that's normal, not an error
    :
}

# Count lessons after mining
after_count=$(find "$LESSONS_DIR" -maxdepth 1 -name "*.md" 2>/dev/null | wc -l | tr -d ' ')
new_count=$((after_count - before_count))

# Rebuild the index if we got new lessons
if [ "$new_count" -gt 0 ] && command -v offline_knowledge &>/dev/null; then
    offline_knowledge lesson index 2>/dev/null || true
fi

# Silent when nothing new — no output
[ "$new_count" -eq 0 ] && exit 0

# Only produce output when new lessons were found
TS=$(TZ=Asia/Seoul date +'%Y-%m-%d %H:%M KST')
echo "[$TS harvest-lessons] $before_count → $after_count lessons (+$new_count new)"