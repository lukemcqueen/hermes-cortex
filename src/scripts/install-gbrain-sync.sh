#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Hermes Cortex — Multi-OS gbrain Sync Service
#  Called by install.sh. Sets up auto-sync via
#  launchd (macOS), systemd (Linux), or scheduled task (Windows).
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"
source "${SCRIPT_DIR}/os-config.sh"
source "${SCRIPT_DIR}/service-writer.sh"

GREEN="${GREEN:-'\033[0;32m'}"; YELLOW="${YELLOW:-'\033[1;33m'}"; RESET="${RESET:-'\033[0m'}"
info()  { printf "${GREEN}✓${RESET} %s\n" "$*"; }
warn()  { printf "${YELLOW}⚠${RESET} %s\n" "$*"; }

setup_gbrain_sync_service() {
  local sync_script="${HOME}/.gbrain/sync-watch.sh"
  local label="com.gbrain.sync-watch"
  local autopilot_label="com.gbrain.autopilot"

  # gbrain autopilot (installed by `gbrain autopilot --install`) is a
  # self-maintaining daemon that handles sync internally every ~150s.
  # PGLite 0.4.x only supports one connection at a time, so sync-watch
  # cannot coexist with autopilot. Skip if autopilot is already present.
  if service_running "$autopilot_label" 2>/dev/null; then
    info "gbrain autopilot detected — autopilot handles sync internally, skipping sync-watch"
    return 0
  fi
  if launchctl list "$autopilot_label" &>/dev/null 2>&1; then
    info "gbrain autopilot plist found — autopilot handles sync internally, skipping sync-watch"
    return 0
  fi

  if service_running "$label"; then
    info "gbrain sync-watch already running"
    return 0
  fi

  # Create sync script
  mkdir -p "${HOME}/.gbrain"
  if [[ ! -f "$sync_script" ]]; then
    cat > "$sync_script" <<'SCRIPTEOF'
#!/bin/bash
# gbrain sync watch daemon
# Polls gbrain sync every 120 seconds.
# Auto-detects sources — skips cycle if none are registered
# (prevents useless polling on a fresh install before seed-project-brain.sh).
# Launchd/systemd manages this via KeepAlive

BUN="${HOME}/.bun/bin/bun"
GBRAIN="${HOME}/.bun/bin/gbrain"
LOG="${HOME}/.gbrain/sync-watch.log"
ERR_LOG="${HOME}/.gbrain/sync-watch.err"
INTERVAL=120

exec >> "$LOG" 2>> "$ERR_LOG"
echo "[$(date)] gbrain sync watch daemon starting — interval ${INTERVAL}s"

# Detect how many non-default sources exist
count_sources() {
    "$BUN" "$GBRAIN" sources list 2>/dev/null \
        | grep -c '^  [^d]' 2>/dev/null || echo 0
}

while true; do
    src_count=$(count_sources)
    if [[ "$src_count" -eq 0 ]]; then
        echo "[$(date)] No non-default sources registered — skipping cycle (run seed-project-brain.sh)"
        sleep "$INTERVAL"
        continue
    fi
    echo "[$(date)] === Sync cycle (${src_count} source(s)) ==="
    "$BUN" "$GBRAIN" sync --all --skip default --no-pull 2>&1
    echo "[$(date)] === Cycle complete, sleeping ${INTERVAL}s ==="
    sleep "$INTERVAL"
done
SCRIPTEOF
    chmod +x "$sync_script"
  fi

  # Create service
  local bun_path="${HOME}/.bun/bin/bun"
  local gbrain_path="${HOME}/.bun/bin/gbrain"
  local bash_cmd

  if [[ "$CORTEX_OS" == "macos" ]]; then
    # On macOS, write_service needs a simple command — use bash to run the script
    write_service "$label" \
      "/bin/bash ${sync_script}" \
      "${HOME}" \
      "PATH=${HOME}/.bun/bin:/usr/local/bin:/usr/bin:/bin HOME=${HOME}"
    start_service "$label"
    info "  gbrain sync-watch launched"

  elif [[ "$CORTEX_OS" == "linux" ]]; then
    write_service "$label" \
      "/bin/bash ${sync_script}" \
      "${HOME}" \
      "PATH=${HOME}/.bun/bin:/usr/local/bin:/usr/bin:/bin HOME=${HOME}"
    start_service "$label"
    info "  gbrain sync-watch launched"

  elif [[ "$CORTEX_OS" == "windows" ]]; then
    write_service "$label" \
      "\"${bun_path}\" \"${gbrain_path}\" sync --all --skip default --no-pull" \
      "${HOME}"
    start_service "$label"
    info "  gbrain sync-watch scheduled"
  fi
}

# ── Main ────────────────────────────────────────────────────
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  setup_gbrain_sync_service
fi
