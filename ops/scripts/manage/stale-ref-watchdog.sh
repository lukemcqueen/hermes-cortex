#!/usr/bin/env bash
# stale-ref-watchdog — nightly stale-path scan across all deploy layers
# Checks for:
#   1. Broken symlinks in ~/.hermes/ and ~/.hermes-cortex/
#   2. Deployed scripts referenced by crons that don't exist
#   3. Orphaned cron script paths
set -euo pipefail

EXIT_CODE=0

echo "[stale-ref-watchdog] $(date -u '+%Y-%m-%dT%H:%M:%SZ') — nightly stale-path scan"
echo ""

# 1. Broken symlinks in deploy directories
echo "--- Deploy symlinks ---"
DEPLOY_DIRS=(
  "$HOME/.hermes/scripts"
  "$HOME/.hermes/plugins"
  "$HOME/.hermes-cortex/scripts"
)
for dir in "${DEPLOY_DIRS[@]}"; do
  if [ -d "$dir" ]; then
    broken=$(find "$dir" -xtype l 2>/dev/null | head -20)
    if [ -n "$broken" ]; then
      echo "BROKEN symlinks in $dir:"
      echo "$broken"
      EXIT_CODE=1
    fi
  fi
done
if [ "$EXIT_CODE" -eq 0 ]; then
  echo "  All symlinks valid"
fi
echo ""

# 2. Check registered script paths from cortex-update.sh MAP exist in repo
echo "--- Cortex registered scripts ---"
REGISTER_CHECK=(
  "$HOME/hermes-cortex/ops/scripts/manage/cortex-doctor.py"
  "$HOME/hermes-cortex/ops/scripts/manage/stale-ref-watchdog.sh"
  "$HOME/hermes-cortex/ops/scripts/health/cron-quality-watchdog.py"
  "$HOME/hermes-cortex/ops/scripts/cron-failure-state.sh"
)
for script in "${REGISTER_CHECK[@]}"; do
  if [ ! -f "$script" ]; then
    echo "MISSING: $script"
    EXIT_CODE=1
  fi
done
if [ "$EXIT_CODE" -eq 0 ]; then
  echo "  All registered scripts present"
fi
echo ""

# 3. Check cron scripts deployed to ~/.hermes/scripts exist
echo "--- Cron deploy layer (~/.hermes/scripts) ---"
CRON_SCRIPTS=(
  "agent-apply-fixes.py"
  "agent-ip-submission.sh"
  "agent-learning-collector.py"
  "agent-message-handler.py"
  "agent-remediate-apply.py"
  "auto-save-sessions.py"
  "collect-agent-skills.sh"
  "cron-quality-watchdog.py"
  "governance-auditor.py"
  "inbox-flag.py"
  "langfuse-health-watchdog.py"
  "llm-judge-scorer.py"
  "memory-to-brain-sync.py"
  "model-health-watchdog.py"
  "nginx-threat-pipeline.sh"
  "secret-leak-watchdog.py"
  "service-recovery.py"
  "session_cache.py"
  "system-alert-watchdog.py"
)
missing=0
for script in "${CRON_SCRIPTS[@]}"; do
  if [ ! -f "$HOME/.hermes/scripts/$script" ]; then
    echo "MISSING in ~/.hermes/scripts/: $script"
    missing=$((missing + 1))
  fi
done
if [ "$missing" -eq 0 ]; then
  echo "  All cron scripts present in ~/.hermes/scripts/"
else
  echo "  $missing cron script(s) missing"
  EXIT_CODE=1
fi
echo ""

if [ "$EXIT_CODE" -eq 0 ]; then
  echo "[stale-ref-watchdog] ✓ No stale references found"
else
  echo "[stale-ref-watchdog] ⚠ Stale references detected (exit=$EXIT_CODE)"
fi

exit $EXIT_CODE
