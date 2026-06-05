#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Hermes Cortex — Multi-OS gbrain Sync Service
#  Called by install.sh. Sets up auto-sync via
#  launchd (macOS), systemd (Linux), or scheduled task (Windows).
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/os-config.sh"

GREEN="${GREEN:-'\033[0;32m'}"; YELLOW="${YELLOW:-'\033[1;33m'}"; RESET="${RESET:-'\033[0m'}"
info()  { printf "${GREEN}✓${RESET} %s\n" "$*"; }
warn()  { printf "${YELLOW}⚠${RESET} %s\n" "$*"; }

setup_gbrain_sync_service() {
  local sync_script="${HOME}/.gbrain/sync-watch.sh"
  local label="com.gbrain.sync-watch"

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
# Polls gbrain sync every 120 seconds
# Launchd/systemd manages this via KeepAlive

BUN="${HOME}/.bun/bin/bun"
GBRAIN="${HOME}/.bun/bin/gbrain"
LOG="${HOME}/.gbrain/sync-watch.log"
ERR_LOG="${HOME}/.gbrain/sync-watch.err"
INTERVAL=120

exec >> "$LOG" 2>> "$ERR_LOG"
echo "[$(date)] gbrain sync watch daemon starting — interval ${INTERVAL}s"

while true; do
    echo "[$(date)] === Sync cycle ==="
    "$BUN" "$GBRAIN" sync --all --no-pull 2>&1
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
      "\"${bun_path}\" \"${gbrain_path}\" sync --all --no-pull" \
      "${HOME}"
    start_service "$label"
    info "  gbrain sync-watch scheduled"
  fi
}

# ── Main ────────────────────────────────────────────────────
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  setup_gbrain_sync_service
fi
