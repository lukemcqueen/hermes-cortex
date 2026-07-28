#!/usr/bin/env bash
# hermes-update.sh — no_agent watchdog: auto-upgrade Hermes Agent + migrate config + verify health
#
# Watchdog pattern:
#   Empty stdout → silent (no update needed)
#   Text output  → delivered (update occurred or error)
#
# Schedule: daily (recommended 22:23 KST, 10 min before hermes-cortex-sync)
#
# Cron imposes a 120s timeout on no_agent scripts, and `hermes update` can
# take >120s when downloading a new binary.  We wrap the update step with an
# internal timeout so migrate/doctor still run even if the download stalls —
# the update will simply be picked up on the next daily cycle.
set -euo pipefail

# ── Helpers ──────────────────────────────────────────────────────────
log() { echo "[$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST') hermes-update] $*"; }
HAD_OUTPUT=false

# ── Track previous update date to suppress duplicate reports ──
STATE_DIR="$HOME/.hermes/state"
LATEST_UPDATE_FILE="$STATE_DIR/hermes-update-latest"
mkdir -p "$STATE_DIR"

# Read latest version from last run
CURRENT_VERSION=""
if [ -f "$LATEST_UPDATE_FILE" ]; then
    CURRENT_VERSION=$(cat "$LATEST_UPDATE_FILE")
fi

# Step 1: Update upstream Hermes Agent
# NOTE: hermes update -y requires gateway restart approval and hangs in cron context.
# Use a timeout to avoid blocking indefinitely — if it times out, skip to migrate+doctor.
UPDATE_OUTPUT=$(timeout 30 hermes update -y 2>&1) || {
    UPDATE_EXIT=$?
    if [ $UPDATE_EXIT -eq 124 ]; then
        log "hermes update timed out (non-interactive); skipping."
        HAD_OUTPUT=true
    else
        log "hermes update failed (exit $UPDATE_EXIT)"
        log "$UPDATE_OUTPUT"
        HAD_OUTPUT=true
    fi
}

# Detect if Hermes was actually updated (new binary version)
NEW_VERSION=$(hermes version 2>/dev/null | head -1 || echo "$CURRENT_VERSION")
if [ "$NEW_VERSION" != "$CURRENT_VERSION" ] && [ -n "$NEW_VERSION" ]; then
    echo "$NEW_VERSION" > "$LATEST_UPDATE_FILE"
    if $HAD_OUTPUT; then
        log "Updated: $CURRENT_VERSION → $NEW_VERSION"
    else
        # Tiny summary — only on actual version change
        TS=$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST')
        echo "[$TS hermes-update] Updated Hermes: ${CURRENT_VERSION:-?} → ${NEW_VERSION}"
    fi
fi

# Step 2: Config migration (runs even if update timed out or failed)
MIGRATE_OUTPUT=$(timeout 35 hermes config migrate 2>&1) || {
    MIGRATE_EXIT=$?
    log "config migrate failed (exit $MIGRATE_EXIT)"
    log "$MIGRATE_OUTPUT"
    HAD_OUTPUT=true
}

# Step 3: Final health check
DOCTOR_OUTPUT=$(timeout 30 hermes doctor 2>&1) || {
    DOCTOR_EXIT=$?
    log "hermes doctor failed (exit $DOCTOR_EXIT)"
    log "$DOCTOR_OUTPUT"
    HAD_OUTPUT=true
}

# Silent if nothing noteworthy happened
$HAD_OUTPUT || exit 0