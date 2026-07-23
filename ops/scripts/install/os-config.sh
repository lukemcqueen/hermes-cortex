# ─────────────────────────────────────────────────────────────
#  Hermes Cortex — OS Configuration & Detection
#  Source this from install.sh to get OS-agnostic variables.
#
#  Sets: CORTEX_OS, PKG_*, SERVICE_*, paths, init system
# ─────────────────────────────────────────────────────────────

# ── OS Detection ────────────────────────────────────────────
# Auto-detect, but allow override via CORTEX_OS env var
DETECTED_OS="$(uname -s)"
CORTEX_OS="${CORTEX_OS:-$DETECTED_OS}"

# Normalize
case "$(echo "$CORTEX_OS" | tr '[:upper:]' '[:lower:]')" in
  darwin)  CORTEX_OS="macos"  ;;
  linux)   CORTEX_OS="linux"  ;;
  windows|mingw*|msys*|cygwin*) CORTEX_OS="windows"  ;;
  *)       CORTEX_OS="$CORTEX_OS" ;;  # passthrough
esac

# ── Profile (role) ──────────────────────────────────────────
CORTEX_PROFILE="${CORTEX_PROFILE:-server}"

# ── Agent Type (role detection) ────────────────────────────
# Used by scripts to self-audit: run only on correct agent type.
# Values: orchestrator, server, dev
# Detection: AGENT_TYPE env var → IS_ORCHESTRATOR → hostname → 'server'
if [[ -n "${AGENT_TYPE:-}" ]]; then
  CORTEX_AGENT_TYPE="$AGENT_TYPE"
elif [[ "${IS_ORCHESTRATOR:-false}" == "true" ]]; then
  CORTEX_AGENT_TYPE="orchestrator"
else
  _host=$(hostname -s 2>/dev/null || echo "unknown")
  case "$_host" in
    moses|esther) CORTEX_AGENT_TYPE="orchestrator" ;;
    *)           CORTEX_AGENT_TYPE="server" ;;
  esac
fi

# Self-audit: scripts call this to refuse on wrong agent type
check_agent_type() {
  local required="$1"
  local script_name="${2:-${BASH_SOURCE[1]:-unknown}}"
  if [[ "$CORTEX_AGENT_TYPE" != "$required" ]]; then
    echo "❌ $script_name requires AGENT_TYPE=$required (current: $CORTEX_AGENT_TYPE)" >&2
    echo "   On $required agents, run the appropriate install or update script." >&2
    echo "   To remove this component if it should not be here:" >&2
    echo "     AGENT_TYPE=$required bash $script_name --uninstall" >&2
    return 1
  fi
  return 0
}

export CORTEX_AGENT_TYPE

# ── Package Manager ─────────────────────────────────────────
if [[ "$CORTEX_OS" == "macos" ]]; then
  PKG_MANAGER="brew"
  PKG_INSTALL="brew install"
  PKG_CASK_INSTALL="brew install --cask"
  PKG_UPDATE="brew update"
  PKG_UPGRADE="brew upgrade"
elif [[ "$CORTEX_OS" == "linux" ]]; then
  # Detect Linux package manager
  if   command -v apt &>/dev/null; then
    PKG_MANAGER="apt"
    PKG_INSTALL="sudo apt install -y"
    PKG_CASK_INSTALL=""  # no cask equivalent on Linux
    PKG_UPDATE="sudo apt update"
    PKG_UPGRADE="sudo apt upgrade -y"
  elif command -v dnf &>/dev/null; then
    PKG_MANAGER="dnf"
    PKG_INSTALL="sudo dnf install -y"
    PKG_CASK_INSTALL=""
    PKG_UPDATE="sudo dnf check-update || true"
    PKG_UPGRADE="sudo dnf upgrade -y"
  elif command -v pacman &>/dev/null; then
    PKG_MANAGER="pacman"
    PKG_INSTALL="sudo pacman -S --noconfirm"
    PKG_CASK_INSTALL=""
    PKG_UPDATE="sudo pacman -Sy"
    PKG_UPGRADE="sudo pacman -Su --noconfirm"
  elif command -v zypper &>/dev/null; then
    PKG_MANAGER="zypper"
    PKG_INSTALL="sudo zypper install -y"
    PKG_CASK_INSTALL=""
    PKG_UPDATE="sudo zypper refresh"
    PKG_UPGRADE="sudo zypper update -y"
  else
    PKG_MANAGER="unknown"
    PKG_INSTALL="echo 'WARN: no package manager found — install manually:'"
    PKG_CASK_INSTALL=""
    PKG_UPDATE="true"
    PKG_UPGRADE="true"
  fi
