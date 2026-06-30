#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  cortex-health.sh — Single green-check system readiness
#
#  Checks: Ollama, Langfuse, gbrain sources, sync daemon,
#          memory freshness, disk usage.
#
#  Prints a clean status table and exits 0 if all UP,
#  1 if any DEGRADED or DOWN.
#
#  Usage:
#    bash cortex-health.sh
#    bash cortex-health.sh --json    # machine-readable output
#    bash cortex-health.sh --watch   # re-check every 5s (like htop)
# ─────────────────────────────────────────────────────────────
set -euo pipefail

# ── Colors ──────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BOLD='\033[1m'; CYAN='\033[0;36m'; RESET='\033[0m'

# ── Config ──────────────────────────────────────────────────
BUN="${HOME}/.bun/bin/bun"
GBRAIN="${HOME}/.bun/bin/gbrain"
BRAIN_DIR="${HOME}/brain"
HERMES_HOME="${HERMES_HOME:-${HOME}/.hermes-cortex}"
JSON_MODE=false
WATCH_MODE=false
OVERALL="HEALTHY"

# ── Helpers ─────────────────────────────────────────────────
icon() {
  case "$1" in
    UP)       echo -e "${GREEN}●${RESET}" ;;
    DEGRADED) echo -e "${YELLOW}◐${RESET}" ;;
    DOWN)     echo -e "${RED}○${RESET}" ;;
    UNKNOWN)  echo -e "${CYAN}◌${RESET}" ;;
    ERROR)    echo -e "${RED}⚠${RESET}" ;;
  esac
}

json_escape() {
  # Minimal JSON string escape for values
  echo "$1" | sed 's/"/\\"/g' | tr '\n' ' ' | sed 's/ *$//'
}

print_row() {
  local name="$1" status="$2" detail="$3"
  if $JSON_MODE; then
    echo "    {\"name\":\"$(json_escape "$name")\",\"status\":\"$status\",\"detail\":\"$(json_escape "$detail")\"}"
  else
    printf "  %s %-26s %-10s %s\n" "$(icon "$status")" "$name" "$status" "$detail"
  fi
}

aggregate() {
  local status="$1"
  case "$status" in
    DOWN)    OVERALL="CRITICAL" ;;
    ERROR)   [[ "$OVERALL" != "CRITICAL" ]] && OVERALL="ERROR" ;;
    DEGRADED) [[ "$OVERALL" == "HEALTHY" ]] && OVERALL="DEGRADED" ;;
  esac
}

# ── Checks ──────────────────────────────────────────────────

check_ollama() {
  local url="${OLLAMA_URL:-http://localhost:11434}"
  if command -v curl &>/dev/null; then
    if curl -sf "$url/api/tags" -o /dev/null --max-time 5 2>/dev/null; then
      print_row "Ollama" "UP" "$url"
    elif curl -sf "$url" -o /dev/null --max-time 3 2>/dev/null; then
      print_row "Ollama" "DEGRADED" "Responds but /api/tags failed"
    else
      print_row "Ollama" "DOWN" "No response on $url"
    fi
  else
    print_row "Ollama" "UNKNOWN" "curl not available"
  fi
}

check_langfuse() {
  local port="${LANGFUSE_PORT:-3000}"
  local url="http://localhost:$port"
  if command -v curl &>/dev/null; then
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 "$url/api/public/health" 2>/dev/null || echo "000")
    if [[ "$http_code" == "200" ]]; then
      print_row "Langfuse" "UP" "port $port, health OK"
    elif [[ "$http_code" == "000" ]]; then
      print_row "Langfuse" "DOWN" "No response on port $port"
    else
      print_row "Langfuse" "DEGRADED" "HTTP $http_code on port $port"
    fi
  else
    print_row "Langfuse" "UNKNOWN" "curl not available"
  fi
}

