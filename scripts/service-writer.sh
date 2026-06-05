# ─────────────────────────────────────────────────────────────
#  Hermes Cortex — Multi-Platform Service File Writer
#  Source this from install.sh to get write_service().
#  Generates launchd plists (macOS), systemd units (Linux),
#  or PowerShell scheduled tasks (Windows).
# ─────────────────────────────────────────────────────────────

# ── Write Service File ──────────────────────────────────────
# Usage: write_service <name> <command> <workdir> [extra_env]
#
# Writes a service file to SERVICE_DIR/<name>.<SERVICE_EXT>
# and loads it. On macOS: launchd plist.
# On Linux: systemd user service.
# On Windows: PowerShell scheduled task script.
write_service() {
  local name="$1"
  local command="$2"
  local workdir="${3:-$HOME}"
  local extra_env="${4:-}"
  local label="${name}"

  mkdir -p "$SERVICE_DIR"

  if [[ "$CORTEX_OS" == "macos" ]]; then
    _write_launchd_plist "$name" "$command" "$workdir" "$extra_env"
  elif [[ "$CORTEX_OS" == "linux" ]]; then
    _write_systemd_unit "$name" "$command" "$workdir" "$extra_env"
  elif [[ "$CORTEX_OS" == "windows" ]]; then
    _write_windows_task "$name" "$command" "$workdir" "$extra_env"
  fi
}

# ── Start (Load) Service ────────────────────────────────────
start_service() {
  local name="$1"
  if [[ "$CORTEX_OS" == "macos" ]]; then
    launchctl load "${SERVICE_DIR}/${name}.${SERVICE_EXT}" 2>/dev/null || true
    launchctl start "$name" 2>/dev/null || true
  elif [[ "$CORTEX_OS" == "linux" ]]; then
    systemctl --user daemon-reload 2>/dev/null || true
    systemctl --user enable "$name" 2>/dev/null || true
    systemctl --user start "$name" 2>/dev/null || true
  elif [[ "$CORTEX_OS" == "windows" ]]; then
    powershell -File "${SERVICE_DIR}/${name}.ps1" -Action Start 2>/dev/null || true
  fi
}

# ── Stop (Unload) Service ───────────────────────────────────
stop_service() {
  local name="$1"
  if [[ "$CORTEX_OS" == "macos" ]]; then
    launchctl stop "$name" 2>/dev/null || true
    launchctl unload "${SERVICE_DIR}/${name}.${SERVICE_EXT}" 2>/dev/null || true
  elif [[ "$CORTEX_OS" == "linux" ]]; then
    systemctl --user stop "$name" 2>/dev/null || true
    systemctl --user disable "$name" 2>/dev/null || true
  elif [[ "$CORTEX_OS" == "windows" ]]; then
    powershell -File "${SERVICE_DIR}/${name}.ps1" -Action Stop 2>/dev/null || true
  fi
}

# ── Check if Service is Running ─────────────────────────────
service_running() {
  local name="$1"
  if [[ "$CORTEX_OS" == "macos" ]]; then
    launchctl list "$name" &>/dev/null
  elif [[ "$CORTEX_OS" == "linux" ]]; then
    systemctl --user is-active "$name" &>/dev/null
  elif [[ "$CORTEX_OS" == "windows" ]]; then
    powershell "Get-ScheduledTask -TaskName 'Hermes-${name}' -ErrorAction SilentlyContinue" &>/dev/null
  fi
}

# ── Internal: launchd plist writer ──────────────────────────
_write_launchd_plist() {
  local name="$1" command="$2" workdir="$3" extra_env="$4"
  local plist="${SERVICE_DIR}/${name}.plist"

  cat > "$plist" <<PLISTEOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${name}</string>
    <key>ProgramArguments</key>
    <array>
PLISTEOF
  # Split command into array elements
  for arg in $command; do
    echo "        <string>${arg}</string>" >> "$plist"
  done

  cat >> "$plist" <<PLISTEOF
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>10</integer>
    <key>WorkingDirectory</key>
    <string>${workdir}</string>
    <key>StandardOutPath</key>
    <string>${workdir}/.hermes/logs/${name}.log</string>
    <key>StandardErrorPath</key>
    <string>${workdir}/.hermes/logs/${name}.log</string>
PLISTEOF

  # Add environment variables if provided
  if [[ -n "$extra_env" ]]; then
    echo "    <key>EnvironmentVariables</key>" >> "$plist"
    echo "    <dict>" >> "$plist"
    # extra_env is "KEY=VAL KEY2=VAL2"
    for pair in $extra_env; do
      local key="${pair%%=*}"
      local val="${pair#*=}"
      echo "        <key>${key}</key>" >> "$plist"
      echo "        <string>${val}</string>" >> "$plist"
    done
    echo "    </dict>" >> "$plist"
  fi

  echo "</dict>" >> "$plist"
  echo "</plist>" >> "$plist"

  info "  Created launchd plist: ${plist}"
}

# ── Internal: systemd unit writer ───────────────────────────
_write_systemd_unit() {
  local name="$1" command="$2" workdir="$3" extra_env="$4"
  local unit="${SERVICE_DIR}/${name}.service"

  cat > "$unit" <<UNITEOF
[Unit]
Description=Hermes Cortex — ${name}
After=network.target

[Service]
Type=simple
ExecStart=${command}
WorkingDirectory=${workdir}
Restart=on-failure
RestartSec=10
StandardOutput=append:${workdir}/.hermes/logs/${name}.log
StandardError=append:${workdir}/.hermes/logs/${name}.log
UNITEOF

  # Add environment variables if provided
  if [[ -n "$extra_env" ]]; then
    echo "Environment=${extra_env}" >> "$unit"
  fi

  cat >> "$unit" <<UNITEOF

[Install]
WantedBy=default.target
UNITEOF

  info "  Created systemd unit: ${unit}"
}

# ── Internal: Windows scheduled task writer ─────────────────
_write_windows_task() {
  local name="$1" command="$2" workdir="$3" extra_env="$4"
  local script="${SERVICE_DIR}/${name}.ps1"

  cat > "$script" <<PS1EOF
# Hermes Cortex — ${name} service wrapper
# Generated by install.sh
param([string]${Action} = "Start")

${task_name} = "Hermes-${name}"
${bin_path} = "${command}"
${work_dir} = "${workdir}"

function Start-Task {
    \$task = Get-ScheduledTask -TaskName \$task_name -ErrorAction SilentlyContinue
    if (-not \$task) {
        \$action = New-ScheduledTaskAction -Execute \$bin_path -WorkingDirectory \$work_dir
        \$trigger = New-ScheduledTaskTrigger -AtStartup
        \$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
        Register-ScheduledTask -TaskName \$task_name -Action \$action -Trigger \$trigger -Settings \$settings -Force
        Write-Output "Created scheduled task: \$task_name"
    }
    Start-ScheduledTask -TaskName \$task_name
    Write-Output "Started: \$task_name"
}

function Stop-Task {
    Stop-ScheduledTask -TaskName \$task_name -ErrorAction SilentlyContinue
    Write-Output "Stopped: \$task_name"
}

switch (\$Action) {
    "Start" { Start-Task }
    "Stop"  { Stop-Task }
    default { Write-Output "Usage: \$script -Action Start|Stop" }
}
PS1EOF

  info "  Created Windows service script: ${script}"
}

# ── Export ──────────────────────────────────────────────────
export -f write_service start_service stop_service service_running
