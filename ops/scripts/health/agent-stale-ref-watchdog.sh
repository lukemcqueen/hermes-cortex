#!/usr/bin/env bash
# stale-ref-watchdog — nightly stale-path scan across all deploy layers
# SILENT on success (no output = no issue). Output only when stale refs found.
# Checks for:
#   1. Broken symlinks in ~/.hermes/ and ~/.hermes-cortex/
#   2. Deployed scripts referenced by crons that don't exist
#   3. Orphaned cron script paths
set -euo pipefail

EXIT_CODE=0
OUTPUT=""

log() { OUTPUT+="$1"$'\n'; }

log "[stale-ref-watchdog] $(date -u '+%Y-%m-%dT%H:%M:%SZ') — nightly stale-path scan"
log ""

# 1. Broken symlinks in deploy directories
log "--- Deploy symlinks ---"
DEPLOY_DIRS=(
  "$HOME/.hermes/scripts"
  "$HOME/.hermes/plugins"
  "$HOME/.hermes-cortex/scripts"
)
for dir in "${DEPLOY_DIRS[@]}"; do
  if [ -d "$dir" ]; then
    broken=$(find "$dir" -type l ! -exec test -e {} \; 2>/dev/null | sed -n '1,20p')
    if [ -n "$broken" ]; then
      log "BROKEN symlinks in $dir:"
      log "$broken"
      EXIT_CODE=1
    fi
  fi
done
if [ "$EXIT_CODE" -eq 0 ]; then
  log "  All symlinks valid"
fi
log ""

# 2. Check registered script paths from cortex-update.sh MAP exist in repo
log "--- Cortex registered scripts ---"
REGISTER_CHECK=(
  "$HOME/hermes-cortex/ops/scripts/manage/cortex-doctor.py"
  "$HOME/hermes-cortex/ops/scripts/health/agent-stale-ref-watchdog.sh"
  "$HOME/hermes-cortex/ops/scripts/health/agent-cron-quality-watchdog.py"
  "$HOME/hermes-cortex/ops/scripts/cron-failure-state.sh"
)
for script in "${REGISTER_CHECK[@]}"; do
  if [ ! -f "$script" ]; then
    log "MISSING: $script"
    EXIT_CODE=1
  fi
done
if [ "$EXIT_CODE" -eq 0 ]; then
  log "  All registered scripts present"
fi
log ""

# 3. Check cron scripts deployed to ~/.hermes/scripts exist
log "--- Cron deploy layer (~/.hermes/scripts) ---"
CRON_SCRIPTS=(
  "agent-apply-fixes.py"
  "agent-ip-submission.sh"
  "agent-learning-collector.py"
  "agent-message-handler.py"
  "agent-remediate-apply.py"
  "agent-auto-save-sessions.py"
  "agent-collect-skills.sh"
  "agent-cron-quality-watchdog.py"
  "agent-governance-auditor.py"
  "agent-langfuse-health-watchdog.py"
  "agent-llm-judge-scorer.py"
  "agent-memory-to-brain-sync.py"
  "agent-model-health-watchdog.py"
  "agent-nginx-threat-pipeline.sh"
  "agent-secret-leak-watchdog.py"
  "agent-service-recovery.py"
  "agent-session_cache.py"
  "agent-system-alert-watchdog.py"
)
missing=0
for script in "${CRON_SCRIPTS[@]}"; do
  if [ ! -f "$HOME/.hermes/scripts/$script" ]; then
    log "MISSING in ~/.hermes/scripts/: $script"
    missing=$((missing + 1))
  fi
done
if [ "$missing" -eq 0 ]; then
  log "  All cron scripts present in ~/.hermes/scripts/"
else
  log "  $missing cron script(s) missing"
  EXIT_CODE=1
fi
log ""

# Silent on success — only emit output when stale refs found
if [ "$EXIT_CODE" -ne 0 ]; then
  log "[stale-ref-watchdog] ⚠ Stale references detected (exit=$EXIT_CODE)"
  echo "$OUTPUT"
fi

exit $EXIT_CODE
