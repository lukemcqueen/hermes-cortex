#!/usr/bin/env bash
# Wrapper for offline_code.py — resolves symlinks to find the real script dir
SCRIPT_DIR="$(cd "$(dirname "$(perl -MCwd -le 'print Cwd::abs_path(shift)' "${BASH_SOURCE[0]}")")" && pwd)"
exec python3 "$SCRIPT_DIR/offline_code.py" "$@"
