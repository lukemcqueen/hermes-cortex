#!/usr/bin/env bash
# Wrapper for loop-gov-mcp.py — uses dedicated venv with mcp package
exec ~/.hermes/mcp-servers/venv/bin/python3 "$HOME/hermes-cortex/src/mcp-servers/loop-gov-mcp.py" "$@"
