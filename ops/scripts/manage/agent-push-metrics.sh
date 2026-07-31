#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# push-metrics.sh — Agent Metrics Push Script
#
# Collects system-level metrics and pushes them to VictoriaMetrics
# using the Prometheus-compatible push endpoint.
#
# Supported OS: Linux, macOS
# Uses Prometheus text exposition format (v0.4.0).
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

# ── Source env (hermes-cortex.env) before configuration ─────
_env_file="${HOME}/.hermes-cortex/hermes-cortex.env"
if [ -f "$_env_file" ]; then
  set -a; source "$_env_file" 2>/dev/null || true; set +a
fi

# ── Config ──────────────────────────────────────────────────
AGENT_NAME="${AGENT_NAME:-$(hostname)}"

# ── Source environment ──────────────────────────────────────
# Cron scheduler does not source hermes-cortex.env before running no_agent scripts.
ENV_FILE="${HOME}/.hermes-cortex/hermes-cortex.env"
if [ -f "$ENV_FILE" ]; then
  # shellcheck source=/dev/null
  set -a; source "$ENV_FILE"; set +a
fi

# VictoriaMetrics URL — optional; skip silently if not configured
if [ -z "${VICTORIA_METRICS_URL:-}" ]; then
  echo "[push-metrics] VICTORIA_METRICS_URL not set — metrics push disabled (this is optional)" >&2
  exit 0
fi
VICTORIA_URL="$VICTORIA_METRICS_URL"
export VICTORIA_URL

MAX_RETRIES=3
RETRY_DELAY=2
OS="$(uname)"

# ── Metric Collection ────────────────────────────────────────

