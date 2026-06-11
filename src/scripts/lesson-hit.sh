#!/bin/bash
# lesson-hit.sh — Increment success_count on a lesson after a match.
#
# Usage:
#   lesson-hit.sh <lesson-file>          # by file path
#   lesson-hit.sh --search "<title>"     # by title (searches ~/brain/lessons/)
#   lesson-hit.sh --by-id "<basename>"   # by filename (e.g., my-lesson.md)
#
# Increments success_count + updates timestamp in the YAML frontmatter.
# Exits 1 if lesson file not found, 0 on success.

set -euo pipefail

LESSONS_DIR="${HOME}/brain/lessons"
[ -d "$LESSONS_DIR" ] || { echo "ERROR: Lessons dir not found: $LESSONS_DIR" >&2; exit 1; }

# ── Resolve lesson file ────────────────────────────────────────────────
LESSON_FILE=""
MODE="$1"  # first arg

if [ "$MODE" = "--search" ]; then
    shift
    TITLE="$*"
    # Search for title in frontmatter
    LESSON_FILE=$(grep -rl "^title:.*${TITLE}" "$LESSONS_DIR" 2>/dev/null | head -1)
    [ -z "$LESSON_FILE" ] && { echo "ERROR: No lesson found matching title: $TITLE" >&2; exit 1; }
elif [ "$MODE" = "--by-id" ]; then
    shift
    LESSON_FILE="${LESSONS_DIR}/${1}.md"
    [ ! -f "$LESSON_FILE" ] && LESSON_FILE="${LESSONS_DIR}/${1}"
    [ ! -f "$LESSON_FILE" ] && { echo "ERROR: Lesson not found: ${LESSONS_DIR}/${1}" >&2; exit 1; }
else
    LESSON_FILE="$MODE"
    [ ! -f "$LESSON_FILE" ] && { echo "ERROR: Lesson file not found: $LESSON_FILE" >&2; exit 1; }
fi

# ── Increment success_count ────────────────────────────────────────────
CURRENT=$(grep -E '^success_count:' "$LESSON_FILE" | sed 's/.*: *//' || echo 0)
[ -z "$CURRENT" ] && CURRENT=0
NEW=$((CURRENT + 1))

NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# Use sed for in-place edit (portable: -i '' on macOS, -i on Linux)
if sed --version 2>/dev/null | grep -q GNU; then
    # GNU sed
    sed -i "s/^success_count:.*/success_count: ${NEW}/" "$LESSON_FILE"
    if grep -q '^updated:' "$LESSON_FILE"; then
        sed -i "s/^updated:.*/updated: ${NOW}/" "$LESSON_FILE"
    else
        sed -i "/^success_count:/a\\updated: ${NOW}" "$LESSON_FILE"
    fi
else
    # BSD sed (macOS)
    sed -i '' "s/^success_count:.*/success_count: ${NEW}/" "$LESSON_FILE"
    if grep -q '^updated:' "$LESSON_FILE"; then
        sed -i '' "s/^updated:.*/updated: ${NOW}/" "$LESSON_FILE"
    else
        # Add updated: line after success_count
        sed -i '' "/^success_count:/a\\"$'\n'"updated: ${NOW}" "$LESSON_FILE"
    fi
fi

echo "✅ Hit recorded: success_count ${CURRENT}→${NEW} ($(basename "$LESSON_FILE"))"
