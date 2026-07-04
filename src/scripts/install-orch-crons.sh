#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  install-orch-crons.sh — Register orchestrator-only cron jobs
#
#  Creates Hermes Agent-level cron jobs that should ONLY run
#  on orchestrator machines (Moses primary, Esther backup).
#  Worker agents should NEVER run this script.
#
#  Usage:
#    bash install-orch-crons.sh              # create missing crons
#    bash install-orch-crons.sh --dry-run    # show what would be created
#    bash install-orch-crons.sh --force      # recreate all crons (overwrite)
#    bash install-orch-crons.sh --uninstall  # remove all orch crons
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"
source "${SCRIPT_DIR}/os-config.sh"

HERMES_HOME="${HERMES_HOME:-${HOME}/.hermes}"
CRON_JOBS_FILE="${HERMES_HOME}/cron/jobs.json"
SCRIPTS_DIR="${HOME}/.hermes-cortex/scripts"
HERMES_CMD=""
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
WOULD_CREATE=0

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

# ── Uninstall ──────────────────────────────────────────────
if $UNINSTALL; then
  echo ""
  printf "${CYAN}━━━ Uninstalling Orchestrator-Only Crons ━━━${RESET}\n\n"
  for job in \
    "orch-team-messages" "orch-team-health" \
    "agent-ip-submission" "agent-daily-soul-refinement"; do
    remove_cron "$job" 2>/dev/null || true
  done
  info "Uninstall complete"
  exit 0
fi

# ── Pre-flight ─────────────────────────────────────────────
echo ""
printf "${CYAN}━━━ Orchestrator-Only Hermes Cron Jobs ━━━${RESET}\n\n"

if ! command -v python3 &>/dev/null; then
  error "python3 is required for cron existence checks"
  exit 1
fi

# ── Helper: check if a cron job exists ────────────────────
cron_exists() {
  local name="$1"
  if [[ -f "$CRON_JOBS_FILE" ]]; then
    if python3 -c "
import json, sys
try:
    data = json.load(open('$CRON_JOBS_FILE'))
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
" 2>/dev/null; then
      return 0
    fi
  fi
  if command -v "${HERMES_CMD:-hermes}" &>/dev/null; then
    if "${HERMES_CMD:-hermes}" cron list --all 2>/dev/null | grep -q "Name:[[:space:]]*${name}$"; then
      return 0
    fi
  fi
  return 1
}

# ── Helper: verify script exists ───────────────────────────
script_exists() {
  local script="$1"
  if [[ -z "$script" ]]; then
    return 0
  fi
  if [[ -f "${SCRIPTS_DIR}/${script}" ]]; then
    return 0
  fi
  if [[ -f "${SCRIPT_DIR}/${script}" ]]; then
    return 0
  fi
  if [[ -f "${HOME}/.local/bin/${script}" ]]; then
    return 0
  fi
  return 1
}

# ── Helper: create a cron job ─────────────────────────────
create_cron() {
  local name="$1" schedule="$2" script="$3" prompt="$4" skill="$5" toolsets="$6" deliver="$7" workdir="$8" no_agent="$9"
  local model="${10:-}" provider="${11:-}"

  local exists=false
  if cron_exists "$name"; then
    exists=true
  fi

  if $exists && ! $FORCE; then
    SKIPPED=$((SKIPPED + 1))
    return 0
  fi

  if [[ -n "$script" ]] && ! script_exists "$script"; then
    warn "Script not found: ${script} — skipping cron '${name}'"
    FAILED=$((FAILED + 1))
    return 0
  fi

  if $DRY_RUN; then
    local action="Create"
    if $exists && $FORCE; then
      action="Update (force)"
    fi
    info "[DRY-RUN] ${action} cron: ${name}"
    printf "  schedule=%s\n" "$schedule"
    printf "  script=%s\n" "${script:-<none>}"
    printf "  skill=%s\n" "${skill:-<none>}"
    [[ -n "$model"    ]] && printf "  model=%s\n" "$model"
    [[ -n "$provider" ]] && printf "  provider=%s\n" "$provider"
    WOULD_CREATE=$((WOULD_CREATE + 1))
    return 0
  fi

  if $exists && $FORCE && [[ -n "$HERMES_CMD" ]]; then
    local job_id _tmp
    _tmp="${HERMES_HOME}/state/_cron_find.py"
    mkdir -p "$(dirname "$_tmp")"
    cat > "$_tmp" << 'PYEOF'
import json, sys
try:
    with open(sys.argv[1]) as f:
        data = json.load(f)
    jobs = data.get("jobs", []) if isinstance(data, dict) else data
    target = sys.argv[2]
    for j in jobs:
        if isinstance(j, dict) and j.get("name") == target:
            sys.stdout.write(j.get("id", ""))
            sys.exit(0)
except:
    pass
sys.exit(1)
PYEOF
    job_id=$(python3 "$_tmp" "$CRON_JOBS_FILE" "$name" 2>/dev/null || true)
    if [[ -n "$job_id" ]]; then
      local edit_cmd=("$HERMES_CMD" "cron" "edit" "$job_id")
      edit_cmd+=("--schedule" "$schedule")
      [[ -n "$script" ]]  && edit_cmd+=("--script" "$script")
      [[ -n "$skill" ]]   && edit_cmd+=("--skill" "$skill")
      [[ -n "$deliver" ]] && edit_cmd+=("--deliver" "$deliver")
      [[ -n "$workdir" ]] && edit_cmd+=("--workdir" "$workdir")
      if [[ "$no_agent" == "true" ]]; then
        edit_cmd+=("--no-agent")
      elif [[ -n "$script" ]]; then
        edit_cmd+=("--agent")
      fi
      [[ -n "$prompt" ]] && edit_cmd+=("--prompt" "$prompt")
      if "${edit_cmd[@]}" 2>&1; then
        info "Updated cron: ${name} (${schedule})"
        CREATED=$((CREATED + 1))
        if [[ -n "$model" || -n "$provider" ]]; then
          pin_cron_model "$name" "$model" "$provider"
        fi
      else
        warn "Failed to update cron: ${name}"
        FAILED=$((FAILED + 1))
      fi
      return 0
    fi
  fi

  if [[ -z "$HERMES_CMD" ]]; then
    warn "Hermes not found — cannot create cron '${name}'"
    warn "  Create manually: hermes cron create --name \"${name}\" --schedule \"${schedule}\" ..."
    FAILED=$((FAILED + 1))
    return 0
  fi

  local cmd=("$HERMES_CMD" "cron" "create" "--name" "$name")
  [[ -n "$script" ]]  && cmd+=("--script" "$script")
  [[ -n "$skill" ]]   && cmd+=("--skill" "$skill")
  [[ -n "$deliver" ]] && cmd+=("--deliver" "$deliver")
  [[ -n "$workdir" ]] && cmd+=("--workdir" "$workdir")
  [[ "$no_agent" == "true" ]] && cmd+=("--no-agent")
  cmd+=("$schedule")
  [[ -n "$prompt" ]] && cmd+=("$prompt")

  if "${cmd[@]}" 2>&1; then
    info "Created cron: ${name} (${schedule})"
    CREATED=$((CREATED + 1))
    if [[ -n "$model" || -n "$provider" ]]; then
      pin_cron_model "$name" "$model" "$provider"
    fi
  else
    warn "Failed to create cron: ${name}"
    FAILED=$((FAILED + 1))
  fi
}

