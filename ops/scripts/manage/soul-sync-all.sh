#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# soul-sync-local.sh — Sync the current agent's SOUL.md with template
#
# Runs soul-merge.py for the current agent only (hostname).
# Agent profiles were removed from the repo (commit d43e776);
# each agent syncs its own SOUL.md during its own update cycle.
# Returns exit code 1 if merged, 0 if up to date.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

REPO_DIR="${HOME}/hermes-cortex"
SOUL_MERGE="${REPO_DIR}/ops/scripts/manage/soul-merge.py"
# profiles removed from repo — no longer synced from repo paths
CHANGED=0

echo "━━━ soul-sync-local: Syncing current agent SOUL.md with template ━━━"

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
  echo "✅ Current agent SOUL.md is up to date with the template."
fi
exit "$CHANGED"
