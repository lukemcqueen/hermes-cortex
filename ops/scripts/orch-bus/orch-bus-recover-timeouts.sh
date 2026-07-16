#!/usr/bin/env bash
# recover-bus-timeouts.sh — no_agent cron; recovers stuck processing messages
# Silent when nothing to recover. Reports count when >0.
set -euo pipefail

RESULT=$(sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -t -c \\
  \"SELECT bus.recover_timeouts();\"" 2>/dev/null | tr -d '[:space:]')

if [ -n "$RESULT" ] && [ "$RESULT" != "0" ] && [ "$RESULT" != "0" ]; then
  echo "⏰ Recovered $RESULT stuck message(s) from processing back to pending."
fi
