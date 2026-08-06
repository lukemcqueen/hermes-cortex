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

# ── Guard: orchestrator check via shared os-config.sh ──
# Sources os-config.sh for agent-type detection (hostname+home-dir
# authoritative) + check_agent_type helper. IS_ORCHESTRATOR env/.env
# values grant no orch powers — os-config never promotes from env.
# os-config.sh deploys to ${CORTEX_DEPLOY_HOME}/scripts/install/ while this
# script deploys flat to scripts/ — resolve from either location.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"
OS_CONFIG=""
for candidate in "${SCRIPT_DIR}/os-config.sh" "${SCRIPT_DIR}/install/os-config.sh"; do
  if [[ -f "$candidate" ]]; then
    OS_CONFIG="$candidate"
    break
  fi
done
if [[ -z "$OS_CONFIG" ]]; then
  echo "ERROR: os-config.sh not found (needed for check_agent_type). Run cortex-update.sh to deploy." >&2
  exit 1
fi
source "$OS_CONFIG"
# .env is sourced for cron config values (model, provider) — NOT for role.
# Role comes exclusively from os-config.sh's hostname+home-dir detection.
CORTEX_ENV="${REPO_DIR:-${HOME}/hermes-cortex}/.env"
if [[ -f "$CORTEX_ENV" ]]; then
  set -a; source "$CORTEX_ENV"; set +a
fi
# Self-audit: refuse if not orchestrator
check_agent_type "orchestrator" "${BASH_SOURCE[0]}" || {
  echo "  Run --uninstall to remove any existing orch crons:"
  echo "    bash ${BASH_SOURCE[0]} --uninstall"
  exit 1
}

# ── Telegram recipient (PII — never hardcoded) ────────────
# Resolved from ~/.hermes/.env (same file agent-message-handler.py reads for
# TELEGRAM_BOT_TOKEN). TELEGRAM_HOME_CHANNEL is the canonical Hermes env var
# (gateway/cron scheduler resolve it per host) — already present on every
# agent; no new var. create_cron fails loudly if a telegram-delivering cron
# is requested without it — never a hardcoded literal, never deliver-nowhere.
TELEGRAM_HOME_CHANNEL="$(grep -E '^TELEGRAM_HOME_CHANNEL=' "${HERMES_HOME:-${HOME}/.hermes}/.env" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"

# ── Repo path ──────────────────────────────────────────────
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

# os-config.sh already sourced at the top (guard block) — path resolution
# there covers both repo-sibling and deployed-subdir layouts. Keep this
# explicit re-source only if os-config.sh changed; otherwise it is redundant.
[[ -n "$OS_CONFIG" ]] || OS_CONFIG="${SCRIPT_DIR}/os-config.sh"
source "$OS_CONFIG"

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
    "orch-bus-audit-watchdog" \
    "orch-bus-confirmation-alert" \
    "orch-bus-confirmation-poller" \
    "orch-bus-forwarder-sync" \
    "orch-bus-inbox-relay" \
    "orch-bus-recover-timeouts" \
    "orch-clean-health-queue" \
    "orch-fleet-watchdog" \
    "orch-health-report-saturday" \
    "orch-health-report-weekday" \
    "orch-skill-lifecycle" \
    "orch-skill-evaluate" \
    "orch-skill-report-request"; do
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
    sys.exit(1)
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

  # Fail-loud guard: a telegram-delivering cron requires TELEGRAM_HOME_CHANNEL
  # from ~/.hermes/.env — never a hardcoded literal, never deliver-nowhere.
  if [[ "$deliver" == "telegram:"* && -z "$TELEGRAM_HOME_CHANNEL" ]]; then
    echo "✗ cron '${name}': telegram deliver target requires TELEGRAM_HOME_CHANNEL in ${HERMES_HOME:-${HOME}/.hermes}/.env (refusing to create a cron that delivers nowhere)" >&2
    exit 1
  fi

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
    sys.exit(1)
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

