#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  install-crons.sh — Register essential Hermes Agent cron jobs
#
#  Creates Hermes Agent-level cron jobs (no_agent watchdogs and
#  LLM-driven crons) for auto-remediation, system health, web
#  cache, and memory synchronization.
#
#  Skips jobs that already exist (checks ~/.hermes/cron/jobs.json
#  by job name). Safe to re-run — only creates missing jobs.
#
#  Usage:
#    bash install-crons.sh              # create missing crons
#    bash install-crons.sh --dry-run    # show what would be created
#    bash install-crons.sh --force      # recreate all crons (overwrite)
#    bash install-crons.sh --uninstall  # remove all hermes crons
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
  local model="${10:-}" provider="${11:-}"

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
    [[ -n "$model"    ]] && printf "  model=%s\\n" "$model"
    [[ -n "$provider" ]] && printf "  provider=%s\\n" "$provider"
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
    # Pin model/provider post-creation (CLI doesn't support --model/--provider)
    if [[ -n "$model" || -n "$provider" ]]; then
      pin_cron_model "$name" "$model" "$provider"
    fi
  else
    warn "Failed to create cron: ${name}"
    FAILED=$((FAILED + 1))
  fi
}

# ── Pin Model/Provider ────────────────────────────────────
# The hermes CLI doesn't support --model/--provider flags, so we
# patch the jobs.json directly after creating an LLM cron.
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
    "agent-auto-remediate" "system-heartbeat" "memory-to-brain-sync" \
    "system-alert-watchdog" "service-recovery" "inbox-sensor" \
    "orch-team-messages" "remediation-sensor" \
    "hermes-update" "gbrain-nightly-dream" "gbrain-update-sync" \
    "hermes-cortex-sync" "harvest-lessons" "memory-pruning" \
    "auto-save-sessions" "agent-daily-bible-reading" \
    "agent-daily-soul-refinement" \
    "llm-judge-scorer-weekday" "llm-judge-scorer-weekend" \
    "offline-code-index" "model-health-watchdog" \
    "process-mcp-agent-inbox-messages"; do
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
create_cron "agent-auto-remediate" "*/30 * * * *" \
  "" \
  "Run the auto-remediation workflow using the auto-remediation skill. Load the skill first, check for errors, fix, report." \
  "auto-remediation" \
  "terminal,file,web" \
  "origin" \
  "$HOME" \
  "false" \
  "deepseek-v4-flash" "opencode-zen"

# ── 2. Remediation Sensor (no_agent, companion) ────────────
create_cron "remediation-sensor" "*/5 * * * *" \
  "remediation-sensor.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# ── 3. System Alert Watchdog (merged heartbeat) ──────────
printf "\n${CYAN}  2. System Health Monitoring${RESET}\n"
create_cron "system-alert-watchdog" "*/30 * * * *" \
  "system-alert-watchdog.py" \
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
  "memory-to-brain-sync.py" \
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

# ── 9. Score Auditor (checks for unscored changes) ──────────
printf "\n${CYAN}  5. Change Scoring Audit${RESET}\n"
create_cron "score-auditor" "0 */6 * * *" \
  "score-auditor.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# ── Orchestrator-only crons ─────────────────────────────────
# These crons only run on the orchestrator (Moses) and backup
# orchestrator. Worker agents skip them entirely.
# Agent-registry detection: if this host's hostname matches the
# orchestrator field, it runs the orch-* crons.

