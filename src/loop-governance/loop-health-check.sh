#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Loop Governance — Health Check Script (for cron/auto-pilot)
#  Runs verify.sh, attempts auto-repair, and exposes results
#  to the system-alert pipeline.
#
#  Designed to be called from a no_agent cron every 10 minutes.
#  Silent on success — alerts only on failure.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

INSTALL_DIR="${HOME}/.hermes-cortex/tools/loop-governance"
[[ -d "$INSTALL_DIR" ]] || INSTALL_DIR="${HOME}/hermes-cortex/src/loop-governance"
[[ -d "$INSTALL_DIR" ]] || { echo "LOOP-GOVERNANCE:NOT-FOUND"; exit 1; }

# Run quick verify, get JSON output
RESULT=$(bash "${INSTALL_DIR}/verify.sh" --quick --json 2>/dev/null || echo '{"failed":1,"checks":[{"status":"fail","check":"verify.sh failed to run"}]}')

# Extract counts (bash-safe approach)
FAILED=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('failed',0))" 2>/dev/null || echo "1")

if [[ "$FAILED" != "0" ]]; then
  # Extract details for alert message
  FAIL_CHECKS=$(echo "$RESULT" | python3 -c "
import sys,json
d=json.load(sys.stdin)
fails = [c['check'] for c in d.get('checks',[]) if c['status'] != 'pass']
print('; '.join(fails))
" 2>/dev/null || echo "Unknown failure")

  echo "LOOP-GOVERNANCE:UNHEALTHY"
  echo "failed=$FAILED"
  echo "issues=$FAIL_CHECKS"

  # Auto-fix: if Ollama is the problem, try to restart it
  if echo "$FAIL_CHECKS" | grep -qi "ollama"; then
    echo "action=restarting-ollama"
    if command -v ollama &>/dev/null; then
      ollama serve &>/dev/null &
      # Retry up to 10 seconds (macOS can be slow to start)
      for i in 1 2 3 4 5; do
        sleep 2
        if curl -sf http://localhost:11434/api/tags &>/dev/null; then
          echo "action=ollama-restarted"
          break
        fi
        if [[ "$i" == "5" ]]; then
          echo "action=ollama-restart-failed"
        fi
      done
    fi
  fi
  exit 1
fi

# Healthy — silent exit (no_agent cron won't deliver anything)
exit 0