#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  check-memory-budget.sh — MEMORY.md usage monitor
#
#  Reports MEMORY.md character usage as a percentage with color
#  coding. Designed for cron integration:
#    - Non-empty stdout at ≥90% → cron delivers warning
#    - Silent when under threshold → no noise
#    - --report forces output regardless
#
#  Usage:
#    bash check-memory-budget.sh              # Silent when healthy
#    bash check-memory-budget.sh --report     # Always print
#    bash check-memory-budget.sh --file /path # Custom file path
# ─────────────────────────────────────────────────────────────
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BOLD='\033[1m'; RESET='\033[0m'
FORCE_REPORT=false

MEMORY_FILE="${HOME}/.hermes/memories/MEMORY.md"
USER_FILE="${HOME}/.hermes/memories/USER.md"
# Character limits from SOUL.md memory architecture
MEMORY_LIMIT=2200
USER_LIMIT=1375
MEMORY_WARN_PCT=85
MEMORY_CRIT_PCT=95

for arg in "$@"; do
  case "$arg" in
    --report) FORCE_REPORT=true ;;
    --file=*) MEMORY_FILE="${arg#*=}" ;;
    --help|-h)
      echo "Usage: bash check-memory-budget.sh [--report] [--file=/path/to/MEMORY.md]"
      echo ""
      echo "  --report       Always print, even when healthy"
      echo "  --file=<path>  Check a specific file instead of default MEMORY.md"
      echo ""
      echo "Exit codes:"
      echo "  0 = healthy (< ${MEMORY_WARN_PCT}%)"
      echo "  1 = warning (≥ ${MEMORY_WARN_PCT}%)"
      echo "  2 = critical (≥ ${MEMORY_CRIT_PCT}%)"
      exit 0
      ;;
  esac
done

check_file() {
  local file="$1"
  local label="$2"
  local limit="$3"

  if [[ ! -f "$file" ]]; then
    echo "⚠ ${label}: file not found — ${file}"
    return 1
  fi

  local chars size pct
  chars=$(wc -m < "$file" | tr -d ' ')
  size=$(wc -c < "$file" | tr -d ' ')
  pct=$(( chars * 100 / limit ))

  local icon status_color status_text
  if [[ "$pct" -ge "$MEMORY_CRIT_PCT" ]]; then
    icon="🔴"
    status_color="$RED"
    status_text="CRITICAL"
  elif [[ "$pct" -ge "$MEMORY_WARN_PCT" ]]; then
    icon="🟡"
    status_color="$YELLOW"
    status_text="WARNING"
  else
    icon="🟢"
    status_color="$GREEN"
    status_text="OK"
  fi

  # Build bar
  local bar_width=20 filled empty
  filled=$(( pct * bar_width / 100 ))
  [[ "$filled" -gt "$bar_width" ]] && filled=$bar_width
  empty=$(( bar_width - filled ))

  local bar=""
  for ((i=0; i<filled; i++)); do bar="${bar}█"; done
  for ((i=0; i<empty; i++)); do bar="${bar}░"; done

  echo "${icon} ${label}: ${status_color}${pct}%${RESET} [${bar}] ${chars}/${limit} chars (${size} bytes) — ${status_text}"

  if [[ "$pct" -ge "$MEMORY_CRIT_PCT" ]]; then
    return 2
  elif [[ "$pct" -ge "$MEMORY_WARN_PCT" ]]; then
    return 1
  fi
  return 0
}

# ── Main ───────────────────────────────────────────────────
echo ""
echo -e "${BOLD}━━━ Memory Budget Check ━━━${RESET}"
echo ""

MEMORY_RC=0
USER_RC=0

check_file "$MEMORY_FILE" "MEMORY.md" "$MEMORY_LIMIT" || MEMORY_RC=$?
echo ""
check_file "$USER_FILE" "USER.md" "$USER_LIMIT" || USER_RC=$?

echo ""
echo -e "${BOLD}━━━${RESET}"

# Determine overall exit code
OVERALL_RC=0
if [[ "$MEMORY_RC" -ge 2 || "$USER_RC" -ge 2 ]]; then
  OVERALL_RC=2
elif [[ "$MEMORY_RC" -ge 1 || "$USER_RC" -ge 1 ]]; then
  OVERALL_RC=1
fi

# Check if there's an associated cron job template to suggest
if [[ "$MEMORY_RC" -ge 1 || "$USER_RC" -ge 1 ]]; then
  echo ""
  echo -e "${YELLOW}Memory budget is tight. Consider:${RESET}"
  echo "  • Run the pointer pattern: compress entries to ~120 chars each"
  echo "  • Move detail to ~/brain/moses/references/ and index with gbrain"
  echo "  • The cron job 'memory-pruning' (4am daily) handles this automatically"
  echo "  • See docs/agent-memory-pointer-pattern.md for the pointer pattern guide"
fi

# Silent unless forced or above threshold
if [[ "$FORCE_REPORT" == "false" && "$OVERALL_RC" -eq 0 ]]; then
  exit 0  # Silent exit — no output for healthy cron
fi

exit "$OVERALL_RC"
