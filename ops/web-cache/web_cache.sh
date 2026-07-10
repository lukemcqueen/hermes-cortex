#!/bin/bash
# web_cache — CLI wrapper for the semantic web cache
# Installed by Hermes Cortex install.sh

VENV_PYTHON="$HOME/.hermes-cortex/web-cache/.venv/bin/python3"
SCRIPT="$HOME/.hermes-cortex/web-cache/web_cache.py"

if [ ! -f "$SCRIPT" ]; then
    # Fallback to repo location
    SCRIPT="$HOME/hermes-cortex/src/web-cache/web_cache.py"
fi

if [ ! -f "$SCRIPT" ]; then
    echo "Error: web_cache.py not found" >&2
    exit 1
fi

exec "$VENV_PYTHON" "$SCRIPT" "$@"
