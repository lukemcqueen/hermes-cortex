#!/usr/bin/env bash
# offline_code_index_cron.sh — Weekly offline code corpus index rebuild
#
# Rebuilds the offline code search index so new snippets added via
# offline_code learn are discoverable in future searches.
#
# Watchdog pattern:
#   Empty stdout → silent (index already current or nothing new)
#   Text output  → delivered (index rebuilt)
set -euo pipefail

OFFLINE_CODE="${HOME}/.hermes/bin/offline_code"

if [ ! -x "$OFFLINE_CODE" ]; then
    echo "[offline-code-index] offline_code CLI not found at $OFFLINE_CODE"
    echo "  Install: ln -sf ~/hermes-cortex/ops/offline/offline_code.sh ~/.hermes/bin/offline_code"
    exit 1
fi

# Run index — incremental, only rebuilds when snippet count changes
OUTPUT=$("$OFFLINE_CODE" index 2>&1) || {
    echo "[offline-code-index] Index rebuild failed"
    echo "$OUTPUT"
    exit 1
}

# Silent when nothing changed (index was already current)
if echo "$OUTPUT" | grep -q "already current\|up to date\|nothing to index\|Index is current"; then
    exit 0
fi

# Index was rebuilt or had activity — report it
echo "$OUTPUT"