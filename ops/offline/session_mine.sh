#!/bin/bash
# session-mine — Mine session history for bug-fix lessons
# Installed by Steadfaste Fleet install.sh

SCRIPT_DIR="$HOME/.steadfaste-fleet/offline"
SCRIPT="$SCRIPT_DIR/session_mine.py"

if [ ! -f "$SCRIPT" ]; then
    # Fallback to repo location
    SCRIPT="$HOME/steadfaste-fleet/ops/offline/session_mine.py"
fi

if [ ! -f "$SCRIPT" ]; then
    echo "Error: session_mine.py not found" >&2
    exit 1
fi

# Ensure Hermes paths are on PYTHONPATH
export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}${HOME}/.steadfaste-fleet/scripts"

exec python3 "$SCRIPT" "$@"
