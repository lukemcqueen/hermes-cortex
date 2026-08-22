#!/usr/bin/env bash

# Timezone-aware timestamp: honors HERMES_TIMEZONE (IANA), else system TZ.
ts() {
  if [[ -n "${HERMES_TIMEZONE:-}" ]]; then
    TZ="${HERMES_TIMEZONE}" date '+%Y-%m-%d %H:%M %Z'
  else
    date '+%Y-%m-%d %H:%M %Z'
  fi
}
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
log() { echo "[$(ts) hermes-update] $*"; }
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
        TS=$(ts)
        echo "[$TS hermes-update] Updated Hermes: ${CURRENT_VERSION:-?} → ${NEW_VERSION}"
    fi
fi

# Restart-needed marker: hermes update replaces source files (scheduler.py,
# enforcer, plugins) but the RUNNING daemon keeps stale modules in memory
# until a real restart — which requires gateway-restart approval and can't
# happen from inside cron. Write a durable marker so the doctor flags
# "update applied but not loaded" instead of silently running stale code
# (O1-S1b: cost cache-split patch was on disk for hours while the daemon
# wrote audit lines without it, 2026-08-21/22).
RESTART_MARKER="${HOME}/.hermes-cortex/state/restart-pending"
if [ "$NEW_VERSION" != "$CURRENT_VERSION" ] && [ -n "$NEW_VERSION" ]; then
    echo "updated:${NEW_VERSION}" > "$RESTART_MARKER"
    log "restart-pending marker written (${NEW_VERSION}) — daemon must reload"
    HAD_OUTPUT=true
elif [ -f "$RESTART_MARKER" ] && ! grep -q "updated:${NEW_VERSION}" "$RESTART_MARKER" 2>/dev/null; then
    # version unchanged but marker stale from an earlier update — keep it
    # (scheduler.py may still be newer than the loaded module)
    true
fi

# ── Step 1.5: Post-update auto-reapply of the cost-capture patch (O1-S3) ──
# `hermes update` replaces scheduler.py / cronjob_tools.py, silently wiping
# the cron-cost-tracking marker patch. The reapply used to live only in
# cortex-update.sh, which runs only when the hermes-cortex repo has new
# commits — a version-only update left cost capture dead until the next
# repo change (2-day cron-costs.db gap, 2026-08-21). Re-run the idempotent
# installer here, in the same cycle as the update, so the patch always
# survives. Silent when everything is already applied (SKIP-only).
COST_INSTALLER="${CORTEX_DEPLOY_HOME:-${HOME}/.hermes-cortex}/scripts/install-cron-cost-tracking.py"
if [ -f "$COST_INSTALLER" ]; then
    COST_OUTPUT=$(timeout 30 python3 "$COST_INSTALLER" 2>&1) || {
        COST_EXIT=$?
        log "cost-tracking reapply failed (exit $COST_EXIT)"
        log "$(echo "$COST_OUTPUT" | tail -5)"
        HAD_OUTPUT=true
    }
    # Report only when a patch was actually (re)applied or something FAILed —
    # SKIP-only output means the patch survived and needs no attention.
    # (The `|| true` above already logged failures; only fire on OK lines here,
    # and only when the installer itself exited 0 — a FAIL text on non-zero
    # exit must not double-report as "re-applied".)
    if [ "${COST_EXIT:-0}" -eq 0 ] && echo "$COST_OUTPUT" | grep -qE '^  OK   (scheduler|cronjob_tools)'; then
        log "cost-tracking patch re-applied after hermes update"
        HAD_OUTPUT=true
    fi
else
    log "install-cron-cost-tracking.py missing at $COST_INSTALLER — cost capture may be dead"
    HAD_OUTPUT=true
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