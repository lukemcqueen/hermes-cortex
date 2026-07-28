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
# Derive VM URL the same way push-metrics.sh does
VM_URL=""
bus_conf="${CORTEX_BUS_CONF:-${HOME}/.hermes-cortex/cortex-bus.conf}"
if [ -f "$bus_conf" ]; then
  # shellcheck source=/dev/null
  source "$bus_conf" 2>/dev/null || true
  if [ -n "${CORTEX_BUS_URL:-}" ]; then
    bus_host=$(echo "$CORTEX_BUS_URL" | sed -E 's|^https?://([^:/]+).*|\1|')
    VM_URL="https://${bus_host}:13005/api/v1/import/prometheus"
  fi
fi

if [ -n "$VM_URL" ]; then
  # Check reachability with auth from cortex-bus.conf
  vm_auth=""
  if [ -n "${CORTEX_BASIC_AUTH}" ]; then
    vm_auth="-u ${CORTEX_BASIC_AUTH}"
  fi
  if ! curl -sf ${vm_auth:-} -o /dev/null --connect-timeout 5 "${VM_URL%/*}" >/dev/null 2>&1; then
    echo "[setup-push-metrics] ⚠️  VictoriaMetrics not reachable at ${VM_URL%/*} — skipping cron install"
    echo "[setup-push-metrics] Run this script again after nginx :13005 is deployed."
    exit 0
  fi
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
