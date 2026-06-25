#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  install-hermes-crons.sh — Register essential Hermes Agent cron jobs
#
#  Creates Hermes Agent-level cron jobs (no_agent watchdogs and
#  LLM-driven crons) for auto-remediation, system health, web
#  cache, and memory synchronization.
#
#  Skips jobs that already exist (checks ~/.hermes/cron/jobs.json
#  by job name). Safe to re-run — only creates missing jobs.
#
#  Usage:
#    bash install-hermes-crons.sh              # create missing crons
#    bash install-hermes-crons.sh --dry-run    # show what would be created
#    bash install-hermes-crons.sh --force      # recreate all crons (overwrite)
#    bash install-hermes-crons.sh --uninstall  # remove all hermes crons
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"
source "${SCRIPT_DIR}/os-config.sh"

HERMES_HOME="${HERMES_HOME:-${HOME}/.hermes}"
CRON_JOBS_FILE="${HERMES_HOME}/cron/jobs.json"
SCRIPTS_DIR="${HOME}/.hermes-cortex/scripts"
HERMES_CMD=""
# Try to find hermes command
for candidate in hermes "${HERMES_HOME}/hermes-agent/venv/bin/hermes"; do
  if command -v "$candidate" &>/dev/null; then
    HERMES_CMD="$candidate"
    break
  fi
done

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; RESET='\033[0m'
info()  { printf "${GREEN}✓${RESET} %s\n" "$*"; }
warn()  { printf "${YELLOW}⚠${RESET} %s\n" "$*"; }
error() { printf "${RED}✗${RESET} %s\n" "$*"; }

DRY_RUN=false
UNINSTALL=false
FORCE=false
CREATED=0
SKIPPED=0
FAILED=0

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dry-run) DRY_RUN=true; shift ;;
      --force) FORCE=true; shift ;;
      --uninstall) UNINSTALL=true; shift ;;
      *) warn "Unknown option: $1"; shift ;;
    esac
  done
}
parse_args "$@"

# ── Pre-flight checks ──────────────────────────────────────
if $UNINSTALL; then
  if [[ -z "$HERMES_CMD" ]]; then
    warn "Hermes not found — nothing to uninstall"
    exit 0
  fi
  info "Uninstalling Hermes cron jobs…"
  # Allow uninstall even without hermes by removing from jobs.json
fi

# ── Helper: check if a cron job exists in jobs.json ────────
cron_exists() {
  local name="$1"
  if [[ -f "$CRON_JOBS_FILE" ]]; then
    # jobs.json structure: { "jobs": [...] } or [ ... ]
    # Check by name field
    python3 -c "
import json, sys
try:
    data = json.load(open('$CRON_JOBS_FILE'))
    # Handle nested structure: { 'jobs': [...] }
    if isinstance(data, dict) and 'jobs' in data:
        data = data['jobs']
    if isinstance(data, list):
        for j in data:
            if isinstance(j, dict) and j.get('name') == '$name':
                sys.exit(0)
    elif isinstance(data, dict):
        for jid, j in data.items():
            if isinstance(j, dict) and j.get('name') == '$name':
                sys.exit(0)
except Exception:
    pass
sys.exit(1)
"
    if [ $? -eq 0 ]; then
      return 0
    fi
  fi
  return 1
}

# ── Helper: verify script exists ───────────────────────────
script_exists() {
  local script="$1"
  if [[ -z "$script" ]]; then
    return 0  # No script required (skill-based cron)
  fi
  if [[ -f "${SCRIPTS_DIR}/${script}" ]]; then
    return 0
  fi
  # Also check repo source
  if [[ -f "${SCRIPT_DIR}/${script}" ]]; then
    return 0
  fi
  return 1
}

# ── Helper: create a cron job via hermes or prompt ────────
create_cron() {
  local name="$1" schedule="$2" script="$3" prompt="$4" skill="$5" toolsets="$6" deliver="$7" workdir="$8" no_agent="$9"

  # Check if cron exists
  local exists=false
  if cron_exists "$name"; then
    exists=true
  fi

  if $exists && ! $FORCE; then
    SKIPPED=$((SKIPPED + 1))
    return 0
  fi

  # Verify script exists before creating cron
  if [[ -n "$script" ]] && ! script_exists "$script"; then
    warn "Script not found: ${script} — skipping cron '${name}'"
    FAILED=$((FAILED + 1))
    return 0
  fi

  if $DRY_RUN; then
    local action="Create"
    if $exists && $FORCE; then
      action="Recreate (force)"
    fi
    info "[DRY-RUN] ${action} cron: ${name}"
    printf "  schedule=%s\\n" "$schedule"
    printf "  script=%s\\n" "${script:-<none>}"
    printf "  skill=%s\\n" "${skill:-<none>}"
    CREATED=$((CREATED + 1))
    return 0
  fi

  # Remove existing cron if --force
  if $exists && $FORCE && [[ -n "$HERMES_CMD" ]]; then
    "$HERMES_CMD" cron remove --name "$name" 2>/dev/null || true
  fi

  if [[ -z "$HERMES_CMD" ]]; then
    warn "Hermes not found — cannot create cron '${name}'"
    warn "  Create manually: hermes cron create --name \"${name}\" --schedule \"${schedule}\" ..."
    FAILED=$((FAILED + 1))
    return 0
  fi

  # Build the hermes cron create command
  # Note: schedule and prompt are POSITIONAL arguments (must come at END)
  # Note: --no-agent uses hyphen, not underscore
  # Order: hermes cron create [FLAGS] schedule [prompt]
  # Note: --enabled-toolsets is NOT a valid CLI flag (toolsets must be set via API)
  local cmd=("$HERMES_CMD" "cron" "create" "--name" "$name")
  if [[ -n "$script" ]]; then
    cmd+=("--script" "$script")
  fi
  if [[ -n "$skill" ]]; then
    cmd+=("--skill" "$skill")
  fi
  # Skip toolsets - not supported by CLI, must be set via API
  if [[ -n "$deliver" ]]; then
    cmd+=("--deliver" "$deliver")
  fi
  if [[ -n "$workdir" ]]; then
    cmd+=("--workdir" "$workdir")
  fi
  if [[ "$no_agent" == "true" ]]; then
    cmd+=("--no-agent")
  fi
  # Positional arguments MUST come at the end
  cmd+=("$schedule")
  if [[ -n "$prompt" ]]; then
    cmd+=("$prompt")
  fi

  if "${cmd[@]}" 2>&1; then
    info "Created cron: ${name} (${schedule})"
    CREATED=$((CREATED + 1))
  else
    warn "Failed to create cron: ${name}"
    FAILED=$((FAILED + 1))
  fi
}

