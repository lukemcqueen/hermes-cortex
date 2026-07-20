#!/bin/bash
# install-worker.sh — install agent-worker as a systemd --user service
# Run once per agent machine. No Hermes cron needed.
#
# Usage:
#   bash install-worker.sh              # interactive (prompts for agent name)
#   bash install-worker.sh joseph       # or pass agent name as argument
#
# After install:
#   systemctl --user status hermes-agent-worker
#   journalctl --user -u hermes-agent-worker -f

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; RESET='\033[0m'
info()  { echo -e "${GREEN}[INFO]${RESET} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${RESET} $*"; }
err()   { echo -e "${RED}[ERR]${RESET} $*"; }

# ── Config ──

AGENT_NAME="${1:-}"
if [ -z "$AGENT_NAME" ]; then
  echo -n "Enter agent name (e.g. esther, joseph, gisu): "
  read -r AGENT_NAME
fi
if [ -z "$AGENT_NAME" ]; then
  err "Agent name required"
  exit 1
fi

CORTEX_REPO="${CORTEX_REPO:-${HOME}/hermes-cortex}"
CORTEX_DEPLOY_HOME="${CORTEX_DEPLOY_HOME:-${HOME}/.hermes-cortex}"
HERMES_HOME="${HERMES_HOME:-${HOME}/.hermes}"
WORKER_SCRIPT_SRC="${CORTEX_REPO}/ops/scripts/agent/agent-worker.py"
WORKER_SCRIPT_DST="${HERMES_HOME}/scripts/agent-worker.py"
SERVICE_FILE="${HOME}/.config/systemd/user/hermes-agent-worker.service"
CONFIG_FILE="${CORTEX_DEPLOY_HOME}/cortex-bus.conf"

# ── Grant bus permissions ──
info "Granting bus permissions for ${CYAN}${AGENT_NAME}${RESET}..."
if command -v docker &>/dev/null && docker ps --filter name=gbrain --format "{{.Names}}" 2>/dev/null | grep -q gbrain; then
  docker exec gbrain-postgres psql -U gbrain -d gbrain -c \
    "UPDATE bus.permissions SET can_write = CASE WHEN NOT (can_write @> '{workflow_step_result}'::text[]) THEN can_write || '{workflow_step_result}' ELSE can_write END WHERE agent_name = '${AGENT_NAME}';" \
    2>/dev/null && info "${GREEN}✓${RESET} Bus permissions granted" || warn "Could not grant permissions"
else
  warn "Cannot access bus DB remotely. Ask Moses to grant permissions:"
  warn "  Moses: UPDATE bus.permissions SET can_write = can_write || '{workflow_step_result}' WHERE agent_name = '${AGENT_NAME}';"
fi

# ── Check prerequisites ──

# ── Conflict warning ──

if crontab -l 2>/dev/null | grep -q agent-message-handler; then
  warn "⚠️  agent-message-handler cron detected — this worker will conflict with the handler!"
  warn "   Both read from inbox_${AGENT_NAME} via the bus."
  warn "   The worker uses vt=0 peek so non-workflow messages stay visible for the handler."
else
  info "  No handler cron detected."
fi

# ── Install ──

info "Installing agent-worker for: ${CYAN}${AGENT_NAME}${RESET}"

if [ ! -f "$WORKER_SCRIPT_SRC" ]; then
  warn "No local repo at ${CORTEX_REPO}. Will download from GitHub."
  WORKER_SCRIPT_SRC="https://raw.githubusercontent.com/fleet-operator/hermes-cortex/main/ops/scripts/agent/agent-worker.py"
fi

if [ ! -f "$CONFIG_FILE" ]; then
  warn "Config not found: ${CONFIG_FILE}"
  warn "Create it with: BUS_URL, CORTEX_BASIC_AUTH, AGENT_NAME"
fi

# ── Ensure systemd user dir ──

mkdir -p "${HOME}/.config/systemd/user"
mkdir -p "${HERMES_HOME}/scripts"

# ── Copy worker script ──

if [ -f "$WORKER_SCRIPT_SRC" ]; then
  cp "$WORKER_SCRIPT_SRC" "$WORKER_SCRIPT_DST"
  info "Copied worker script to ${WORKER_SCRIPT_DST}"
else
  info "Downloading from GitHub..."
  curl -sL -o "$WORKER_SCRIPT_DST" "$WORKER_SCRIPT_SRC"
fi
chmod +x "$WORKER_SCRIPT_DST"

# ── Create systemd service file ──

cat > "$SERVICE_FILE" << SERVICEEOF
[Unit]
Description=Hermes Agent Worker — ${AGENT_NAME}
Documentation=https://github.com/fleet-operator/hermes-cortex
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/env python3 ${WORKER_SCRIPT_DST}
Restart=always
RestartSec=10
Environment=AGENT_NAME=${AGENT_NAME}
EnvironmentFile=${CONFIG_FILE}
Environment=OLLAMA_URL=http://localhost:11434
Environment=OLLAMA_MODEL=qwen2.5-coder:3b
Environment=POLL_INTERVAL=30
Environment=VT_SECONDS=120
Environment=MAX_RETRIES=3

[Install]
WantedBy=default.target
SERVICEEOF

info "Created service: ${SERVICE_FILE}"

# ── Check service file contains agent config ──

grep -q "AGENT_NAME=${AGENT_NAME}" "$SERVICE_FILE" || {
  err "Service file does not contain AGENT_NAME=${AGENT_NAME}"
  exit 1
}

# ── Reload systemd and enable ──

systemctl --user daemon-reload 2>/dev/null || true
systemctl --user enable hermes-agent-worker 2>/dev/null && \
  info "Service enabled (will auto-start on boot)" || \
  warn "Could not enable service (systemd user mode OK)"

systemctl --user restart hermes-agent-worker 2>/dev/null && \
  info "Service started" || \
  warn "Could not start service. Try: systemctl --user start hermes-agent-worker"

# ── Verify ──

sleep 2
if systemctl --user is-active hermes-agent-worker >/dev/null 2>&1; then
  info "${GREEN}✓${RESET} hermes-agent-worker is ACTIVE for ${CYAN}${AGENT_NAME}${RESET}"
else
  warn "Service not active. Check: journalctl --user -u hermes-agent-worker -n 20"
fi

info "Done. Worker logs: ${HERMES_HOME}/logs/agent-worker-${AGENT_NAME}.log"
info "Worker flags: ${HERMES_HOME}/state/worker-pending/"
