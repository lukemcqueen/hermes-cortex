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
#    bash install-hermes-crons.sh --uninstall  # remove all hermes crons
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"
source "${SCRIPT_DIR}/os-config.sh"

HERMES_HOME="${HERMES_HOME:-${HOME}/.hermes}"
CRON_JOBS_FILE="${HERMES_HOME}/cron/jobs.json"
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
CREATED=0
SKIPPED=0

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --dry-run) DRY_RUN=true; shift ;;
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
    # jobs.json is a list of job objects OR a dict keyed by job_id
    # Check by name field
    if python3 -c "
import json, sys
try:
    data = json.load(open('$CRON_JOBS_FILE'))
    if isinstance(data, list):
        for j in data:
            if j.get('name') == '$name':
                sys.exit(0)
    elif isinstance(data, dict):
        for jid, j in data.items():
            if isinstance(j, dict) and j.get('name') == '$name':
                sys.exit(0)
except: pass
sys.exit(1)
" 2>/dev/null; then
      return 0
    fi
  fi
  return 1
}

# ── Helper: create a cron job via hermes or prompt ────────
create_cron() {
  local name="$1" schedule="$2" script="$3" prompt="$4" skill="$5" toolsets="$6" deliver="$7" workdir="$8" no_agent="$9"

  if cron_exists "$name"; then
    SKIPPED=$((SKIPPED + 1))
    return 0
  fi

  if $DRY_RUN; then
    info "[DRY-RUN] Would create cron: ${name}"
    printf "  schedule=%s\n" "$schedule"
    printf "  script=%s\n" "${script:-<none>}"
    printf "  skill=%s\n" "${skill:-<none>}"
    CREATED=$((CREATED + 1))
    return 0
  fi

  if [[ -z "$HERMES_CMD" ]]; then
    warn "Hermes not found — cannot create cron '${name}'"
    warn "  Create manually: hermes cron create --name \"${name}\" --schedule \"${schedule}\" ..."
    SKIPPED=$((SKIPPED + 1))
    return 0
  fi

  # Build the hermes cron create command
  local cmd=("$HERMES_CMD" "cron" "create" "--name" "$name" "--schedule" "$schedule")
  if [[ -n "$script" ]]; then
    cmd+=("--script" "$script")
  fi
  if [[ -n "$skill" ]]; then
    cmd+=("--skill" "$skill")
  fi
  if [[ -n "$prompt" ]]; then
    cmd+=("--prompt" "$prompt")
  fi
  if [[ -n "$toolsets" ]]; then
    cmd+=("--enabled-toolsets" "$toolsets")
  fi
  if [[ -n "$deliver" ]]; then
    cmd+=("--deliver" "$deliver")
  fi
  if [[ -n "$workdir" ]]; then
    cmd+=("--workdir" "$workdir")
  fi
  if [[ "$no_agent" == "true" ]]; then
    cmd+=("--no_agent")
  fi

  if "${cmd[@]}" 2>&1; then
    info "Created cron: ${name} (${schedule})"
    CREATED=$((CREATED + 1))
  else
    warn "Failed to create cron: ${name}"
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
    "check-agent-messages" "agent-health-monitor" "remediation-sensor"; do
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

# ── 4. Agent Health Monitor ─────────────────────────────────
create_cron "agent-health-monitor" "*/10 * * * *" \
  "agent-health-monitor.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

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

create_cron "check-agent-messages" "*/10 * * * *" \
  "check-agent-messages.sh" \
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
fi
echo ""
info "Cron jobs are stored in: ${CRON_JOBS_FILE}"
if [[ "$CREATED" -gt 0 && -n "$HERMES_CMD" ]]; then
  info "Verify with: ${HERMES_CMD} cron list"
fi
