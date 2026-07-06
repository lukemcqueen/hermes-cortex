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

# Step 1: Update upstream Hermes Agent
# NOTE: hermes update -y requires gateway restart approval and hangs in cron context.
# Use a timeout to avoid blocking indefinitely — if it times out, skip to migrate+doctor.
UPDATE_OUTPUT=$(timeout 30 hermes update -y 2>&1) || {
    UPDATE_EXIT=$?
    TS=$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST')
    if [ $UPDATE_EXIT -eq 124 ]; then
        echo "[$TS hermes-update] hermes update timed out (non-interactive cron context); skipping."
    else
        echo "[$TS hermes-update] hermes update failed (exit $UPDATE_EXIT)"
        echo "[$TS hermes-update] $UPDATE_OUTPUT"
        # Non-fatal — allow migrate and doctor to proceed
    fi
}

# Step 2: Config migration (runs even if update timed out or failed)
MIGRATE_OUTPUT=$(timeout 35 hermes config migrate 2>&1) || {
    TS=$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST')
    MIGRATE_EXIT=$?
    echo "[$TS hermes-update] config migrate failed (exit $MIGRATE_EXIT)"
    echo "[$TS hermes-update] $MIGRATE_OUTPUT"
}

# Step 3: Final health check
DOCTOR_OUTPUT=$(timeout 30 hermes doctor 2>&1) || {
    TS=$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST')
    DOCTOR_EXIT=$?
    echo "[$TS hermes-update] hermes doctor failed (exit $DOCTOR_EXIT)"
    echo "[$TS hermes-update] $DOCTOR_OUTPUT"
}

# Silent exit — no news is good news
exit 0