elif [[ "$CORTEX_OS" == "windows" ]]; then
  # Windows — prefer winget, fall back to choco
  if command -v winget &>/dev/null; then
    PKG_MANAGER="winget"
    PKG_INSTALL="winget install --silent --accept-package-agreements"
    PKG_CASK_INSTALL=""  # winget doesn't distinguish
    PKG_UPDATE="winget source update"
    PKG_UPGRADE="winget upgrade --all --silent"
  elif command -v choco &>/dev/null; then
    PKG_MANAGER="choco"
    PKG_INSTALL="choco install -y"
    PKG_CASK_INSTALL=""
    PKG_UPDATE="choco upgrade -y"
    PKG_UPGRADE="choco upgrade all -y"
  else
    PKG_MANAGER="unknown"
    PKG_INSTALL="echo 'WARN: no package manager found — install manually:'"
    PKG_CASK_INSTALL=""
    PKG_UPDATE="true"
    PKG_UPGRADE="true"
  fi
fi

# ── Service Manager ─────────────────────────────────────────
if [[ "$CORTEX_OS" == "macos" ]]; then
  SERVICE_MANAGER="launchd"
  SERVICE_DIR="${HOME}/Library/LaunchAgents"
  SERVICE_EXT="plist"
  SERVICE_LOAD="launchctl load"
  SERVICE_UNLOAD="launchctl unload"
  SERVICE_START="launchctl start"
  SERVICE_STOP="launchctl stop"
  SERVICE_LIST="launchctl list"
elif [[ "$CORTEX_OS" == "linux" ]]; then
  SERVICE_MANAGER="systemd"
  SERVICE_DIR="${HOME}/.config/systemd/user"
  SERVICE_EXT="service"
  SERVICE_LOAD="systemctl --user daemon-reload && systemctl --user enable"
  SERVICE_UNLOAD="systemctl --user disable"
  SERVICE_START="systemctl --user start"
  SERVICE_STOP="systemctl --user stop"
  SERVICE_LIST="systemctl --user list-units --type=service"
  # System-level services (Docker, nginx) use system-wide systemd
  SYSTEM_SERVICE_DIR="/etc/systemd/system"
  SYSTEM_SERVICE_LOAD="sudo systemctl daemon-reload && sudo systemctl enable"
  SYSTEM_SERVICE_UNLOAD="sudo systemctl disable"
  SYSTEM_SERVICE_START="sudo systemctl start"
  SYSTEM_SERVICE_STOP="sudo systemctl stop"
elif [[ "$CORTEX_OS" == "windows" ]]; then
  SERVICE_MANAGER="windows-service"
  SERVICE_DIR="${APPDATA}/hermes-cortex/services"
  SERVICE_EXT="ps1"  # PowerShell scripts for scheduled tasks
  SERVICE_LOAD="powershell -File"
  SERVICE_UNLOAD="powershell -File"
  SERVICE_START="powershell -File"
  SERVICE_STOP="powershell -File"
  SERVICE_LIST="powershell Get-ScheduledTask -TaskPrefix 'Hermes'"
fi

# ── Path Conventions ────────────────────────────────────────
if [[ "$CORTEX_OS" == "macos" ]]; then
  :  # Use $HOME as-is
elif [[ "$CORTEX_OS" == "linux" ]]; then
  :  # Use $HOME as-is
