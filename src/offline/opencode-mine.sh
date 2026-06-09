#!/bin/bash
# opencode-mine — Mine OpenCode session history for bug-fix lessons
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$SCRIPT_DIR/opencode_lesson_mine.py"
if [ ! -f "$SCRIPT" ]; then
    echo "Error: opencode_lesson_mine.py not found alongside this script ($SCRIPT)" >&2
    exit 1
fi
exec python3 "$SCRIPT" "$@"