check_gbrain_sources() {
  if [[ ! -f "$GBRAIN" ]]; then
    print_row "gbrain" "DOWN" "Not installed at $GBRAIN"
    return
  fi
  local output
  output=$("$BUN" "$GBRAIN" sources list 2>/dev/null) || {
    print_row "gbrain" "DEGRADED" "CLI available but sources list failed"
    return
  }
  # Count sources with pages (format: "  name    type   N pages  ...")
  local total=0 zero_pages=0 never_synced=0
  while IFS= read -r line; do
    parts=($line)
    if [[ ${#parts[@]} -ge 3 && "${parts[2]}" =~ ^[0-9]+$ ]]; then
      total=$((total + 1))
      [[ "${parts[2]}" == "0" ]] && zero_pages=$((zero_pages + 1))
      echo "$line" | grep -qi "never synced" && never_synced=$((never_synced + 1))
    fi
  done <<< "$output"

  if [[ "$total" -eq 0 ]]; then
    print_row "gbrain sources" "UNKNOWN" "No non-default sources registered"
    return
  fi
  local detail="$total source(s)"
  [[ "$zero_pages" -gt 0 ]] && detail="$detail, $zero_pages with 0 pages"
  [[ "$never_synced" -gt 0 ]] && detail="$detail, $never_synced never synced"
  if [[ "$zero_pages" -gt 0 || "$never_synced" -gt 0 ]]; then
    print_row "gbrain sources" "DEGRADED" "$detail"
  else
    print_row "gbrain sources" "UP" "$detail"
  fi
}

check_sync_daemon() {
  if [[ "$(uname -s)" == "Darwin" ]]; then
    # Prefer autopilot (self-maintaining daemon); fall back to sync-watch.
    local output
    output=$(launchctl list com.gbrain.autopilot 2>/dev/null) || \
      output=$(launchctl list com.gbrain.sync-watch 2>/dev/null) || {
      print_row "gbrain sync daemon" "DOWN" "Not registered with launchd"
      return
    }
    if echo "$output" | grep -q '"PID"'; then
      local pid
      pid=$(echo "$output" | grep -o '"PID"[[:space:]]*=[[:space:]]*[0-9]*' | grep -o '[0-9]*')
      print_row "gbrain sync daemon" "UP" "PID $pid"
    elif echo "$output" | grep -q 'LastExitStatus.*= 0'; then
      print_row "gbrain sync daemon" "DEGRADED" "Registered but not running (exited 0)"
    else
      print_row "gbrain sync daemon" "DOWN" "Registered but exited with error"
    fi
  elif [[ "$(uname -s)" == "Linux" ]]; then
    if systemctl --user is-active --quiet gbrain-autopilot 2>/dev/null; then
      print_row "gbrain sync daemon" "UP" "systemd active (autopilot)"
    elif systemctl --user is-active --quiet com.gbrain.sync-watch 2>/dev/null; then
      print_row "gbrain sync daemon" "UP" "systemd active (sync-watch, legacy)"
    else
      print_row "gbrain sync daemon" "DOWN" "neither autopilot nor sync-watch active"
    fi
  else
    print_row "gbrain sync daemon" "UNKNOWN" "Unsupported OS: $(uname -s)"
  fi
}

check_memory_freshness() {
  local current="${BRAIN_DIR}/shared/hermes-memory/current.md"
  if [[ ! -f "$current" ]]; then
    print_row "Memory sync" "UNKNOWN" "current.md not found — run memory-to-brain-sync.py"
    return
  fi
  local mtime
  mtime=$(stat -f "%m" "$current" 2>/dev/null || stat -c "%Y" "$current" 2>/dev/null || echo 0)
  if [[ "$mtime" -eq 0 ]]; then
    print_row "Memory sync" "UNKNOWN" "Cannot read mtime"
    return
  fi
  local now
  now=$(date +%s)
  local age_minutes=$(( (now - mtime) / 60 ))
  if [[ "$age_minutes" -lt 480 ]]; then
    print_row "Memory sync" "UP" "${age_minutes}m ago"
  elif [[ "$age_minutes" -lt 1440 ]]; then
    print_row "Memory sync" "DEGRADED" "${age_minutes}m ago — stale"
  else
    print_row "Memory sync" "DOWN" "${age_minutes}m ago — very stale"
  fi
}

check_disk() {
  local path="${1:-/}"
  if [[ "$(uname -s)" == "Darwin" ]]; then
    local output
    output=$(df -h "$path" 2>/dev/null | tail -1) || {
      print_row "Disk usage" "UNKNOWN" "df failed"
      return
    }
    local pct_used
    pct_used=$(echo "$output" | awk '{print $5}' | tr -d '%')
    local avail
    avail=$(echo "$output" | awk '{print $4}')
    if [[ "$pct_used" -lt 80 ]]; then
      print_row "Disk usage" "UP" "${pct_used}% used, ${avail} available"
    elif [[ "$pct_used" -lt 90 ]]; then
      print_row "Disk usage" "DEGRADED" "${pct_used}% used, ${avail} available"
    else
      print_row "Disk usage" "DOWN" "${pct_used}% used, ${avail} available"
    fi
  else
    local output
    output=$(df -h "$path" 2>/dev/null | tail -1) || {
      print_row "Disk usage" "UNKNOWN" "df failed"
      return
    }
    local pct_used
    pct_used=$(echo "$output" | awk '{print $5}' | tr -d '%')
    local avail
    avail=$(echo "$output" | awk '{print $4}')
    if [[ "$pct_used" -lt 80 ]]; then
      print_row "Disk usage" "UP" "${pct_used}% used, ${avail} available"
    elif [[ "$pct_used" -lt 90 ]]; then
      print_row "Disk usage" "DEGRADED" "${pct_used}% used, ${avail} available"
    else
      print_row "Disk usage" "DOWN" "${pct_used}% used, ${avail} available"
    fi
  fi
}

check_cortex_dashboard() {
  local url="http://localhost:8901"
  if command -v curl &>/dev/null; then
    local http_code
    http_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "$url" 2>/dev/null || echo "000")
    if [[ "$http_code" == "200" ]]; then
      print_row "Cortex Dashboard" "UP" "port 8901"
    elif [[ "$http_code" == "000" ]]; then
      print_row "Cortex Dashboard" "DOWN" "No response on port 8901"
    else
      print_row "Cortex Dashboard" "DEGRADED" "HTTP $http_code"
    fi
  else
    print_row "Cortex Dashboard" "UNKNOWN" "curl not available"
  fi
}

check_service_manager() {
  # Verify important services are managed by systemd (Linux) or launchd (macOS)
  # This catches processes running ad-hoc without a service manager
  local os
  os=$(uname -s)

  if [[ "$os" == "Darwin" ]]; then
    local -a LABELS=("com.ollama.serve" "com.gbrain.autopilot" "com.hermes.gateway" "com.hermes.cortex-dashboard" "com.hermes.agent-inbox")
    local -a DISPLAYS=("Ollama (launchd)" "gbrain (launchd)" "Hermes Gateway (launchd)" "Cortex Dashboard (launchd)" "Agent Inbox (launchd)")
    local all_ok=0 any_down=0
    for i in "${!LABELS[@]}"; do
      if launchctl list "${LABELS[$i]}" &>/dev/null 2>&1; then
        local pid
        pid=$(launchctl list "${LABELS[$i]}" 2>/dev/null | awk '{print $1}' | grep -v '^\s*$')
        [[ -n "$pid" && "$pid" != "-" ]] && all_ok=$((all_ok + 1)) || any_down=$((any_down + 1))
      else
        any_down=$((any_down + 1))
      fi
    done
    local detail="$all_ok managed, $any_down down/missing"
    if [[ "$any_down" -eq 0 ]]; then
      print_row "Service manager (launchd)" "UP" "$detail"
    elif [[ "$all_ok" -gt 0 ]]; then
      print_row "Service manager (launchd)" "DEGRADED" "$detail"
    else
      print_row "Service manager (launchd)" "DOWN" "$detail"
    fi

  elif [[ "$os" == "Linux" ]]; then
    local -a UNITS=("ollama" "gbrain-autopilot" "hermes-gateway" "hermes-cortex-dashboard" "hermes-agent-inbox")
    local -a DISPLAYS=("Ollama (systemd)" "gbrain (systemd)" "Hermes Gateway (systemd)" "Cortex Dashboard (systemd)" "Agent Inbox (systemd)")
    local all_ok=0 any_down=0 any_unmanaged=0

    for i in "${!UNITS[@]}"; do
      if systemctl --user is-active --quiet "${UNITS[$i]}" 2>/dev/null; then
        all_ok=$((all_ok + 1))
      else
        # Check if unit file exists (enabled but not active is still managed)
        if systemctl --user is-enabled --quiet "${UNITS[$i]}" 2>/dev/null; then
          any_down=$((any_down + 1))
        else
          any_unmanaged=$((any_unmanaged + 1))
        fi
      fi
    done

    # Also detect processes running without systemd
    local ollama_pid hermes_pid
    ollama_pid=$(pgrep -f "ollama serve" 2>/dev/null || true)
    hermes_pid=$(pgrep -f "hermes_cli.main" 2>/dev/null || true)
    if [[ -n "$ollama_pid" ]] && ! systemctl --user is-active --quiet ollama 2>/dev/null; then
      any_unmanaged=$((any_unmanaged + 1))
    fi
    if [[ -n "$hermes_pid" ]] && ! systemctl --user is-active --quiet hermes-gateway 2>/dev/null; then
      any_unmanaged=$((any_unmanaged + 1))
    fi

    local detail="$all_ok active"
    [[ "$any_down" -gt 0 ]] && detail="$detail, $any_down inactive"
    [[ "$any_unmanaged" -gt 0 ]] && detail="$detail, $any_unmanaged UNMANAGED"
    if [[ "$any_unmanaged" -gt 0 ]]; then
      print_row "Service manager (systemd)" "DOWN" "$detail"
    elif [[ "$all_ok" -eq ${#UNITS[@]} ]]; then
      print_row "Service manager (systemd)" "UP" "$detail"
    else
      print_row "Service manager (systemd)" "DEGRADED" "$detail"
    fi
  fi
}

# ── Main ────────────────────────────────────────────────────

parse_args() {
  for arg in "$@"; do
    case "$arg" in
      --json) JSON_MODE=true ;;
      --watch) WATCH_MODE=true ;;
      --help|-h)
        echo "Usage: bash cortex-health.sh [--json] [--watch]"
        echo ""
        echo "  --json    Machine-readable JSON output"
        echo "  --watch   Re-check every 5 seconds (like htop)"
        exit 0
        ;;
    esac
  done
}

run_checks() {
  local timestamp
  timestamp=$(date "+%Y-%m-%d %H:%M:%S %Z")
  OVERALL="HEALTHY"

  if $JSON_MODE; then
    echo "{"
    echo "  \"timestamp\": \"$(json_escape "$timestamp")\","
    echo "  \"checks\": ["
  else
    echo ""
    echo -e "${BOLD}━━━ Cortex Health — ${timestamp} ━━━${RESET}"
    echo ""
  fi

  # Run checks — each prints its line to stdout and writes status to sep file
  local status_file result_line
  status_file=$(mktemp)

  run_and_capture() {
    local line
    line=$("$@" 2>/dev/null)
    echo "$line"
    # Extract status: the third whitespace-delimited field after the icon
    # Icon is 2 chars (● ◐ ○ ◌ ⚠ + space), so status is at a fixed position
    # "  ● gbrain sources             DEGRADED   ..."
    # Use awk with a trick: print the field that matches status keywords
    local s
    s=$(echo "$line" | awk '{
      for(i=1;i<=NF;i++) {
        if($i == "UP" || $i == "DEGRADED" || $i == "DOWN" || $i == "UNKNOWN" || $i == "ERROR") {
          print $i; exit
        }
      }
    }')
    echo "$s" >> "$status_file"
  }

  run_and_capture check_ollama
  run_and_capture check_langfuse
  run_and_capture check_gbrain_sources
  run_and_capture check_sync_daemon
  run_and_capture check_memory_freshness
  run_and_capture check_cortex_dashboard
  run_and_capture check_disk
  run_and_capture check_service_manager

  # Aggregate from captured statuses
  while IFS= read -r s; do
    [[ -z "$s" ]] && continue
    aggregate "$s"
  done < "$status_file"
  rm -f "$status_file"

  if $JSON_MODE; then
    echo "  ],"
    echo "  \"overall\": \"$OVERALL\""
    echo "}"
  else
    echo ""
    echo -e "${BOLD}━━━ Result ━━━${RESET}"
    case "$OVERALL" in
      HEALTHY)   echo -e "  ${GREEN}● All systems go${RESET}" ;;
      DEGRADED)  echo -e "  ${YELLOW}◐ Running with warnings${RESET}" ;;
      CRITICAL)  echo -e "  ${RED}○ Issues need attention${RESET}" ;;
      ERROR)     echo -e "  ${RED}⚠ Errors detected${RESET}" ;;
    esac
    echo ""
  fi
}

parse_args "$@"

if $WATCH_MODE; then
  while true; do
    clear 2>/dev/null || true
    run_checks
    sleep 5
  done
else
  run_checks
  case "$OVERALL" in
    HEALTHY)  exit 0 ;;
    DEGRADED) exit 1 ;;
    CRITICAL) exit 2 ;;
    ERROR)    exit 3 ;;
    *)        exit 4 ;;
  esac
fi
