#!/bin/bash
# session-mine — Mine session history for bug-fix lessons
# Installed by Hermes Cortex install.sh

SCRIPT_DIR="$HOME/.hermes-cortex/offline"
SCRIPT="$SCRIPT_DIR/session_mine.py"

if [ ! -f "$SCRIPT" ]; then
    # Fallback to repo location
    SCRIPT="$HOME/hermes-cortex/src/offline/session_mine.py"
fi

if [ ! -f "$SCRIPT" ]; then
    echo "Error: session_mine.py not found" >&2
    exit 1
fi

exec python3 "$SCRIPT" "$@"