elif [[ "$CORTEX_OS" == "windows" ]]; then
  # Convert to Windows paths where needed
  :  # $HOME maps to /c/Users/name in Git Bash
fi

# ── nginx Path ──────────────────────────────────────────────
# Uses : ${VAR:=default} pattern so env vars from ~/.hermes/hermes-cortex.env
# (sourced before os-config.sh) override the auto-detected defaults.
if [[ "$CORTEX_OS" == "macos" ]]; then
  if [[ "$(uname -m)" == "arm64" ]]; then
    : "${NGINX_CONFIG_DIR:=/opt/homebrew/etc/nginx/servers}"
    : "${NGINX_ROOT:=/opt/homebrew/etc/nginx}"
  else
    : "${NGINX_CONFIG_DIR:=/usr/local/etc/nginx/servers}"
    : "${NGINX_ROOT:=/usr/local/etc/nginx}"
  fi
elif [[ "$CORTEX_OS" == "linux" ]]; then
  : "${NGINX_CONFIG_DIR:=/etc/nginx/sites-enabled}"
  : "${NGINX_ROOT:=/etc/nginx}"
fi

# ── nginx Log & htpasswd Paths (OS-aware) ────────────────────
if [[ "$CORTEX_OS" == "macos" ]]; then
  if [[ "$(uname -m)" == "arm64" ]]; then
    : "${NGINX_LOG_DIR:=/opt/homebrew/var/log/nginx}"
  else
    : "${NGINX_LOG_DIR:=/usr/local/var/log/nginx}"
  fi
  : "${NGINX_HTPASSWD:=${NGINX_ROOT}/.htpasswd}"
elif [[ "$CORTEX_OS" == "linux" ]]; then
  : "${NGINX_LOG_DIR:=/var/log/nginx}"
  : "${NGINX_HTPASSWD:=${NGINX_ROOT}/.hermes-htpasswd}"
fi

# ── Path Substitution Helper ─────────────────────────────────
# Replaces __NGINX_CONFIG_DIR__, __NGINX_ROOT__, __NGINX_LOG_DIR__,
# __HTPASSWD_FILE__ placeholders in a config file with OS-appropriate paths.
subst_nginx_paths() {
  sed \
    -e "s|__NGINX_CONFIG_DIR__|${NGINX_CONFIG_DIR}|g" \
    -e "s|__NGINX_ROOT__|${NGINX_ROOT}|g" \
    -e "s|__NGINX_LOG_DIR__|${NGINX_LOG_DIR}|g" \
    -e "s|__HTPASSWD_FILE__|${NGINX_HTPASSWD}|g"
}

# ── Ollama Install Path ─────────────────────────────────────
if [[ "$CORTEX_OS" == "macos" ]]; then
  if [[ "$(uname -m)" == "arm64" ]]; then
    OLLAMA_BIN="/opt/homebrew/bin/ollama"
  else
    OLLAMA_BIN="/usr/local/bin/ollama"
  fi
  OLLAMA_SERVICE_NAME="com.ollama.serve"
elif [[ "$CORTEX_OS" == "linux" ]]; then
  OLLAMA_BIN="/usr/local/bin/ollama"
  OLLAMA_SERVICE_NAME="ollama"
elif [[ "$CORTEX_OS" == "windows" ]]; then
  OLLAMA_BIN="${LOCALAPPDATA}/Ollama/ollama.exe"
  OLLAMA_SERVICE_NAME="HermesOllama"
fi

# ── Summary ─────────────────────────────────────────────────
# Export for subprocesses
export CORTEX_OS CORTEX_PROFILE
export PKG_MANAGER PKG_INSTALL PKG_CASK_INSTALL
export SERVICE_MANAGER SERVICE_DIR SERVICE_EXT
export SERVICE_LOAD SERVICE_UNLOAD SERVICE_START SERVICE_STOP SERVICE_LIST
export NGINX_CONFIG_DIR NGINX_ROOT NGINX_LOG_DIR NGINX_HTPASSWD OLLAMA_BIN
