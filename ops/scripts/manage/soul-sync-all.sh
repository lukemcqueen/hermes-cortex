#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# soul-sync-all.sh — Sync ALL agent SOUL.md profiles with template
#
# Runs soul-merge.py for every agent profile, then syncs the
# current agent's deployed copy back to its repo profile.
# Returns exit code 1 if any agent needed updates.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

REPO_DIR="${HOME}/hermes-cortex"
SOUL_MERGE="${REPO_DIR}/ops/scripts/manage/soul-merge.py"
PROFILES_DIR="${REPO_DIR}/profiles/personal/agent-profiles"
CHANGED=0

echo "━━━ soul-sync-all: Syncing all agent SOUL.md profiles ━━━"

# 1. Sync the current agent's deployed copy
echo "  → Current agent ($(hostname))..."
if python3 "$SOUL_MERGE" 2>&1 | sed 's/^/    /'; then
  : # exit 0 = up to date
fi
# soul-merge exits 0 (no change) or 1 (merged) — both are success
local_exit=$?
if [ "$local_exit" -eq 1 ]; then
  CHANGED=1
fi
echo ""

# 2. Sync every repo profile
if [ -d "$PROFILES_DIR" ]; then
  for agent_dir in "$PROFILES_DIR"/*/; do
    agent_name=$(basename "$agent_dir")
    [ -n "$agent_name" ] || continue

    echo "  → Agent: ${agent_name}..."
    if python3 "$SOUL_MERGE" --agent="$agent_name" 2>&1 | sed 's/^/    /'; then
      : # up to date
    fi
    agent_exit=$?
    if [ "$agent_exit" -eq 1 ]; then
      CHANGED=1
    fi
    echo ""
  done
fi

if [ "$CHANGED" -eq 1 ]; then
  echo "⚠️  Some SOUL.md profiles were updated. Commit and push the changes."
else
  echo "✅ All SOUL.md profiles are current with the template."
fi
exit "$CHANGED"
