#!/usr/bin/env bash
# Wrapper for loop-gov-mcp.py — uses dedicated venv with mcp package
# P1-A hardening (2026-07-31): exec the IMMUTABLE deployed copy
# (~/.hermes-cortex/tools/loop-governance/), NOT the user-writable repo
# working tree. Editing the repo copy must not disable begin_change
# enforcement. The deployed copy is kept current by cortex-update.sh
# (register entry) and locked by hermes-plugin-lock.
exec ~/.hermes-cortex/mcp-servers/venv/bin/python3 "$HOME/.hermes-cortex/tools/loop-governance/loop-gov-mcp.py" "$@"
