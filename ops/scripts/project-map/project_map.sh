#!/bin/bash
# project-map — Project static analysis tool
# Installed by Steadfaste Fleet install.sh

SCRIPT_DIR="$HOME/.steadfaste-fleet/offline"
SCRIPT="$SCRIPT_DIR/project_map.py"

if [ ! -f "$SCRIPT" ]; then
    # Fallback to repo location
    SCRIPT="$HOME/steadfaste-fleet/ops/scripts/project-map/project_map.py"
fi

if [ ! -f "$SCRIPT" ]; then
    echo "Error: project_map.py not found" >&2
    exit 1
fi

exec python3 "$SCRIPT" "$@"
