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
  # Check common locations even if not on PATH (Linux ~/.local/bin/ scenario)
  if command -v ollama &>/dev/null; then
    info "Ollama already installed — $(ollama --version 2>/dev/null || echo 'ollama')"
    return 0
  fi
  if [[ -x "${HOME}/.local/bin/ollama" ]]; then
    info "Ollama already installed at ~/.local/bin/ollama"
    # Ensure it's on PATH for subsequent steps
    export PATH="${HOME}/.local/bin:$PATH"
    return 0
  fi

  echo "  Installing Ollama…"

  if [[ "$CORTEX_OS" == "macos" ]]; then
    if command -v brew &>/dev/null; then
      brew install --cask ollama
    else
      warn "Homebrew not found. Installing Ollama via curl…"
      curl -fsSL --retry 3 --retry-delay 5 https://ollama.com/install.sh -o /tmp/ollama-install.sh
      sh /tmp/ollama-install.sh
      rm -f /tmp/ollama-install.sh
    fi

  elif [[ "$CORTEX_OS" == "linux" ]]; then
    if ! command -v ollama &>/dev/null; then
      curl -fsSL --retry 3 --retry-delay 5 https://ollama.com/install.sh -o /tmp/ollama-install.sh
      sh /tmp/ollama-install.sh
      rm -f /tmp/ollama-install.sh
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

  # Quick check: if Ollama is already responding on its API port, skip service setup
  if curl -s http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    info "Ollama already running at 127.0.0.1:11434 — service config skipped"
    return 0
  fi

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
      "PATH=/usr/local/bin:/usr/bin:/bin HOME=${HOME} OLLAMA_HOST=127.0.0.1 OLLAMA_NUM_THREADS=2 OLLAMA_KEEP_ALIVE=0"
    start_service "$OLLAMA_SERVICE_NAME"

  elif [[ "$CORTEX_OS" == "linux" ]]; then
    # On Linux, the Ollama install script usually sets up systemd.
    # If not, create a user service.
    if ! systemctl --user is-active ollama &>/dev/null 2>&1; then
      write_service "$OLLAMA_SERVICE_NAME" \
        "$ollama_bin serve" \
        "$workdir" \
        "PATH=/usr/local/bin:/usr/bin:/bin HOME=${HOME} OLLAMA_HOST=127.0.0.1 OLLAMA_NUM_THREADS=2 OLLAMA_KEEP_ALIVE=0"
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
  # Source model config for EMBEDDING_MODEL (survives cortex-update.sh)
  # Priority: ~/.hermes/hermes-cortex.env > ~/.hermes/models.env
  local unified_env="${HOME}/.hermes/hermes-cortex.env"
  [ -f "$unified_env" ] && source "$unified_env" 2>/dev/null || true
  local models_env="${HOME}/.hermes/models.env"
  [ -f "$models_env" ] && source "$models_env" 2>/dev/null || true
  local model="${1:-${EMBEDDING_MODEL:-nomic-embed-text:v1.5}}"
  if ollama list 2>/dev/null | grep -q "$model"; then
    info "Embedding model '${model}' already pulled"
  else
    echo "  Pulling embedding model: ${model}…"
    ollama pull "$model"
    info "Pulled ${model}"
  fi
}

# ── Build model with sufficient context ─────────────────────
# Hermes Agent uses local models (qwen2.5:3b, 7b variants, etc.)
# as judge/coding models. All models need 64k (65536) context for
# Hermes Agent's tool calls and conversation history.
#
# THERMAL NOTE: On CPU-only machines (e.g. MacBook i7-4980HQ), the
# default Ollama thread count (all cores) + model kept loaded 24/7
# causes 92°C throttling. The fix is NOT reducing context — it's:
#   1. OLLAMA_NUM_THREADS=2 — limits to 2 CPU cores (the real heat fix)
#   2. OLLAMA_KEEP_ALIVE=0  — unloads model between uses
# With both set, 65536 context runs at 58°C under load. Verified 2026-07-03.
#
# qwen2.5:3b  → Ollama registry build defaults to 32k → build with 64k
# Larger variants    → ship with 128k+ out of the box, well above minimum
#
# This function checks the model's current context length and only
# rebuilds if it's below 64k. Idempotent: safe to run on any model.
build_qwen_model() {
  local model_name="${1:-qwen2.5:3b}"
  local modelfile
  modelfile="$(mktemp)"

  if ! command -v ollama &>/dev/null; then
    warn "Ollama not installed — cannot build ${model_name} with 64k context"
    rm -f "$modelfile"
    return 0
  fi

  # Check if model exists and was built with 64k context
  local existing_ctx=""
  if ollama list 2>/dev/null | grep -qF "$model_name"; then
    existing_ctx=$(ollama show "$model_name" 2>/dev/null | grep -i "context length" | grep -oE '[0-9]+' | head -1 || echo "")
  fi

  if [[ -n "$existing_ctx" ]] && [[ "$existing_ctx" -ge 65536 ]]; then
    info "Model '${model_name}' already built with ${existing_ctx} context — OK"
    rm -f "$modelfile"
    return 0
  fi

  # Generate Modelfile dynamically so it works for any model variant
  # (qwen2.5:3b, mannix/qwen2.5-coder:7b-iq3_xs, etc.)
  {
    echo "FROM ${model_name}"
    echo "PARAMETER num_ctx 65536"
  } > "$modelfile"

  if [[ -n "$existing_ctx" ]]; then
    warn "Model '${model_name}' exists with ${existing_ctx} context (Hermes needs 64k)"
    warn "  Rebuilding with 64k context…"
  else
    echo "  Building ${model_name} with 64k context…"
  fi

  ollama create "$model_name" -f "$modelfile" 2>&1
  local result=$?
  rm -f "$modelfile"

  if [[ $result -eq 0 ]]; then
    info "Built ${model_name} with 64k context"
  else
    warn "Failed to build ${model_name} — check ollama status"
  fi
}

# ── Verify model context ────────────────────────────────────
verify_qwen_context() {
  local model_name="${1:-qwen2.5:3b}"
  local ctx
  ctx=$(ollama show "$model_name" 2>/dev/null | grep -i "context length" | grep -oE '[0-9]+' | head -1 || echo "unknown")
  if [[ "$ctx" == "unknown" ]] || [[ "$ctx" -lt 65536 ]]; then
    warn "⚠  ${model_name} context: ${ctx} (Hermes needs 64k / 65536 — thread limit with OLLAMA_NUM_THREADS=2 keeps thermals safe)"
    warn "   Rebuild: ollama create ${model_name} -f <(echo -e \"FROM ${model_name}\\nPARAMETER num_ctx 65536\")"
    return 1
  fi
  info "✅ ${model_name} context: ${ctx} (64k OK)"
  return 0
}

# ── Main ────────────────────────────────────────────────────
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  action="${1:-all}"
  case "$action" in
    install)   install_ollama ;;
    service)   setup_ollama_service ;;
    wait)      wait_for_ollama ;;
    embed)     pull_embedding_model "${2:-nomic-embed-text:v1.5}" ;;
    build_qwen) build_qwen_model "${2:-qwen2.5:3b}" ;;
    all|*)
      install_ollama
      setup_ollama_service
      wait_for_ollama
      pull_embedding_model "${2:-nomic-embed-text:v1.5}"
      build_qwen_model "${3:-qwen2.5:3b}"
      ;;
  esac
fi
