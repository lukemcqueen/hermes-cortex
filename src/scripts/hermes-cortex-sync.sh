#!/usr/bin/env bash
# hermes-cortex-sync.sh — no_agent watchdog: pull latest hermes-cortex + re-sync tools
#
# Watchdog pattern:
#   Empty stdout → silent (already up-to-date)
#   Text output  → delivered (updated or error)
#
# Schedule: daily (recommended 22:33 KST, 10 min after hermes-update)
set -euo pipefail

CORTEX_REPO="$HOME/hermes-cortex"

if [ ! -d "$CORTEX_REPO" ]; then
    echo "[cortex-sync] Repo not found at $CORTEX_REPO"
    exit 1
fi

cd "$CORTEX_REPO"

FETCH_OUTPUT=$(git fetch origin 2>&1) || {
    echo "[cortex-sync] git fetch failed (exit $?)"
    echo "$FETCH_OUTPUT"
    exit 1
}

# Silent exit if already up-to-date
if ! git log HEAD..origin/main --oneline | grep -q .; then
    exit 0
fi

# Use rebase instead of merge to handle local auto-remediation commits
# that are ahead of origin. Merge would fail when both sides changed
# the same files (install.sh, scripts, etc.).
PULL_OUTPUT=$(git pull --rebase origin main 2>&1) || {
    echo "[cortex-sync] git rebase pull failed (exit $?)"
    echo "$PULL_OUTPUT"
    exit 1
}

# Re-sync tools and crons
if [ -f "src/loop-governance/install-crons.py" ]; then
    python3 src/loop-governance/install-crons.py 2>&1 || true
fi
if [ -f "src/loop-governance/setup.sh" ]; then
    bash src/loop-governance/setup.sh 2>&1 || true
fi

echo "[cortex-sync] hermes-cortex updated, tools re-synced."
