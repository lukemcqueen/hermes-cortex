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
  local _ollama_out
  _ollama_out=$(python3 << "PYEOF" 2>&1)
import os
fp = os.path.expanduser("${config_file}")
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
    # Try inserting before fallback_providers:
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
    "agent-fixer" "system-heartbeat" "memory-to-brain-sync" \
    "system-alert-watchdog" "service-recovery" "inbox-sensor" "inbox-flag" \
    "orch-team-messages" "orch-team-health" "remediation-sensor" \
    "hermes-update" "gbrain-nightly-dream" "gbrain-update-sync" \
    "hermes-cortex-sync" "harvest-lessons" "memory-pruning" \
    "auto-save-sessions" "agent-daily-bible-reading" \
    "agent-daily-soul-refinement" \
    "llm-judge-scorer-weekday" "llm-judge-scorer-weekend" \
    "offline-code-index" "model-health-watchdog" \
    "agent-inbox" "agent-remediate-apply" "agent-apply-fixes" \
    "score-auditor" "threat-pipeline" "agent-ip-submission" \
    "scoring-activity-watchdog" "skill-miner" "agent-weekly-loop-eval" \
    "session-cache-build" "cron-quality-watchdog"; do
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

# Setup local Ollama provider for qwen crons
setup_ollama_provider

# ── 1. Auto-Remediation Pipeline ────────────────────────────
printf "${CYAN}  1. Auto-Remediation Pipeline${RESET}\\\n"

# LLM-driven auto-remediation (every 2h)
create_cron "agent-fixer" "0 */2 * * *" \
  "" \
  "Run the auto-remediation workflow using the auto-remediation skill. Load the skill first, check for errors, fix, report.

## OUTPUT FORMAT — FOLLOW EXACTLY
Match this structure line for line. Your content replaces the values.
Everything else stays: dashes, colons, spacing, line breaks.

agent-fixer (JOB_ID) [YYYY-MM-DD HH:MM KST]
-------------

Phase 1 — Issues found: 2 active issues detected
- [nginx] port 13001 unreachable
- [disk] /var/log at 85% capacity

Phase 2 — Fixes applied: 2 of 2 resolved
- nginx: service restart succeeded
- disk: log rotation freed 2.3GB

Phase 3 — Unresolved: 0 remaining

Result: All issues fixed. System nominal.

📊 deepseek-v4-flash (opencode-zen) | \$0.006/run ≈ \$2.18/mo

If nothing to report: output exactly [SILENT]" \
  "auto-remediation" \
  "terminal,file,web" \
  "origin" \
  "$HOME" \
  "false" \
  "deepseek-v4-flash" "opencode-zen"

# Companion sensor (no_agent, every 5 min)
create_cron "remediation-sensor" "*/5 * * * *" \
  "remediation-sensor.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# Inbox flag sensor (no_agent, every 10 min) — feeds context to agent-inbox
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

# ── 4. Agent Inbox Processing ────────────────────────────────
printf "\\n${CYAN}  4. Agent Inbox Processing${RESET}\\\n"

create_cron "inbox-sensor" "*/10 * * * *" \
  "inbox-sensor.py" \
  "" \
  "" \
  "" \
  "local" \
  "" \
  "true"

# ── 5. Change Scoring Audit ──────────────────────────────────
printf "\\n${CYAN}  5. Change Scoring Audit${RESET}\\\n"

create_cron "score-auditor" "0 */6 * * *" \
  "score-auditor.py" \
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

# Agent inbox message processing (LLM, every 2h, cost-optimized with inbox-flag sensor)
create_cron "agent-inbox" "0 */2 * * *" \
  "" \
  "Process the agent inbox using the Inbox Message Decision Framework. The inbox-flag sensor output is injected below as context — it shows which new messages (if any) are waiting for you.

## Standard inbox processing
1. Read the context_from sensor output to see if there are new messages
2. If no messages: output [SILENT] and nothing else
3. If messages exist: use inbox-watch and inbox-read MCP tools
4. For each unread message, use the Inbox Message Decision Framework:
   - Assess Priority (critical/urgent/normal)
   - Assess Actionability (AUTO-ACT / DELEGATE / ESCALATE / ACKNOWLEDGE)
   - Assess Scope (simple/moderate/complex/multi-agent)
5. Act according to the decision matrix
6. Deliver a concise report of what was processed

## Agent Cron Management (🔗 CRON requests)
When an agent sends an inbox message with subject \`🔗 CRON: create|update|remove\`, process it.

## OUTPUT FORMAT — FOLLOW EXACTLY
Match this structure line for line. Your content replaces the values.
Everything else stays: dashes, colons, spacing, line breaks.

agent-inbox (JOB_ID) [YYYY-MM-DD HH:MM KST]
-------------

Phase 1 — Messages found: 2 unread messages waiting
- 🔗 CRON: create from titus — wants new disk-watchdog cron
- [normal] from moses — system health check passed

Phase 2 — Actions taken: 2 of 2 processed
- Created disk-watchdog cron (schedule: */30 * * * *, no_agent)
- Acknowledged health check — no action needed

Phase 3 — Escalated: 0

Result: Inbox empty. All items processed.

📊 deepseek-v4-flash (opencode-zen) | \$0.006/run ≈ \$2.18/mo

If nothing to report: output exactly [SILENT]" \
  "" "" "origin" "" "false" \
  "deepseek-v4-flash" "opencode-zen"

# Agent-specific local fixer (local model, every 10m — reads sensor output, applies fixes)
create_cron "agent-apply-fixes" "*/10 * * * *" \
  "" \
  "Process remediation markers in ~/.hermes/state/remediate/. If markers exist, read them and apply fixes. Report results or stay silent if nothing to fix." \
  "" "" "local" "" "false" \
  "qwen2.5-coder:3b" "custom:ollama-local"

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

# Loop-governance: skill miner — mines local data, sends findings via inbox
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
  "deepseek-v4-flash" "opencode-zen"

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

# ── 7. Orchestrator-Only Crons ──────────────────────────────────
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

# ── 8. Deployment-Specific Crons ─────────────────────────────
# These are specific to Luke's deployment but tracked in the
# repo so install-crons.sh --force can recreate them.
# (All crons listed in the AGENTS.md reference table.)

printf "\n${CYAN}  8. Deployment-Specific Crons${RESET}\n"

# Daily Hermes Agent self-update
create_cron "hermes-update" "23 22 * * *" \
  "hermes-update.sh" \
  "" \
  "" \
  "" \
  "origin" \
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
  "deepseek-v4-flash" "opencode-zen"

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

# Agent IP submission processor — every 30 min, merges blocked_ips.submit into blocked_ips.add
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
