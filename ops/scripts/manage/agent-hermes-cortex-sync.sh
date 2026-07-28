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
    echo "[$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST') cortex-sync] Repo not found at $CORTEX_REPO"
    exit 1
fi

cd "$CORTEX_REPO"

# Use the same strategy as the working monitor script - assert repo exists and log what's happening
log()  { echo "[$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST') cortex-sync] $*"; }
stash_pop() { if $STASHED; then git stash pop 2>&1 | while IFS= read -r line; do echo "[$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST') cortex-sync] $line"; done || true; fi }

# Stash any uncommitted changes before fetch/rebase
STASHED=false
if ! git diff --quiet || ! git diff --cached --quiet; then
    log "Stashing local changes before sync"
    git stash push -m "auto-stash before cortex-sync $(date -u +%Y%m%dT%H%M%SZ)" 2>&1 | while IFS= read -r line; do log "$line"; done || true
    STASHED=true
fi

FETCH_OUTPUT=$(timeout 12 git fetch origin 2>&1) || {
    FETCH_EXIT=$?
    CTS=$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST')
    if [ "$FETCH_EXIT" -eq 124 ]; then
        echo "[$CTS cortex-sync] git fetch timed out after 12s, will retry next cycle"
        stash_pop
        exit 1
    fi
    echo "[$CTS cortex-sync] git fetch failed (exit $FETCH_EXIT)"
    echo "[$CTS cortex-sync] $FETCH_OUTPUT"
    stash_pop
    exit 1
}

# Silent exit if already up-to-date
if ! git log HEAD..origin/main --oneline | grep -q .; then
    stash_pop
    exit 0
fi

# Use rebase instead of merge to handle local auto-remediation commits
# that are ahead of origin. Merge would fail when both sides changed
# the same files (install.sh, scripts, etc.).
# GIT_EDITOR=true prevents editor spawn on conflict — conflicts auto-fail
# instead of hanging indefinitely within the timeout (v2: 2026-06-27).
PULL_OUTPUT=$(GIT_EDITOR=true timeout 20 git pull --rebase origin main 2>&1) || {
    PULL_EXIT=$?
    CTS=$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST')
    if [ "$PULL_EXIT" -eq 124 ]; then
        echo "[$CTS cortex-sync] git pull --rebase timed out after 20s, will retry next cycle"
        stash_pop
        exit 1
    fi
    echo "[$CTS cortex-sync] git rebase pull failed (exit $PULL_EXIT)"
    echo "[$CTS cortex-sync] $PULL_OUTPUT"
    stash_pop
    exit 1
}

# Re-sync tools (crons installed separately via install-crons.sh)
if [ -f "core/governance/setup.sh" ]; then
    timeout 10 bash core/governance/setup.sh 2>&1 | while IFS= read -r line; do log "$line"; done || true
fi

# Restore stashed changes
stash_pop

# Deploy skills manifest from template
SKILLS_TEMPLATE="$CORTEX_REPO/docs/templates/skills.yaml"
SKILLS_DEST="$HOME/.hermes-cortex/skills.yaml"
if [ -f "$SKILLS_TEMPLATE" ]; then
    if [ ! -f "$SKILLS_DEST" ] || ! diff -q "$SKILLS_TEMPLATE" "$SKILLS_DEST" >/dev/null 2>&1; then
        cp "$SKILLS_TEMPLATE" "$SKILLS_DEST"
        log "skills.yaml deployed from template"
    fi
fi

echo "[$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST') cortex-sync] hermes-cortex updated, tools re-synced."