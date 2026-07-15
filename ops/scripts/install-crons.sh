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
source "${SCRIPT_DIR}/install/os-config.sh"

# ── Source project .env ──────────────────────────────────
# ~/hermes-cortex/.env contains LLM_CRON_MODEL, LLM_CRON_PROVIDER,
# LOCAL_CRON_MODEL, LOCAL_CRON_PROVIDER, and other runtime vars.
# Source it before validation so agents don't need manual exports.
ENV_FILE="${HOME}/hermes-cortex/.env"
if [[ -f "$ENV_FILE" ]]; then
  set -a; source "$ENV_FILE"; set +a
fi

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

# ── Pre-flight checks ──────────────────────────────────────
if $UNINSTALL; then
  if [[ -z "$HERMES_CMD" ]]; then
    warn "Hermes not found — nothing to uninstall"
    exit 0
  fi
  info "Uninstalling Hermes cron jobs…"
  # Allow uninstall even without hermes by removing from jobs.json
fi

# ── Helper: check if a cron job exists ────────────────────
cron_exists() {
  local name="$1"

  # Method 1: Check jobs.json (fast, direct)
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

  # Method 2: Fallback to hermes CLI (more robust — works even if
  # jobs.json is temporarily locked, being rewritten, or missing)
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
    return 0  # No script required (skill-based cron)
  fi
  if [[ -f "${SCRIPTS_DIR}/${script}" ]]; then
    return 0
  fi
  # Also check repo source
  if [[ -f "${SCRIPT_DIR}/${script}" ]]; then
    return 0
  fi
  # Check CLI wrapper symlinks (loop-governance setup.sh)
  if [[ -f "${HOME}/.local/bin/${script}" ]]; then
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
      action="Update (force)"
    fi
    info "[DRY-RUN] ${action} cron: ${name}"
    printf "  schedule=%s\\n" "$schedule"
    printf "  script=%s\\n" "${script:-<none>}"
    printf "  skill=%s\\n" "${skill:-<none>}"
    [[ -n "$model"    ]] && printf "  model=%s\\n" "$model"
    [[ -n "$provider" ]] && printf "  provider=%s\\n" "$provider"
    WOULD_CREATE=$((WOULD_CREATE + 1))
    return 0
  fi

  # Remove existing cron if --force — actually use edit to avoid duplicates
  if $exists && $FORCE && [[ -n "$HERMES_CMD" ]]; then
    # Find job_id by name from jobs.json directly
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
      # Build edit command — only pass non-empty fields
      local edit_cmd=("$HERMES_CMD" "cron" "edit" "$job_id")
      edit_cmd+=("--schedule" "$schedule")
      if [[ -n "$script" ]]; then
        edit_cmd+=("--script" "$script")
      fi
      if [[ -n "$skill" ]]; then
        edit_cmd+=("--skill" "$skill")
      fi
      if [[ -n "$deliver" ]]; then
        edit_cmd+=("--deliver" "$deliver")
      fi
      if [[ -n "$workdir" ]]; then
        edit_cmd+=("--workdir" "$workdir")
      fi
      if [[ "$no_agent" == "true" ]]; then
        edit_cmd+=("--no-agent")
      elif [[ -n "$script" ]]; then
        edit_cmd+=("--agent")
      fi
      if [[ -n "$prompt" ]]; then
        edit_cmd+=("--prompt" "$prompt")
      fi
      if "${edit_cmd[@]}" 2>&1; then
        info "Updated cron: ${name} (${schedule})"
        CREATED=$((CREATED + 1))
        # Pin model/provider post-edit
        if [[ -n "$model" || -n "$provider" ]]; then
          pin_cron_model "$name" "$model" "$provider"
        fi
      else
        warn "Failed to update cron: ${name}"
        FAILED=$((FAILED + 1))
      fi
      return 0
    fi
    # Fall through to create if we couldn't find the job_id
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


# ── Setup Local Ollama Provider ────────────────────────────
# Adds the custom:ollama-local provider to Hermes config.yaml
# so crons can use qwen2.5-coder:3b locally at zero cost.
setup_ollama_provider() {
  local config_file="${HERMES_HOME}/config.yaml"
  if [[ ! -f "$config_file" ]]; then
    warn "config.yaml not found at ${config_file} — cannot set up ollama provider"
    return 0
  fi
  if grep -q 'custom_providers:' "$config_file" 2>/dev/null && grep -q 'ollama-local' "$config_file" 2>/dev/null; then
    info "Local Ollama provider custom:ollama-local already configured"
    return 0
  fi
  if $DRY_RUN; then
    info "[DRY-RUN] Would add custom:ollama-local provider to config.yaml"
    return 0
  fi
  # Insert custom_providers block before fallback_providers
  local _tmp
  _tmp=$(mktemp)
  cat > "$_tmp" << 'PYEOF'
import os
fp = os.path.expanduser("REPLACE_CONFIG_FILE")
with open(fp) as f:
    text = f.read()
old_model = (
    '  default: deepseek-v4-flash\n'
    '  provider: opencode-zen\n'
)
if old_model in text:
    custom_block = (
        '  default: deepseek-v4-flash\n'
        '  provider: opencode-zen\n'
        'custom_providers:\n'
        '  ollama-local:\n'
        '    base_url: http://localhost:11434/v1\n'
        '    api_key: ""\n'
        '    api_mode: chat_completions\n'
        '    models:\n'
        '      qwen2.5-coder:3b:\n'
        '        context_length: 65536\n'
        '        ollama_num_ctx: 65536\n'
    )
    text = text.replace(old_model, custom_block, 1)
    with open(fp, 'w') as f:
        f.write(text)
    print("ADDED")
else:
    lines_t = text.split("\n")
    for i, line in enumerate(lines_t):
        if line.strip() == "fallback_providers:":
            custom_block = ('custom_providers:\n'
                '  ollama-local:\n'
                '    base_url: http://localhost:11434/v1\n'
                '    api_key: ""\n'
                '    api_mode: chat_completions\n'
                '    models:\n'
                '      qwen2.5-coder:3b:\n'
                '        context_length: 65536\n'
                '        ollama_num_ctx: 65536\n')
            lines_t.insert(i, custom_block)
            text = "\n".join(lines_t)
            with open(fp, 'w') as f:
                f.write(text)
            print("ADDED")
            break
PYEOF
  sed -i "s|REPLACE_CONFIG_FILE|$config_file|g" "$_tmp"
  local _ollama_out
  _ollama_out=$(python3 "$_tmp" 2>&1)
  rm -f "$_tmp"
  if [[ "$_ollama_out" == *"ADDED"* ]]; then
    info "Added local Ollama provider: custom:ollama-local"
  else
    warn "Could not auto-add custom provider — add manually to config.yaml"
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
    "agent-fixer-workday" "agent-fixer-evening" "agent-fixer-overnight" "system-heartbeat" "memory-to-brain-sync" \
    "system-alert-watchdog" "service-recovery" "inbox-sensor" "inbox-flag" \
    "inbox-depth-watchdog" \
    "remediation-sensor" \
    "hermes-update" "gbrain-nightly-dream" "gbrain-update-sync" \
    "hermes-cortex-sync" "harvest-lessons" "memory-pruning" \
    "auto-save-sessions" "agent-daily-bible-reading" \
    "agent-daily-soul-refinement" \
    "llm-judge-scorer-weekday" "llm-judge-scorer-weekend" \
    "offline-code-index" "model-health-watchdog" \
    "agent-remediate-apply" "agent-apply-fixes" \
    "governance-auditor" "threat-pipeline" "agent-ip-submission" \
    "scoring-activity-watchdog" "skill-miner" "agent-weekly-loop-eval" \
    "session-cache-build" "cron-quality-watchdog" \
    "collect-agent-skills"; do
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

# ── Validate LLM cron model/provider env vars ──────────────
# LLM-driven crons need a model + provider. Set in ~/hermes-cortex/.env.
# The install script now sources ~/hermes-cortex/.env via set -a above, so
# LLM_CRON_MODEL and LLM_CRON_PROVIDER will be picked up automatically.
LLM_CRON_MODEL="${LLM_CRON_MODEL:-}"
LLM_CRON_PROVIDER="${LLM_CRON_PROVIDER:-}"

if [[ -z "$LLM_CRON_MODEL" || -z "$LLM_CRON_PROVIDER" ]]; then
  echo ""
  echo "━━━ LLM Cron Model/Provider Not Configured ━━━"
  echo ""
  echo "  LLM-driven cron jobs need a model and provider."
  echo "  Set them in ~/hermes-cortex/.env:"
  echo ""
  echo "    LLM_CRON_MODEL=deepseek-v4-flash"
  echo "    LLM_CRON_PROVIDER=deepseek"
  echo ""
  echo "  These control which model/provider all LLM-driven crons use."
  echo "  Local-only crons (qwen on Ollama) use LOCAL_CRON_MODEL/PROVIDER."
  echo ""
  exit 1
fi

# Setup local Ollama provider for qwen crons
setup_ollama_provider

# ── 1. Auto-Remediation Pipeline ────────────────────────────
printf "${CYAN}  1. Auto-Remediation Pipeline${RESET}\\\n"

# LLM-driven auto-remediation tiered (workday: hourly M-F 9-6pm, evening: every 2h M-F 6-12am, overnight: once M-F 3am)
create_cron "agent-fixer-workday" "0 9-17 * * 1-5" \
  "" \
  "Respond in English. Run the auto-remediation workflow using the auto-remediation skill. Load the skill first, check for errors, fix, report.

## OUTPUT FORMAT — FOLLOW EXACTLY
Match this structure line for line. Your content replaces the values.
Everything else stays: dashes, colons, spacing, line breaks.

agent-fixer-workday (JOB_ID) [YYYY-MM-DD HH:MM KST]
-------------

Phase 1 — Issues found: 0 issues
- All crons healthy. All services running.

Phase 2 — Bus: Empty.

Phase 3 — System: Disk 37%, Memory 46GB/62GB.

Result: Nothing to fix. All nominal.

📊 deepseek-v4-flash (opencode-zen) | \$0.006/run ≈ \$0.03/mo

If nothing to report: output exactly [SILENT]" \
  "auto-remediation" \
  "terminal,file,web" \
  "origin" \
  "$HOME" \
  "false" \
  "$LLM_CRON_MODEL" "$LLM_CRON_PROVIDER"

create_cron "agent-fixer-evening" "0 18,20,22 * * 1-5" \
  "" \
  "Respond in English. Run the auto-remediation workflow using the auto-remediation skill. Load the skill first, check for errors, fix, report.

## OUTPUT FORMAT — FOLLOW EXACTLY
Match this structure line for line. Your content replaces the values.
Everything else stays: dashes, colons, spacing, line breaks.

agent-fixer-evening (JOB_ID) [YYYY-MM-DD HH:MM KST]
-------------

Phase 1 — Issues found: 0 issues
- All crons healthy. All services running.

Phase 2 — Bus: Empty.

Phase 3 — System: Disk 37%, Memory 46GB/62GB.

Result: Nothing to fix. All nominal.

📊 deepseek-v4-flash (opencode-zen) | \$0.006/run ≈ \$0.01/mo

If nothing to report: output exactly [SILENT]" \
  "auto-remediation" \
  "terminal,file,web" \
  "origin" \
  "$HOME" \
  "false" \
  "$LLM_CRON_MODEL" "$LLM_CRON_PROVIDER"

create_cron "agent-fixer-overnight" "0 3 * * 1-5" \
  "" \
  "Respond in English. Run the auto-remediation workflow using the auto-remediation skill. Load the skill first, check for errors, fix, report.

## OUTPUT FORMAT — FOLLOW EXACTLY
Match this structure line for line. Your content replaces the values.
Everything else stays: dashes, colons, spacing, line breaks.

agent-fixer-overnight (JOB_ID) [YYYY-MM-DD HH:MM KST]
-------------

Phase 1 — Issues found: 0 issues
- All crons healthy. All services running.

Phase 2 — Bus: Empty.

Phase 3 — System: Disk 37%, Memory 46GB/62GB.

Result: Nothing to fix. All nominal.

📊 deepseek-v4-flash (opencode-zen) | \$0.006/run ≈ \$0.002/mo

If nothing to report: output exactly [SILENT]" \
  "auto-remediation" \
  "terminal,file,web" \
  "origin" \
  "$HOME" \
  "false" \
  "$LLM_CRON_MODEL" "$LLM_CRON_PROVIDER"

# Companion sensor (no_agent, every 5 min)
create_cron "remediation-sensor" "*/5 * * * *" \
  "remediation-sensor.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# Inbox flag sensor (no_agent, every 10 min) — feeds context to bus LLM crons
create_cron "inbox-flag" "*/10 * * * *" \
  "inbox-flag.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# ── 2. System Health Monitoring ──────────────────────────────
printf "\\n${CYAN}  2. System Health Monitoring${RESET}\\\n"

create_cron "system-alert-watchdog" "*/30 * * * *" \
  "system-alert-watchdog.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

create_cron "service-recovery" "*/5 * * * *" \
  "service-recovery.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# ── 3. Knowledge & Memory ────────────────────────────────────
printf "\\n${CYAN}  3. Knowledge & Memory${RESET}\\\n"

create_cron "memory-to-brain-sync" "0 */6 * * *" \
  "memory-to-brain-sync.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# ── 4. Agent Bus Processing ───────────────────────────────────
printf "\\n${CYAN}   4. Agent Bus Processing${RESET}\\\n"

create_cron "inbox-sensor" "*/10 * * * *" \
  "inbox-sensor.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# Inbox depth watchdog (no_agent, every 1 min) — silent when empty, feeds context to bus crons
create_cron "inbox-depth-watchdog" "*/1 * * * *" \
  "bus/bus-depth-watchdog.sh" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "" \
  "true"

# ── 5. Governance Audit & Lock Cleanup ──────────────────────
printf "\\n${CYAN}  5. Change Scoring Audit${RESET}\\\n"

create_cron "governance-auditor" "0 */6 * * *" \
  "governance-auditor.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# ── 6. Universal Agent Crons ──────────────────────────────
printf "\n${CYAN}  6. Universal Agent Crons${RESET}\n"

# LLM judge scorer — weekday (Mon-Fri 12:00 and 20:00)
create_cron "llm-judge-scorer-weekday" "0 12,20 * * 1-5" \
  "llm-judge-scorer.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# LLM judge scorer — weekend (Sat-Sun 22:00)
create_cron "llm-judge-scorer-weekend" "0 22 * * 0,6" \
  "llm-judge-scorer.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# Offline code index rebuild (weekly Sunday 05:00)
create_cron "offline-code-index" "0 5 * * 0" \
  "offline_code_index_cron.sh" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# Model health watchdog (daily 07:00)
create_cron "model-health-watchdog" "0 7 * * *" \
  "model-health-watchdog.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Langfuse health + ClickHouse merge watchdog (silent when healthy, every hour)
create_cron "langfuse-health-watchdog" "0 * * * *" \
  "langfuse-health-watchdog.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Daily gbrain brain health check — pauses autopilot, runs doctor, restarts (macOS + Linux)
create_cron "agent-gbrain-doctor" "0 6 * * *" \
  "agent-gbrain-doctor.sh" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Agent-specific local fixer (no_agent script — reads markers, searches offline corpus, applies fixes)
create_cron "agent-apply-fixes" "*/10 * * * *" \
  "agent-apply-fixes.py" \
  "" \
  "" "" "local" "" "true"

# Agent remediation apply (no_agent script — reads sensor output, applies deterministic fixes)
create_cron "agent-remediate-apply" "*/10 * * * *" \
  "agent-remediate-apply.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Scoring activity watchdog — alerts if too few cycles logged today
create_cron "scoring-activity-watchdog" "0 14,20 * * *" \
  "scoring-activity-watchdog.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Loop-governance: skill miner — mines local data, sends findings via bus
create_cron "skill-miner" "0 6 * * 1" \
  "skill_miner.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Loop-governance: weekly evaluation — report, skill miner, auto-apply, retention
create_cron "agent-weekly-loop-eval" "0 9 * * 1" \
  "" \
  "Run the loop governance evaluation pipeline for the last 7 days, then run the skill miner, auto-apply safe config changes, and vacuum old cycles.

1. Generate the evaluation report using the loop-governance skill (last 7 days).
2. Run the skill miner: report findings.
3. Run auto-apply: report what was applied or skipped.
4. Run DB retention (archive cycles older than 90 days).
5. Deliver a combined message.

## OUTPUT FORMAT — FOLLOW EXACTLY
Match this structure line for line. Your content replaces the values.
Everything else stays: dashes, colons, spacing, line breaks.

agent-weekly-loop-eval (JOB_ID) [YYYY-MM-DD HH:MM KST]
-------------

Phase 1 — Evaluation report: 7-day analysis complete
- 43 cycles scored, avg score 7.2/10
- 15 STOP decisions, 28 LOOP
- Top task: fix-auth-403 (8 cycles, avg 8.1)

Phase 2 — Skill miner: 2 new skill patterns identified
- found recurrent \"docker-compose restart\" fix pattern
- found \"nginx config reload after deploy\" pattern

Phase 3 — Auto-apply + retention:
- 4 safe config changes applied (threshold adjustments)
- Archived 312 cycles older than 90 days
- DB vacuumed: freed 1.8MB

Result: Evaluation complete. 2 skills mined. DB cleaned.

📊 deepseek-v4-flash (opencode-zen) | \$0.006/run ≈ \$2.18/mo" \
  "loop-governance" "" "origin" "" "false" \
  "$LLM_CRON_MODEL" "$LLM_CRON_PROVIDER"

# Session embedding cache rebuild (weekly Monday 05:00 — universal, loop-governance)
create_cron "session-cache-build" "0 5 * * 1" \
  "session_cache.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Cron output quality gate (every 10 min, silent when healthy — universal)
create_cron "cron-quality-watchdog" "*/10 * * * *" \
  "cron-quality-watchdog.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# ── 7. Deployment-Specific Crons ─────────────────────────────
# These are specific to Luke's deployment but tracked in the
# repo so install-crons.sh --force can recreate them.
# (All crons listed in the AGENTS.md reference table.)

printf "\n${CYAN}  7. Deployment-Specific Crons${RESET}\n"

# Daily Hermes Agent self-update
create_cron "hermes-update" "23 22 * * *" \
  "hermes-update.sh" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# Weekly gbrain dream for knowledge enrichment
create_cron "gbrain-nightly-dream" "0 3 * * 6" \
  "gbrain-nightly-dream.sh" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Weekly gbrain update and health check
create_cron "gbrain-update-sync" "0 2 * * 0" \
  "gbrain-update-sync.sh" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Daily hermes-cortex sync and update
create_cron "hermes-cortex-sync" "33 22 * * *" \
  "hermes-cortex-sync.sh" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Weekly lesson harvesting
create_cron "harvest-lessons" "0 5 * * 1" \
  "harvest-lessons.sh" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Weekly memory pruning and consolidation (deepseek — needs Hermes memory tool)
create_cron "memory-pruning" "0 4 * * 1" \
  "" \
  "Consolidate Hermes agent memory and project agent instructions. Read MEMORY.md, USER.md from the active profile and project roots. Consolidate into compact pointers. Prune stale entries. Keep under 2,200 chars.

## OUTPUT FORMAT — FOLLOW EXACTLY
Match this structure line for line. Your content replaces the values.
Everything else stays: dashes, colons, spacing, line breaks.

memory-pruning (JOB_ID) [YYYY-MM-DD HH:MM KST]
-------------

Phase 1 — Memory read: MEMORY.md at 1,850 chars (12 entries), USER.md at 890 chars (8 entries)
- Found 3 stale entries (dated 2026-06-15 or earlier, no longer referenced in recent sessions)
- Found 2 verbose entries that could be consolidated

Phase 2 — Pruning applied: Removed 3 stale entries (185 chars freed)
- Consolidated 2 tool-quirk entries into 1 compact pointer
- Merged 2 user-preference entries into 1
- Final MEMORY.md: 1,420 chars (within 2,200 limit)

Phase 3 — USER.md: No changes needed — all 8 entries still current

Result: Memory consolidated. 3 stale entries pruned, 2 merged. Under limit.

📊 deepseek-v4-flash (opencode-zen) | \$0.006/run ≈ \$2.18/mo

If nothing to report: output exactly [SILENT]" \
  "" "" "origin" "" "false" \
  "$LLM_CRON_MODEL" "$LLM_CRON_PROVIDER"

# Auto-save sessions every 6 hours
create_cron "auto-save-sessions" "every 360m" \
  "auto-save-sessions.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# Daily bible reading (no_agent script — reads SOUL.md, calls deepseek API, appends)
create_cron "agent-daily-bible-reading" "0 1 * * *" \
  "agent-daily-bible-reading.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Daily threat pipeline — scanner → fail2ban → deploy → commit → push
create_cron "threat-pipeline" "0 5 * * *" \
  "nginx-threat-pipeline.sh" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Agent IP submission processor (every 30 min) — universal
create_cron "agent-ip-submission" "*/30 * * * *" \
  "agent-ip-submission.sh" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Daily soul refinement (deepseek — needs Hermes tools: session_search, memory, patch) — universal
create_cron "agent-daily-soul-refinement" "0 23 * * *" \
  "" \
  "Load the soul-refinement skill. Use session_search() to find today's sessions. Look for any user corrections, feedback, or behavior patterns worth noting. Update SOUL.md with insights. Keep it under 5KB.

## OUTPUT FORMAT — FOLLOW EXACTLY
Match this structure line for line. Your content replaces the values.
Everything else stays: dashes, colons, spacing, line breaks.

agent-daily-soul-refinement (JOB_ID) [YYYY-MM-DD HH:MM KST]
-------------

Phase 1 — Session mining: found 12 sessions today
- 3 corrections from user (fixed: nginx port naming, cron schedule typo)
- 2 recurring questions (add to SOUL.md Patterns section)
- 1 new tool quirk discovered (pgrep -x limitation)

Phase 2 — SOUL.md update:
- Added Communication Style section (user prefers bullet points)
- Added nginx-reload pitfall (use nginx -t before systemctl reload)
- Pruned stale Python 3.9 workaround (no longer deployed)

Phase 3 — Size check: SOUL.md at 4.2KB (under 5KB limit)

Result: SOUL.md refined. 2 corrections applied, 1 pattern added, 1 pitfall documented.

📊 deepseek-v4-flash (opencode-zen) | \$0.006/run ≈ \$2.18/mo

If nothing to report: output exactly [SILENT]" \
  "soul-refinement" "" "origin" "" "false" \
  "$LLM_CRON_MODEL" "$LLM_CRON_PROVIDER"

# ── AGENTS.md auto-trim: daily scan + LLM apply (M-Sa) ──
# Phase 1: deterministic scan — silent when clean, JSON report when candidates found
create_cron "agents-md-prune-scan" "0 4 * * 1-6" \
  "agents-md-prune-scan.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# Phase 2: LLM review + apply — reads scan output via context_from
create_cron "agents-md-prune-apply" "30 4 * * 1-6" \
  "" \
  "Review the AGENTS.md pruning scan report injected below (via context_from=agents-md-prune-scan).
If candidates exist and look correct, apply them by running:
  python3 ~/.hermes-cortex/scripts/agents-doc-audit.py --repo ~/hermes-cortex --prune --apply
Then commit and push the changes.
If no candidates (empty context) or you disagree with the recommendations, stay silent.

## OUTPUT FORMAT — FOLLOW EXACTLY
Match this structure line for line. Your content replaces the values.
Everything else stays: dashes, colons, spacing, line breaks.

agents-md-prune-apply (JOB_ID) [YYYY-MM-DD HH:MM KST]
-------------

Phase 1 — Scan: 12 candidates found
Phase 2 — Review: accepted 10 / rejected 2
Phase 3 — Apply: 10 sections moved to docs/

📊 deepseek-v4-flash (opencode-zen) | \$0.006/run ≈ \$0.18/mo

If nothing to apply: output exactly [SILENT]" \
  "" "" "origin" \
  "$HOME" "false" \
  "$LLM_CRON_MODEL" "$LLM_CRON_PROVIDER"

# ── 5. Skill Collection (universal — all agents) ──────────
printf "${CYAN}  5. Skill Collection Pipeline${RESET}\n"

# Collect custom skills every 6h — scans skills dirs, reports to Moses inbox
create_cron "collect-agent-skills" "0 */6 * * *" \
  "collect-agent-skills.sh" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# (Removed: send-skill-report — API endpoint /api/send no longer exists.
#  Agent inbox migrated to Agent Bus (PGMQ). Collect-agent-skills.sh
#  still runs independently; this reporter cron was dead code.)

echo ""
printf "${CYAN}━━━ Summary ━━━${RESET}\n"
if $DRY_RUN; then
  info "Would create: ${WOULD_CREATE} cron job(s)"
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
