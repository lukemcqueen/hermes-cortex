#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  install-crons.sh — Register essential Hermes Agent cron jobs
#
#  Creates Hermes Agent-level cron jobs (no_agent watchdogs and
#  LLM-driven crons) for auto-remediation, system health, web
#  cache, and memory synchronization.
#
#  ONLY add crons here that belong in the repo — infrastructure
#  other agents could use. Local-only crons (server-specific
#  maintenance, personal briefings, ad-hoc watchdogs) go directly
#  via `cronjob action='create' name='local-<name>'` and use
#  the `local-*` prefix. They do NOT belong in this installer.
#  See the cron-job-management skill for full naming convention.
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
    sys.exit(1)
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
  # Also check repo source (including subdirs like agent/, manage/, orch-bus/)
  if [[ -f "${SCRIPT_DIR}/${script}" ]]; then
    return 0
  fi
  if find "${SCRIPT_DIR}" -maxdepth 2 -name "${script}" -type f 2>/dev/null | grep -q .; then
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

  if $exists; then
    if ! $FORCE; then
      # Drift detection: check if existing cron's script OR skill differs from desired.
      # Script-only checks miss skill renames on LLM crons (empty script) — e.g. the
      # agent-inbox → agent-bus-* rename (2026-07-27) left deployed jobs referencing
      # non-existent skills, silently skipped by the scheduler every fire. Compare both.
      local _drift=false
      if { [[ -n "$script" || -n "$skill" ]] && [[ -f "$CRON_JOBS_FILE" ]]; } && command -v python3 &>/dev/null; then
        local _cur_script _cur_skill
        IFS=$'\x1f' read -r _cur_script _cur_skill < <(python3 -c "
import json, sys
try:
    with open('$CRON_JOBS_FILE') as f:
        data = json.load(f)
    jobs = data.get('jobs', []) if isinstance(data, dict) else data
    for j in jobs:
        if isinstance(j, dict) and j.get('name') == '$name':
            sys.stdout.write((j.get('script', '') or '') + '\x1f' + (j.get('skill', '') or '') + '\n')
            sys.exit(0)
except: pass
sys.exit(1)
" 2>/dev/null || true) || true
        if [[ -n "$script" && -n "$_cur_script" && "$_cur_script" != "$script" ]]; then
          _drift=true
          info "Drift detected: cron '${name}' script '${_cur_script}' → '${script}'"
        fi
        if [[ -n "$skill" && -n "$_cur_skill" && "$_cur_skill" != "$skill" ]]; then
          _drift=true
          info "Drift detected: cron '${name}' skill '${_cur_skill}' → '${skill}'"
        fi
      fi
      if ! $_drift; then
        SKIPPED=$((SKIPPED + 1))
        return 0
      fi
      # Fall through to the edit path below (drift detected)
      local _do_edit=true
    else
      local _do_edit=false
    fi
  else
    local _do_edit=false
  fi

  # Verify script exists before creating cron
  if [[ -n "$script" ]] && ! script_exists "$script"; then
    warn "Script not found: ${script} — skipping cron '${name}'"
    FAILED=$((FAILED + 1))
    return 0
  fi

  if $DRY_RUN; then
    local action="Create"
    if $exists && { $FORCE || ${_do_edit:-false}; }; then
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
  if $exists && { $FORCE || ${_do_edit:-false}; } && [[ -n "$HERMES_CMD" ]]; then
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
    sys.exit(1)
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
    "agent-agents-md-prune-apply" \
    "agent-agents-md-prune-scan" \
    "agent-apply-fixes" \
    "agent-auto-save-sessions" \
    "agent-bus-evening" \
    "agent-bus-overnight" \
    "agent-bus-workday" \
    "agent-cron-quality-watchdog" \
    "agent-daily-bible-reading" \
    "agent-fixer-evening" \
    "agent-fixer-overnight" \
    "agent-fixer-workday" \
    "agent-governance-auditor" \
    "agent-hermes-cortex-sync" \
    "agent-hermes-update" \
    "agent-inbox-evening" \
    "agent-inbox-overnight" \
    "agent-inbox-workday" \
    "agent-ip-submission" \
    "agent-langfuse-health-watchdog" \
    "agent-learning-collector" \
    "agent-llm-judge-scorer-weekday" \
    "agent-llm-judge-scorer-weekend" \
    "agent-memory-pruning" \
    "agent-memory-to-brain-sync" \
    "agent-message-handler" \
    "agent-mycortex-sync" \
    "agent-mycortex-retention" \
    "agent-model-health-watchdog" \
    "agent-nginx-threat-pipeline" \
    "agent-no-verify-audit" \
    "agent-offline-code-index" \
    "agent-push-metrics" \
    "agent-remediate-apply" \
    "agent-remediation-sensor" \
    "agent-scoring-activity-watchdog" \
    "agent-secret-leak-watchdog" \
    "agent-service-recovery" \
    "agent-session-cache-build" \
    "agent-session-correction-scan" \
    "agent-session-mine" \
    "agent-stale-ref-watchdog" \
    "agent-system-alert-watchdog"; do
  
  
  

  
  
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

SILENT WHEN HEALTHY: Produce NO output when everything is clean. No all-clear summaries,
no \"nothing to report\" messages, no tables of zero counts. Only deliver output when you
find something actionable — failed workflows, stuck messages, blocked items, or critical
alerts. If all you did was run checks and everything is fine, stay completely silent." \
  "auto-remediation" \
  "terminal,file,web" \
  "origin" \
  "$HOME" \
  "false" \
  "$LLM_CRON_MODEL" "$LLM_CRON_PROVIDER"

create_cron "agent-fixer-evening" "0 18,20,22 * * 1-5" \
  "" \
  "Respond in English. Run the auto-remediation workflow using the auto-remediation skill. Load the skill first, check for errors, fix, report.

SILENT WHEN HEALTHY: Produce NO output when everything is clean. No all-clear summaries,
no \"nothing to report\" messages, no tables of zero counts. Only deliver output when you
find something actionable — failed workflows, stuck messages, blocked items, or critical
alerts. If all you did was run checks and everything is fine, stay completely silent." \
  "auto-remediation" \
  "terminal,file,web" \
  "origin" \
  "$HOME" \
  "false" \
  "$LLM_CRON_MODEL" "$LLM_CRON_PROVIDER"

create_cron "agent-fixer-overnight" "0 3 * * 1-5" \
  "" \
  "Respond in English. Run the auto-remediation workflow using the auto-remediation skill. Load the skill first, check for errors, fix, report.

SILENT WHEN HEALTHY: Produce NO output when everything is clean. No all-clear summaries,
no \"nothing to report\" messages, no tables of zero counts. Only deliver output when you
find something actionable — failed workflows, stuck messages, blocked items, or critical
alerts. If all you did was run checks and everything is fine, stay completely silent." \
  "auto-remediation" \
  "terminal,file,web" \
  "origin" \
  "$HOME" \
  "false" \
  "$LLM_CRON_MODEL" "$LLM_CRON_PROVIDER"

# Companion sensor (no_agent, every 5 min)
create_cron "agent-remediation-sensor" "*/5 * * * *" \
  "agent-remediation-sensor.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"



# ── 2. System Health Monitoring ──────────────────────────────
printf "\\n${CYAN}  2. System Health Monitoring${RESET}\\\n"

create_cron "agent-system-alert-watchdog" "*/30 * * * *" \
  "agent-system-alert-watchdog.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

create_cron "agent-service-recovery" "*/5 * * * *" \
  "agent-service-recovery.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# ── 3. Knowledge & Memory ────────────────────────────────────
printf "\\n${CYAN}  3. Knowledge & Memory${RESET}\\\n"

create_cron "agent-memory-to-brain-sync" "0 */6 * * *" \
  "agent-memory-to-brain-sync.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# mycortex knowledge brain sync — every 15 min (design D4: per-host, NOT
# orchestrator-only). Syncs this host's registered sources into the mycortex
# schema. no_agent watchdog pattern: silent on success, output only on
# failure. Jittered per host inside the wrapper (stable hostname-derived
# offset); advisory lock makes multi-host sync safe.
create_cron "agent-mycortex-sync" "*/15 * * * *" \
  "agent-mycortex-sync.sh" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# daily mycortex retention — prune ingest_log >90d, hard-purge archived
# pages past the 7-day soft-delete window (S-016). no_agent: silent when
# nothing pruned, one-line summary when rows are removed.
create_cron "agent-mycortex-retention" "0 6 * * *" \
  "agent-mycortex-retention.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# ── 4. Agent Bus Processing ───────────────────────────────────
printf "\\\\n${CYAN}   4. Agent Bus Processing${RESET}\\\\\\n"

# Agent message handler — polls inbox for UPDATE_REQUEST etc., runs --once per tick
create_cron "agent-message-handler" "*/5 * * * *" \
  "agent-message-handler.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# Bus processing — weekday (hourly M-F 9-5), evening (every 2h M-F 6-10), overnight (3am M-F)
create_cron "agent-bus-workday" "0 9-17 * * 1-5" \
  "" \
  "Process the Agent Bus using the Inbox Message Decision Framework. The bus-flag sensor output is injected as context. Check for any pending messages, urgent or critical items, blocked workflows, or DLQ items. SILENT WHEN HEALTHY: Produce NO output when everything is clean." \
  "agent-bus-automation" \
  "terminal" \
  "origin" \
  "" \
  "false" \
  "$LLM_CRON_MODEL" "$LLM_CRON_PROVIDER"

create_cron "agent-bus-evening" "0 18,20,22 * * 1-5" \
  "" \
  "Process the Agent Bus messages. The bus-flag sensor output is injected as context. Check for any pending messages, urgent or critical items, blocked workflows, or DLQ items. SILENT WHEN HEALTHY: Produce NO output when everything is clean." \
  "agent-bus-automation" \
  "terminal" \
  "origin" \
  "" \
  "false" \
  "$LLM_CRON_MODEL" "$LLM_CRON_PROVIDER"

create_cron "agent-bus-overnight" "0 3 * * 1-5" \
  "" \
  "Process the Agent Bus overnight. The bus-flag sensor output is injected as context. Check for any urgent or critical items, blocked workflows, or DLQ items. SILENT WHEN HEALTHY: Produce NO output when everything is clean." \
  "agent-bus-automation" \
  "terminal" \
  "origin" \
  "" \
  "false" \
  "$LLM_CRON_MODEL" "$LLM_CRON_PROVIDER"


# ── 5. Inbox Processing ────────────────────────────────
printf "\n${CYAN}  5. Inbox Processing${RESET}\n"

create_cron "agent-inbox-workday" "0 9-17 * * 1-5" \
  "" \
  "Process pending inbox messages using the Inbox Message Decision Framework. Read unread inbox messages, classify them using Priority/Actionability/Scope axes, and auto-act, delegate, escalate, or acknowledge each. SILENT WHEN HEALTHY: Produce NO output when nothing actionable." \
  "agent-bus-automation" \
  "terminal" \
  "origin" \
  "" \
  "false" \
  "$LLM_CRON_MODEL" "$LLM_CRON_PROVIDER"

create_cron "agent-inbox-evening" "0 18,20,22 * * 1-5" \
  "" \
  "Process pending inbox messages using the Inbox Message Decision Framework. Read unread inbox messages, classify them using Priority/Actionability/Scope axes, and auto-act, delegate, escalate, or acknowledge each. SILENT WHEN HEALTHY: Produce NO output when nothing actionable." \
  "agent-bus-automation" \
  "terminal" \
  "origin" \
  "" \
  "false" \
  "$LLM_CRON_MODEL" "$LLM_CRON_PROVIDER"

create_cron "agent-inbox-overnight" "0 3 * * 1-5" \
  "" \
  "Process pending inbox messages using the Inbox Message Decision Framework. Read unread inbox messages, classify them using Priority/Actionability/Scope axes, and auto-act, delegate, escalate, or acknowledge each. SILENT WHEN HEALTHY: Produce NO output when nothing actionable." \
  "agent-bus-automation" \
  "terminal" \
  "origin" \
  "" \
  "false" \
  "$LLM_CRON_MODEL" "$LLM_CRON_PROVIDER"

# ── 6. Governance Audit & Lock Cleanup

create_cron "agent-governance-auditor" "0 */6 * * *" \
  "agent-governance-auditor.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# ── 7. Universal Agent Crons ──────────────────────────────
printf "\n${CYAN}  7. Universal Agent Crons${RESET}\n"

# LLM judge scorer — weekday (Mon-Fri 12:00 and 20:00)
create_cron "agent-llm-judge-scorer-weekday" "0 12,20 * * 1-5" \
  "agent-llm-judge-scorer.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# LLM judge scorer — weekend (Sat-Sun 22:00)
create_cron "agent-llm-judge-scorer-weekend" "0 22 * * 0,6" \
  "agent-llm-judge-scorer.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# Model health watchdog (daily 07:00)
create_cron "agent-model-health-watchdog" "0 7 * * *" \
  "agent-model-health-watchdog.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Langfuse health + ClickHouse merge watchdog (silent when healthy, every hour)
create_cron "agent-langfuse-health-watchdog" "0 * * * *" \
  "agent-langfuse-health-watchdog.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"


# Agent remediation apply (no_agent script — reads sensor output, applies deterministic fixes)
create_cron "agent-remediate-apply" "*/10 * * * *" \
  "agent-remediate-apply.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Agent apply-fixes — companion to sensor: reads sensor output, applies deterministic fixes
create_cron "agent-apply-fixes" "*/10 * * * *" \
  "agent-apply-fixes.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# Scoring activity watchdog — alerts if too few cycles logged today
create_cron "agent-scoring-activity-watchdog" "0 14,20 * * *" \
  "agent-scoring-activity-watchdog.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"


# Session embedding cache rebuild (weekly Monday 05:00 — universal, loop-governance)
create_cron "agent-session-cache-build" "0 5 * * 1" \
  "agent-session_cache.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Daily agent card generation (06:00)

# Replaced by orch-skill-lifecycle (install-orch-crons.sh, 04:00 daily)

# Agent learning collector — every 6h: collect skills delta + lessons + session stats from ALL agents
create_cron "agent-learning-collector" "0 */6 * * *" \
  "agent-learning-collector.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# Agent session mine — overnight: mines sessions and dumps lessons into ~/brain/lessons/
create_cron "agent-session-mine" "0 2 * * *" \
  "agent-session-mine-cron.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# Cron output quality gate (every 10 min, silent when healthy — universal)
create_cron "agent-cron-quality-watchdog" "*/10 * * * *" \
  "agent-cron-quality-watchdog.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# ── 8. Deployment-Specific Crons ─────────────────────────────
# These are specific to Luke's deployment but tracked in the
# repo so install-crons.sh --force can recreate them.
# (All crons listed in the AGENTS.md reference table.)

printf "${CYAN}  8. Deployment-Specific Crons${RESET}\n"

# Daily Hermes Agent self-update
create_cron "agent-hermes-update" "23 22 * * *" \
  "agent-hermes-update.sh" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# Weekly offline code index rebuild (Sunday 05:00 — rebuilds local code search index)
create_cron "agent-offline-code-index" "0 5 * * 0" \
  "agent-offline-code-index.sh" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# Daily hermes-cortex sync and update
create_cron "agent-hermes-cortex-sync" "33 22 * * *" \
  "agent-hermes-cortex-sync.sh" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Weekly memory pruning and consolidation (deepseek — needs Hermes memory tool)
create_cron "agent-memory-pruning" "0 4 * * 1" \
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
create_cron "agent-auto-save-sessions" "every 360m" \
  "agent-auto-save-sessions.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"




create_cron "agent-nginx-threat-pipeline" "0 5 * * *" \
  "agent-nginx-threat-pipeline.sh" \
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

# Agent metrics push (every 5 min, no_agent) — pushes system metrics to VictoriaMetrics
create_cron "agent-push-metrics" "every 5m" \
  "agent-push-metrics.sh" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# ── AGENTS.md auto-trim: daily scan + LLM apply (M-Sa) ──
# Phase 1: deterministic scan — silent when clean, JSON report when candidates found
create_cron "agent-agents-md-prune-scan" "0 4 * * 1-6" \
  "agent-agents-md-prune-scan.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# Phase 2: LLM review + apply — reads scan output via context_from
create_cron "agent-agents-md-prune-apply" "30 4 * * 1-6" \
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
  "documentation-scope" "" "origin" \
  "$HOME" "false" \
  "$LLM_CRON_MODEL" "$LLM_CRON_PROVIDER"

# ── 9. Skill Collection (universal — all agents) ──────────
printf "${CYAN}  9. Skill Collection Pipeline${RESET}\n"

# Collect custom skills every 6h — scans skills dirs, reports to Moses inbox
#  (Restored: send-skill-report — rewritten to use /api/pgmq/send with Bearer/Basic auth.
#  Now resolves CORTEX_BUS_URL → CORTEX_BUS_FALLBACK_URL, supports Basic auth for nginx proxy.
#  Fixed: was using deprecated /api/send endpoint. See ops/scripts/manage/send-skill-report.py)
#  Agent inbox migrated to Agent Bus (PGMQ). Collect-agent-skills.sh
#  Note: agent-collect-skills.sh script still on disk for manual debugging,
#  but the cron is removed — agent-learning-collector handles all collection.
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

# Secret leak watchdog (every 4h, scans cron outputs for leaked credentials)
create_cron "agent-secret-leak-watchdog" "0 */4 * * *" \
  "agent-secret-leak-watchdog.py" \
  "Scans cron outputs and session files for printf/echo credential leaks" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Stale ref watchdog (daily, scans deployment layers for broken symlinks/paths)
create_cron "agent-stale-ref-watchdog" "0 5 * * *" \
  "manage/agent-stale-ref-watchdog.sh" \
  "stale-ref-watchdog -- nightly stale-path scan across all deploy layers" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# Daily bible reading (LLM-driven, uses deepseek)
create_cron "agent-daily-bible-reading" "0 1 * * *" \
  "" \
  "Read the daily bible reading skill and produce today's scripture entry. Append the entry to ~/.hermes-cortex/brain/journal/daily-scripture.md" \
  "agent-daily-bible-reading" \
  "origin" \
  "" \
  "false" \
  "$LLM_CRON_MODEL" "$LLM_CRON_PROVIDER"

# No-verify audit — no-agent script checks for --no-verify commits every 60m
create_cron "agent-no-verify-audit" "every 60m" \
  "manage/agent-no-verify-audit.py" \
  "" \
  "" \
  "" \
  "origin" \
  "" \
  "true"

# ── Correction→Guardrail Recidivism Scan (weekly) ─────────
# P0-1: scans LOCAL state.db for user corrections, classifies, checks guardrail
# registry, flags unguarded + recidivism. Runs on EVERY agent (each host's
# state.db holds that agent's own corrections). Non-orchestrator agents
# forward a condensed report to inbox_moses so Moses can fold per-agent
# recidivism into enforcer work. no_agent — stdout is the report.
create_cron "agent-session-correction-scan" "0 22 * * 0" \
  "manage/agent-session-correction-scan.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# ── Auto-prune old-format cron names ──
# Remove legacy crons that lack the agent- prefix when an agent- replacement exists.
# These accumulate from older installs that used bare names (e.g. 'cron-quality-watchdog'
# before the convention became 'agent-cron-quality-watchdog').
prune_old_cron_names() {
  local jobs_file="${HERMES_HOME:-$HOME/.hermes}/cron/jobs.json"
  local pruned=0
  if [[ ! -f "$jobs_file" ]]; then
    return 0
  fi

  while IFS=$'\t' read -r old_id old_name; do
    # Derive the agent-prefixed name from the old name
    local agent_name="agent-${old_name}"
    # Check if the agent-prefixed version exists as a SEPARATE cron entry
    if grep -q "\"name\": \"$agent_name\"" "$jobs_file" 2>/dev/null; then
      echo "  Pruning duplicate: $old_name → (replaced by $agent_name)"
      hermes cron remove "$old_id" 2>/dev/null || true
      pruned=$((pruned + 1))
    fi
  done < <(python3 -c "
import json, sys
path = '$jobs_file'
try:
    with open(path) as f:
        data = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    sys.exit(0)
jobs = data.get('jobs', [])
agent_names = {j['name'] for j in jobs if j['name'].startswith('agent-')}
for j in jobs:
    name = j['name']
    # Skip agent-prefixed and local- prefixed crons
    if name.startswith('agent-') or name.startswith('local-'):
        continue
    # Check if an agent- version exists
    if f'agent-{name}' in agent_names:
        print(f'{j[\"id\"]}\t{name}')
" 2>/dev/null)

  if [[ $pruned -gt 0 ]]; then
    echo "  Pruned $pruned old-format cron name(s)"
  fi
}

prune_old_cron_names