collect_metrics() {
  local tag="agent=\"${AGENT_NAME}\""

  # ── CPU usage ──
  if [ "$OS" = "Darwin" ]; then
    cpu_pct=$(ps -A -o %cpu | awk '{s+=$1} END {printf "%.1f", s}' 2>/dev/null || echo "0")
  else
    cpu_pct=$(top -bn1 2>/dev/null | awk '/Cpu\(s\)/ {print 100-$8}' || echo "0")
  fi

  # ── Load average ──
  load=$(awk '{print $1,$2,$3}' /proc/loadavg 2>/dev/null || sysctl -n vm.loadavg 2>/dev/null | awk '{print $2,$3,$4}' || echo "0 0 0")
  load_1=$(echo "$load" | awk '{print $1}')
  load_5=$(echo "$load" | awk '{print $2}')
  load_15=$(echo "$load" | awk '{print $3}')

  # ── Memory ──
  if [ "$OS" = "Darwin" ]; then
    # macOS: use vm_stat + sysctl
    mem_total=$(sysctl -n hw.memsize 2>/dev/null || echo "0")
    page_size=$(vm_stat 2>/dev/null | awk '/page size of/ {print $8}' || echo "4096")
    pages_active=$(vm_stat 2>/dev/null | awk '/Pages active/ {print $3}' | tr -d '.' || echo "0")
    pages_wired=$(vm_stat 2>/dev/null | awk '/Pages wired/ {print $4}' | tr -d '.' || echo "0")
    pages_compressed=$(vm_stat 2>/dev/null | awk '/Pages occupied/ {print $5}' | tr -d '.' || echo "0")
    mem_used=$(( (pages_active + pages_wired + pages_compressed) * page_size ))
    # No easy 'free' equivalent on macOS; approximate via memory_pressure
    mem_free_pct=$(memory_pressure 2>/dev/null | awk '/percentage/ {print $5}' | tr -d '%' || echo "0")
    mem_used_pct=$((100 - mem_free_pct))
    # Cached approximated from file-backed pages
    pages_file=$(vm_stat 2>/dev/null | awk '/File-backed/ {print $3}' | tr -d '.' || echo "0")
    mem_cached=$(( pages_file * page_size ))
    mem_total_mb=$(( mem_total / 1048576 ))
    mem_used_mb=$(( mem_used / 1048576 ))
    mem_cached_mb=$(( mem_cached / 1048576 ))
    # Available approximated as total - used (no free(1) equivalent on macOS)
    mem_avail_mb=$(( mem_total_mb - mem_used_mb ))
    [ "$mem_avail_mb" -lt 0 ] && mem_avail_mb=0

    # Swap (macOS)
    swap_total=$(sysctl -n vm.swapusage 2>/dev/null | awk '{print $4}' | tr -d 'M' || echo "0")
    swap_used=$(sysctl -n vm.swapusage 2>/dev/null | awk '{print $7}' | tr -d 'M' || echo "0")
    swap_total_mb=$(echo "$swap_total" | awk '{printf "%.0f", $1}')
    swap_used_mb=$(echo "$swap_used" | awk '{printf "%.0f", $1}')
  else
    # Linux: use /proc/meminfo
    mem_total_kb=$(awk '/MemTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo "0")
    mem_avail_kb=$(awk '/MemAvailable/ {print $2}' /proc/meminfo 2>/dev/null || echo "0")
    mem_free_kb=$(awk '/MemFree/ {print $2}' /proc/meminfo 2>/dev/null || echo "0")
    mem_cached_kb=$(awk '/^Cached:/ {print $2}' /proc/meminfo 2>/dev/null || echo "0")
    mem_buffers_kb=$(awk '/Buffers/ {print $2}' /proc/meminfo 2>/dev/null || echo "0")
    mem_used_kb=$(( mem_total_kb - mem_avail_kb ))
    [ "$mem_total_kb" -gt 0 ] && mem_used_pct=$(awk "BEGIN {printf \"%.1f\", ${mem_used_kb}/${mem_total_kb}*100}") || mem_used_pct="0"
    mem_total_mb=$(( mem_total_kb / 1024 ))
    mem_used_mb=$(( mem_used_kb / 1024 ))
    mem_avail_mb=$(( mem_avail_kb / 1024 ))
    mem_cached_mb=$(( mem_cached_kb / 1024 ))

    # Swap (Linux)
    swap_total_kb=$(awk '/SwapTotal/ {print $2}' /proc/meminfo 2>/dev/null || echo "0")
    swap_free_kb=$(awk '/SwapFree/ {print $2}' /proc/meminfo 2>/dev/null || echo "0")
    [ "$swap_total_kb" -gt 0 ] && swap_used_pct=$(awk "BEGIN {printf \"%.1f\", (${swap_total_kb} - ${swap_free_kb})/${swap_total_kb}*100}") || swap_used_pct="0"
    swap_total_mb=$(( swap_total_kb / 1024 ))
    swap_used_mb=$(( (swap_total_kb - swap_free_kb) / 1024 ))
  fi

  # ── Disk usage (all mount points) ──
  disk_metrics=""
  while IFS= read -r line; do
    mount=$(echo "$line" | awk '{print $6}')
    pct=$(echo "$line" | awk '{print $5}' | tr -d '%')
    used=$(echo "$line" | awk '{print $3}')
    total=$(echo "$line" | awk '{print $2}')
    [ -n "$mount" ] && [ -n "$pct" ] && disk_metrics="${disk_metrics}
node_disk_used_percent{mount=\"${mount}\",${tag}} ${pct}
node_disk_used_bytes{mount=\"${mount}\",${tag}} ${used}
node_disk_total_bytes{mount=\"${mount}\",${tag}} ${total}"
  done < <(df -B1 / /boot /var /home /data 2>/dev/null | awk 'NR>1 {print $2,$3,$5,$6}' || df -B1 / 2>/dev/null | awk 'NR>1 {print $2,$3,$5,$6}')

  # ── Network I/O ──
  if [ "$OS" = "Darwin" ]; then
    net_rx=$(netstat -ib 2>/dev/null | awk '/en0/ {sum+=$7} END {print sum+0}' || echo "0")
    net_tx=$(netstat -ib 2>/dev/null | awk '/en0/ {sum+=$10} END {print sum+0}' || echo "0")
  else
    net_rx=$(awk '/eth0:|ens[0-9]:|enp[0-9]/ {rx=$2} END {print rx+0}' /proc/net/dev 2>/dev/null || echo "0")
    net_tx=$(awk '/eth0:|ens[0-9]:|enp[0-9]/ {tx=$10} END {print tx+0}' /proc/net/dev 2>/dev/null || echo "0")
  fi

  # ── Processes ──
  proc_count=$(ps -e 2>/dev/null | wc -l | tr -d ' ' || echo "0")
  proc_running=$(ps -eo stat 2>/dev/null | grep -c "^R" || echo "0")

  # ── Uptime ──
  if [ "$OS" = "Darwin" ]; then
    boot_epoch=$(sysctl -n kern.boottime 2>/dev/null | awk -F'[= ,]' '{print $6}' || echo "0")
    uptime_seconds=$(( $(date +%s) - boot_epoch ))
  else
    uptime_seconds=$(awk '{print $1}' /proc/uptime 2>/dev/null | cut -d. -f1 || echo "0")
  fi

  # ── I/O wait (Linux only) ──
  io_wait=""
  if [ "$OS" != "Darwin" ]; then
    io_wait=$(top -bn1 2>/dev/null | awk '/Cpu\(s\)/ {print $10}' | tr -d 'wa,' || echo "0")
  fi

  # Output Prometheus-format metrics
  cat <<METRICS
# HELP node_cpu_usage_percent CPU usage percentage (instant snapshot)
# TYPE node_cpu_usage_percent gauge
node_cpu_usage_percent{${tag}} ${cpu_pct}
# HELP node_load1 Load average (1 minute)
# TYPE node_load1 gauge
node_load1{${tag}} ${load_1}
# HELP node_load5 Load average (5 minutes)
# TYPE node_load5 gauge
node_load5{${tag}} ${load_5}
# HELP node_load15 Load average (15 minutes)
# TYPE node_load15 gauge
node_load15{${tag}} ${load_15}
# HELP node_memory_total_bytes Total physical memory
# TYPE node_memory_total_bytes gauge
node_memory_total_bytes{${tag}} $((mem_total_mb * 1048576))
# HELP node_memory_used_bytes Used memory (total - available)
# TYPE node_memory_used_bytes gauge
node_memory_used_bytes{${tag}} $((mem_used_mb * 1048576))
# HELP node_memory_used_percent Memory usage percentage
# TYPE node_memory_used_percent gauge
node_memory_used_percent{${tag}} ${mem_used_pct}
# HELP node_memory_available_bytes Memory available for new processes
# TYPE node_memory_available_bytes gauge
node_memory_available_bytes{${tag}} $((mem_avail_mb * 1048576))
# HELP node_memory_cached_bytes Cache memory
# TYPE node_memory_cached_bytes gauge
node_memory_cached_bytes{${tag}} $((mem_cached_mb * 1048576))
# HELP node_swap_total_bytes Total swap space
# TYPE node_swap_total_bytes gauge
node_swap_total_bytes{${tag}} $((swap_total_mb * 1048576))
# HELP node_swap_used_bytes Used swap space
# TYPE node_swap_used_bytes gauge
node_swap_used_bytes{${tag}} $((swap_used_mb * 1048576))
# HELP node_network_receive_bytes_total Network bytes received (cumulative)
# TYPE node_network_receive_bytes_total counter
node_network_receive_bytes_total{${tag}} ${net_rx}
# HELP node_network_transmit_bytes_total Network bytes transmitted (cumulative)
# TYPE node_network_transmit_bytes_total counter
node_network_transmit_bytes_total{${tag}} ${net_tx}
# HELP node_processes_total Total number of processes
# TYPE node_processes_total gauge
node_processes_total{${tag}} ${proc_count}
# HELP node_processes_running Number of running processes
# TYPE node_processes_running gauge
node_processes_running{${tag}} ${proc_running}
# HELP node_uptime_seconds System uptime in seconds
# TYPE node_uptime_seconds gauge
node_uptime_seconds{${tag}} ${uptime_seconds}
METRICS
if [ -n "$io_wait" ]; then
  echo "# HELP node_iowait_percent I/O wait time percentage
# TYPE node_iowait_percent gauge
node_iowait_percent{${tag}} ${io_wait}"
fi
echo "$disk_metrics"
}

# ── Push ─────────────────────────────────────────────────────

push_metrics() {
  local metrics status
  metrics=$(collect_metrics)

  for attempt in $(seq 1 "${MAX_RETRIES}"); do
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
