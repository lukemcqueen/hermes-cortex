#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  gbrain-update-sync.sh — Weekly gbrain update & health check
#  Runs: gbrain upgrade + health check
#  Uses gbrain-wrapper.sh for autopilot lifecycle management.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

export PATH="$HOME/.bun/bin:$PATH"
export GBRAIN_AI_EMBED_TIMEOUT_MS=300000
WRAPPER="$HOME/.hermes/scripts/gbrain-wrapper.sh"

echo "[$(TZ=Asia/Seoul date +'%Y-%m-%d %H:%M KST')] gbrain-update-sync: starting"

# Step 1: Check for update
if "$WRAPPER" check-update --json 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    has = data.get('has_update', False)
    sys.exit(0 if has else 1)
except: sys.exit(1)
" 2>/dev/null; then
    echo "  Update available — running gbrain upgrade..."
    "$WRAPPER" upgrade 2>&1
    echo "  Upgrade complete"
else
    echo "  gbrain is up to date"
fi

# Step 2: Health check
echo "  Running health check..."
"$WRAPPER" doctor --fast 2>&1 || echo "  ⚠ Health check reported issues"

echo "[$(TZ=Asia/Seoul date +'%Y-%m-%d %H:%M KST')] gbrain-update-sync: done"
