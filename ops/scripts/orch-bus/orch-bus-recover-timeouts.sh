#!/usr/bin/env bash
# orch-bus-recover-timeouts.sh — no_agent cron; recovers stuck processing messages
# Silent until issue. Reports only when >0 messages recovered/archived.
set -euo pipefail

RESULT=$(sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -t -c \
  \"SELECT bus.recover_timeouts();\"" 2>/dev/null | tr -d '[:space:]')

if [ -n "$RESULT" ] && [ "$RESULT" != "0" ]; then
  echo "⏰ Recovered $RESULT message(s) (processing→pending/DLQ/archive)."
fi
