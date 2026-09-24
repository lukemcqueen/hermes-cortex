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
#   VICTORIA_METRICS_URL=http://metrics.example.com:8428/api/v1/import/prometheus \
#     bash push-metrics.sh                        # push to specific host
#   VICTORIA_METRICS_FALLBACK_URL=... bash push-metrics.sh
#     # backup sink (backup orchestrator / local VM) tried after the primary
#     # exhausts its retries — keeps pushes flowing while the primary
#     # orchestrator is unreachable (2026-08-31).
#
# Exit code:
#   0 = pushed successfully
#   1 = push failed after all retries
# ──────────────────────────────────────────────────────────────

set -euo pipefail

# ── Source env (deploy-root .env preferred; old hermes-cortex.env fallback) ──
ENV_FILE="${HOME}/.hermes-cortex/.env"
if [ ! -f "$ENV_FILE" ]; then
  ENV_FILE="${HOME}/.hermes-cortex/hermes-cortex.env"
fi
if [ -f "$ENV_FILE" ]; then
  set -a; source "$ENV_FILE" 2>/dev/null || true; set +a
fi

# ── Config ──────────────────────────────────────────────────
# Agent identity — env → agent.env → .env. NEVER hostname: a machine name is
# not an agent name and would misattribute metrics (Luke directive 2026-08-14).
AGENT_NAME="${AGENT_NAME:-}"
if [ -z "$AGENT_NAME" ] && [ -f "${HOME}/.hermes-cortex/agent.env" ]; then
  AGENT_NAME=$(grep -E '^AGENT_NAME=' "${HOME}/.hermes-cortex/agent.env" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")
fi
if [ -z "$AGENT_NAME" ] && [ -f "${HOME}/hermes-cortex/.env" ]; then
  AGENT_NAME=$(grep -E '^AGENT_NAME=' "${HOME}/hermes-cortex/.env" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")
fi
if [ -z "$AGENT_NAME" ] || [ "$AGENT_NAME" = "unknown" ]; then
  echo "[push-metrics] ❌ AGENT_NAME not configured — set AGENT_NAME= in ~/.hermes-cortex/agent.env / ~/hermes-cortex/.env or export AGENT_NAME" >&2
  exit 1
fi

# ── Source environment (already sourced above; kept for cron clarity) ──
# Cron scheduler does not source the env file before running no_agent
# scripts, so the script sources it itself (deploy-repo .env preferred,
# old hermes-cortex.env fallback).
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
VICTORIA_FALLBACK_URL="${VICTORIA_METRICS_FALLBACK_URL:-}"
export VICTORIA_FALLBACK_URL

MAX_RETRIES=3
RETRY_DELAY=2
OS="$(uname)"

# ── Failure accounting (2026-09-23) ──────────────────────────
# Why: this cron runs every 5m on EVERY host (288 runs/day). When the sink is
# legitimately dead — e.g. the xx005 reverse proxy was never deployed, which
# needs root to fix — the old script exited 1 on every tick. That produced 1053
# consecutive failures, an escalation loop (sensor → P1 issue → task reopen →
# governance cycle) and a cron the watchdog kept pausing, for a condition no
# agent could fix. Bounded alerting keeps the signal and drops the churn:
#   - first failure of a streak   → exit 1 (alert, self-diagnosing)
#   - same streak inside cooldown → exit 0, one suppressed line to stderr
#   - cooldown elapsed            → exit 1 again (re-alert)
#   - recovery                    → exit 0 + recovery line, state cleared
# Fail-closed: if the state file cannot be written we CANNOT prove we already
# alerted, so we alert on every run rather than silently suppressing.
STATE_FILE="${PUSH_METRICS_STATE_FILE:-${HOME}/.hermes-cortex/state/push-metrics.state}"
ALERT_COOLDOWN_S="${PUSH_METRICS_ALERT_COOLDOWN_S:-21600}"   # 6h
CURL_BIN="${PUSH_METRICS_CURL:-curl}"
LAST_STATUS=""

_state_get() {
  # Read one key from the state file; prints nothing when missing.
  [ -f "$STATE_FILE" ] || return 0
  grep -E "^$1=" "$STATE_FILE" 2>/dev/null | sed -n '1p' | cut -d= -f2-
}

_state_write() {
  # Non-zero exit means "cannot track" → caller must alert, never suppress.
  local dir
  dir="$(dirname "$STATE_FILE")"
  mkdir -p "$dir" 2>/dev/null || return 1
  printf '%s\n' "$@" > "${STATE_FILE}.tmp" 2>/dev/null || return 1
  mv "${STATE_FILE}.tmp" "$STATE_FILE" 2>/dev/null || return 1
  return 0
}

_state_clear() {
  rm -f "$STATE_FILE" "${STATE_FILE}.tmp" 2>/dev/null || true
}

_human_age() {
  local secs="${1:-0}"
  [ "$secs" -gt 0 ] 2>/dev/null || { printf '0m'; return 0; }
  if [ "$secs" -lt 3600 ]; then printf '%dm' $((secs / 60));
  elif [ "$secs" -lt 86400 ]; then printf '%dh' $((secs / 3600));
  else printf '%dd' $((secs / 86400)); fi
}

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

sanitize_url() {
  # Strip basic-auth userinfo (user:pass@) from a URL for safe logging —
  # never leak tokens into cron logs/transcripts.
  printf '%s' "$1" | sed -E 's#//[^/@]*@#//<redacted>@#'
}

push_metrics() {
  local metrics status url
  metrics=$(collect_metrics)

  for url in "${VICTORIA_URL}" "${VICTORIA_FALLBACK_URL:-}"; do
    [ -n "$url" ] || continue
    for attempt in $(seq 1 "${MAX_RETRIES}"); do
      # Bounded curl (2026-08-05): a dead endpoint must fail fast, not hang the
      # cron — Gisu reported a curl hang on a downed VictoriaMetrics proxy that
      # held the whole tick. --max-time caps the total transfer; the connect
      # timeout catches an unresponsive host quickly.
      local curl_args=("-s" "-X" "POST" "${url}"
        "-H" "Content-Type: text/plain; version=0.4.0"
        "--data-binary" "@-"
        "--max-time" "20" "--connect-timeout" "5"
        "-w" "%{http_code}" "-o" "/dev/null")

      status=$(echo "${metrics}" | "$CURL_BIN" "${curl_args[@]}")
      LAST_STATUS="${status}"

      if [ "${status}" = "204" ]; then
        return 0
      fi

      echo "[push-metrics] attempt ${attempt}/${MAX_RETRIES} on $(sanitize_url "${url}"): HTTP ${status}" >&2
      if [ "${attempt}" -lt "${MAX_RETRIES}" ]; then
        sleep "${RETRY_DELAY}"
      fi
    done
    echo "[push-metrics] $(sanitize_url "${url}") unreachable — trying fallback sink" >&2
  done

  return 1
}

# ── Main ─────────────────────────────────────────────────────

now="$(date +%s)"
consec="$(_state_get CONSECUTIVE)"; case "$consec" in ''|*[!0-9]*) consec=0 ;; esac
first_fail="$(_state_get FIRST_FAILURE)"; case "$first_fail" in ''|*[!0-9]*) first_fail=0 ;; esac
last_alert="$(_state_get LAST_ALERT)"; case "$last_alert" in ''|*[!0-9]*) last_alert=0 ;; esac

