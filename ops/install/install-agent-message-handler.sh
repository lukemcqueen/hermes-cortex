#!/usr/bin/env bash
# install-agent-message-handler.sh — Install the agent message handler service
#
# Installs agent-message-handler.py as a launchd (macOS) or systemd (Linux)
# service that polls the agent's bus inbox and processes fleet commands.
#
# Set CORTEX_BUS_URL before installing so it's baked into the
# service definition:
#
#   export CORTEX_BUS_URL=https://orchestrator-host:13004
#   export AGENT_NAME=titus
#   export CORTEX_BUS_AUTH=user:pass
#
# Usage:
#   bash install-agent-message-handler.sh              # install + start
#   bash install-agent-message-handler.sh --service-only  # just (re)register the service
#
# Compatible: Linux (systemd --user) and macOS (launchd)

set -euo pipefail

REPO_DIR="${CORTEX_REPO:-$HOME/hermes-cortex}"
AGENT_NAME="${AGENT_NAME:-$(hostname)}"
HANDLER_SCRIPT="${REPO_DIR}/ops/scripts/agent/agent-message-handler.py"

# ── Colors ──
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${GREEN}✓${NC} $*"; }
warn()  { echo -e "${YELLOW}⚠${NC} $*"; }
err()   { echo -e "${RED}✗${NC} $*"; }

# ── Detect platform ──
IS_MAC=false
IS_LINUX=false
if [[ "$(uname)" == "Darwin" ]]; then
    IS_MAC=true
elif [[ "$(uname)" == "Linux" ]]; then
    IS_LINUX=true
fi

# ── Service definition ──

install_launchd() {
    local label="com.hermes.agent-message-handler"
    local plist="$HOME/Library/LaunchAgents/${label}.plist"

    cat > "$plist" <<LAUNCHDPLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>${label}</string>
    <key>ProgramArguments</key>
    <array>
        <string>${HANDLER_SCRIPT}</string>
        <string>--once</string>
    </array>
    <key>StartInterval</key>
    <integer>300</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>${HOME}/Library/Logs/hermes-agent-message-handler.log</string>
    <key>StandardErrorPath</key>
    <string>${HOME}/Library/Logs/hermes-agent-message-handler.err</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>AGENT_NAME</key>
        <string>${AGENT_NAME}</string>
        <key>CORTEX_BUS_URL</key>
        <string>${CORTEX_BUS_URL}</string>
        <key>CORTEX_BUS_TOKEN</key>
        <string>${CORTEX_BUS_TOKEN}</string>
        <key>CORTEX_BUS_AUTH</key>
        <string>${CORTEX_BUS_AUTH}</string>
    </dict>
</dict>
</plist>
LAUNCHDPLIST

    launchctl load "$plist" 2>/dev/null || true
    info "launchd plist installed: ${plist}"
}

install_systemd() {
    local unit_name="hermes-agent-message-handler"
    local service_dir="${HOME}/.config/systemd/user"
    mkdir -p "$service_dir"

    # Service unit (runs once per tick)
    cat > "${service_dir}/${unit_name}.service" <<SYSTEMD_SERVICE
[Unit]
Description=Hermes Agent Message Handler
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=${HANDLER_SCRIPT} --once
Environment=AGENT_NAME=${AGENT_NAME}
Environment=CORTEX_BUS_URL=${CORTEX_BUS_URL}
Environment=CORTEX_BUS_TOKEN=${CORTEX_BUS_TOKEN}
Environment=CORTEX_BUS_AUTH=${CORTEX_BUS_AUTH}
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
SYSTEMD_SERVICE

    # Timer unit (every 5 min)
    cat > "${service_dir}/${unit_name}.timer" <<SYSTEMD_TIMER
[Unit]
Description=Hermes Agent Message Handler Timer

[Timer]
OnCalendar=*:0/5
Persistent=true

[Install]
WantedBy=timers.target
SYSTEMD_TIMER

    systemctl --user daemon-reload
    systemctl --user enable --now "${unit_name}.timer"
    info "systemd timer installed: ${unit_name}.timer"
}

# ── Main ──

echo ""
echo "━━━ Agent Message Handler Installer ──────────"
echo "  Agent:      ${AGENT_NAME}"
echo "  Platform:   $(uname -s)"
echo "  Handler:    ${HANDLER_SCRIPT}"
echo "───────────────────────────────────────────────"
echo ""

# 1. Verify handler exists
if [[ ! -f "$HANDLER_SCRIPT" ]]; then
    err "Handler not found: ${HANDLER_SCRIPT}"
    err "Clone the repo first: git clone https://github.com/fleet-operator/hermes-cortex.git"
    exit 1
fi

# 2. Install service
if $IS_MAC; then
    install_launchd
elif $IS_LINUX; then
    install_systemd
else
    err "Unsupported platform: $(uname -s)"
    exit 1
fi

# 3. Verify
echo ""
info "Agent message handler installed. Logs:"
if $IS_MAC; then
    echo "  tail -f ${HOME}/Library/Logs/hermes-agent-message-handler.log"
elif $IS_LINUX; then
    echo "  journalctl --user -u hermes-agent-message-handler.service -f"
fi

cat <<HELP

Next steps:
  1. Verify the handler can reach the bus via CORTEX_BUS_URL
  2. The handler runs every 5 minutes and checks for UPDATE_REQUEST etc.
  3. When Moses dispatches fleet commands, this agent processes them

HELP
