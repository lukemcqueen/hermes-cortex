#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
#  gbrain-wrapper.sh — gbrain CLI wrapper with autopilot lifecycle mgmt
#
#  Cross-platform: Linux (systemd) + macOS (launchd)
#
#  Manages the gbrain autopilot service around every gbrain command.
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

# ── OS detection ───────────────────────────────────────────────────
IS_MAC=false
IS_LINUX=false
case "$(uname -s)" in
  Darwin) IS_MAC=true  ;;
  Linux)  IS_LINUX=true ;;
  *)      echo "[gbrain-wrapper] ⚠ Unknown OS: $(uname -s) — assuming Linux service semantics"
          IS_LINUX=true ;;
esac

# ── Service management helpers ─────────────────────────────────────
# On Linux:    systemctl --user
# On macOS:    launchctl
SERVICE_NAME_AUTOPILOT="gbrain-autopilot"
SERVICE_NAME_LEGACY="com.gbrain.sync-watch"
if $IS_MAC; then
  SERVICE_NAME_AUTOPILOT="com.gbrain.autopilot"
  SERVICE_NAME_LEGACY="com.gbrain.sync-watch"
fi

_service_is_active() {
  local name="$1"
  if $IS_LINUX; then
    systemctl --user is-active --quiet "$name" 2>/dev/null
  elif $IS_MAC; then
    local out
    out=$(launchctl list "$name" 2>/dev/null) || return 1
    echo "$out" | grep -q '"PID"' && return 0 || return 1
  fi
}

_service_stop() {
  local name="$1"
  if $IS_LINUX; then
    systemctl --user stop "$name" 2>/dev/null || true
  elif $IS_MAC; then
    launchctl bootout gui/$(id -u)/"$name" 2>/dev/null || true
  fi
}

_service_start() {
  local name="$1"
  if $IS_LINUX; then
    systemctl --user start "$name" 2>/dev/null || \
      echo "[gbrain-wrapper] ⚠ Could not start $name — run 'gbrain autopilot --install' first"
  elif $IS_MAC; then
    launchctl bootstrap gui/$(id -u)/"$name" 2>/dev/null || \
      launchctl kickstart gui/$(id -u)/"$name" 2>/dev/null || \
      echo "[gbrain-wrapper] ⚠ Could not start $name — run 'gbrain autopilot --install' first"
  fi
}

# ── Environment ────────────────────────────────────────────────────
export PATH="$HOME/.bun/bin:$PATH"
export GBRAIN_AI_EMBED_TIMEOUT_MS=300000

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
    if ! _service_is_active "$SERVICE_NAME_AUTOPILOT"; then
        log "Restarting autopilot ($([ $IS_MAC ] && echo 'launchd' || echo 'systemd'))…"
        _service_start "$SERVICE_NAME_AUTOPILOT"
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
if _service_is_active "$SERVICE_NAME_AUTOPILOT"; then
    log "Stopping autopilot ($([ $IS_MAC ] && echo 'launchd' || echo 'systemd'))…"
    _service_stop "$SERVICE_NAME_AUTOPILOT"
    # Wait for clean shutdown (up to 10s)
    for i in $(seq 1 10); do
        if ! _service_is_active "$SERVICE_NAME_AUTOPILOT"; then
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
