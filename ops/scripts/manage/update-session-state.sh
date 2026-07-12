#!/usr/bin/env bash
# update-session-state.sh — Refresh the Repo State section of .hermes-cortex/sessions/current.md
#
# Usage: ./ops/scripts/manage/update-session-state.sh
#   Runs silently if nothing changed (watchdog/CRON mode).
#   Pass --verbose to always print status.
#
# Scope: hermes-cortex workdir only. Ignores all other repos.
# Design: updates only the auto-tracked sections (git state, file metrics).
#         Never touches the Session Notes section (agent-managed).

set -euo pipefail

REPO_DIR="/home/esther/hermes-cortex"
VERBOSE=false

# Parse args
while [[ $# -gt 0 ]]; do
    case "$1" in
        --verbose|-v) VERBOSE=true; shift ;;
        *) REPO_DIR="$1"; shift ;;
    esac
done
SESSION_FILE="$REPO_DIR/.hermes-cortex/sessions/current.md"

if [ ! -f "$SESSION_FILE" ]; then
    echo "ERROR: $SESSION_FILE not found. Run from the hermes-cortex repo root." >&2
    exit 1
fi

# --- Gather current state ---
cd "$REPO_DIR"

LAST_COMMIT_HASH=$(git log --oneline -1 2>/dev/null | awk '{print $1}')
LAST_COMMIT_MSG=$(git log --oneline -1 2>/dev/null | cut -d' ' -f2-)
LAST_COMMIT_DATE=$(git log -1 --format="%ai" 2>/dev/null | cut -d' ' -f1-2)
BRANCH=$(git branch --show-current)
DIRTY=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')
UNPUSHED=$(git log --oneline @{u}..HEAD 2>/dev/null | wc -l | tr -d ' ')
TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "none")

# Recent commits (last 5)
RECENT_COMMITS=$(git log --oneline -5 --format="| %ad | \`%h\` | %s" --date=format:"%Y-%m-%d" 2>/dev/null)

# File counts (Python, shell, markdown)
PY_COUNT=$(find . -name '*.py' -not -path './.git/*' -not -path './node_modules/*' 2>/dev/null | wc -l | tr -d ' ')
SH_COUNT=$(find . -name '*.sh' -not -path './.git/*' 2>/dev/null | wc -l | tr -d ' ')
MD_COUNT=$(find . -name '*.md' -not -path './.git/*' -not -path './node_modules/*' 2>/dev/null | wc -l | tr -d ' ')
TOTAL_FILES=$(find . -type f -not -path './.git/*' -not -path './node_modules/*' -not -path './src/offline/code-corpus/*' 2>/dev/null | wc -l | tr -d ' ')

PY_LINES=$(find . -name '*.py' -not -path './.git/*' -not -path './node_modules/*' -exec cat {} + 2>/dev/null | wc -l | tr -d ' ')
SH_LINES=$(find . -name '*.sh' -not -path './.git/*' -exec cat {} + 2>/dev/null | wc -l | tr -d ' ')

NOW=$(date "+%Y-%m-%d %H:%M KST")

# --- Build the new auto-tracked section ---
read -r -d '' NEW_SECTION <<EOF || true
## Repo State

| Metric | Value |
|--------|-------|
| Last commit | \`${LAST_COMMIT_HASH}\` — ${LAST_COMMIT_DATE} |
| Working tree | $([ "$DIRTY" = "0" ] && echo "clean" || echo "dirty ($DIRTY files)") |
| Unpushed | $([ "$UNPUSHED" = "0" ] && echo "none" || echo "$UNPUSHED commits") |
| Tag | \`${TAG}\` |

### Recent Commits

| Date | Commit | Description |
|------|--------|-------------|
$RECENT_COMMITS

---

## Architecture Overview

| Layer | What |
|-------|------|
| Installer | \`install.sh\` — $(wc -l < install.sh | tr -d ' ') lines, 26 steps, idempotent |
| Skills | $(find skills -name 'SKILL.md' -not -path './.git/*' 2>/dev/null | wc -l | tr -d ' ') skills across 4 categories (software-development, devops, social-media, productivity) |
| Python files | ${PY_COUNT} files (${PY_LINES} LOC) |
| Shell files | ${SH_COUNT} files (${SH_LINES} LOC) |
| Markdown files | ${MD_COUNT} files |
| Total | ${TOTAL_FILES} tracked files |
| Dashboard | Flask app + nginx proxy — Langfuse traces + system health |
| Scripts | 16 utility scripts (heartbeat, memory-sync, LLM scoring, service recovery) |
| OpenCode | 15 commands + 3 agents + 30 optional skills |
| Offline | code corpus (386 snippets, 26 languages) + kiwix ZIM + offline reader |

---

## Status Checklist

- [ ] Tests passing (no test suite configured yet)
- [ ] Dashboard health confirmed
- [ ] Langfuse traces flowing
- [ ] nginx config valid
- [ ] Skills manifest synced
- [ ] Install.sh tested on clean target
- [ ] SECURITY.md up to date
- [ ] README matches reality
- [ ] Changelog updated
- [ ] Tag synced

---

*Last updated: ${NOW}*
EOF

# --- Check if anything changed ---
CURRENT_TAIL=$(sed -n '/^## Repo State/,$p' "$SESSION_FILE" 2>/dev/null || echo "")
NEW_TAIL="$NEW_SECTION"

if [ "$CURRENT_TAIL" = "$NEW_TAIL" ] && [ "$VERBOSE" = false ]; then
    # Silent exit — nothing changed
    exit 0
fi

# --- Update the file ---
# Keep everything before "## Repo State" (header + project identity + session notes),
# then replace from "## Repo State" to end of file.
HEADER=$(sed '/^## Repo State/q' "$SESSION_FILE" 2>/dev/null | sed '$d' 2>/dev/null || head -$(grep -n "^## Repo State" "$SESSION_FILE" | cut -d: -f1) "$SESSION_FILE" | head -n -1)

# Write updated content
{
    echo "$HEADER"
    echo ""
    echo "$NEW_SECTION"
} > "$SESSION_FILE"

echo "✅ .hermes-cortex/sessions/current.md updated — ${NOW}"
echo "   Last commit: ${LAST_COMMIT_HASH} — ${LAST_COMMIT_MSG}"
echo "   Branch: ${BRANCH} | ${DIRTY:+dirty ($DIRTY files)}${DIRTY:-clean}"