IS_ORCHESTRATOR=false
REGISTRY="${CORTEX_REPO:-$HOME/hermes-cortex}/src/agent-registry.json"
if [ -f "$REGISTRY" ]; then
  HOST=$(hostname -s 2>/dev/null || echo "unknown")
  # Check if this hostname matches any orchestrator (primary or backup)
  PY_RESULT=$(python3 -c "
import json, sys
d = json.load(open('$REGISTRY'))
agents = d.get('agents', {})
host = '$HOST'
for name, info in agents.items():
    if info.get('is_orchestrator') or info.get('is_backup_orchestrator'):
        if info.get('hostname') == host:
            print('true')
            sys.exit(0)
print('false')
" 2>/dev/null || echo "false")
  if [ "$PY_RESULT" = "true" ]; then
    IS_ORCHESTRATOR=true
  fi
fi

if $IS_ORCHESTRATOR; then
  create_cron "orch-team-messages" "*/10 * * * *" \
    "orch-team-messages.sh" \
    "" \
    "" \
    "" \
    "origin" \
    "" \
    "true"

  # orch-team-health — cross-agent health polling
  create_cron "orch-team-health" "*/10 * * * *" \
    "orch-team-health.py" \
    "" \
    "" \
    "" \
    "origin" \
    "" \
    "true"
fi

# ── Deployment-Specific Crons ─────────────────────────────
# These are specific to Luke's deployment but tracked in the
# repo so install-crons.sh --force can recreate them.
# (All crons listed in the AGENTS.md reference table.)

printf "\n${CYAN}  6. Deployment-Specific Crons${RESET}\n"

# Daily Hermes Agent self-update
create_cron "hermes-update" "23 22 * * *" \
  "hermes-update.sh" \
  "" "" "" "origin" "" "true"

# Weekly gbrain dream for knowledge enrichment
create_cron "gbrain-nightly-dream" "0 3 * * 6" \
  "gbrain-nightly-dream.sh" \
  "" "" "" "origin" "" "true"

# Weekly gbrain update and health check
create_cron "gbrain-update-sync" "0 2 * * 0" \
  "gbrain-update-sync.sh" \
  "" "" "" "origin" "" "true"

# Daily hermes-cortex sync and update
create_cron "hermes-cortex-sync" "33 22 * * *" \
  "hermes-cortex-sync.sh" \
  "" "" "" "origin" "" "true"

# Weekly lesson harvesting
create_cron "harvest-lessons" "0 5 * * 1" \
  "harvest-lessons.sh" \
  "" "" "" "origin" "" "true"

# Weekly memory pruning and consolidation
create_cron "memory-pruning" "0 4 * * 1" \
  "" \
  "Consolidate Hermes agent memory and project agent instructions. Read MEMORY.md, USER.md from the active profile and project roots. Consolidate into compact pointers. Prune stale entries. Keep under 2,200 chars." \
  "" "" "origin" "" "false" \
  "deepseek-v4-flash" "opencode-zen"

# Auto-save sessions every 6 hours
create_cron "auto-save-sessions" "every 360m" \
  "auto-save-sessions.py" \
  "" "" "" "local" "" "true"

# Daily bible reading (LLM with soul-refinement skill)
create_cron "agent-daily-bible-reading" "0 1 * * *" \
  "" \
  "Load the soul-refinement skill. Read ~/.hermes/SOUL.md and find the last book covered in the Scripture schedule. Read and summarize the next book. Add the daily verse to the session log." \
  "soul-refinement" "" "origin" "" "false" \
  "deepseek-v4-flash" "opencode-zen"

# Daily threat pipeline — scanner → fail2ban → deploy → commit → push
create_cron "threat-pipeline" "0 5 * * *" \
  "nginx-threat-pipeline.sh" \
  "" "" "" "origin" "" "true"

# Daily soul refinement (LLM with soul-refinement skill)
create_cron "agent-daily-soul-refinement" "0 23 * * *" \
  "" \
  "Load the soul-refinement skill. Use session_search() to find today's sessions. Look for any user corrections, feedback, or behavior patterns worth noting. Update SOUL.md with insights. Keep it under 5KB." \
  "soul-refinement" "" "origin" "" "false" \
  "deepseek-v4-flash" "opencode-zen"

# ── 7. Universal Agent Crons ──────────────────────────────
printf "\n${CYAN}  7. Universal Agent Crons${RESET}\n"

# LLM judge scorer — weekday (Mon-Fri 12:00 and 20:00)
create_cron "llm-judge-scorer-weekday" "0 12,20 * * 1-5" \
  "llm-judge-scorer.py" \
  "" "" "" "local" "" "true"

# LLM judge scorer — weekend (Sat-Sun 22:00)
create_cron "llm-judge-scorer-weekend" "0 22 * * 0,6" \
  "llm-judge-scorer.py" \
  "" "" "" "local" "" "true"

# Offline code index rebuild (weekly Sunday 05:00)
create_cron "offline-code-index" "0 5 * * 0" \
  "offline_code_index_cron.sh" \
  "" "" "" "local" "" "true"

# Model health watchdog (daily 07:00)
create_cron "model-health-watchdog" "0 7 * * *" \
  "model-health-watchdog.py" \
  "" "" "" "origin" "" "true"

# Agent inbox message processing (LLM, hourly 6am-11pm)
create_cron "process-mcp-agent-inbox-messages" "0 6-23 * * *" \
  "" \
  "Check the agent inbox for new messages via inbox-watch MCP tool (mcp_agent_inbox_inbox_watch). If new messages are found, read (mcp_agent_inbox_inbox_read) and process using the Inbox Message Decision Framework. Report actionable items with evidence. Outside 6am-11pm daily, be silent if nothing urgent." \
  "" "" "origin" "" "false" \
  "deepseek-v4-flash" "opencode-zen"

# Scoring activity watchdog — alerts if too few cycles logged today
create_cron "scoring-activity-watchdog" "0 14,20 * * *" \
  "scoring-activity-watchdog.py" \
  "" "" "" "origin" "" "true"

# Loop-governance: skill miner — mines local data, sends findings via inbox
create_cron "skill-miner" "0 6 * * 1" \
  "skill_miner.py" \
  "" "" "" "origin" "" "true"

# Loop-governance: weekly evaluation — report, skill miner, auto-apply, retention
create_cron "agent-weekly-loop-eval" "0 9 * * 1" \
  "" \
  "Run the loop governance evaluation pipeline for the last 7 days, then run the skill miner, auto-apply safe config changes, and vacuum old cycles.\n\n1. Generate the evaluation report using the loop-governance skill (last 7 days).\n2. Run the skill miner: execute `skill-miner` and report findings.\n3. Run auto-apply: execute `auto-apply --json`. Report what was applied or skipped.\n4. Run DB retention (archive cycles older than 90 days).\n5. Deliver a combined message." \
  "loop-governance" "" "origin" "" "false" \
  "deepseek-v4-flash" "opencode-zen"

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
