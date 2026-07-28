#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# push-metrics.sh — Standalone Agent Metrics Push Script
#
# Collects system-level metrics and pushes them to VictoriaMetrics
# using the Prometheus-compatible push endpoint.
#
# Uses Prometheus text exposition format (v0.4.0).
# Can be called from cron or systemd timer.
#
# Usage:
#   bash push-metrics.sh                          # push to default URL
#   VICTORIA_METRICS_URL=http://central:8428/api/v1/import/prometheus \
#     bash push-metrics.sh                        # push to specific host
#
# Exit code:
#   0 = pushed successfully
#   1 = push failed after all retries
# ──────────────────────────────────────────────────────────────

set -euo pipefail

# ── Config ──────────────────────────────────────────────────
AGENT_NAME="${AGENT_NAME:-$(hostname)}"

# Determine VictoriaMetrics URL
if [ -n "${VICTORIA_METRICS_URL:-}" ]; then
  VICTORIA_URL="$VICTORIA_METRICS_URL"
else
  # Default: try localhost first (works when running on Moses server)
  VICTORIA_URL="http://localhost:8428/api/v1/import/prometheus"

  # Source cortex-bus.conf to get the Moses bus URL (every agent has this)
  bus_conf="${CORTEX_BUS_CONF:-${HOME}/.hermes-cortex/cortex-bus.conf}"
  if [ -f "$bus_conf" ]; then
    # shellcheck source=/dev/null
    source "$bus_conf" 2>/dev/null || true
    if [ -n "${CORTEX_BUS_URL:-}" ]; then
      bus_host=$(echo "$CORTEX_BUS_URL" | sed -E 's|^https?://([^:/]+).*|\1|')
      if [ "$bus_host" != "127.0.0.1" ] && [ "$bus_host" != "localhost" ]; then
        # VictoriaMetrics is behind nginx on port 13005 (bus is 13004)
        VICTORIA_URL="https://${bus_host}:13005/api/v1/import/prometheus"
      fi
    fi
  fi
fi
export VICTORIA_URL

MAX_RETRIES=3
RETRY_DELAY=2

# ── Metric Collection ────────────────────────────────────────

collect_metrics() {
  local cpu_pct mem_pct disk_pct uptime_seconds

  # CPU usage (Linux /proc/stat delta handled by VictoriaMetrics rate())
  # This is a point-in-time snapshot; use rate(node_cpu_seconds_total) in Grafana
  cpu_pct=$(top -bn1 2>/dev/null | awk '/Cpu\(s\)/ {print 100-$8}' || echo "0")

  # Memory usage percentage
  mem_pct=$(free 2>/dev/null | awk '/Mem/ {printf "%.1f", $3/$2 * 100}' || echo "0")

  # Disk usage percentage (root partition)
  disk_pct=$(df / 2>/dev/null | awk 'NR==2 {print $5}' | tr -d '%' || echo "0")

  # Uptime in seconds
  uptime_seconds=$(awk '{print $1}' /proc/uptime 2>/dev/null || echo "0")

  # Output Prometheus-format metrics
  cat <<EOF
# HELP node_cpu_usage_percent CPU usage percentage (instant snapshot)
# TYPE node_cpu_usage_percent gauge
node_cpu_usage_percent{agent="${AGENT_NAME}"} ${cpu_pct}
# HELP node_memory_used_percent Memory usage percentage
# TYPE node_memory_used_percent gauge
node_memory_used_percent{agent="${AGENT_NAME}"} ${mem_pct}
# HELP node_disk_used_percent Root partition usage percentage
# TYPE node_disk_used_percent gauge
node_disk_used_percent{agent="${AGENT_NAME}"} ${disk_pct}
# HELP node_uptime_seconds System uptime in seconds
# TYPE node_uptime_seconds gauge
node_uptime_seconds{agent="${AGENT_NAME}"} ${uptime_seconds}
EOF
}

# ── Push ─────────────────────────────────────────────────────

push_metrics() {
  local metrics status

  metrics=$(collect_metrics)

  for attempt in $(seq 1 "${MAX_RETRIES}"); do
    status=$(echo "${metrics}" | curl -s -X POST "${VICTORIA_URL}" \
      -H "Content-Type: text/plain; version=0.4.0" \
      --data-binary @- \
      -w "%{http_code}" -o /dev/null)

    if [ "${status}" = "204" ]; then
      return 0
    fi

    echo "[push-metrics] attempt ${attempt}/${MAX_RETRIES}: HTTP ${status}" >&2
    if [ "${attempt}" -lt "${MAX_RETRIES}" ]; then
      sleep "${RETRY_DELAY}"
    fi
  done

  return 1
}

# ── Main ─────────────────────────────────────────────────────

if ! push_metrics; then
  echo "[push-metrics] FAILED — all retries exhausted" >&2
  exit 1
fi

exit 0
