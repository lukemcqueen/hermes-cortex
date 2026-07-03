#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
#  gbrain-nightly-dream.sh — Weekly knowledge enrichment (dream)
#
#  Manages autopilot lifecycle to avoid PGLite lock contention:
#    1. Stop the autopilot (graceful SIGTERM with 10s timeout)
#    2. Clear stale autopilot lock files
#    3. Run `gbrain dream` (with 5-minute timeout)
#    4. Restart autopilot (via trap, guarantees restart even on failure)
#
#  PGLite is single-connection — the autopilot holds the exclusive lock
#  during its ~150s sync cycles. Any `gbrain dream` call that needs DB
#  access (sync, embed, synthesize) will hang or fail with a WASM error
#  unless the autopilot is stopped first.
#
#  The trap handler on EXIT ensures the autopilot is restarted regardless
#  of whether dream succeeds or fails. This prevents a crashed dream from
#  leaving the system without continuous sync.
#
#  CROSS-AGENT NOTES:
#  - GBRAIN_REPO is auto-detected from the running autopilot's --repo flag
#  - Falls back to ~/brain/moses if autopilot isn't running
#  - Override via env var: GBRAIN_REPO=/path/to/brain ./gbrain-nightly-dream.sh
#  - DREAM_TIMEOUT defaults to 300s; override via env var
#
#  All agents: if you write any cron script that calls `gbrain <command>`
#  and needs DB access while the autopilot is running, use this same
#  stop-dream-restart pattern. Never run `gbrain dream` or `gbrain sync`
#  without first stopping the autopilot.
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

export PATH="$HOME/.bun/bin:$PATH"
export GBRAIN_AI_EMBED_TIMEOUT_MS=300000
GBRAIN="$HOME/.bun/bin/gbrain"

# ── Configuration (env-overridable) ─────────────────────────────────

# Auto-detect brain repo from running autopilot's --repo flag
# Override via: GBRAIN_REPO=/path/to/brain ./script.sh
DEFAULT_REPO=""
if AUTOPILOT_CMD=$(ps -o args= -p "$(pgrep -f 'gbrain.*autopilot' | head -1)" 2>/dev/null); then
  DEFAULT_REPO=$(echo "$AUTOPILOT_CMD" | sed -n 's/.*--repo //p' | awk '{print $1}')
fi
GBRAIN_REPO="${GBRAIN_REPO:-${DEFAULT_REPO:-${HOME}/brain/moses}}"

# Max seconds to let gbrain dream run before aborting
# Override via: DREAM_TIMEOUT=600 ./script.sh
DREAM_TIMEOUT="${DREAM_TIMEOUT:-300}"

echo "[$(TZ=Asia/Seoul date +'%Y-%m-%d %H:%M KST')] gbrain-nightly-dream: starting"
echo "  Repo: ${GBRAIN_REPO}"
echo "  Timeout: ${DREAM_TIMEOUT}s"

# ── Helpers ──────────────────────────────────────────────────────────

# Find autopilot PID (any gbrain process running as autopilot)
find_autopilot_pid() {
    pgrep -f 'gbrain.*autopilot' 2>/dev/null | head -1 || true
}

# Verify no autopilot is running
autopilot_is_dead() {
    [ -z "$(find_autopilot_pid)" ]
}

# Start the autopilot daemon in background
start_autopilot() {
    cd "$HOME"
    nohup "$GBRAIN" autopilot --repo "$GBRAIN_REPO" > /dev/null 2>&1 &
    local NEW_PID=$!
    echo "  Autopilot restarted (PID $NEW_PID)"
}

# ── Trap: guarantee autopilot restart on script exit ─────────────────
# This runs on ANY exit (normal, error, SIGINT, SIGTERM).
# Check via pgrep — if autopilot isn't running, start it.
autopilot_restart_handler() {
    local EXIT_STATUS=$?
    if autopilot_is_dead; then
        echo "  [trap] Autopilot not running — restarting..."
        start_autopilot
    else
        echo "  [trap] Autopilot already running — no action needed"
    fi
    # Preserve original exit code for cron delivery
    return "$EXIT_STATUS"
}
trap autopilot_restart_handler EXIT

# ── Step 1: Stop the autopilot ──────────────────────────────────────
AUTOPILOT_PID=$(find_autopilot_pid)

if [ -n "$AUTOPILOT_PID" ]; then
    echo "  Found autopilot PID $AUTOPILOT_PID — stopping..."

    # Graceful shutdown
    kill -TERM "$AUTOPILOT_PID" 2>/dev/null || true

    # Wait up to 10 seconds for graceful exit
    for i in $(seq 1 10); do
        if autopilot_is_dead; then
            echo "  Autopilot stopped (took ${i}s)"
            break
        fi
        sleep 1
    done

    # Force kill if still alive after timeout
    if ! autopilot_is_dead; then
        echo "  ⚠ Autopilot didn't stop gracefully after 10s — force killing..."
        kill -KILL "$AUTOPILOT_PID" 2>/dev/null || true
        sleep 1
        if autopilot_is_dead; then
            echo "  Autopilot force-killed"
        else
            echo "  ⚠ Could not stop autopilot — dream may still fail"
        fi
    fi

    # ── Clear stale lock files ──
    # autopilot.lock + cycle.lock + PGLite's .gbrain-lock persist after
    # process death and block `gbrain dream` with "another cycle is
    # already running"
    for lock in "$HOME/.gbrain/autopilot.lock" "$HOME/.gbrain/cycle.lock" "$HOME/.gbrain/brain.pglite/.gbrain-lock/lock" "$HOME/.gbrain/.locks"; do
        if [ -e "$lock" ]; then
            rm -rf "$lock"
            echo "  ✓ Cleared stale lock: $lock"
        fi
    done
else
    echo "  ⚠ No autopilot process found — will run dream anyway"
fi

# ── Step 2: Run the dream (with timeout) ────────────────────────────
echo ""
echo "  Running gbrain dream (timeout: ${DREAM_TIMEOUT}s)..."

# First, purge any stale cycle state from the database
echo "  → Pre-flight: purging stale cycle state..."
"$GBRAIN" dream --phase purge 2>&1 | tail -3 || true

DREAM_EXIT=0
timeout "$DREAM_TIMEOUT" "$GBRAIN" dream 2>&1 | tail -20 || DREAM_EXIT=$?

if [ "$DREAM_EXIT" -eq 124 ]; then
    echo "  ⚠ gbrain dream timed out after ${DREAM_TIMEOUT}s"
elif [ "$DREAM_EXIT" -ne 0 ]; then
    echo "  ⚠ gbrain dream exited with code $DREAM_EXIT"
fi

echo ""
echo "[$(TZ=Asia/Seoul date +'%Y-%m-%d %H:%M KST')] gbrain-nightly-dream: completed (exit=$DREAM_EXIT)"
