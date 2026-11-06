#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  fleet-health.sh — Quick system readiness check
#
#  Delegates to fleet-doctor.py --quick for all checks.
#  Preserves original --json and --watch flags.
#
#  Usage:
#    bash fleet-health.sh              # quick status table
#    bash fleet-health.sh --json       # JSON output
#    bash fleet-health.sh --watch      # every 5s (like htop)
# ─────────────────────────────────────────────────────────────
set -euo pipefail

JSON_MODE=false
WATCH_MODE=false

for arg in "$@"; do
  case "$arg" in
    --json) JSON_MODE=true ;;
    --watch) WATCH_MODE=true ;;
  esac
done

# Locate fleet-doctor.py
DOCTOR=""
for candidate in fleet-doctor.py ~/.steadfaste-fleet/scripts/fleet-doctor.py ~/steadfaste-fleet/ops/scripts/manage/fleet-doctor.py; do
  if resolved=$(command -v "$candidate" 2>/dev/null); then
    DOCTOR="$resolved"
    break
  fi
done

if [[ -z "$DOCTOR" ]]; then
  echo "❌ fleet-doctor.py not found"
  exit 1
fi

if $WATCH_MODE; then
  echo "🔍 Watching system health (Ctrl+C to stop)..."
  while true; do
    clear 2>/dev/null || true
    printf "\n  $(date '+%H:%M:%S')  ── fleet-doctor quick check ──\n"
    python3 "$DOCTOR" --quick ${JSON_MODE:+--json} 2>&1
    sleep 5
  done
else
  exec python3 "$DOCTOR" --quick ${JSON_MODE:+--json}
fi
