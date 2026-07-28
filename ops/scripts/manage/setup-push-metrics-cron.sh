#!/bin/bash
# ──────────────────────────────────────────────────────────────
# setup-push-metrics-cron.sh — Install the agent-push-metrics cron
#
# Creates a no_agent cron that pushes system metrics to
# VictoriaMetrics every 5 minutes.
#
# Must be run on the agent machine after push-metrics.sh has
# been deployed (via cortex-update.sh).
#
# Pre-flight check: verifies VictoriaMetrics is reachable before
# creating the cron. Silent skip if unreachable (harmless for
# fresh agent installs where Moses hasn't deployed VM yet).
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

# ── Pre-flight: check VictoriaMetrics reachability ──────────
# Uses VICTORIA_METRICS_URL env var (same source as push-metrics.sh)
VM_URL="${VICTORIA_METRICS_URL:-}"
if [ -z "$VM_URL" ]; then
  echo "[setup-push-metrics] ⚠️  VICTORIA_METRICS_URL not set — cannot verify reachability"
  echo "[setup-push-metrics] Set it in hermes-cortex.env (~/.hermes-cortex/hermes-cortex.env)"
  echo "[setup-push-metrics] Example: VICTORIA_METRICS_URL=https://domain:13005/api/v1/import/prometheus"
  exit 0
fi

if ! curl -sf -o /dev/null --connect-timeout 5 "${VM_URL%/*}" >/dev/null 2>&1; then
  echo "[setup-push-metrics] ⚠️  VictoriaMetrics not reachable at ${VM_URL%/*} — skipping cron install"
  echo "[setup-push-metrics] Run this script again after port forwarding is set up for port 13005."
  exit 0
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
