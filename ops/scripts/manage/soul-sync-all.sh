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
# profiles removed from repo — no longer synced from repo paths
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

if [ "$CHANGED" -eq 1 ]; then
  echo "⚠️  Some SOUL.md profiles were updated. Commit and push the changes."
else
  echo "✅ All SOUL.md profiles are current with the template."
fi
exit "$CHANGED"
