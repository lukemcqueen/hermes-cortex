#!/bin/bash
# ──────────────────────────────────────────────────────────────
# setup-push-metrics-cron.sh — Install the agent-push-metrics cron
#
# Creates a no_agent cron that pushes system metrics to
# VictoriaMetrics every 5 minutes.
#
# Must be run on the agent machine after push-metrics.sh has
# been deployed (via cortex-update.sh).
# ──────────────────────────────────────────────────────────────
set -euo pipefail

CRON_NAME="agent-push-metrics"
CRON_SCHEDULE="every 5m"
SCRIPT_NAME="push-metrics.sh"

# Check if hermes CLI is available
if ! command -v hermes &>/dev/null; then
  echo "[setup-push-metrics] ERROR: hermes CLI not found — install Hermes Agent first"
  exit 1
fi

# Check if the cron already exists
if hermes cron list 2>/dev/null | grep -q "^Name:.*${CRON_NAME}"; then
  echo "[setup-push-metrics] Cron '${CRON_NAME}' already exists — no action needed"
  exit 0
fi

# Create the cron (hermes cron create <schedule> --name ... --script ... --no-agent --deliver ...)
hermes cron create "${CRON_SCHEDULE}" \
  --name "${CRON_NAME}" \
  --no-agent \
  --script "${SCRIPT_NAME}" \
  --deliver local

echo "[setup-push-metrics] ✅ Cron '${CRON_NAME}' created (every 5m, no_agent, local delivery)"
