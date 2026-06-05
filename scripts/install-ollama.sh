#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Hermes Cortex — Multi-OS Ollama Installer
#  Called by install.sh. Handles installation and service setup
#  for Ollama + embedding model on any supported OS.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

# Source OS config (expects CORTEX_OS, PKG_*, SERVICE_* to be set)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/os-config.sh"

# Colors (inherit or set defaults)
GREEN="${GREEN:-'\033[0;32m'}"; YELLOW="${YELLOW:-'\033[1;33m'}"; RESET="${RESET:-'\033[0m'}"
info()  { printf "${GREEN}✓${RESET} %s\n" "$*"; }
warn()  { printf "${YELLOW}⚠${RESET} %s\n" "$*"; }

install_ollama() {
  if command -v ollama &>/dev/null; then
    info "Ollama already installed — $(ollama --version 2>/dev/null || echo 'ollama')"
    return 0
  fi

  echo "  Installing Ollama…"

  if [[ "$CORTEX_OS" == "macos" ]]; then
    if command -v brew &>/dev/null; then
      brew install --cask ollama
    else
      warn "Homebrew not found. Installing Ollama via curl…"
      curl -fsSL https://ollama.com/install.sh | sh
    fi

  elif [[ "$CORTEX_OS" == "linux" ]]; then
    curl -fsSL https://ollama.com/install.sh | sh

  elif [[ "$CORTEX_OS" == "windows" ]]; then
    # Windows: download the installer
    local installer="/tmp/OllamaSetup.exe"
    curl -fsSL https://ollama.com/download/OllamaSetup.exe -o "$installer"
    "$installer" /S
    rm -f "$installer"
  fi

  info "Ollama installed"
}

setup_ollama_service() {
  local ollama_bin="${OLLAMA_BIN}"
  local workdir="${HOME}"

  if service_running "$OLLAMA_SERVICE_NAME"; then
    info "Ollama service already running"
    return 0
  fi

  echo "  Configuring Ollama service…"

  if [[ "$CORTEX_OS" == "macos" ]]; then
    mkdir -p "${HOME}/.ollama"
    write_service "$OLLAMA_SERVICE_NAME" \
      "$ollama_bin serve" \
      "$workdir" \
      "PATH=/usr/local/bin:/usr/bin:/bin HOME=${HOME} OLLAMA_HOST=127.0.0.1"
    start_service "$OLLAMA_SERVICE_NAME"

  elif [[ "$CORTEX_OS" == "linux" ]]; then
    # On Linux, the Ollama install script usually sets up systemd.
    # If not, create a user service.
    if ! systemctl --user is-active ollama &>/dev/null 2>&1; then
      write_service "$OLLAMA_SERVICE_NAME" \
        "$ollama_bin serve" \
        "$workdir" \
        "PATH=/usr/local/bin:/usr/bin:/bin HOME=${HOME} OLLAMA_HOST=127.0.0.1"
      start_service "$OLLAMA_SERVICE_NAME"
    fi

  elif [[ "$CORTEX_OS" == "windows" ]]; then
    write_service "$OLLAMA_SERVICE_NAME" \
      "\"${ollama_bin}\" serve" \
      "$workdir"
    start_service "$OLLAMA_SERVICE_NAME"
  fi
}

wait_for_ollama() {
  echo "  Waiting for Ollama to respond…"
  for i in {1..30}; do
    if curl -s http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
      info "Ollama ready at 127.0.0.1:11434"
      return 0
    fi
    sleep 2
  done
  warn "Ollama didn't start in time. Continue anyway (start manually later)."
  return 0
}

pull_embedding_model() {
  local model="${1:-nomic-embed-text}"
  if ollama list 2>/dev/null | grep -q "$model"; then
    info "Embedding model '${model}' already pulled"
  else
    echo "  Pulling embedding model: ${model}…"
    ollama pull "$model"
    info "Pulled ${model}"
  fi
}

# ── Main ────────────────────────────────────────────────────
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  action="${1:-all}"
  case "$action" in
    install)   install_ollama ;;
    service)   setup_ollama_service ;;
    wait)      wait_for_ollama ;;
    embed)     pull_embedding_model "${2:-nomic-embed-text}" ;;
    all|*)
      install_ollama
      setup_ollama_service
      wait_for_ollama
      pull_embedding_model "${2:-nomic-embed-text}"
      ;;
  esac
fi
