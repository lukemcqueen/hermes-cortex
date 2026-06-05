#!/usr/bin/env bash
# Wrapper for offline_code.py — symlink to ~/.hermes/bin/offline_code
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/offline_code.py" "$@"
