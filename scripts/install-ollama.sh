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
    if ! command -v ollama &>/dev/null; then
      curl -fsSL https://ollama.com/install.sh | sh
    fi
    # gbrain's ollama provider runs llama-server directly (not the HTTP API).
    # Ensure the full Ollama tarball contents are available under ~/.local/lib/ollama/,
    # including llama-server binary and all .so libraries (libllama-server-impl.so,
    # libggml-*.so CPU backends).  This is needed because the official install.sh
    # only installs bin/ollama — gbrain needs the companion binaries.
    OLLAMA_LIB_DIR="${HOME}/.local/lib/ollama"
    if [[ ! -f "${OLLAMA_LIB_DIR}/llama-server" ]]; then
      echo "  Extracting Ollama tarball to ${OLLAMA_LIB_DIR}…"
      mkdir -p "$OLLAMA_LIB_DIR"
      # Detect architecture
      local arch
      arch="$(uname -m)"
      [[ "$arch" == "x86_64" ]] && arch="amd64"
      local tarball_url="https://ollama.com/download/ollama-linux-${arch}.tgz"
      local tmp_dir
      tmp_dir="$(mktemp -d)"
      if curl -fsSL "$tarball_url" -o "${tmp_dir}/ollama.tgz" 2>/dev/null; then
        tar -xzf "${tmp_dir}/ollama.tgz" -C "$tmp_dir" 2>/dev/null || true
        # Copy everything: bin/ollama, lib/ollama/* → ~/.local/lib/ollama/
        if [[ -d "${tmp_dir}/lib/ollama" ]]; then
          cp -r "${tmp_dir}/lib/ollama/"* "${OLLAMA_LIB_DIR}/" 2>/dev/null || true
        fi
        # Also copy any top-level binaries
        if [[ -f "${tmp_dir}/bin/ollama" ]] && [[ ! -f "${OLLAMA_LIB_DIR}/ollama" ]]; then
          cp "${tmp_dir}/bin/ollama" "${OLLAMA_LIB_DIR}/" 2>/dev/null || true
        fi
        # Ensure llama-server is executable
        chmod +x "${OLLAMA_LIB_DIR}/llama-server" 2>/dev/null || true
        chmod +x "${OLLAMA_LIB_DIR}/ollama" 2>/dev/null || true
        rm -rf "$tmp_dir"
        info "  Extracted llama-server + libs to ${OLLAMA_LIB_DIR}"
      else
        warn "Could not download Ollama tarball — gbrain may not find llama-server"
        rm -rf "$tmp_dir"
      fi
    else
      info "  llama-server already at ${OLLAMA_LIB_DIR}"
    fi

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