sinks="$(sanitize_url "${VICTORIA_URL}")"
if [ -n "${VICTORIA_FALLBACK_URL}" ]; then
  sinks="${sinks} + $(sanitize_url "${VICTORIA_FALLBACK_URL}")"
fi

if push_metrics; then
  if [ "$consec" -gt 0 ]; then
    echo "[push-metrics] ✓ sink reachable again after ${consec} consecutive failure(s) over $( _human_age "$(( now - first_fail ))" ) — alert state cleared" >&2
    _state_clear
  fi
  exit 0
fi

# ── Failure path — bounded alerting (see config block for the why) ──
consec=$((consec + 1))
if [ "$first_fail" -eq 0 ]; then
  first_fail="$now"
fi

alert=0
alert_why=""
if [ "$consec" -eq 1 ]; then
  alert=1
  alert_why="first failure of this streak"
elif [ $(( now - last_alert )) -ge "$ALERT_COOLDOWN_S" ]; then
  alert=1
  alert_why="alert cooldown ($( _human_age "$ALERT_COOLDOWN_S" )) elapsed"
fi

if [ "$alert" -eq 1 ]; then
  saved_alert="$now"
else
  saved_alert="$last_alert"
fi

if ! _state_write \
    "CONSECUTIVE=${consec}" \
    "FIRST_FAILURE=${first_fail}" \
    "LAST_FAILURE=${now}" \
    "LAST_ALERT=${saved_alert}" \
    "LAST_STATUS=${LAST_STATUS:-000}" \
    "SINKS=${sinks}"; then
  # Fail-closed: cannot prove a prior alert happened → alert every run.
  alert=1
  alert_why="state file not writable (${STATE_FILE}) — suppression impossible"
fi

outage_age=$(( now - first_fail ))

if [ "$alert" -eq 1 ]; then
  cat >&2 <<EOF
[push-metrics] ❌ SINK UNREACHABLE — ${alert_why}
  sinks       : ${sinks}
  last HTTP   : ${LAST_STATUS:-000}   (000 = refused/DNS/timeout; 401/403 = auth, not a dead sink)
  failing for : $( _human_age "$outage_age" ) (${consec} consecutive attempt(s); this cron runs every 5m)
  next alert  : suppressed for $( _human_age "$ALERT_COOLDOWN_S" ) from now — later ticks exit 0
  what to do  : the sink is the xx005 reverse proxy in front of VictoriaMetrics.
                On the host that owns the sink (an orchestrator): deploy it —
                docs/runbooks/push-metrics-nginx-deploy.md
                If this host is not supposed to push anywhere: unset
                VICTORIA_METRICS_URL in ${ENV_FILE} (pushing is optional; the
                script exits 0 quietly when it is unset).
EOF
  exit 1
fi

echo "[push-metrics] sink still down ($( _human_age "$outage_age" ), ${consec} attempts, last HTTP ${LAST_STATUS:-000}) — alert already sent, next in $( _human_age "$(( ALERT_COOLDOWN_S - (now - last_alert) ))" )" >&2
exit 0
