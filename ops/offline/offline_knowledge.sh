#!/bin/bash
# offline_knowledge — CLI for offline knowledge cascade
# Installed by Steadfaste Fleet install.sh

SCRIPT_DIR="$HOME/.steadfaste-fleet/offline"
SCRIPT="$SCRIPT_DIR/offline_knowledge.py"

if [ ! -f "$SCRIPT" ]; then
    # Fallback to repo location
    SCRIPT="$HOME/steadfaste-fleet/ops/offline/offline_knowledge.py"
fi

if [ ! -f "$SCRIPT" ]; then
    echo "Error: offline_knowledge.py not found" >&2
    exit 1
fi

exec python3 "$SCRIPT" "$@"
