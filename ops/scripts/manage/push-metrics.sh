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

# VictoriaMetrics URL — REQUIRED. Set in hermes-cortex.env or ~/.hermes/.env.
# Example: VICTORIA_METRICS_URL=https://domain:13005/api/v1/import/prometheus
if [ -z "${VICTORIA_METRICS_URL:-}" ]; then
  echo "[push-metrics] ERROR: VICTORIA_METRICS_URL not set — configure in hermes-cortex.env" >&2
  exit 1
fi
VICTORIA_URL="$VICTORIA_METRICS_URL"
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
    # Build curl args — add basic auth if available from cortex-bus.conf
    local curl_args=("-s" "-X" "POST" "${VICTORIA_URL}"
      "-H" "Content-Type: text/plain; version=0.4.0"
      "--data-binary" "@-"
      "-w" "%{http_code}" "-o" "/dev/null")

    status=$(echo "${metrics}" | curl "${curl_args[@]}")

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
