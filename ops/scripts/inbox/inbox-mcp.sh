#!/usr/bin/env bash
# Wrapper for inbox-mcp.py — uses dedicated venv with mcp package
exec ~/.hermes-cortex/mcp-servers/venv/bin/python3 "$HOME/.hermes-cortex/scripts/inbox-mcp-updated.py" "$@"
