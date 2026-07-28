#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  docker-volume-safety.sh — Sentinel guard for docker volumes
#
#  Hard blocks docker volume deletion in non-interactive
#  contexts (cron jobs, automated scripts, CI pipelines).
#  The user can always delete volumes manually in their
#  interactive terminal.
#
#  Usage:
#    docker-volume-safety.sh check     — check if context is safe
#    docker-volume-safety.sh audit     — find volume-deleting patterns in scripts
#
#  Returns 0 (safe) or 1 (blocked / issues found).
# ─────────────────────────────────────────────────────────────
set -euo pipefail

CORTEX_REPO="${HOME}/hermes-cortex"
SCRIPTS_DIR="${CORTEX_REPO}/ops/scripts"

# ── Canonical forbidden patterns — matched exactly, no false positives ──
FORBIDDEN_PATTERNS=(
  "docker volume prune"
  "docker system prune.*--volumes"
  "docker volume rm"
)

case "${1:-check}" in
  check)
    # Check 1: Are we in an interactive terminal?
    if [ ! -t 1 ]; then
      # Non-interactive — check if any forbidden command is in the call chain
      if ps -o command= $PPID 2>/dev/null | grep -qE '(docker volume|docker system prune.*--volumes)'; then
        echo "🔴 BLOCKED: docker volume deletion attempted in non-interactive context"
        echo "   Docker volumes contain irreplaceable data."
        echo "   Run this command manually in an interactive terminal."
        exit 1
      fi
    fi
    echo "OK"
    exit 0
    ;;

  audit)
    echo "🔍 Scanning scripts for volume-deleting patterns..."
    issues=0
    while IFS= read -r -d '' script; do
      # Skip self — contains patterns as search strings, not execution
      [[ "${script}" == *"docker-volume-safety.sh" ]] && continue
      for pattern in "${FORBIDDEN_PATTERNS[@]}"; do
        if grep -qnE "${pattern}" "${script}" 2>/dev/null; then
          echo "  ⚠️  ${script}: matches pattern '${pattern}'"
          issues=$((issues + 1))
        fi
      done
    done < <(find "${SCRIPTS_DIR}" -type f \( -name "*.sh" -o -name "*.py" \) -print0 2>/dev/null)
    if [ "${issues}" -gt 0 ]; then
      echo "🔴 ${issues} script(s) have volume-deleting patterns — review and fix"
      exit 1
    fi
    echo "✅ All clean — no volume-deleting patterns found"
    exit 0
    ;;

  *)
    echo "usage: docker-volume-safety.sh <check|audit>"
    exit 1
    ;;
esac
