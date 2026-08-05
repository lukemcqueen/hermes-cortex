#!/usr/bin/env bash
# recover-bus-timeouts.sh — no_agent cron; recovers stuck processing messages
# Silent when nothing to recover. Reports count when >0.
set -euo pipefail

RESULT=$(docker exec mycortex-postgres psql -U mycortex -d mycortex -t -c \
  "SELECT bus.recover_timeouts();" 2>/dev/null | tr -d '[:space:]')

if [ -n "$RESULT" ] && [ "$RESULT" != "0" ] && [ "$RESULT" != "0" ]; then
  echo "⏰ Recovered $RESULT stuck message(s) from processing back to pending."
fi
