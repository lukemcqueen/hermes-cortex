#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
#  gbrain-nightly-dream.sh — Weekly knowledge enrichment (dream)
#
#  Wraps `gbrain dream` in the stop/restart lifecycle using the
#  gbrain-wrapper.sh. The wrapper handles autopilot stop/start via
#  systemctl --user so this script just runs the dream commands.
#
#  CROSS-AGENT NOTES:
#  - GBRAIN_REPO is auto-detected from the running autopilot's --repo flag
#  - Falls back to ~/brain/moses if autopilot isn't running
#  - Override via env var: GBRAIN_REPO=/path/to/brain ./gbrain-nightly-dream.sh
#  - DREAM_TIMEOUT defaults to 300s; override via env var
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

export PATH="$HOME/.bun/bin:$PATH"
export GBRAIN_AI_EMBED_TIMEOUT_MS=300000
WRAPPER="$HOME/.hermes-cortex/scripts/gbrain-wrapper.sh"

# ── Configuration (env-overridable) ─────────────────────────────────

# Auto-detect brain repo from running autopilot's --repo flag
DEFAULT_REPO=""
if AUTOPILOT_CMD=$(ps -o args= -p "$(pgrep -f 'gbrain.*autopilot' | head -1)" 2>/dev/null); then
  DEFAULT_REPO=$(echo "$AUTOPILOT_CMD" | sed -n 's/.*--repo //p' | awk '{print $1}')
fi
GBRAIN_REPO="${GBRAIN_REPO:-${DEFAULT_REPO:-${HOME}/hermes-cortex}}"

# Max seconds to let gbrain dream run before aborting
DREAM_TIMEOUT="${DREAM_TIMEOUT:-300}"

echo "[$(TZ=Asia/Seoul date +'%Y-%m-%d %H:%M KST')] gbrain-nightly-dream: starting"
echo "  Repo: ${GBRAIN_REPO}"
echo "  Timeout: ${DREAM_TIMEOUT}s"

# ── Step 1: Pre-flight — purge stale cycle state ───────────────────
echo "  → Pre-flight: purging stale cycle state..."
"$WRAPPER" dream --phase purge 2>&1 | tail -3 || true

# ── Step 2: Run the dream (with timeout) ───────────────────────────
echo ""
echo "  Running gbrain dream (timeout: ${DREAM_TIMEOUT}s)..."

DREAM_EXIT=0
timeout "$DREAM_TIMEOUT" "$WRAPPER" dream 2>&1 | tail -20 || DREAM_EXIT=$?

if [ "$DREAM_EXIT" -eq 124 ]; then
    echo "  ⚠ gbrain dream timed out after ${DREAM_TIMEOUT}s"
elif [ "$DREAM_EXIT" -ne 0 ]; then
    echo "  ⚠ gbrain dream exited with code $DREAM_EXIT"
fi

echo ""
echo "[$(TZ=Asia/Seoul date +'%Y-%m-%d %H:%M KST')] gbrain-nightly-dream: completed (exit=$DREAM_EXIT)"
