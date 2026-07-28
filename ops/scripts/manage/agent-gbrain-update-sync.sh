#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  gbrain-update-sync.sh — Weekly gbrain update & health check
#  Runs: gbrain upgrade + health check
#  Uses gbrain-wrapper.sh for autopilot lifecycle management.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

export PATH="$HOME/.bun/bin:$PATH"
export GBRAIN_AI_EMBED_TIMEOUT_MS=300000
WRAPPER="$HOME/.hermes-cortex/scripts/gbrain-wrapper.sh"

# ── State tracking — only report on actual changes ──
STATE_DIR="$HOME/.hermes/state"
HAD_OUTPUT=false
log() { echo "[$(TZ=Asia/Seoul date +'%Y-%m-%d %H:%M KST') gbrain-update-sync] $*"; }

# Step 1: Check for update
if "$WRAPPER" check-update --json 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    has = data.get('has_update', False)
    sys.exit(0 if has else 1)
except: sys.exit(1)
" 2>/dev/null; then
    log "Update available — running gbrain upgrade..."
    HAD_OUTPUT=true
    "$WRAPPER" upgrade 2>&1 | while IFS= read -r line; do log "  $line"; done
    log "Upgrade complete"
fi

# Step 2: Health check — only report if issues
if HEALTH_OUTPUT=$("$WRAPPER" doctor --fast 2>&1); then
    :  # doctor passed — stay silent
else
    log "⚠ Health check reported issues"
    log "$HEALTH_OUTPUT"
    HAD_OUTPUT=true
fi

# Silent if nothing noteworthy happened
$HAD_OUTPUT || exit 0
