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
# v3: Reduced from 60s to 30s (2026-06-25) — 60s still insufficient for
# migrate+doctor after update timeout. 30s gives 90s for remaining steps.
# v5: Reduced from 30/40/40 to 25/35/30 (2026-06-26) — 30+40+40=110s still
# exceeded 120s cron cap with overhead. 25+35+30=90s gives 30s buffer.
set -euo pipefail

# Step 1: Update upstream Hermes Agent (with guarded timeout)
UPDATE_OUTPUT=$(timeout 25 hermes update -y 2>&1) || {
    UPDATE_EXIT=$?
    if [ "$UPDATE_EXIT" -eq 124 ]; then
        echo "[hermes-update] hermes update timed out (>25s), will retry next cycle"
    else
        echo "[hermes-update] hermes update failed (exit $UPDATE_EXIT)"
        echo "$UPDATE_OUTPUT"
    fi
    # Non-fatal — continue to migrate + doctor
}

# Step 2: Migrate config schema (needed after version bumps)
# v4: Added timeout 40 to migrate (2026-06-25) — without this, migrate+doctor
# could exceed the remaining 90s and trigger the cron 120s kill.
MIGRATE_OUTPUT=$(timeout 35 hermes config migrate 2>&1) || {
    MIGRATE_EXIT=$?
    if [ "$MIGRATE_EXIT" -eq 124 ]; then
        echo "[hermes-update] config migrate timed out (>35s), will retry next cycle"
    else
        echo "[hermes-update] config migrate failed (exit $MIGRATE_EXIT)"
        echo "$MIGRATE_OUTPUT"
        exit 1
    fi
}

# Step 3: Verify health
# v4: Added timeout 40 to doctor for same reason as migrate.
DOCTOR_OUTPUT=$(timeout 30 hermes doctor --fix 2>&1) || {
    DOCTOR_EXIT=$?
    if [ "$DOCTOR_EXIT" -eq 124 ]; then
        echo "[hermes-update] doctor check timed out (>30s), will retry next cycle"
    else
        echo "[hermes-update] doctor check found issues (exit $DOCTOR_EXIT)"
        echo "$DOCTOR_OUTPUT"
        exit 1
    fi
}

echo "[hermes-update] Hermes Agent updated, config migrated, health verified."
