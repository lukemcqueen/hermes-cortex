#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  install-orch-crons.sh — Register orchestrator-only cron jobs
#
#  Creates Hermes Agent-level cron jobs that should ONLY run
#  on orchestrator machines (Moses primary, Esther backup).
#  Worker agents should NEVER run this script.
#
#  Guard: IS_ORCHESTRATOR=true in ~/hermes-cortex/.env
#  Fallback: hostname is 'moses' or 'esther' (legacy compat)
#
#  Usage:
#    bash install-orch-crons.sh              # create missing crons
#    bash install-orch-crons.sh --dry-run    # show what would be created
#    bash install-orch-crons.sh --force      # recreate all crons (overwrite)
#    bash install-orch-crons.sh --uninstall  # remove all orch crons
# ─────────────────────────────────────────────────────────────
set -euo pipefail

# ── Guard: orchestrator check via env var (with hostname fallback) ──
# IS_ORCHESTRATOR is the primary gate. Set in ~/hermes-cortex/.env:
#   IS_ORCHESTRATOR=true   (on orchestrators like Moses / Esther)
#   IS_ORCHESTRATOR=false  (on all other agents — default)
CORTEX_ENV="${REPO_DIR:-${HOME}/hermes-cortex}/.env"
if [[ -f "$CORTEX_ENV" ]]; then
  set -a; source "$CORTEX_ENV"; set +a
fi

_IS_ORCH=false
if [[ "${IS_ORCHESTRATOR:-false}" == "true" ]]; then
  _IS_ORCH=true
fi
# Fallback: hostname check for backward compat with pre-1.4 installs
if ! $_IS_ORCH; then
  HOSTNAME="$(hostname -s 2>/dev/null || echo 'unknown')"
  if [[ "$HOSTNAME" == "moses" || "$HOSTNAME" == "esther" ]]; then
    _IS_ORCH=true
  fi
fi

if ! $_IS_ORCH; then
  echo "✗ This script installs orchestrator-only crons (orch-team-messages)."
  echo "  IS_ORCHESTRATOR is not set to 'true' — only orchestrators need these crons."
  echo "  If you are a worker agent, you do NOT need orchestration crons."
  echo "  To run on this machine, set IS_ORCHESTRATOR=true in ~/hermes-cortex/.env"
  exit 0
fi

# ── Validate LLM cron model/provider env vars ──────────────
# LLM-driven crons need a model + provider. Set these in ~/hermes-cortex/.env.
# The install script sources .env above, so these will be picked up.
# If not set, halt with a clear message showing where to set them.
LLM_CRON_MODEL="${LLM_CRON_MODEL:-}"
LLM_CRON_PROVIDER="${LLM_CRON_PROVIDER:-}"

if [[ -z "$LLM_CRON_MODEL" || -z "$LLM_CRON_PROVIDER" ]]; then
  echo ""
  echo "━━━ LLM Cron Model/Provider Not Configured ━━━"
  echo ""
  echo "  LLM-driven cron jobs (skill-evaluate, memory-pruning, etc.)"
  echo "  need a model and provider. Set them in ~/hermes-cortex/.env:"
  echo ""
  echo "    LLM_CRON_MODEL=deepseek-v4-flash"
  echo "    LLM_CRON_PROVIDER=deepseek"
  echo ""
  echo "  These apply to all LLM-driven crons on this machine."
  echo "  Local-only crons (qwen on Ollama) use LOCAL_CRON_MODEL/PROVIDER."
  echo ""
  exit 1
fi

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
    "orch-team-messages" "orch-fleet-watchdog" \
    "skill-report-request" "skill-report-process" "skill-evaluate" \
    "orch-bus-forwarder-sync" "orch-bus-audit-watchdog" \
    "orch-bus-recover-timeouts" "orch-bus-confirmation-poller" \
    "orch-bus-confirmation-alert"; do
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
    _tmp="${CORTEX_DEPLOY_HOME:-${HOME}/.hermes-cortex}/state/_cron_find.py"
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

# Fleet health report — hourly weekday, twice Saturday (no_agent, Telegram-ready)
create_cron "orch-health-report-weekday" "0 9-18 * * 1-5" \
  "orch-health-report.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

create_cron "orch-health-report-saturday" "0 11,17 * * 6" \
  "orch-health-report.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Fleet watchdog — cross-agent health polling (no_agent, Telegram alerts)
# Orchestrator-only: Moses primary, Esther backup
create_cron "orch-fleet-watchdog" "*/5 * * * *" \
  "orch-fleet-watchdog.py" \
  "" \
  "" \
  "" \
  "telegram:1270130526" \
  "" \
  "true"