# ── Pin Model/Provider ────────────────────────────────────
pin_cron_model() {
  local name="$1" model="$2" provider="$3"
  if [[ -z "$model" && -z "$provider" ]]; then
    return 0
  fi
  local db="${HERMES_HOME}/cron/jobs.json"
  if [[ ! -f "$db" ]]; then
    warn "  Cannot pin model for '${name}' — jobs.json not found"
    return 0
  fi
  python3 -c "
import json, sys
with open('$db') as f:
    data = json.load(f)
jobs = data.get('jobs', []) if isinstance(data, dict) else data
patched = False
for job in jobs:
    if isinstance(job, dict) and job.get('name') == '$name':
        if '$model':    job['model'] = '$model'
        if '$provider': job['provider'] = '$provider'
        patched = True
        break
if patched:
    with open('$db', 'w') as f:
        json.dump(data, f, indent=2, default=str)
    print('PINNED')
" 2>&1 | grep -q PINNED && info "  Pinned ${name} → ${model:-<default>}/${provider:-<default>}" || true
}

# ── Helper: remove a single cron ──────────────────────────
remove_cron() {
  local name="$1"
  if ! cron_exists "$name"; then
    return 0
  fi
  if [[ -n "$HERMES_CMD" ]]; then
    "$HERMES_CMD" cron remove --name "$name" 2>/dev/null && info "Removed cron: ${name}" || true
  fi
}

# ── 1. Orchestrator Crons ─────────────────────────────────
printf "${CYAN}  1. Orchestrator-Specific Crons${RESET}\n"

# Cross-agent health and team messages (every 10 min)
create_cron "orch-team-messages" "*/10 * * * *" \
  "orch-team-messages.sh" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

create_cron "orch-team-health" "*/10 * * * *" \
  "orch-team-health.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Agent IP submission processor (every 30 min)
create_cron "agent-ip-submission" "*/30 * * * *" \
  "agent-ip-submission.sh" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Daily soul refinement (deepseek — needs Hermes tools: session_search, memory, patch)
create_cron "agent-daily-soul-refinement" "0 23 * * *" \
  "" \
  "Load the soul-refinement skill. Use session_search() to find today's sessions. Look for any user corrections, feedback, or behavior patterns worth noting. Update SOUL.md with insights. Keep it under 5KB.

## OUTPUT FORMAT — FOLLOW EXACTLY
Match this structure line for line. Your content replaces the values.
Everything else stays: dashes, colons, spacing, line breaks.

agent-daily-soul-refinement (JOB_ID) [YYYY-MM-DD HH:MM KST]
-------------

Phase 1 — Sessions reviewed: 8 sessions found today
- Found 1 user correction: \"stop using vague language in reports\"
- Found 2 behavioral patterns: consistently missing pre-commit hook check, verbosity in error reports

Phase 2 — SOUL.md updates applied:
- Added behavioral rule: verify pre-commit hook presence before git operations
- Added style correction: prefer tool output over prose descriptions
- Updated existing verbosity guideline to be more specific

Phase 3 — Current SOUL.md: 4.2KB (within 5KB limit)

Result: 3 insights added to SOUL.md. SOUL.md at 4.2KB.

📊 deepseek-v4-flash (opencode-zen) | \$0.006/run ≈ \$2.18/mo

If nothing to report: output exactly [SILENT]" \
  "soul-refinement" "" "origin" "" "false" \
  "deepseek-v4-flash" "opencode-zen"

# ── Summary ────────────────────────────────────────────────
echo ""
if $DRY_RUN; then
  printf "${CYAN}━━━ Summary (dry run) ─━━${RESET}\n"
  printf "  Would create:  %d\n" "$WOULD_CREATE"
  exit 0
fi
printf "${CYAN}━━━ Summary ─━━${RESET}\n"
printf "  Created: %d  Skipped: %d  Failed: %d\n" "$CREATED" "$SKIPPED" "$FAILED"
echo ""
