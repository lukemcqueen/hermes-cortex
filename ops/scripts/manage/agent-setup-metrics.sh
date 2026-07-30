#!/bin/bash
# ──────────────────────────────────────────────────────────────
# agent-setup-metrics.sh — Bootstrap metrics push on a fleet agent
#
# One-time setup script. Reads cortex-bus.conf for the Moses host
# and auth, configures hermes-cortex.env, creates the cron, and
# does a test push. Reports results at each step.
#
# Run via EXEC after UPDATE_REQUEST deploys the latest scripts.
# ──────────────────────────────────────────────────────────────
set -euo pipefail

echo "[agent-setup-metrics] === Metrics push setup ==="

# ── 1. Source cortex-bus.conf ──
bus_conf="${CORTEX_BUS_CONF:-${HOME}/.hermes-cortex/cortex-bus.conf}"
if [ ! -f "$bus_conf" ]; then
  echo "[agent-setup-metrics] ❌ cortex-bus.conf not found at $bus_conf"
  exit 1
fi
# shellcheck source=/dev/null
source "$bus_conf"

if [ -z "${CORTEX_BUS_URL:-}" ] || [ -z "${CORTEX_BASIC_AUTH:-}" ]; then
  echo "[agent-setup-metrics] ❌ cortex-bus.conf missing CORTEX_BUS_URL or CORTEX_BASIC_AUTH"
  exit 1
fi

bus_host=$(echo "$CORTEX_BUS_URL" | sed -E 's|^https?://([^:/]+).*|\1|')
VM_URL="https://${CORTEX_BASIC_AUTH}@${bus_host}:13005/api/v1/import/prometheus"
echo "[agent-setup-metrics] ✅ Derived VICTORIA_METRICS_URL from cortex-bus.conf"

# ── 2. Set env var in hermes-cortex.env ──
env_file="${HOME}/.hermes-cortex/hermes-cortex.env"
if grep -q "VICTORIA_METRICS_URL" "$env_file" 2>/dev/null; then
  echo "[agent-setup-metrics] ⏭️  VICTORIA_METRICS_URL already in ${env_file}"
else
  echo "VICTORIA_METRICS_URL=${VM_URL}" >> "$env_file"
  echo "[agent-setup-metrics] ✅ Wrote VICTORIA_METRICS_URL to ${env_file}"
fi

# Source it for the current shell and export so child processes see it
# shellcheck source=/dev/null
set -a; source "$env_file" 2>/dev/null || true; set +a

# ── 3. Pre-flight check ──
echo "[agent-setup-metrics] Checking VictoriaMetrics reachability..."
base_url=$(echo "$VICTORIA_METRICS_URL" | sed 's|/api/v1/import/prometheus$||')
if curl -sf -o /dev/null --connect-timeout 5 "${base_url}/health" 2>/dev/null; then
  echo "[agent-setup-metrics] ✅ VictoriaMetrics reachable at ${base_url}"
else
  echo "[agent-setup-metrics] ⚠️  VictoriaMetrics not reachable at ${base_url}"
  echo "[agent-setup-metrics]    The cron will push when it becomes available."
fi

# ── 4. Run setup-push-metrics-cron.sh ──
echo "[agent-setup-metrics] Creating cron (if not exists)..."
if [ -f "${HOME}/.hermes-cortex/scripts/setup-push-metrics-cron.sh" ]; then
  bash "${HOME}/.hermes-cortex/scripts/setup-push-metrics-cron.sh" 2>&1
  echo "[agent-setup-metrics] ✅ setup-push-metrics-cron.sh completed"
else
  echo "[agent-setup-metrics] ⚠️  setup-push-metrics-cron.sh not found — may need UPDATE_REQUEST first"
fi

# ── 5. Test push ──
echo "[agent-setup-metrics] Testing metrics push..."
if [ -f "${HOME}/.hermes-cortex/scripts/agent-push-metrics.sh" ]; then
  if bash "${HOME}/.hermes-cortex/scripts/agent-push-metrics.sh" 2>&1; then
    echo "[agent-setup-metrics] ✅ Test push SUCCEEDED"
  else
    echo "[agent-setup-metrics] ❌ Test push FAILED"
  fi
else
  echo "[agent-setup-metrics] ⚠️  agent-push-metrics.sh not found — may need UPDATE_REQUEST first"
fi

echo "[agent-setup-metrics] === Setup complete ==="