# ── Remove Cron ─────────────────────────────────────────────
remove_cron() {
  local name="$1"
  if ! cron_exists "$name"; then
    return 0
  fi
  if $DRY_RUN; then
    info "[DRY-RUN] Would remove cron: ${name}"
    return 0
  fi
  if [[ -n "$HERMES_CMD" ]]; then
    "$HERMES_CMD" cron remove --name "$name" 2>/dev/null && info "Removed cron: ${name}" || true
  fi
}

if $UNINSTALL; then
  echo ""
  printf "${CYAN}━━━ Uninstalling Hermes Cron Jobs ━━━${RESET}\n\n"
  for job in \
    "cron-auto-remediate" "system-heartbeat" "memory-to-brain-sync" \
    "system-alert-watchdog" "service-recovery" "inbox-sensor" \
    "orch-check-agent-messages" "remediation-sensor"; do
    remove_cron "$job"
  done
  info "Uninstall complete"
  exit 0
fi

# ── Main ────────────────────────────────────────────────────
echo ""
printf "${CYAN}━━━ Essential Hermes Cron Jobs ━━━${RESET}\n\n"

if ! command -v python3 &>/dev/null; then
  error "python3 is required for cron existence checks"
  exit 1
fi

# ── 1. Auto-Remediation (LLM-driven, skill-based) ──────────
printf "${CYAN}  1. Auto-Remediation Pipeline${RESET}\n"
create_cron "cron-auto-remediate" "*/5 * * * *" \
  "" \
  "Run the auto-remediation workflow using the auto-remediation skill. Load the skill first, check for errors, fix, report." \
  "auto-remediation" \
  "terminal,file,web" \
  "local" \
  "$HOME" \
  "false"

# ── 2. Remediation Sensor (no_agent, companion) ────────────
create_cron "remediation-sensor" "*/5 * * * *" \
  "remediation-sensor.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# ── 3. System Heartbeat ─────────────────────────────────────
printf "\n${CYAN}  2. System Health Monitoring${RESET}\n"
create_cron "system-heartbeat" "*/30 * * * *" \
  "heartbeat.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# agent-team-health-monitor cron is NOT registered here — it is
# orchestrator-only (Moses polls peer agents). Not needed on peers.
# Moses adds it manually via `hermes cron create`.

# ── 5. System Alert Watchdog ────────────────────────────────
create_cron "system-alert-watchdog" "*/10 * * * *" \
  "system-alert.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# ── 6. Service Recovery ─────────────────────────────────────
create_cron "service-recovery" "*/5 * * * *" \
  "service-recovery.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# ── 7. Memory to Brain Sync ─────────────────────────────────
printf "\n${CYAN}  3. Knowledge & Memory${RESET}\n"
create_cron "memory-to-brain-sync" "0 */6 * * *" \
  "memory-to-brain.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# ── 8. Inbox Monitoring ─────────────────────────────────────
printf "\n${CYAN}  4. Agent Inbox Processing${RESET}\n"
create_cron "inbox-sensor" "*/10 * * * *" \
  "inbox-sensor.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

create_cron "orch-check-agent-messages" "*/10 * * * *" \
  "orch-check-agent-messages.sh" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# ── Summary ─────────────────────────────────────────────────
echo ""
printf "${CYAN}━━━ Summary ━━━${RESET}\n"
if $DRY_RUN; then
  info "Would create: ${CREATED} cron job(s)"
  info "Would skip: ${SKIPPED} existing job(s)"
  info "Run without --dry-run to apply"
else
  info "Created: ${CREATED} new cron job(s)"
  info "Skipped: ${SKIPPED} existing job(s)"
  if [[ "$FAILED" -gt 0 ]]; then
    warn "Failed: ${FAILED} cron job(s) — check warnings above"
  fi
fi
echo ""
info "Cron jobs are stored in: ${CRON_JOBS_FILE}"
if [[ "$CREATED" -gt 0 && -n "$HERMES_CMD" ]]; then
  info "Verify with: ${HERMES_CMD} cron list"
fi

# Exit with error if any crons failed
if [[ "$FAILED" -gt 0 ]]; then
  exit 1
fi
