#!/usr/bin/env bash
# stale-ref-watchdog — nightly stale-path scan across all deploy layers
# Checks for stale references: deploy scripts pointing to non-existent files,
# symlinks to missing targets, and orphaned paths.
set -euo pipefail

EXIT_CODE=0
CORTEX_HOME="${CORTEX_HOME:-$HOME/hermes-cortex}"

echo "[stale-ref-watchdog] $(date -u '+%Y-%m-%dT%H:%M:%SZ') — nightly stale-path scan"

# 1. Check symlinks in deploy dirs
SYMLINK_TARGETS=(
  "$HOME/.hermes/plugins/governance-enforcer"
)

for target in "${SYMLINK_TARGETS[@]}"; do
  if [ -L "$target" ]; then
    resolved=$(readlink -f "$target" 2>/dev/null || true)
    if [ ! -e "$resolved" ] && [ -n "$resolved" ]; then
      echo "STALE: symlink $target → $resolved (missing target)"
      EXIT_CODE=1
    fi
  fi
done

# 2. Check registered scripts exist
REGISTERED_SCRIPTS=(
  "$CORTEX_HOME/ops/scripts/manage/stale-ref-scanner.py"
  "$CORTEX_HOME/ops/scripts/manage/cortex-doctor.py"
  "$CORTEX_HOME/ops/scripts/cron-quality-watchdog.py"
)

for script in "${REGISTERED_SCRIPTS[@]}"; do
  if [ ! -f "$script" ]; then
    echo "WARN: registered script not found: $script"
    EXIT_CODE=1
  fi
done

if [ "$EXIT_CODE" -eq 0 ]; then
  echo "[stale-ref-watchdog] ✓ No stale references found"
else
  echo "[stale-ref-watchdog] ⚠ Stale references detected (exit=$EXIT_CODE)"
fi

exit $EXIT_CODE