# ── 1a. Orchestrator Bus Tools (orch-bus-*) ──────────────
printf "${CYAN}  1a. Orchestrator Bus Tools${RESET}\n"

# Bidirectional bus sync — Moses primary ↔ Esther backup (every 2 min)
create_cron "orch-bus-forwarder-sync" "*/2 * * * *" \
  "orch-bus-forwarder.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Bus audit watchdog — new message events to Telegram (every 1 min)
create_cron "orch-bus-audit-watchdog" "*/1 * * * *" \
  "orch-bus-audit-watchdog.py" \
  "" \
  "" \
  "" \
  "telegram:1270130526" \
  "" \
  "true"

# Stuck message recovery — Postgres processing timeouts (every 5 min)
create_cron "orch-bus-recover-timeouts" "*/5 * * * *" \
  "orch-bus-recover-timeouts.sh" \
  "Recover stuck processing messages from the bus Postgres database every 5 minutes" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Bus confirmation poller — track message delivery confirmations (every 10m)
create_cron "orch-bus-confirmation-poller" "every 10m" \
  "orch-bus-message-tracker.py" \
  "poll" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# Bus confirmation alert — alert on undelivered messages (every 60m)
create_cron "orch-bus-confirmation-alert" "every 60m" \
  "orch-bus-message-tracker-alert.sh" \
  "alert" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# ── 2. Daily gbrain brain health check ──────────────────
printf "${CYAN}  2. Daily gbrain Brain Health Check${RESET}\n"

# Uses gbrain-wrapper.sh to pause autopilot, run doctor, restart.
# no_agent silent pattern: output only when issues found.

# ── 3. Skill Report Pipeline (orchestrator-only) ──────────
printf "${CYAN}  3. Skill Report Pipeline${RESET}\n"

# Weekly: request skill reports from all registered agents
create_cron "skill-report-request" "0 2 * * 1" \
  "request-skill-reports.sh" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Daily: process collected skill reports into digest
create_cron "skill-report-process" "0 3 * * *" \
  "process-skill-reports.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Weekly: evaluate collected skills and propose upstreaming
create_cron "skill-evaluate" "0 9 * * 2" \
  "" \
  "You are running a scheduled skill evaluation cron for the Moses orchestrator.\n\nYour job is to:\n1. Run process-skill-reports.py to collect any pending skill reports\n2. For each reported custom skill, evaluate:\n   - Is it well-structured? (proper YAML frontmatter, description, behavioral principles)\n   - Is it useful across the fleet or specific to one agent?\n   - Should it be upstreamed to hermes-cortex/.hermes-cortex/skills/ or left as-is?\n3. Summarize findings and recommendations for each skill\n\n## OUTPUT FORMAT — FOLLOW EXACTLY\nMatch this structure line for line. Your content replaces the values.\nEverything else stays: dashes, colons, spacing, line breaks.\n\nskill-evaluate (JOB_ID) [YYYY-MM-DD HH:MM KST]\n-------------\n\nPhase 1 — Collection: 3 new skill reports from 2 agents\n- titus: 2 custom skills\n- esther: 1 custom skill\n\nPhase 2 — Evaluation: 3 total skills reviewed\n- auto-remediation: ⭐ 5, upstream\n  - Strengths: clear workflow, COST-SAVING mandate, self-learning\n  - Weaknesses: none\n  - Recommendation: upstream to shared skills\n\nPhase 3 — Upstream candidates: 2 ready for public-contribution\n- auto-remediation → hermes-cortex/skills/devops/auto-remediation/\n\nResult: 3 evaluated, 2 recommended for upstreaming.\n\nIf no new reports: output exactly [SILENT]\n\n📊 deepseek-v4-flash (opencode-zen) | \$0.006/run ≈ \$1.80/mo" \
  "" "" "origin" "" "false" \
  "$LLM_CRON_MODEL" "$LLM_CRON_PROVIDER"

echo ""
printf "${CYAN}━━━ Summary ━━━${RESET}\n"
if $DRY_RUN; then
  printf "${CYAN}━━━ Summary (dry run) ─━━${RESET}\n"
  printf "  Would create:  %d\n" "$WOULD_CREATE"
  exit 0
fi
printf "${CYAN}━━━ Summary ─━━${RESET}\n"
printf "  Created: %d  Skipped: %d  Failed: %d\n" "$CREATED" "$SKIPPED" "$FAILED"
echo ""
