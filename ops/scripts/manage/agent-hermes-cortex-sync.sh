#!/usr/bin/env bash
# hermes-cortex-sync.sh — no_agent watchdog: pull latest hermes-cortex + re-sync tools
#
# Watchdog pattern:
#   Empty stdout → silent (already up-to-date)

# Timezone-aware timestamp: honors HERMES_TIMEZONE (IANA), else system TZ.
ts() {
  if [[ -n "${HERMES_TIMEZONE:-}" ]]; then
    TZ="${HERMES_TIMEZONE}" date '+%Y-%m-%d %H:%M %Z'
  else
    date '+%Y-%m-%d %H:%M %Z'
  fi
}
#   Text output  → delivered (updated or error)
#
# Schedule: daily (recommended 22:33 KST, 10 min after hermes-update)
set -euo pipefail

CORTEX_REPO="$HOME/hermes-cortex"

if [ ! -d "$CORTEX_REPO" ]; then
    echo "[$(ts) cortex-sync] Repo not found at $CORTEX_REPO"
    exit 1
fi

cd "$CORTEX_REPO"

# Use the same strategy as the working monitor script - assert repo exists and log what's happening
log()  { echo "[$(ts) cortex-sync] $*"; }
stash_pop() { if $STASHED; then git stash pop 2>&1 | while IFS= read -r line; do echo "[$(ts) cortex-sync] $line"; done || true; fi }

# Stash any uncommitted changes before fetch/rebase
STASHED=false
if ! git diff --quiet || ! git diff --cached --quiet; then
    log "Stashing local changes before sync"
    git stash push -m "auto-stash before cortex-sync $(date -u +%Y%m%dT%H%M%SZ)" 2>&1 | while IFS= read -r line; do log "$line"; done || true
    STASHED=true
fi

FETCH_OUTPUT=$(timeout 12 git fetch origin 2>&1) || {
    FETCH_EXIT=$?
    CTS=$(ts)
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
# SKIP_POST_MERGE=1 (v3: 2026-08-07): the post-merge hook runs
# cortex-update.sh (a 2+ min deploy) which exceeds the network-oriented 20s
# timeout and gets killed mid-deploy — the merge succeeds (reflog) but the
# cron reports error and leaves a partial deploy. The deploy now runs
# explicitly below with its own generous budget.
PULL_OUTPUT=$(GIT_EDITOR=true SKIP_POST_MERGE=1 timeout 20 git pull --rebase origin main 2>&1) || {
    PULL_EXIT=$?
    CTS=$(ts)
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

# Old governance re-sync removed (core/governance/ gone July 2026 — MCP-based replaces it)

# Restore stashed changes
stash_pop

# Explicit deploy — the post-merge hook was skipped above so the 20s pull
# timeout only bounds the network operation. Run the full cortex-update.sh
# now with a generous budget; without this the hook's deploy was killed
# mid-flight at 20s, erroring the cron on every merge (v3: 2026-08-07).
DEPLOY_OUTPUT=$(timeout 600 bash "$CORTEX_REPO/ops/scripts/cortex-update.sh" 2>&1) || {
    DEPLOY_EXIT=$?
    CTS=$(ts)
    echo "[$CTS cortex-sync] cortex-update.sh failed (exit $DEPLOY_EXIT)"
    echo "[$CTS cortex-sync] $(echo "$DEPLOY_OUTPUT" | tail -20)"
    exit 1
}

# Deploy skills manifest from template
SKILLS_TEMPLATE="$CORTEX_REPO/docs/templates/skills.yaml"
SKILLS_DEST="$HOME/.hermes-cortex/skills.yaml"
if [ -f "$SKILLS_TEMPLATE" ]; then
    if [ ! -f "$SKILLS_DEST" ] || ! diff -q "$SKILLS_TEMPLATE" "$SKILLS_DEST" >/dev/null 2>&1; then
        cp "$SKILLS_TEMPLATE" "$SKILLS_DEST"
        log "skills.yaml deployed from template"
    fi
fi

echo "[$(ts) cortex-sync] hermes-cortex updated, tools re-synced."