#!/usr/bin/env bash
# hermes-update.sh — no_agent watchdog: auto-upgrade Hermes Agent + migrate config + verify health
#
# Watchdog pattern:
#   Empty stdout → silent (no update needed)
#   Text output  → delivered (update occurred or error)
#
# Schedule: daily (recommended 22:23 KST, 10 min before hermes-cortex-sync)
set -euo pipefail

# Step 1: Update upstream Hermes Agent
UPDATE_OUTPUT=$(hermes update -y 2>&1) || {
    echo "[hermes-update] hermes update failed (exit $?)"
    echo "$UPDATE_OUTPUT"
    exit 1
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
