#!/usr/bin/env bash
# offline-code-index.sh — Rebuild the offline code search index
# Runs weekly. Silent when successful (no news is good news).
set -euo pipefail
export PATH="$HOME/.hermes/bin:$HOME/.bun/bin:/usr/local/bin:/usr/bin:/bin"
offline_code index 2>&1 || echo "offline-code-index: rebuild failed (exit $?)"