# ── 0. Clean up old-format cron names (pre-orch-* rename) ──
printf "${CYAN}  0. Cleaning up old-format cron names${RESET}\n"
for old_name in "skill-report-request" "skill-report-process" "skill-evaluate"; do
  if cron_exists "$old_name"; then
    remove_cron "$old_name"
  fi
done

# ── 1. Orchestrator Crons ─────────────────────────────────
printf "${CYAN}  1. Orchestrator-Specific Crons${RESET}\n"

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
  "telegram:${TELEGRAM_HOME_CHANNEL}" \
  "" \
  "true"

# ── 1a. Bus Tools (bus-*) ───────────────────────────
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

# Failover inbox relay — backup orchestrator processes the shared
# orchestrator inbox while acting primary (every 5 min; silent when idle)
create_cron "orch-bus-inbox-relay" "*/5 * * * *" \
  "orch-bus-inbox-relay.py" \
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
  "telegram:${TELEGRAM_HOME_CHANNEL}" \
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
  "orch-bus-confirmation-poller.py" \
  "poll" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# Bus confirmation alert — alert on undelivered messages (every 60m)
create_cron "orch-bus-confirmation-alert" "every 60m" \
  "orch-bus-confirmation-alert.sh" \
  "alert" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Drain and archive health pings from inbox_health_check (every 10m)
create_cron "orch-clean-health-queue" "*/10 * * * *" \
  "orch-clean-health-queue.py" \
  "Drain and archive health pings from inbox_health_check. Archives old pings and reports count." \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# ── 3. Skill Lifecycle Pipeline (orchestrator-only) ──────────
printf "${CYAN}  3. Skill Lifecycle Pipeline${RESET}\n"

# Unified daily skill lifecycle — replaces old skill-miner, skill-triage, harvest-lessons,
# agent-weekly-loop-eval, agent-daily-soul-refinement
# Reads inbox_orchestrator for BOTH Learning Report: and Skill Report: formats from ALL agents.
create_cron "orch-skill-lifecycle" "0 4 * * *" \
  "" \
  "Load the orch-skill-lifecycle skill and follow the three-phase pipeline. Run the complete skill lifecycle for today.

Phase 1 — Collection:
1. Read inbox_orchestrator PGMQ queue (the shared orchestrator inbox — where agents send reports) for ALL agent reports:
   - \"Learning Report:\" from agent-learning-collector (skills delta, lessons, session stats — every 6h)
2. Check git log for self-improvement patterns needing broader consolidation
3. Scan skill inventory for stale/modified skills
4. Cross-reference reports across agents for consolidation candidates

Phase 2 — Evaluation:
For each item found, classify it. Deduplicate against existing skills. Cross-reference across agents — if 3 agents report the same fix, it's a consolidation candidate. If today is Monday, run the full deep evaluation pass.

Phase 3 — Upgrade:
Execute approved actions: patch skills via skill_manage, create new ones, prune stale ones, update SOUL.md with principles, upstream new skills to the repo, archive processed bus messages.

If nothing changed: output exactly [SILENT]" \
  "orch-skill-lifecycle" "terminal,file,web" "origin" "" "false" \
  "$LLM_CRON_MODEL" "$LLM_CRON_PROVIDER"

# ── 4. Skill Report Pipeline ──────────────────────────────
printf "${CYAN}  4. Skill Report Pipeline${RESET}\n"

# Request skill reports from all agents (weekly Monday 2am)
create_cron "orch-skill-report-request" "0 2 * * 1" \
  "orch-skill-report-request.sh" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Evaluate reported skills and decide on upstreaming (Tuesday 9am)
create_cron "orch-skill-evaluate" "0 9 * * 2" \
  "orch-skill-evaluate.sh" \
  "You are running a scheduled skill evaluation cron for the orchestrator.

Your job is to:
1. Run orch-skill-report-process.py to collect any pending skill reports
2. For each reported custom skill, evaluate its quality, relevance, and whether it should be upstreamed to the repo
3. Report findings on what was evaluated and what was decided" \
  "skill-vetting" \
  "" \
  "origin" \
  "" \
  "false" \
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
