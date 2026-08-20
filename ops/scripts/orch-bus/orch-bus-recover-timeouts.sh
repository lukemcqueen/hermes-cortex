#!/usr/bin/env bash
# bus-recover-timeouts.sh — no_agent cron; recovers stuck processing messages
# Silent until issue. Reports only when >=50 messages recovered/archived.
# Dedup (2026-08-20): a persistent stuck-message set must not re-deliver the
# same alert every 5 min — report only when the recovered count CHANGES.
set -euo pipefail

RESULT=$(sg docker -c "docker exec mycortex-postgres psql -U mycortex -d mycortex -t -c \
  \"SELECT bus.recover_timeouts();\"" 2>/dev/null | tr -d '[:space:]')

RECOVER_THRESHOLD=50  # silent below this — small timeouts are routine
STATE_FILE="$HOME/.hermes-cortex/state/bus-recover-timeouts.state"

LAST=""
if [ -f "$STATE_FILE" ]; then
  LAST=$(cat "$STATE_FILE" 2>/dev/null || true)
fi

if [ -n "$RESULT" ] && [ "$RESULT" -ge "$RECOVER_THRESHOLD" ] 2>/dev/null && [ "$RESULT" != "$LAST" ]; then
  echo "⏰ Recovered $RESULT message(s) (processing→pending/DLQ/archive)."
fi

if [ -n "$RESULT" ]; then
  mkdir -p "$(dirname "$STATE_FILE")"
  echo "$RESULT" > "$STATE_FILE"
fi
