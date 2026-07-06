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
timestamp() {
    TZ=Asia/Seoul date +'%Y-%m-%d %H:%M KST'
}

os_type() {
    case "$(uname -s)" in
        Darwin*) echo "macos" ;;
        Linux*)  echo "linux" ;;
        *)       echo "unknown" ;;
    esac
}

# Count repos listed in repos.yaml
count_repos() {
    if [ ! -f "$REPOS_FILE" ]; then
        echo 0
        return
    fi
    # Count lines matching "  - path:" (top-level repos only)
    grep -c '^  - path:' "$REPOS_FILE" 2>/dev/null || echo 0
}

# Count repos by tier
count_tier() {
    local tier="$1"
    if [ ! -f "$REPOS_FILE" ]; then
        echo 0
        return
    fi
    grep -c "tier: $tier" "$REPOS_FILE" 2>/dev/null || echo 0
}

# ── Main ─────────────────────────────────────────────────────────

mkdir -p "$LESSONS_DIR"

# Report repo registry status
repo_count=$(count_repos)
heavy_count=$(count_tier heavy)
mod_count=$(count_tier moderate)
light_count=$(count_tier light)

echo "[$(timestamp)] Harvesting lessons..."
echo "[$(timestamp)] Platform: $(os_type)"
echo "[$(timestamp)] Repo registry ($REPOS_FILE): $repo_count repos ($heavy_count heavy, $mod_count moderate, $light_count light)"

# Edge case: empty repo list is fine — session DB still has data
if [ "$repo_count" -eq 0 ]; then
    echo "[$(timestamp)] No repos in registry — mining global session DB only"
fi

# Count lessons before mining
before_count=$(find "$LESSONS_DIR" -maxdepth 1 -name "*.md" 2>/dev/null | wc -l | tr -d ' ')

# Mine sessions for bug fixes
if ! session-mine mine --days 7 --auto 2>&1; then
    echo "[$(timestamp)] session-mine returned non-zero (likely no new sessions to mine)"
fi

# Count lessons after mining
after_count=$(find "$LESSONS_DIR" -maxdepth 1 -name "*.md" 2>/dev/null | wc -l | tr -d ' ')
new_count=$((after_count - before_count))

# Rebuild the index so new lessons are searchable
if command -v offline_knowledge &>/dev/null; then
    echo "[$(timestamp)] Rebuilding lesson index..."
    if ! offline_knowledge lesson index 2>&1; then
        echo "[$(timestamp)] Warning: lesson index rebuild had issues (non-fatal)"
    fi
fi

echo "[$(timestamp)] Done: $before_count → $after_count lessons (+$new_count)"

# Silent when nothing new
[ "$new_count" -eq 0 ] && exit 0