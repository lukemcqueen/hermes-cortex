#!/usr/bin/env bash
# orch-bus-recover-timeouts.sh — no_agent cron; recovers stuck processing messages
# Silent until issue. Reports only when >=50 messages recovered/archived.
set -euo pipefail

RESULT=$(sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -t -c \
  \"SELECT bus.recover_timeouts();\"" 2>/dev/null | tr -d '[:space:]')

RECOVER_THRESHOLD=50  # silent below this — small timeouts are routine

if [ -n "$RESULT" ] && [ "$RESULT" -ge "$RECOVER_THRESHOLD" ] 2>/dev/null; then
  echo "⏰ Recovered $RESULT message(s) (processing→pending/DLQ/archive)."
fi
