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
# internal 60s timeout so migrate/doctor still run even if the download is
# wait — the update will simply be picked up on the next daily cycle.
#
# v2: Reduced from 90s to 60s (2026-06-25) — 90s left only 30s for
# migrate+doctor, which still exceeded the 120s cron cap. 60s gives 60s
# for remaining steps.
set -euo pipefail

# Step 1: Update upstream Hermes Agent (with guarded timeout)
UPDATE_OUTPUT=$(timeout 60 hermes update -y 2>&1) || {
    UPDATE_EXIT=$?
    if [ "$UPDATE_EXIT" -eq 124 ]; then
        echo "[hermes-update] hermes update timed out (>60s), will retry next cycle"
    else
        echo "[hermes-update] hermes update failed (exit $UPDATE_EXIT)"
        echo "$UPDATE_OUTPUT"
    fi
    # Non-fatal — continue to migrate + doctor
}

# Step 2: Migrate config schema (needed after version bumps)
MIGRATE_OUTPUT=$(hermes config migrate 2>&1) || {
    echo "[hermes-update] config migrate failed (exit $?)"
    echo "$MIGRATE_OUTPUT"
    exit 1
}

# Step 3: Verify health
DOCTOR_OUTPUT=$(hermes doctor --fix 2>&1) || {
    echo "[hermes-update] doctor check found issues (exit $?)"
    echo "$DOCTOR_OUTPUT"
    exit 1
}

echo "[hermes-update] Hermes Agent updated, config migrated, health verified."
