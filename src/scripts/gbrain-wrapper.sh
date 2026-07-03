#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
#  gbrain-wrapper.sh — gbrain CLI wrapper with autopilot lifecycle mgmt
#
#  Manages the systemd autopilot service around every gbrain command.
#  PGLite is single-connection — the autopilot holds the exclusive lock.
#  Any CLI command (dream, sync, stats, sources list) will fail or hang
#  unless the autopilot is stopped first.
#
#  Usage:
#    gbrain-wrapper.sh <gbrain-command> [args...]
#
#  Examples:
#    gbrain-wrapper.sh dream
#    gbrain-wrapper.sh stats
#    gbrain-wrapper.sh sources list
#    gbrain-wrapper.sh check-update --json
#
#  For commands that don't need DB access (doctor --fast, check-update,
#  upgrade), the wrapper still stops/restarts for consistency — the
#  overhead is ~2 seconds.
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Environment ────────────────────────────────────────────────────
export PATH="$HOME/.bun/bin:$PATH"
export GBRAIN_AI_EMBED_TIMEOUT_MS=300000

SERVICE="gbrain-autopilot.service"
GBRAIN_BIN="$(command -v gbrain || echo "$HOME/.bun/bin/gbrain")"

# ── Source shell profiles for API keys ────────────────────────────
# Source only non-interactive-safe profiles. zshrc (Oh My Zsh) can hang
# or be very slow in non-interactive shells — skip it entirely.
[ -f ~/.zshenv ] && source ~/.zshenv 2>/dev/null || true
[ -f ~/.bashrc ] && source ~/.bashrc 2>/dev/null || true

# ── Helpers ─────────────────────────────────────────────────────────

log()   { echo "[gbrain-wrapper] $*"; }
error() { echo "[gbrain-wrapper] ❌ $*" >&2; }

# ── Trap: guarantee autopilot restart on script exit ───────────────
restart_autopilot_handler() {
    local EXIT_STATUS=$?
    if ! systemctl --user is-active --quiet "$SERVICE" 2>/dev/null; then
        log "Restarting autopilot (systemd)…"
        systemctl --user start "$SERVICE" 2>/dev/null || \
            log "⚠ Could not start $SERVICE — run 'gbrain autopilot --install' first"
    fi
    return "$EXIT_STATUS"
}
trap restart_autopilot_handler EXIT

# ── Validate args ──────────────────────────────────────────────────
if [ $# -eq 0 ]; then
    echo "Usage: gbrain-wrapper.sh <gbrain-command> [args...]"
    exit 1
fi

if [ ! -x "$GBRAIN_BIN" ]; then
    error "gbrain not found at $GBRAIN_BIN"
    exit 1
fi

# ── Step 1: Stop the autopilot ─────────────────────────────────────
if systemctl --user is-active --quiet "$SERVICE" 2>/dev/null; then
    log "Stopping autopilot (systemd)…"
    systemctl --user stop "$SERVICE" 2>/dev/null || true
    # Wait for clean shutdown (up to 10s)
    for i in $(seq 1 10); do
        if ! systemctl --user is-active --quiet "$SERVICE" 2>/dev/null; then
            break
        fi
        sleep 1
    done
else
    log "Autopilot not running — skipping stop"
fi

# ── Clear stale lock files (from previous crashes) ─────────────────
for lock in "$HOME/.gbrain/autopilot.lock" "$HOME/.gbrain/cycle.lock" \
            "$HOME/.gbrain/brain.pglite/.gbrain-lock/lock"; do
    [ -e "$lock" ] && rm -f "$lock" && log "Cleared stale lock: $lock"
done

# ── Step 2: Run the gbrain command ──────────────────────────────────
log "Running: gbrain $*"
"$GBRAIN_BIN" "$@"
CMD_EXIT=$?

if [ "$CMD_EXIT" -ne 0 ]; then
    log "⚠ gbrain $1 exited with code $CMD_EXIT"
fi

exit "$CMD_EXIT"
