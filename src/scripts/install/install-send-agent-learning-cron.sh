#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  install-send-agent-learning-cron.sh — Register agent learning sender cron
#
#  Creates a system-level cron job (launchd / systemd timer / crontab)
#  that runs send-agent-learning.sh every 6 hours.
#  The job is silent when nothing new to report (watchdog pattern).
#
#  Usage:
#    bash install-send-agent-learning-cron.sh
#    bash install-send-agent-learning-cron.sh --uninstall
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/os-config.sh"

SERVICE_NAME="com.hermes.agent-learning-sender"
UPDATE_SCRIPT="${CORTEX_DEPLOY_HOME:-${HOME}/.hermes-cortex}/scripts/send-agent-learning.sh"
STATE_DIR="${CORTEX_DEPLOY_HOME:-${HOME}/.hermes-cortex}/state"
mkdir -p "$STATE_DIR"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; RESET='\033[0m'
info()  { printf "${GREEN}✓${RESET} %s\\n" "$*"; }
warn()  { printf "${YELLOW}⚠${RESET} %s\\n" "$*"; }
error() { printf "${RED}✗${RESET} %s\\n" "$*"; }

install_cron() {
  if [[ ! -f "$UPDATE_SCRIPT" ]]; then
    error "send-agent-learning.sh not found at ${UPDATE_SCRIPT}"
    error "Install Hermes Cortex first, then run this script."
    return 1
  fi

  if [[ "$CORTEX_OS" == "macos" ]]; then
    _install_launchd
  elif [[ "$CORTEX_OS" == "linux" ]]; then
    _install_systemd
  elif [[ "$CORTEX_OS" == "windows" ]]; then
    _install_windows
  else
    warn "Unsupported OS: ${CORTEX_OS} — falling back to crontab"
    _install_crontab
  fi
}

uninstall_cron() {
  if [[ "$CORTEX_OS" == "macos" ]]; then
    _uninstall_launchd
  elif [[ "$CORTEX_OS" == "linux" ]]; then
    _uninstall_systemd
  elif [[ "$CORTEX_OS" == "windows" ]]; then
    _uninstall_windows
  else
    _uninstall_crontab
  fi
}

# ── macOS (launchd) ──────────────────────────────────────────
_install_launchd() {
  local plist_dest="${HOME}/Library/LaunchAgents/${SERVICE_NAME}.plist"
  # Every 6 hours = StartCalendarInterval with Hour=*/6 (0,6,12,18), Minute=0
  cat > "$plist_dest" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${SERVICE_NAME}</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/bash</string>
        <string>${UPDATE_SCRIPT}</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>0</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>RepeatInterval</key>
    <integer>21600</integer> <!-- 6 hours in seconds -->
    <key>StandardOutPath</key>
    <string>${STATE_DIR}/agent-learning-output.log</string>
    <key>StandardErrorPath</key>
    <string>${STATE_DIR}/agent-learning-error.log</string>
    <key>RunAtLoad</key>
    <false/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>
PLIST
  chmod 644 "$plist_dest"
  launchctl load "$plist_dest" 2>/dev/null || true
  info "launchd plist installed: ${SERVICE_NAME} (every 6h)"
}

_uninstall_launchd() {
  local plist="${HOME}/Library/LaunchAgents/${SERVICE_NAME}.plist"
  launchctl unload "$plist" 2>/dev/null || true
  rm -f "$plist"
  info "launchd plist removed: ${SERVICE_NAME}"
}

# ── Linux (systemd user timer) ────────────────────────────────
_install_systemd() {
  local unit_dir="${HOME}/.config/systemd/user"
  mkdir -p "$unit_dir"

  # Service unit
  cat > "${unit_dir}/${SERVICE_NAME}.service" <<UNIT
[Unit]
Description=Hermes Agent Learning Sender
After=network.target

[Service]
Type=oneshot
ExecStart=${UPDATE_SCRIPT}
StandardOutput=append:${STATE_DIR}/agent-learning-output.log
StandardError=append:${STATE_DIR}/agent-learning-error.log
UNIT

  # Timer unit — every 6 hours
  cat > "${unit_dir}/${SERVICE_NAME}.timer" <<TIMER
[Unit]
Description=Hermes Agent Learning Sender Timer

[Timer]
OnCalendar=*-*-* 00/6:00:00
Persistent=true

[Install]
WantedBy=default.target
TIMER

  systemctl --user daemon-reload 2>/dev/null || true
  systemctl --user enable "${SERVICE_NAME}.timer" 2>/dev/null || true
  systemctl --user start "${SERVICE_NAME}.timer" 2>/dev/null || true
  info "systemd timer installed: ${SERVICE_NAME} (every 6h)"
}

_uninstall_systemd() {
  systemctl --user stop "${SERVICE_NAME}.timer" 2>/dev/null || true
  systemctl --user disable "${SERVICE_NAME}.timer" 2>/dev/null || true
  rm -f "${HOME}/.config/systemd/user/${SERVICE_NAME}.service"
  rm -f "${HOME}/.config/systemd/user/${SERVICE_NAME}.timer"
  systemctl --user daemon-reload 2>/dev/null || true
  info "systemd timer removed: ${SERVICE_NAME}"
}

# ── Windows (scheduled task) ─────────────────────────────────
_install_windows() {
  powershell -Command "
    \$action = New-ScheduledTaskAction -Execute 'bash.exe' -Argument '${UPDATE_SCRIPT//\\//\\\\}'
    \$trigger = New-ScheduledTaskTrigger -Daily -At 0am
    \$trigger.RepetitionInterval = (New-TimeSpan -Hours 6)
    \$trigger.RepetitionDuration = ([TimeSpan]::MaxValue)
    \$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
    Register-ScheduledTask -TaskName '${SERVICE_NAME}' -Action \$action -Trigger \$trigger -Principal \$principal -Force
  " 2>/dev/null && info "Windows scheduled task installed: ${SERVICE_NAME} (every 6h)" \
    || warn "Could not install Windows scheduled task — try running as Administrator"
}

_uninstall_windows() {
  powershell -Command "Unregister-ScheduledTask -TaskName '${SERVICE_NAME}' -Confirm:\$false" 2>/dev/null || true
  info "Windows scheduled task removed: ${SERVICE_NAME}"
}

# ── Crontab fallback ─────────────────────────────────────────
_install_crontab() {
  local cron_line="0 */6 * * * ${UPDATE_SCRIPT} >> ${STATE_DIR}/agent-learning-output.log 2>> ${STATE_DIR}/agent-learning-error.log"
  (crontab -l 2>/dev/null | grep -v "${SERVICE_NAME}" || true; echo "${cron_line}") | crontab -
  info "crontab entry installed: ${SERVICE_NAME} (every 6h)"
}

_uninstall_crontab() {
  crontab -l 2>/dev/null | grep -v "${SERVICE_NAME}" | crontab - 2>/dev/null || true
  info "crontab entry removed: ${SERVICE_NAME}"
}

# ── Main ────────────────────────────────────────────────────
case "${1:-}" in
  --uninstall) uninstall_cron ;;
  --help|-h)   echo "Usage: $(basename "$0") [--uninstall]"; exit 0 ;;
  *)           install_cron ;;
esac