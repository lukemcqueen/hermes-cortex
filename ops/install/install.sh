#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# Hermes Cortex — Full System Installer
# https://github.com/fleet-operator/hermes-cortex
#
# One-line install:
#  curl -fsSL https://raw.githubusercontent.com/fleet-operator/hermes-cortex/main/install.sh | bash
#
# Or from a local clone:
#  git clone --depth 1 https://github.com/fleet-operator/hermes-cortex.git
#  cd hermes-cortex && bash install.sh
#
# Installs: Ollama · Bun · gbrain · Langfuse† · Cortex Dashboard† ·
#      nginx† · Brain directory structure · Hermes plugins ·
#      Web Cache · Offline Knowledge (kiwix ZIM) · Skills
# † Server profile only (CORTEX_PROFILE=server). Laptop profile
#  (CORTEX_PROFILE=laptop) skips Docker-dependent services.
#
# Platforms: macOS (native) · Linux (systemd) · Windows (scheduled tasks)
# Set CORTEX_OS to override auto-detection: darwin, linux, windows
# Launchd services · Cron jobs (via agent)
#
# Idempotent — safe to re-run. Skips already-installed steps.
# ─────────────────────────────────────────────────────────────
set -euo pipefail
IFS=$'\n\t'

# Read version from VERSION file (single source of truth)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd 2>/dev/null)" || SCRIPT_DIR=""
if [[ -n "$SCRIPT_DIR" && -f "${SCRIPT_DIR}/VERSION" ]]; then
 VERSION="$(cat "${SCRIPT_DIR}/VERSION")"
else
 VERSION="1.0.0" # fallback for remote/curl install
fi

# ── Locate repo root ─────────────────────────────────────────
# SCRIPT_DIR may be ops/install/ (local clone) or the tarball root (remote)
if [[ -n "$SCRIPT_DIR" && ( "$SCRIPT_DIR" == */ops/install || "$SCRIPT_DIR" == */hermes-cortex-main/ops/install ) ]]; then
 REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
elif [[ -n "$SCRIPT_DIR" ]]; then
 REPO_ROOT="$SCRIPT_DIR"
else
 REPO_ROOT=""
fi

export REPO_ROOT

# ── Path resolution helpers ─────────────────────────────────
# Maps old paths → new paths. All internal references use these.
_scripts() { echo "${REPO_ROOT}/ops/scripts"; }
_offline() { echo "${REPO_ROOT}/ops/offline"; }
_core_gov() { echo "${REPO_ROOT}/core/governance"; }
_deploy() { echo "${REPO_ROOT}/ops/install/deploy"; }
_dashboard() { echo "${REPO_ROOT}/ops/services/dashboard"; }

# ── Remote install detection ─────────────────────────────────
# If running from a curl pipe, SCRIPT_DIR will be empty or
# /dev/stdin and os-config.sh won't exist. In that case,
# download the repo tarball and extract to a temp directory.
REMOTE_CLEANUP=""
if [[ -z "$REPO_ROOT" || ! -f "$(_scripts)/install/os-config.sh" ]]; then
 if [[ ! -f "${REPO_ROOT:-/dev/null}/ops/scripts/install/os-config.sh" ]]; then
  printf "📡 Remote install detected — downloading hermes-cortex…\n\n"

  # Check required tools
  for cmd in curl tar mktemp; do
   if ! command -v "$cmd" &>/dev/null; then
    printf "\033[0;31m✗\033[0m Required tool not found: %s\n" "$cmd" >&2
    printf " Install it first, then re-run the installer.\n" >&2
    exit 1
   fi
  done

  REMOTE_CLEANUP=$(mktemp -d)
  REPO_URL="https://github.com/fleet-operator/hermes-cortex/archive/refs/heads/main.tar.gz"

  printf " Downloading %s …\n" "$REPO_URL"
  curl -fsSL "$REPO_URL" | tar -xz -C "$REMOTE_CLEANUP" 2>/dev/null || {
   printf "\033[0;31m✗\033[0m Download failed. Check your internet connection.\n" >&2
   rm -rf "$REMOTE_CLEANUP"
   exit 1
  }

  SCRIPT_DIR="${REMOTE_CLEANUP}/hermes-cortex-main"
  printf "\033[0;32m✓\033[0m Downloaded and extracted to temp directory\n\n"

  # Cleanup is handled by the existing EXIT trap below
 fi
fi

# ── Colors ──────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; MAGENTA='\033[0;35m'; CYAN='\033[0;36m'
BOLD='\033[1m'; RESET='\033[0m'

# ── Check mode ──────────────────────────────────────────────
# If --check is passed, run prerequisites check only and exit
if [[ "${1:-}" == "--check" ]]; then
 source "$(_scripts)/install/os-config.sh" 2>/dev/null || true
 echo ""
 echo " ${BOLD}Hermes Cortex — Prerequisites Check${RESET}"
 echo ""

 # Python — prefer 3.12+ (macOS ships 3.9 which breaks PEP 604)
 PYTHON=$(command -v python3.12 || command -v python3 || command -v python || echo "")
 if [[ -n "$PYTHON" ]]; then
  VER=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
  echo " ${GREEN}✓${RESET} Python ${VER} at ${PYTHON}"
 else
  echo " ${RED}✗${RESET} Python 3 not found"
 fi

 # Git
 if command -v git &>/dev/null; then
  echo " ${GREEN}✓${RESET} Git: $(git --version 2>&1)"
 else
  echo " ${RED}✗${RESET} Git not found"
 fi

 # Ollama
 if command -v ollama &>/dev/null; then
  echo " ${GREEN}✓${RESET} Ollama binary found"
  if curl -sf http://localhost:11434/api/tags &>/dev/null; then
   echo " ${GREEN}✓${RESET} Ollama server running"
   if curl -sf http://localhost:11434/api/tags | grep -q "nomic-embed-text:v1.5"; then
    echo " ${GREEN}✓${RESET} nomic-embed-text:v1.5 model loaded"
   else
    echo " ${YELLOW}⚠${RESET} nomic-embed-text:v1.5 not pulled"
   fi
  else
   echo " ${YELLOW}⚠${RESET} Ollama server not running"
  fi
 else
  echo " ${YELLOW}⚠${RESET} Ollama not installed"
 fi

 # Docker (needed for server profile)
 if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
  echo " ${GREEN}✓${RESET} Docker running"
 else
  echo " ${YELLOW}⚠${RESET} Docker not available (needed for server profile)"
 fi

 # ~/.local/bin
 if echo "$PATH" | tr ':' '\n' | grep -q "${HOME}/.local/bin"; then
  echo " ${GREEN}✓${RESET} ~/.local/bin in PATH"
 else
  echo " ${YELLOW}⚠${RESET} ~/.local/bin not in PATH"
 fi

 echo ""
 echo " Run without --check to install: bash install.sh"
 echo ""
 exit 0
fi
STEP=0

info() { printf "${GREEN}✓${RESET} %s\n" "$1"; }
warn() { printf "${YELLOW}⚠${RESET} %s\n" "$1" >&2; }
error() { printf "${RED}✗${RESET} %s\n" "$1"; }
header() {
 printf "\n${CYAN}${BOLD}━━━ %s ━━━${RESET}\n" "$1"
}
step() {
 STEP=$((STEP+1))
 printf "\n${MAGENTA}${BOLD}[%s/%s]${RESET} ${BOLD}%s${RESET}\n" "$STEP" "${TOTAL_STEPS:-10}" "$1"
}
ok()  { printf " ${GREEN}done${RESET}\n"; }
skip() { printf " ${YELLOW}skip${RESET} — %s\n" "$1"; }

# ── Abort handler ───────────────────────────────────────────
trap 'printf "\n${RED}Installation aborted at step $STEP${RESET}\n"; rm -rf "${REMOTE_CLEANUP}"' EXIT

# ── Source OS Abstraction Layer ─────────────────────────────
source "$(_scripts)/install/os-config.sh"
source "$(_scripts)/install/service-writer.sh"

# ── Python version probe ────────────────────────────────────
# HERMES NOW REQUIRES PYTHON 3.12+. Earlier versions (3.9, 3.10, 3.11)
# lack PEP 604 union syntax support and/or sqlite3 extension support.
# macOS ships 3.9.6 — its sqlite3 can't enable_load_extension (breaks sqlite-vec).
find_best_python() {
 local candidates="python3 python3.12 $(command -v python3.13 python3.14 2>/dev/null | tr '\n' ' ')"
 local found=""
 for candidate in $candidates; do
  if command -v "$candidate" &>/dev/null; then
   local ver
   ver=$("$candidate" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null)
   local major="${ver%.*}"
   local minor="${ver#*.}"
   if [[ "$major" -ge 3 && "$minor" -ge 12 ]] 2>/dev/null; then
    # Verify sqlite3 extension support
    if "$candidate" -c 'import sqlite3; sqlite3.connect(":memory:").enable_load_extension(True)' 2>/dev/null; then
     found="$candidate"
     break
    fi
   fi
  fi
 done
 if [[ -z "$found" ]]; then
  # Fallback: use whatever python3 is available, warn
  found="python3"
  warn "No Python 3.12+ with sqlite3 extension support found — web_cache may fail"
  warn "Install with: brew install python@3.12 # 3.12 is the minimum for all Hermes projects"
 fi
 echo "$found"
}

# ─────────────────────────────────────────────────────────────
# 0. System Verification Check
# ─────────────────────────────────────────────────────────────
header "SYSTEM VERIFICATION"
CHECK_SCRIPT="$(_scripts)/check-system.sh"

if [[ -f "$CHECK_SCRIPT" ]]; then
 bash "$CHECK_SCRIPT" || {
  error "System verification failed. Review the issues above."
  error "Fix them and re-run install.sh"
  exit 1
 }
 printf "\n"
else
 warn "ops/scripts/install/check-system.sh not found — skipping verification"
 printf "\n"
fi

# ─────────────────────────────────────────────────────────────
# Prerequisites & Configuration
# ─────────────────────────────────────────────────────────────
header "PREREQUISITES"

# Profile: 'core' = minimum (default), 'laptop' = no Docker, 'server' = full stack
: "${CORTEX_PROFILE:=core}"

if [[ "$CORTEX_PROFILE" == "core" ]]; then
 info "Profile: core (minimal — loop-governance, Ollama, brain, skills)"
elif [[ "$CORTEX_PROFILE" == "laptop" ]]; then
 info "Profile: laptop (lean — no Docker services)"
elif [[ "$CORTEX_PROFILE" == "server" ]]; then
 info "Profile: server (full stack — Langfuse, Dashboard, nginx)"
else
 info "Profile: ${CORTEX_PROFILE}"
fi

# User info
CORTEX_USER="${CORTEX_USER:-$USER}"
CORTEX_HOME="${CORTEX_HOME:-$HOME}"
BRAIN_DIR="${CORTEX_HOME}/brain"
CORTEX_DEPLOY_HOME="${CORTEX_DEPLOY_HOME:-${CORTEX_HOME}/.hermes-cortex}"

# SCRIPT_DIR is already set at the top of the script

# Brain sources — default is 'default' + optionally more
if [[ -z "${CORTEX_SOURCES:-}" ]]; then
 # Single-user default
 CORTEX_SOURCES="default"
 info "Brain sources: ${CORTEX_SOURCES}"
 info " To add more sources (e.g. for multi-person), set CORTEX_SOURCES before running:"
 info "  export CORTEX_SOURCES='luke,amy,shared,default'"
fi

IFS=',' read -ra SOURCES <<< "$CORTEX_SOURCES"
TOTAL_STEPS=27
STEP=0

# Ensure Hermes is installed
if ! command -v hermes &>/dev/null && [[ ! -x "${CORTEX_DEPLOY_HOME}/hermes-agent/venv/bin/hermes" ]]; then
 warn "Hermes Agent not found. Install it first: https://hermes-agent.nousresearch.com/docs"
 warn "The script will install everything else, but you'll need Hermes for the final agent-side setup."
fi

# Ensure package manager
if [[ "$CORTEX_OS" == "macos" ]] && ! command -v brew &>/dev/null; then
 step "Installing Homebrew…"
 curl -fsSL --retry 3 --retry-delay 5 https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh -o /tmp/homebrew-install.sh
 /bin/bash /tmp/homebrew-install.sh
 rm -f /tmp/homebrew-install.sh
 if [[ "$(uname -m)" == "arm64" ]]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
 else
  eval "$(/usr/local/bin/brew shellenv)"
 fi
 ok
fi

# ─────────────────────────────────────────────────────────────
# 1. Ollama — local LLM server for embeddings
# ─────────────────────────────────────────────────────────────
step "Installing Ollama (local LLM server)"
bash "$(_scripts)/install-ollama.sh" install
ok

# Configure Ollama service
step "Configuring Ollama service"
bash "$(_scripts)/install-ollama.sh" service
ok

# Wait for Ollama to be ready
step "Waiting for Ollama to respond…"
bash "$(_scripts)/install-ollama.sh" wait
ok

# Pull embedding model
step "Pulling embedding model (nomic-embed-text:v1.5)"
bash "$(_scripts)/install-ollama.sh" embed nomic-embed-text:v1.5
ok

# ── Ollama security check ──────────────────────────────────
step "Checking Ollama network binding"
# Check if Ollama is accidentally exposed on 0.0.0.0
if command -v ss &>/dev/null; then
 if ss -tlnp 2>/dev/null | grep -q "0.0.0.0:11434"; then
  warn "⚠ OLLAMA IS EXPOSED TO YOUR NETWORK (0.0.0.0:11434)!"
  warn " This means any device on your LAN can access your LLM server."
  warn " Fixing by setting OLLAMA_HOST=127.0.0.1 in the service config…"
  # Fix: stop and restart with localhost-only binding
  if [[ "$CORTEX_OS" == "macos" ]]; then
   launchctl unload "$HOME/Library/LaunchAgents/${OLLAMA_SERVICE_NAME:-com.ollama.serve}.plist" 2>/dev/null || true
   write_service "${OLLAMA_SERVICE_NAME:-com.ollama.serve}" \
    "$(command -v ollama) serve" \
    "$HOME" \
    "PATH=/usr/local/bin:/usr/bin:/bin HOME=${HOME} OLLAMA_HOST=127.0.0.1"
   launchctl load "$HOME/Library/LaunchAgents/${OLLAMA_SERVICE_NAME:-com.ollama.serve}.plist" 2>/dev/null || true
  elif [[ "$CORTEX_OS" == "linux" ]]; then
   mkdir -p "$HOME/.config/systemd/user"
   cat > "$HOME/.config/systemd/user/ollama.service" <<OLLAMDEOF
[Unit]
Description=Ollama LLM Server (restricted to localhost)
After=network-online.target

[Service]
ExecStart=$(command -v ollama) serve
Environment=OLLAMA_HOST=127.0.0.1
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
OLLAMDEOF
   systemctl --user daemon-reload 2>/dev/null || true
   systemctl --user restart ollama 2>/dev/null || true
  fi
  printf "\n"
  warn "${RED}${BOLD}‼ SECURITY FIX APPLIED ‼${RESET}"
  warn "${YELLOW}OLLAMA WAS EXPOSED TO YOUR NETWORK! We've fixed it by restarting"
  warn "with OLLAMA_HOST=127.0.0.1 so it only listens on localhost."
  warn "Read more in docs/SECURITY.md${RESET}"
  printf "\n"
 else
  info "Ollama is bound to localhost only — secure"
 fi
elif command -v lsof &>/dev/null; then
 if lsof -iTCP:11434 -sTCP:LISTEN -P -n 2>/dev/null | grep -qE "\*:11434|0\.0\.0\.0"; then
  warn "⚠ OLLAMA IS EXPOSED TO YOUR NETWORK! Fixing…"
  # Same fix logic as above
  if [[ "$CORTEX_OS" == "macos" ]]; then
   launchctl unload "$HOME/Library/LaunchAgents/${OLLAMA_SERVICE_NAME:-com.ollama.serve}.plist" 2>/dev/null || true
   write_service "${OLLAMA_SERVICE_NAME:-com.ollama.serve}" \
    "$(command -v ollama) serve" \
    "$HOME" \
    "PATH=/usr/local/bin:/usr/bin:/bin HOME=${HOME} OLLAMA_HOST=127.0.0.1"
   launchctl load "$HOME/Library/LaunchAgents/${OLLAMA_SERVICE_NAME:-com.ollama.serve}.plist" 2>/dev/null || true
  fi
  printf "\n"
  warn "${RED}${BOLD}‼ SECURITY FIX APPLIED ‼${RESET}"
  warn "${YELLOW}OLLAMA WAS EXPOSED TO YOUR NETWORK! We've fixed it by restarting"
  warn "with OLLAMA_HOST=127.0.0.1 so it only listens on localhost."
  warn "Read more in docs/SECURITY.md${RESET}"
  printf "\n"
 else
  info "Ollama is bound to localhost only — secure"
 fi
else
 # Fallback: try curl to 0.0.0.0 to detect exposure
 if curl -s --connect-timeout 2 http://0.0.0.0:11434/api/tags >/dev/null 2>&1; then
  warn "⚠ OLLAMA MAY BE EXPOSED TO YOUR NETWORK!"
  warn " Could reach Ollama via 0.0.0.0. Ensure OLLAMA_HOST=127.0.0.1 is set."
  warn " Check docs/SECURITY.md for details."
 else
  info "Ollama does not appear to be exposed — secure"
 fi
fi
ok

# ─────────────────────────────────────────────────────────────
# 2. Bun — JavaScript runtime for gbrain
# ─────────────────────────────────────────────────────────────
step "Installing Bun"
if command -v bun &>/dev/null || [[ -x "${CORTEX_HOME}/.bun/bin/bun" ]]; then
 skip "already installed — $(bun --version 2>/dev/null || echo 'bun found')"
else
 curl -fsSL --retry 3 --retry-delay 5 https://bun.sh/install -o /tmp/bun-install.sh
 bash /tmp/bun-install.sh
 rm -f /tmp/bun-install.sh
 # Ensure bun is in PATH for subsequent steps
 export PATH="${CORTEX_HOME}/.bun/bin:$PATH"
 ok
fi

# Ensure bun is in PATH
if ! command -v bun &>/dev/null; then
 export PATH="${CORTEX_HOME}/.bun/bin:$PATH"
fi

# ─────────────────────────────────────────────────────────────
# 3. gbrain — Knowledge Brain
# ─────────────────────────────────────────────────────────────
step "Installing gbrain (knowledge brain)"
if command -v gbrain &>/dev/null || [[ -x "${CORTEX_HOME}/.bun/bin/gbrain" ]]; then
 skip "already installed — $(gbrain --version 2>/dev/null || echo 'gbrain found')"
else
 # NOTE: plain 'gbrain' on npm is a different package (stormcolor GPU JS, no CLI).
 # garrytan/gbrain is the actual knowledge brain tool with 20k+ stars.
 bun install -g github:garrytan/gbrain
 ok
fi

# Ensure gbrain is callable
GBRAIN_CMD="${CORTEX_HOME}/.bun/bin/gbrain"
if ! command -v gbrain &>/dev/null; then
 alias gbrain="$GBRAIN_CMD" 2>/dev/null || true
fi

# ── gbrain database ──────────────────────────────────────────────
# Init gbrain (Postgres + pgvector — production default)
# Requires Postgres 17 with pgvector 0.8+ running locally.
# See docs/gbrain-postgres-migration.md for detailed setup.
step "Initializing gbrain with Postgres + pgvector"
if "$GBRAIN_CMD" doctor --json --fast 2>/dev/null | grep -q '"connection":'; then
 skip "brain already initialized"
else
 # Try Postgres on common ports (5432, 5433, 15432)
 for pgport in 5433 5432 15432; do
  if pg_isready -p "$pgport" -q 2>/dev/null; then
   DB_URL="postgresql://${USER:-luke}@localhost:${pgport}/gbrain"
   "$GBRAIN_CMD" init --url "$DB_URL" --embedding-model ollama:nomic-embed-text:v1.5 --yes 2>/dev/null && \
    { ok "gbrain initialized on Postgres port ${pgport}"; break; }
  fi
 done || {
  warn "No Postgres with gbrain database found — install Postgres 17 + pgvector and run 'gbrain init --url postgresql://...'"
 }
fi

# Apply any pending migrations
step "Applying pending gbrain migrations"
if "$GBRAIN_CMD" doctor --json --fast 2>/dev/null | grep -q '"pending_count":0'; then
 skip "no pending migrations"
else
 "$GBRAIN_CMD" apply-migrations --yes 2>/dev/null || true
 ok
fi

# ── Ensure bun + gbrain are in PATH via ~/.local/bin ───────
step "Adding bun/gbrain symlinks to ~/.local/bin/"
LOCAL_BIN="${CORTEX_HOME}/.local/bin"
BUN_BIN="${CORTEX_HOME}/.bun/bin"
if [[ -d "$BUN_BIN" ]]; then
 mkdir -p "$LOCAL_BIN"
 for _tool in bun gbrain; do
  if [[ -f "${BUN_BIN}/${_tool}" ]] && [[ ! -f "${LOCAL_BIN}/${_tool}" ]]; then
   ln -sf "${BUN_BIN}/${_tool}" "${LOCAL_BIN}/${_tool}" 2>/dev/null || true
   info " Linked ${_tool} → ${LOCAL_BIN}/${_tool}"
  fi
 done
 # Ensure ~/.local/bin is in PATH for the rest of the script
 export PATH="${LOCAL_BIN}:$PATH"
fi
ok

# ─────────────────────────────────────────────────────────────
# 4. Brain Directory Structure
# ─────────────────────────────────────────────────────────────
step "Creating brain directory structure"

# Default MECE structure for each source
MECE_DIRS="archive civic companies concepts conversations deals hiring household ideas inbox media meetings org people personal programs projects prompts sources writing"

for source in "${SOURCES[@]}"; do
 source_dir="${BRAIN_DIR}/${source}"
 if [[ -d "$source_dir" ]]; then
  skip "${source} — already exists"
 else
  mkdir -p "$source_dir"
  for dir in $MECE_DIRS; do
   mkdir -p "${source_dir}/${dir}" 2>/dev/null || true
  done

  # Create index.md with schema docs
  if [[ ! -f "${source_dir}/index.md" ]]; then
   cat > "${source_dir}/index.md" <<INDEXEOF
# Brain Source: ${source}

## Schema

| Directory | Purpose |
|-----------|---------|
| archive/ | Old / resolved items |
| civic/ | Civic, community, volunteering |
| companies/ | Companies, vendors, orgs |
| concepts/ | Ideas, frameworks, mental models |
| conversations/ | Chat transcripts, meeting notes |
| deals/ | Deals, contracts, agreements |
| hiring/ | Hiring, candidates, interviews |
| household/ | Home, family, chores, logistics |
| ideas/ | Raw ideas, brainstorming |
| inbox/ | Capture zone — unprocessed notes |
| media/ | Books, articles, podcasts |
| meetings/ | Meeting notes, agendas |
| org/ | Organization structure, roles |
| people/ | People, contacts, relationships |
| personal/ | Personal notes, journal |
| programs/ | Programs, courses, training |
| projects/ | Active projects, tasks |
| prompts/ | Saved prompts, templates |
| sources/ | Reference material, links |
| writing/ | Long-form writing, drafts |

## Source Type

- **federated:** \`true\` → auto-searched on every query
- **federated:** \`false\` → searched only with \`--source ${source}\`

---

*Created by Hermes Cortex installer v${VERSION}*
INDEXEOF
  fi
  info " Created ${source_dir}/"
  # Init git repo — gbrain requires git for each brain source
  git -C "${source_dir}" init 2>/dev/null || true
  git -C "${source_dir}" add -A 2>/dev/null || true
  git -C "${source_dir}" commit -m "init: ${source} brain source" 2>/dev/null || true
 fi
done

# Create lessons directory for bug-fix lesson database
mkdir -p "${BRAIN_DIR}/lessons"
info " Created ${BRAIN_DIR}/lessons/"

# ─────────────────────────────────────────────────────────────
# 5. Brain .gitignore — Protect memory and secrets per source
# ─────────────────────────────────────────────────────────────
step "Adding .gitignore to brain sources"
GITIGNORE_TEMPLATE="${SCRIPT_DIR}/docs/templates/gitignore.brain"
GITIGNORE_SRC=""
if [[ -f "$GITIGNORE_TEMPLATE" ]]; then
 GITIGNORE_SRC="$GITIGNORE_TEMPLATE"
fi
for source in "${SOURCES[@]}"; do
 source_dir="${BRAIN_DIR}/${source}"
 if [[ ! -d "$source_dir" ]]; then
  continue
 fi
 if [[ -f "${source_dir}/.gitignore" ]]; then
  skip "${source} — .gitignore already exists"
 elif [[ -n "$GITIGNORE_SRC" ]]; then
  cp "$GITIGNORE_SRC" "${source_dir}/.gitignore"
  info " Added .gitignore to ${source}/"
 else
  # Write inline fallback
  cat > "${source_dir}/.gitignore" <<GITEOF
# Hermes Cortex brain source — never commit per-instance memory or secrets
MEMORY.md
USER.md
.env
.env.*
*.pem
*.key
*.cert
.DS_Store
Thumbs.db
GITEOF
  info " Created inline .gitignore for ${source}/"
 fi
done
ok

# ─────────────────────────────────────────────────────────────
# 6. gbrain Sources & Sync Daemon
# ─────────────────────────────────────────────────────────────
step "Configuring gbrain sources"

for source in "${SOURCES[@]}"; do
 source_dir="${BRAIN_DIR}/${source}"
 # The 'default' gbrain source is special (backs pre-v0.17 brain) and cannot be
 # removed or have --path set. Skip it here; non-default sources get --path.
 if [[ "${source}" == "default" ]]; then
  skip "'default' gbrain source is built-in (cannot set --path)"
  continue
 fi
 # Check if source already exists in gbrain
 if "$GBRAIN_CMD" sources list 2>/dev/null | grep -q "${source}"; then
  skip "gbrain source '${source}' already configured"
 else
  # Init git repo in source dir if not already
  if [[ ! -d "${source_dir}/.git" ]]; then
   git -C "${source_dir}" init 2>/dev/null || true
   git -C "${source_dir}" add -A 2>/dev/null || true
   git -C "${source_dir}" commit -m "initial brain state" 2>/dev/null || true
  fi
  "$GBRAIN_CMD" sources add "${source}" --path "${source_dir}" --name "${source}" 2>/dev/null || \
   warn "Failed to add source '${source}' — may need gbrain re-init"
  info " Added gbrain source: ${source}"
 fi
done

# Federate 'shared' if it exists
if "$GBRAIN_CMD" sources list 2>/dev/null | grep -q "shared"; then
 "$GBRAIN_CMD" sources federate shared 2>/dev/null || true
 info " Federated 'shared' source (auto-searched)"
fi

# Create gbrain sync daemon
step "Creating gbrain sync-watch daemon ($SERVICE_MANAGER)"
bash "$(_scripts)/install-gbrain-sync.sh"
ok

# ── Check for duplicate 'default' gbrain source ──────────
step "Checking for duplicate gbrain sources"
DUPLICATE_FOUND=false
# gbrain sources list has leading spaces — don't anchor at column 0
if "$GBRAIN_CMD" sources list 2>/dev/null | grep -q "^ default[[:space:]].*~/brain/default"; then
 # Check if there's also a 'mybrain' or manual default pointing elsewhere
 for dup_source in default mybrain main; do
  count=$("$GBRAIN_CMD" sources list 2>/dev/null | grep -c "^ ${dup_source}[[:space:]]" || true)
  if [[ "$count" -gt 1 ]]; then
   warn "Duplicate gbrain source '${dup_source}' detected!"
   warn " The 'default' source is built-in and manages ~/brain/default/ automatically."
   warn " Remove the duplicate with: gbrain sources remove <duplicate-name>"
   DUPLICATE_FOUND=true
  fi
 done
 # Also check if user manually added ~/brain/default as a named source
 if "$GBRAIN_CMD" sources list 2>/dev/null | grep -q "~/brain/default"; then
  source_count=$("$GBRAIN_CMD" sources list 2>/dev/null | grep -c "^ default[[:space:]]" || true)
  if [[ "$source_count" -gt 1 ]]; then
   warn "Multiple sources reference ~/brain/default/. The 'default' gbrain source"
   warn "already manages this path. Remove extra entries with: gbrain sources list"
   DUPLICATE_FOUND=true
  fi
 fi
fi
if [[ "$DUPLICATE_FOUND" == "false" ]]; then
 info "No duplicate sources detected"
fi
ok

# ─────────────────────────────────────────────────────────────
# 7. Hermes gbrain Plugin (/brain slash command)
# ─────────────────────────────────────────────────────────────
step "Installing gbrain Hermes plugin (/brain command)"

PLUGIN_DIR="${CORTEX_DEPLOY_HOME}/plugins/gbrain-command"
if [[ -f "${PLUGIN_DIR}/__init__.py" ]]; then
 skip "plugin already installed"
else
 mkdir -p "$PLUGIN_DIR"

 # plugin.yaml
 cat > "${PLUGIN_DIR}/plugin.yaml" <<YAMLEOF
name: gbrain-command
version: 1.1.0
description: "Query your gbrain knowledge brain. Usage: /brain [source] <query>"
author: ${CORTEX_USER}
hooks: []
YAMLEOF

 # Use python3 to generate __init__.py (avoids bash/Python ${…} conflicts in heredocs)
 python3 << 'PYSCRIPT'
import os, json, shlex

cortex_home = os.environ.get('CORTEX_HOME', os.path.expanduser('~'))
hermes_home = os.environ.get('HERMES_HOME', os.path.join(cortex_home, '.hermes-cortex'))
sources_str = os.environ.get('CORTEX_SOURCES', 'default')
sources = [s.strip() for s in sources_str.split(',') if s.strip()]

plugin_dir = os.path.join(hermes_home, 'plugins', 'gbrain-command')
os.makedirs(plugin_dir, exist_ok=True)

bun_path = os.path.join(cortex_home, '.bun/bin')
gbrain_bin = f'{bun_path}/bun {bun_path}/gbrain'

# Build sources dictionary
sources_dict = {}
for s in sources:
  sources_dict[s] = f'--source {s}'

default_sources_parts = [f'--source {s}' for s in sources if s != 'default']
default_source = ' '.join(default_sources_parts)

# Help text
help_parts = []
for s in sources:
  if s != 'default':
    brain_name = f"{s}'s brain"
    help_parts.append(f' /brain {s} <query>     {brain_name} only\\n')
source_help = ''.join(help_parts)

lines = []
lines.append('"""')
lines.append('gbrain slash command plugin for Hermes Agent.')
lines.append('')
lines.append('Provides /brain <query> — queries gbrain knowledge base.')
lines.append('Dynamically generated by hermes-cortex installer.')
lines.append('"""')
lines.append('')
lines.append('from __future__ import annotations')
lines.append('')
lines.append('import asyncio')
lines.append('import logging')
lines.append('import shlex')
lines.append('from typing import Optional')
lines.append('')
lines.append('logger = logging.getLogger(__name__)')
lines.append('')
lines.append(f'_GBRAIN_BIN = {shlex.quote(gbrain_bin)}')
lines.append('')
lines.append('# Source presets')
lines.append('_SOURCES = {')
for s in sources:
  lines.append(f'  {shlex.quote(s)}: {shlex.quote(f"--source {s}")},')
lines.append('}')
lines.append('')
lines.append('_DESCRIPTIONS = {')
for s in sources:
  brain_name = f"{s}'s brain"
  lines.append(f'  {shlex.quote(s)}: {shlex.quote(brain_name)},')
lines.append('}')
lines.append('')
lines.append(f'_DEFAULT_SOURCE = {shlex.quote(default_source)}')
lines.append('')
help_text = f"""/brain — Search your gbrain knowledge base

**Usage:**
 /brain <query>        All sources (default)
{source_help}
**Examples:**
 /brain what's on my mind?
 /brain --help        Show this help

Results from local gbrain (Postgres + pgvector) at postgresql://localhost:5433/gbrain.
"""
lines.append('_HELP_TEXT = ' + repr(help_text))
lines.append('')
lines.append('')
lines.append('async def _run_gbrain_query(query: str, source_flags: str) -> str:')
lines.append('  """Run gbrain query and return formatted results."""')
lines.append('  import shlex')
lines.append('  args = [str(_GBRAIN_BIN), "query"] + shlex.split(source_flags) + [query]')
lines.append('  logger.debug("Running gbrain query: %s", args)')
lines.append('')
lines.append('  proc = await asyncio.create_subprocess_exec(')
lines.append('    *args,')
lines.append('    stdout=asyncio.subprocess.PIPE,')
lines.append('    stderr=asyncio.subprocess.PIPE,')
lines.append('  )')
lines.append('')
lines.append('  try:')
lines.append('    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)')
lines.append('  except asyncio.TimeoutError:')
lines.append('    proc.kill()')
lines.append('    return "\u23f1\ufe0f Brain query timed out after 30s."')
lines.append('')
lines.append('  output = (stdout.decode("utf-8", errors="replace") or "").strip()')
lines.append('  err = (stderr.decode("utf-8", errors="replace") or "").strip()')
lines.append('  # Merge stderr into stdout (replaces shell 2>&1)')
lines.append('  if err:')
lines.append('    output = (output + "\\n" + err) if output else err')
lines.append('')
lines.append('  if proc.returncode != 0:')
lines.append('    return f"\u274c Brain query failed (exit {proc.returncode}):\\\n{err or output}"')
lines.append('')
lines.append('  if not output:')
lines.append('    return "\U0001f914 No results found in your brain."')
lines.append('')
lines.append('  # Format nicely')
lines.append('  lines = output.split("\\n")')
lines.append('  clean_lines = [l for l in lines if not l.startswith("[") and not l.startswith(" ")]')
lines.append('  if not clean_lines:')
lines.append('    clean_lines = lines')
lines.append('  formatted = "\\n".join(clean_lines[:30])')
lines.append('')
lines.append('  return f"\U0001f9e0 **Results:**\\n\\n{formatted}"')
lines.append('')
lines.append('')
lines.append('def _run_gbrain_query_sync(query: str, source_flags: str) -> str:')
lines.append('  try:')
lines.append('    return asyncio.run(_run_gbrain_query(query, source_flags))')
lines.append('  except RuntimeError:')
lines.append('    loop = asyncio.new_event_loop()')
lines.append('    try:')
lines.append('      return loop.run_until_complete(_run_gbrain_query(query, source_flags))')
lines.append('    finally:')
lines.append('      loop.close()')
lines.append('')
lines.append('')
lines.append('def _parse_source(args: str) -> tuple[str, str]:')
lines.append('  """Parse source prefix from args. Returns (query, source_flags)."""')
lines.append('  for source_key in _SOURCES:')
lines.append('    if args.lower().startswith(f"{source_key} "):')
lines.append('      query = args[len(source_key):].strip()')
lines.append('      return query, _SOURCES[source_key]')
lines.append('')
lines.append('  return args, _DEFAULT_SOURCE')
lines.append('')
lines.append('')
lines.append('def _handle_slash(raw_args: str) -> Optional[str]:')
lines.append('  """Handle /brain command."""')
lines.append('  args = raw_args.strip()')
lines.append('')
lines.append('  if not args or args in {"--help", "-h", "help"}:')
lines.append('    return _HELP_TEXT')
lines.append('')
lines.append('  query, source_flags = _parse_source(args)')
lines.append('')
lines.append('  if not query:')
lines.append('    return "Please provide a query. Usage: `/brain <query>`"')
lines.append('')
lines.append('  return _run_gbrain_query_sync(query, source_flags)')
lines.append('')
lines.append('')
lines.append('def register(ctx) -> None:')
lines.append('  """Register /brain slash command."""')
lines.append('  ctx.register_command(')
lines.append('    "brain",')
lines.append('    handler=_handle_slash,')
lines.append('    description="Query your gbrain ([source] <query>)",')
lines.append('    args_hint="[source] <query>",')
lines.append('  )')
lines.append('  logger.info("Registered /brain slash command \u2014 Hermes Cortex")')

with open(os.path.join(plugin_dir, '__init__.py'), 'w', encoding='utf-8') as f:
  f.write('\n'.join(lines))

print(f' Wrote {len(lines)} lines to {plugin_dir}/__init__.py')
PYSCRIPT
 ok
 info "Plugin written to ${PLUGIN_DIR}/"
 info " Run /reset or /new in Hermes to activate"
 ok
fi

# ─────────────────────────────────────────────────────────────
# 8. Hermes Scripts (heartbeat, memory-to-brain)
# ─────────────────────────────────────────────────────────────
step "Installing Hermes utility scripts"
SCRIPTS_DIR="${CORTEX_DEPLOY_HOME}/scripts"
mkdir -p "$SCRIPTS_DIR"

# ── heartbeat.py ──────────────────────────────────────────
HEARTBEAT_PATH="${SCRIPTS_DIR}/heartbeat.py"
if [[ -f "$HEARTBEAT_PATH" ]]; then
 # Check if repo version differs — update if so
 if [[ -f "$(_scripts)/heartbeat.py" ]]; then
  if ! cmp -s "$HEARTBEAT_PATH" "$(_scripts)/heartbeat.py"; then
   cp "$(_scripts)/heartbeat.py" "$HEARTBEAT_PATH"
   chmod +x "$HEARTBEAT_PATH"
   info " Updated heartbeat.py (repo version differs)"
  else
   skip "heartbeat.py up to date"
  fi
 else
  skip "heartbeat.py already exists (no repo copy to compare)"
 fi
else
 # Prefer repo copy to prevent divergence
 if [[ -f "$(_scripts)/heartbeat.py" ]]; then
  cp "$(_scripts)/heartbeat.py" "$HEARTBEAT_PATH"
  chmod +x "$HEARTBEAT_PATH"
  ok
  info " Copied heartbeat.py from repo"
 else
 cat > "$HEARTBEAT_PATH" <<'HEARTBEAT'
#!/usr/bin/env python3
"""heartbeat.py — System health watchdog for Hermes/gbrain stack.

Checks critical daemons and services:
 - Ollama (LLM server)
 - gbrain sync daemon
 - gbrain source health (flagged "never synced" / "0 pages")
 - Hermes gateway
 - Memory-to-brain sync freshness
 - Disk space

Outputs a concise health report. Designed for cron integration:
 - Non-empty stdout on FAILURE → cron delivers alert
 - Empty stdout when healthy → silent (watchdog pattern)
 - Use --report to force output regardless of health
"""
import json, os, subprocess, sys, re
from datetime import datetime, timedelta
from pathlib import Path

HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes-cortex"))
BRAIN_SHARED = Path.home() / "brain" / "shared"
NOW = datetime.now()


def check_launchd(job_label):
  try:
    result = subprocess.run(["launchctl", "list", job_label],
                capture_output=True, text=True, timeout=10)
    if result.returncode != 0:
      return {"status": "DOWN", "detail": f"launchctl list failed: {result.stderr.strip()}"}
    stdout = result.stdout.strip()
    pid_match = re.search(r'"PID"\s*=\s*(\d+);', stdout)
    exit_match = re.search(r'"LastExitStatus"\s*=\s*(\d+);', stdout)
    if pid_match:
      pid = pid_match.group(1)
      exit_code = int(exit_match.group(1)) if exit_match else 0
      if exit_code != 0:
        return {"status": "DEGRADED", "detail": f"Running (PID {pid}) but last exit was {exit_code}"}
      return {"status": "UP", "detail": f"PID {pid}"}
    parts = stdout.split("\t")
    if len(parts) >= 2:
      pid, exit_code = parts[0], parts[1]
      if pid == "-":
        return {"status": "DOWN", "detail": f"No PID (exit code: {exit_code})"}
      return {"status": "UP", "detail": f"PID {pid}"}
    return {"status": "ERROR", "detail": f"Unrecognized output: {stdout[:200]}"}
  except Exception as e:
    return {"status": "ERROR", "detail": str(e)}


def check_systemd(unit_name):
  """Check a systemd user service status — for Linux hosts."""
  try:
    result = subprocess.run(["systemctl", "--user", "is-active", unit_name],
                capture_output=True, text=True, timeout=10)
    status = result.stdout.strip()
    if status == "active":
      return {"status": "UP", "detail": unit_name}
    elif status in ("inactive", "dead", "failed"):
      return {"status": "DOWN", "detail": f"Unit {unit_name} is {status}"}
    return {"status": "DEGRADED", "detail": f"Unit {unit_name}: {status}"}
  except FileNotFoundError:
    return {"status": "ERROR", "detail": "systemctl not found — not a systemd system"}
  except Exception as e:
    return {"status": "ERROR", "detail": str(e)}


def check_service(label):
  """Auto-detect platform and check service using launchd or systemd."""
  try:
    subprocess.run(["launchctl", "list"], capture_output=True, timeout=5)
    return check_launchd(label)
  except FileNotFoundError:
    return check_systemd(label)


def check_gateway_log():
  log_dir = HERMES_HOME / "logs"
  if not log_dir.exists():
    return {"status": "UNKNOWN", "detail": "No log directory"}
  recent = any(
    (NOW - datetime.fromtimestamp(f.stat().st_mtime)) < timedelta(minutes=30)
    for f in log_dir.glob("*.log*")
  )
  if recent:
    return {"status": "UP", "detail": "Activity in last 30 min"}
  return {"status": "DEGRADED", "detail": "No log activity in 30+ min"}


def check_disk_usage(path="/"):
  try:
    result = subprocess.run(["df", "-h", path], capture_output=True, text=True, timeout=10)
    lines = result.stdout.strip().split("\n")
    if len(lines) >= 2:
      pct_str = lines[1].split()[4].rstrip("%")
      pct = int(pct_str)
      status = "UP" if pct < 85 else "DEGRADED" if pct < 95 else "DOWN"
      return {"status": status, "detail": f"{pct}% used on {path}"}
  except Exception as e:
    return {"status": "ERROR", "detail": str(e)}


def check_memory_sync_freshness():
  """Check when memory was last synced to brain."""
  current = BRAIN_SHARED / "hermes-memory" / "current.md"
  if not current.exists():
    return {"status": "UNKNOWN", "detail": "No current.md — sync may not have run yet"}
  mtime = datetime.fromtimestamp(current.stat().st_mtime)
  age = NOW - mtime
  if age < timedelta(hours=8):
    return {"status": "UP", "detail": f"Last sync: {age.total_seconds() / 60:.0f}m ago"}
  elif age < timedelta(hours=24):
    return {"status": "DEGRADED", "detail": f"Last sync: {age.total_seconds() / 3600:.1f}h ago"}
  else:
    return {"status": "DOWN", "detail": f"Last sync: {age.total_seconds() / 3600:.1f}h ago — stale!"}


def check_mycortex():
  """Check mycortex (gbrain replacement) health via the CLI doctor.

  gbrain was decommissioned 2026-08-02. mycortex is a cron-synced Postgres
  index with no daemon; doctor verifies schema version + source freshness.
  Returns UNKNOWN (not DOWN) when mycortex isn't installed.
  """
  cli = Path.home() / ".hermes-cortex" / "scripts" / "mycortex"
  if not cli.exists():
    return {"status": "UNKNOWN", "detail": "mycortex not installed — run install.sh"}
  try:
    result = subprocess.run(
      [str(cli), "doctor", "--json"],
      capture_output=True, text=True, timeout=30,
    )
    # doctor exits 0 iff ok — authoritative. stdout mixes human lines
    # with a trailing JSON line, so fall back to rc on parse failure.
    if result.returncode != 0:
      return {"status": "DEGRADED", "detail": f"mycortex doctor rc={result.returncode}"}
    import json as _json
    try:
      data = _json.loads(result.stdout)
      if data.get("ok"):
        return {"status": "UP", "detail": f"schema {data.get('schema_version', '?')}"}
      return {"status": "DEGRADED", "detail": "mycortex doctor reported issues"}
    except (_json.JSONDecodeError, ValueError):
      return {"status": "UP", "detail": "doctor OK (rc=0)"}
  except subprocess.TimeoutExpired:
    return {"status": "UNKNOWN", "detail": "mycortex check timed out"}
  except Exception as e:
    return {"status": "UNKNOWN", "detail": f"mycortex check: {e}"}


def run():
  checks = {
    "Ollama": check_service("com.ollama.serve"),
    # gbrain sync daemon DECOMMISSIONED 2026-08-02 — mycortex replaces it
    # (cron-synced Postgres index, no daemon to check). Health is verified
    # via the mycortex CLI doctor below.
    "mycortex": check_mycortex(),
    "Gateway activity": check_gateway_log(),
    "Memory→brain sync": check_memory_sync_freshness(),
    "Disk usage": check_disk_usage(),
  }
  status_counts = {}
  for name, result in checks.items():
    s = result["status"]
    status_counts[s] = status_counts.get(s, 0) + 1

  overall = "HEALTHY"
  if status_counts.get("DOWN", 0) > 0:
    overall = "CRITICAL"
  elif status_counts.get("ERROR", 0) > 0:
    overall = "ERROR"
  elif status_counts.get("DEGRADED", 0) > 0:
    overall = "DEGRADED"

  now_str = NOW.strftime("%Y-%m-%d %H:%M:%S %Z")
  report = f"📡 Hermes Heartbeat — {now_str}\nOverall: {overall}\n\n"
  icons = {"UP": "✅", "DEGRADED": "⚠️", "DOWN": "❌", "ERROR": "🔴", "UNKNOWN": "❓"}
  for name, result in checks.items():
    report += f"{icons.get(result['status'], '❓')} {name}: {result['status']} — {result['detail']}\n"

  if overall == "HEALTHY" and "--report" not in sys.argv:
    return ""
  return report


if __name__ == "__main__":
  output = run()
  if output:
    print(output)
HEARTBEAT
 fi
 chmod +x "$HEARTBEAT_PATH"
 ok
fi

# ── send-agent-learning.sh ─────────────────────────────────────
SEND_LEARNING_PATH="${SCRIPTS_DIR}/send-agent-learning.sh"
if [[ -f "$SEND_LEARNING_PATH" ]]; then
 # Check if repo version differs — update if so
 if ! cmp -s "$SEND_LEARNING_PATH" "$(_scripts)/send-agent-learning.sh" 2>/dev/null; then
  cp "$(_scripts)/send-agent-learning.sh" "$SEND_LEARNING_PATH" 2>/dev/null || \
   warn "send-agent-learning.sh copy failed"
  chmod +x "$SEND_LEARNING_PATH"
  info " Updated send-agent-learning.sh (repo version differs)"
 else
  skip "send-agent-learning.sh up to date"
 fi
else
 # Prefer repo copy to prevent divergence
 if [[ -f "$(_scripts)/send-agent-learning.sh" ]]; then
  cp "$(_scripts)/send-agent-learning.sh" "$SEND_LEARNING_PATH" 2>/dev/null || \
   warn "send-agent-learning.sh copy failed"
  chmod +x "$SEND_LEARNING_PATH"
  info " Copied send-agent-learning.sh from repo"
 else
  cat > "$SEND_LEARNING_PATH" <<'SEND_LEARNING'
#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# send-agent-learning.sh — Send recent session/brain learnings
# from this agent to Moses via the agent inbox.
#
# Runs as a no_agent cron (default: every 6h).
# Silent when no new learnings since last run.
# Sends with status=read (informational, not actionable).
#
# Schedule: cron name=agent-learning-sender schedule="0 */6 * * *"
#      script=send-agent-learning.sh no_agent=true deliver=local
# ─────────────────────────────────────────────────────────────
set -euo pipefail

# ── Config ──
AGENT_NAME="${HOSTNAME%%.*}"
INBOX_URL="http://127.0.0.1:8903/send"
STATE_DIR="${HOME}/.hermes-cortex/state"
LAST_SENT_FILE="${STATE_DIR}/agent-learning-last-sent"
INTERVAL_SECONDS="${AGENT_LEARNING_INTERVAL:-21600}" # default 6h
SESSION_DIR="${HOME}/.hermes-cortex/sessions"
BRAIN_LESSONS_DIR="${HOME}/brain/${AGENT_NAME}/lessons"

mkdir -p "${STATE_DIR}"

# ── Helpers ──
log() { echo "[$(date '+%H:%M:%S')] $*"; }

# ── Step 1: Rate limit ──
if [[ -f "${LAST_SENT_FILE}" ]]; then
  LAST_RUN=$(cat "${LAST_SENT_FILE}" 2>/dev/null || echo 0)
  NOW=$(date +%s)
  if [[ $((NOW - LAST_RUN)) -lt ${INTERVAL_SECONDS} ]]; then
    exit 0 # Too soon, skip silently
  fi
fi

# ── Step 2: Gather session takeaways ──
SNIPPETS=""

# From session DB (most recent session file)
LATEST_SESSION=$(find "${SESSION_DIR}" -name "*.md" -type f 2>/dev/null | head -1)
if [[ -n "${LATEST_SESSION}" && -f "${LATEST_SESSION}" ]]; then
  # Extract the last ~30 lines (summary/takeaways section)
  TAIL_OUT=$(tail -30 "${LATEST_SESSION}" 2>/dev/null || true)
  if [[ -n "${TAIL_OUT}" ]]; then
    SNIPPETS+="=== ${AGENT_NAME} — Recent session takeaways ===\n"
    SNIPPETS+="${TAIL_OUT}\n\n"
  fi
fi

# From brain lessons (new/modified since last run)
if [[ -d "${BRAIN_LESSONS_DIR}" ]]; then
  # Find lesson files newer than last run
  NEW_LESSONS=()
  while IFS= read -r -d '' f; do
    NEW_LESSONS+=("$f")
  done < <(find "${BRAIN_LESSONS_DIR}" -name "*.md" -type f -newermt "@${LAST_RUN:-0}" -print0 2>/dev/null)

  if [[ ${#NEW_LESSONS[@]} -gt 0 ]]; then
    SNIPPETS+="=== ${AGENT_NAME} — New lessons (${#NEW_LESSONS[@]}) ===\n"
    for f in "${NEW_LESSONS[@]}"; do
      TITLE=$(basename "${f}" .md)
      # First non-empty line as summary
      SUMMARY=$(grep -m1 -E '^[^#]' "${f}" 2>/dev/null | head -1 || head -1 "${f}")
      SNIPPETS+="• ${TITLE}: ${SUMMARY}\n"
    done
    SNIPPETS+="\n"
  fi
fi

# From script changes (if this agent runs install.sh/cortex-update.sh)
CUSTOM_SCRIPTS="${HOME}/.hermes-cortex/scripts"
if [[ -d "${CUSTOM_SCRIPTS}" ]]; then
  # Check for any custom scripts not from the repo
  REPO_SCRIPTS="${HOME}/hermes-cortex/ops/scripts"
  CUSTOM_COUNT=0
  for f in "${CUSTOM_SCRIPTS}"/*.sh "${CUSTOM_SCRIPTS}"/*.py 2>/dev/null; do
    [[ -f "$f" ]] || continue
    BASENAME=$(basename "$f")
    if [[ ! -f "${REPO_SCRIPTS}/${BASENAME}" ]]; then
      ((CUSTOM_COUNT++))
    fi
  done
  if [[ ${CUSTOM_COUNT} -gt 0 ]]; then
    SNIPPETS+="=== ${AGENT_NAME} — Custom scripts (${CUSTOM_COUNT}) ===\n"
    SNIPPETS+="Found ${CUSTOM_COUNT} scripts not in hermes-cortex repo.\n\n"
  fi
fi

# ── Step 3: Exit if nothing to send ──
if [[ -z "${SNIPPETS}" ]]; then
  exit 0 # Silent — no new learnings
fi

# ── Step 4: Build message ──
BODY="Agent: ${AGENT_NAME}
Host: $(hostname)
Time: $(date -u '+%Y-%m-%d %H:%M:%S UTC')

${SNIPPETS}"

# ── Step 5: Send to Moses via inbox ──
RESPONSE=$(curl -sf -X POST "${INBOX_URL}" \
  -d "from=${AGENT_NAME}" \
  -d "topic=moses" \
  -d "subject=📥 ${AGENT_NAME} learning summary" \
  -d "body=${BODY}" \
  -d "priority=normal" \
  -d "status=read" 2>&1) || {
  log "Failed to send to inbox: ${RESPONSE}"
  exit 1
}

# ── Step 6: Update timestamp ──
date +%s > "${LAST_SENT_FILE}"
log "Sent learning summary to Moses (topic=moses)"
SEND_LEARNING
 fi
fi

# ── memory-to-brain-sync.py ─────────────────────────────────────
M2B_PATH="${SCRIPTS_DIR}/memory-to-brain-sync.py"
if [[ -f "$M2B_PATH" ]]; then
 # Write inline to temp, compare—only update if different
 M2B_TMP=$(mktemp)
 cat > "$M2B_TMP" <<'M2BPY'
#!/usr/bin/env python3
"""memory-to-brain-sync.py — Sync Hermes agent memory → gbrain (long-term brain)

Reads MEMORY.md and USER.md from the active Hermes profile,
formats them as searchable gbrain pages under ~/brain/shared/hermes-memory/,
then git-commits so the gbrain sync daemon picks them up.

Designed to run as a cron job alongside conversation export.
"""

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes-cortex"))
BRAIN_SHARED = Path.home() / "brain" / "shared"
MEMORY_DIR = HERMES_HOME / "memories"
OUT_DIR = BRAIN_SHARED / "hermes-memory"
TIMESTAMP = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z")
ENTRY_DELIMITER = "\n§\n"


def read_entries(filepath: Path) -> list[str]:
  """Read a §-delimited memory file and return non-empty entries."""
  if not filepath.exists() or filepath.stat().st_size == 0:
    return []
  text = filepath.read_text(encoding="utf-8")
  entries = [e.strip() for e in text.split(ENTRY_DELIMITER) if e.strip()]
  return entries


def build_current_md(memory_entries: list[str], user_entries: list[str]) -> str:
  """Build the full markdown snapshot."""
  lines = [
    "---",
    "type: note",
    "tags: [hermes, memory, agent, automation]",
    "---",
    "",
    "# Hermes Agent Memory Snapshot",
    "",
    f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}_",
    "",
  ]

  if memory_entries:
    lines.append("## Agent Notes (MEMORY.md)")
    lines.append("")
    for entry in memory_entries:
      lines.append(entry)
      lines.append("")

  if user_entries:
    lines.append("---")
    lines.append("")
    lines.append("## User Profile (USER.md)")
    lines.append("")
    for entry in user_entries:
      lines.append(entry)
      lines.append("")

  return "\n".join(lines)


def write_snapshot(content: str):
  """Write current snapshot and archived copy."""
  OUT_DIR.mkdir(parents=True, exist_ok=True)

  # Current authoritative copy
  current_path = OUT_DIR / "current.md"
  current_path.write_text(content, encoding="utf-8")
  print(f"✓ Written: current.md ({len(content)} bytes)")

  # Monthly archive for history
  archive_dir = OUT_DIR / "archive" / datetime.now().strftime("%Y-%m")
  archive_dir.mkdir(parents=True, exist_ok=True)
  archive_path = archive_dir / f"{datetime.now().strftime('%Y-%m-%d')}.md"
  archive_path.write_text(content, encoding="utf-8")
  print(f"✓ Archived: {archive_path}")


def git_commit():
  """Git commit in the shared brain repo so sync daemon picks it up."""
  if not (BRAIN_SHARED / ".git").exists():
    print(f"⚠ {BRAIN_SHARED} is not a git repo — skipping commit")
    return

  os.chdir(str(BRAIN_SHARED))
  subprocess.run(["git", "add", "hermes-memory/"], capture_output=True)

  result = subprocess.run(
    ["git", "diff", "--cached", "--quiet"],
    capture_output=True,
  )
  if result.returncode == 0:
    print("No changes to commit")
    return

  msg = f"hermes-memory: auto-sync {datetime.now().strftime('%Y-%m-%d %H:%M')}"
  subprocess.run(["git", "commit", "-m", msg], capture_output=True)
  print(f"✓ Git committed to shared brain")


def main():
  print(f"[{TIMESTAMP}] === memory-to-brain sync ===\n")

  memory_file = MEMORY_DIR / "MEMORY.md"
  user_file = MEMORY_DIR / "USER.md"

  if not memory_file.exists() and not user_file.exists():
    print("Neither MEMORY.md nor USER.md found — nothing to sync.")
    return

  memory_entries = read_entries(memory_file)
  user_entries = read_entries(user_file)
  print(f" Memory entries: {len(memory_entries)}")
  print(f" User entries: {len(user_entries)}")
  print()

  content = build_current_md(memory_entries, user_entries)
  write_snapshot(content)
  git_commit()

  print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S %Z')}] === memory-to-brain sync complete ===")


if __name__ == "__main__":
  main()
M2BPY
 chmod +x "$M2B_TMP"
 if cmp -s "$M2B_PATH" "$M2B_TMP"; then
  rm -f "$M2B_TMP"
  skip "memory-to-brain-sync.py up to date"
 else
  mv "$M2B_TMP" "$M2B_PATH"
  chmod +x "$M2B_PATH"
  info " Updated memory-to-brain-sync.py (inline version changed)"
 fi
else
 M2B_TMP=$(mktemp)
 cat > "$M2B_TMP" <<'M2BPY2'
#!/usr/bin/env python3
"""memory-to-brain-sync.py — Sync Hermes agent memory → gbrain (long-term brain)

Reads MEMORY.md and USER.md from the active Hermes profile,
formats them as searchable gbrain pages under ~/brain/shared/hermes-memory/,
then git-commits so the gbrain sync daemon picks them up.

Designed to run as a cron job alongside conversation export.
"""

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes-cortex"))
BRAIN_SHARED = Path.home() / "brain" / "shared"
MEMORY_DIR = HERMES_HOME / "memories"
OUT_DIR = BRAIN_SHARED / "hermes-memory"
TIMESTAMP = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z")
ENTRY_DELIMITER = "\n§\n"


def read_entries(filepath: Path) -> list[str]:
  """Read a §-delimited memory file and return non-empty entries."""
  if not filepath.exists() or filepath.stat().st_size == 0:
    return []
  text = filepath.read_text(encoding="utf-8")
  entries = [e.strip() for e in text.split(ENTRY_DELIMITER) if e.strip()]
  return entries


def build_current_md(memory_entries: list[str], user_entries: list[str]) -> str:
  """Build the full markdown snapshot."""
  lines = [
    "---",
    "type: note",
    "tags: [hermes, memory, agent, automation]",
    f"generated: {TIMESTAMP}",
    "---",
    "",
    "# Current Agent Context",
    "",
    "> **Purpose:** This file is auto-generated by memory-to-brain-sync.py.",
    "> It captures the agent's current MEMORY.md and USER.md so gbrain",
    "> can search them alongside other brain sources.",
    "",
    "## Memory (agent's personal notes)",
    "",
  ]
  if memory_entries:
    for entry in memory_entries:
      lines.append(entry)
      lines.append("")
  else:
    lines.append("*No memory entries found.*")
    lines.append("")

  if user_entries:
    lines.append("## User Profile (who the user is)")
    lines.append("")
    for entry in user_entries:
      lines.append(entry)
      lines.append("")
  else:
    lines.append("## User Profile")
    lines.append("")
    lines.append("*No user profile entries found.*")
    lines.append("")

  return "\n".join(lines)


def write_current_md(content: str) -> Path:
  """Write the full snapshot to OUT_DIR/current.md."""
  OUT_DIR.mkdir(parents=True, exist_ok=True)
  current = OUT_DIR / "current.md"
  current.write_text(content, encoding="utf-8")
  return current


def write_archive(content: str) -> Path:
  """Write a timestamped copy to OUT_DIR/archive/YYYY-MM-DD-HHMMSS.md."""
  archive_dir = OUT_DIR / "archive"
  archive_dir.mkdir(parents=True, exist_ok=True)
  stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
  archive = archive_dir / f"{stamp}.md"
  archive.write_text(content, encoding="utf-8")
  return archive


def write_snapshot(content: str) -> tuple[Path, Path]:
  """Write both current.md and an archive copy. Returns (current, archive)."""
  cur = write_current_md(content)
  arch = write_archive(content)
  return cur, arch


def git_commit():
  """Git-add and commit in OUT_DIR so gbrain picks up changes."""
  if not (OUT_DIR / ".git").exists():
    subprocess.run(["git", "init"], cwd=str(OUT_DIR), capture_output=True)
  subprocess.run(["git", "add", "-A"], cwd=str(OUT_DIR), capture_output=True)
  subprocess.run(
    ["git", "commit", "--allow-empty", "-m", f"memory sync {TIMESTAMP}"],
    cwd=str(OUT_DIR),
    capture_output=True,
  )


def main():
  print(f"[{TIMESTAMP}] === memory-to-brain sync ===\n")

  memory_file = MEMORY_DIR / "MEMORY.md"
  user_file = MEMORY_DIR / "USER.md"

  memory_entries = read_entries(memory_file)
  user_entries = read_entries(user_file)
  print(f" Memory entries: {len(memory_entries)}")
  print(f" User entries:  {len(user_entries)}")

  content = build_current_md(memory_entries, user_entries)
  write_snapshot(content)
  git_commit()

  print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S %Z')}] === memory-to-brain sync complete ===")


if __name__ == "__main__":
  main()
M2BPY2
 chmod +x "$M2B_TMP"
 mv "$M2B_TMP" "$M2B_PATH"
 chmod +x "$M2B_PATH"
 ok
 info " Installed memory-to-brain-sync.py"
fi

# ── bootstrap-brain.sh ─────────────────────────────────────
BOOTSTRAP_PATH="${SCRIPTS_DIR}/bootstrap-brain.sh"
if [[ -f "$BOOTSTRAP_PATH" ]]; then
 skip "bootstrap-brain.sh already exists"
else
 cp "$(_scripts)/bootstrap-brain.sh" "$BOOTSTRAP_PATH" 2>/dev/null || {
  cat > "$BOOTSTRAP_PATH" <<'BOOTSTRAP'
#!/usr/bin/env bash
# bootstrap-brain.sh — Post-install brain verification
# Auto-generated by install.sh
set -euo pipefail
BRAIN_DIR="${HOME}/brain"
GBRAIN_CMD="${HOME}/.bun/bin/gbrain"
export PATH="${HOME}/.bun/bin:$PATH"
echo "━━━ Brain Bootstrap ━━━"
for dir in "$BRAIN_DIR"/*/; do
 name=$(basename "$dir")
 if [[ ! -d "${dir}/.git" ]]; then
  git -C "$dir" init 2>/dev/null && echo "✓ Git init: ${name}"
 fi
 if [[ ! -f "${dir}/.gitignore" ]]; then
  echo "MEMORY.md\nUSER.md\n.env\n.env.*\n*.pem\n*.key\n.DS_Store" > "${dir}/.gitignore"
  echo "✓ .gitignore: ${name}"
 fi
 # gbrain sources list has leading spaces — don't anchor at column 0
 if ! "$GBRAIN_CMD" sources list 2>/dev/null | grep -q "^ ${name}[[:space:]]"; then
  "$GBRAIN_CMD" sources add "$name" --path "$dir" --name "$name" 2>/dev/null && echo "✓ gbrain source: ${name}"
 fi
 git -C "$dir" add -A 2>/dev/null || true
 git -C "$dir" commit --allow-empty -m "init: ${name}" 2>/dev/null || true
 "$GBRAIN_CMD" sync --source "$name" 2>/dev/null && echo "✓ Synced: ${name}"
 # Get page count from gbrain sources list (3rd field), not a nonexistent --list-pages flag
 pages=$("$GBRAIN_CMD" sources list 2>/dev/null | grep "^ ${name}[[:space:]]" | awk '{print $3}' | head -1)
 pages=${pages:-0}
 echo " ${pages} pages indexed for ${name}"
done
BOOTSTRAP
 }
 chmod +x "$BOOTSTRAP_PATH"
 info " Installed bootstrap-brain.sh"
fi

# ── check-memory-budget.sh ─────────────────────────────────
BUDGET_PATH="${SCRIPTS_DIR}/check-memory-budget.sh"
if [[ -f "$BUDGET_PATH" ]]; then
 skip "check-memory-budget.sh already exists"
else
 cp "$(_scripts)/check-memory-budget.sh" "$BUDGET_PATH" 2>/dev/null || {
  cat > "$BUDGET_PATH" <<'BUDGET'
#!/usr/bin/env bash
# check-memory-budget.sh — MEMORY.md usage monitor
set -euo pipefail
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BOLD='\033[1m'; RESET='\033[0m'
FILE="${HOME}/.hermes/memories/MEMORY.md"
LIMIT=2200
[[ ! -f "$FILE" ]] && { echo "No MEMORY.md found"; exit 0; }
CHARS=$(wc -m < "$FILE" | tr -d ' ')
PCT=$(( CHARS * 100 / LIMIT ))
[[ $PCT -ge 95 ]] && ICON="🔴" && STATUS="CRITICAL"
[[ $PCT -ge 85 && $PCT -lt 95 ]] && ICON="🟡" && STATUS="WARNING"
[[ $PCT -lt 85 ]] && ICON="🟢" && STATUS="OK"
echo "${ICON} MEMORY.md: ${PCT}% (${CHARS}/${LIMIT}) — ${STATUS}"
[[ $PCT -ge 85 ]] && echo "Run: bash ~/.hermes-cortex/scripts/bootstrap-brain.sh to compact"
BUDGET
 }
 chmod +x "$BUDGET_PATH"
 info " Installed check-memory-budget.sh"
fi

# ── cortex-profile.sh ─────────────────────────────────────
CORTEX_PROFILE_PATH="${SCRIPTS_DIR}/cortex-profile.sh"
if [[ -f "$CORTEX_PROFILE_PATH" ]]; then
 skip "cortex-profile.sh already exists"
else
 cp "$(_scripts)/cortex-profile.sh" "$CORTEX_PROFILE_PATH" 2>/dev/null || \
  warn "cortex-profile.sh not available (only from repo)"
 if [[ -f "$CORTEX_PROFILE_PATH" ]]; then
  chmod +x "$CORTEX_PROFILE_PATH"
  info " Installed cortex-profile.sh"
 fi
fi

# ── seed-project-brain.sh ──────────────────────────────────
SEED_BRAIN_PATH="${SCRIPTS_DIR}/seed-project-brain.sh"
if [[ -f "$SEED_BRAIN_PATH" ]]; then
 skip "seed-project-brain.sh already exists"
else
 cp "$(_scripts)/seed-project-brain.sh" "$SEED_BRAIN_PATH" 2>/dev/null || \
  warn "seed-project-brain.sh not available (only from repo)"
 if [[ -f "$SEED_BRAIN_PATH" ]]; then
  chmod +x "$SEED_BRAIN_PATH"
  info " Installed seed-project-brain.sh"
 fi
fi

# ── cortex-health.sh ───────────────────────────────────────
CORTEX_HEALTH_PATH="${SCRIPTS_DIR}/cortex-health.sh"
if [[ -f "$CORTEX_HEALTH_PATH" ]]; then
 skip "cortex-health.sh already exists"
else
 cp "$(_scripts)/cortex-health.sh" "$CORTEX_HEALTH_PATH" 2>/dev/null || \
  warn "cortex-health.sh not available (only from repo)"
 if [[ -f "$CORTEX_HEALTH_PATH" ]]; then
  chmod +x "$CORTEX_HEALTH_PATH"
  info " Installed cortex-health.sh"
 fi
fi

# ── cortex-setup-langfuse.sh ───────────────────────────────
CORTEX_LANGFUSE_PATH="${SCRIPTS_DIR}/cortex-setup-langfuse.sh"
if [[ -f "$CORTEX_LANGFUSE_PATH" ]]; then
 skip "cortex-setup-langfuse.sh already exists"
else
 cp "$(_scripts)/cortex-setup-langfuse.sh" "$CORTEX_LANGFUSE_PATH" 2>/dev/null || \
  warn "cortex-setup-langfuse.sh not available (only from repo)"
 if [[ -f "$CORTEX_LANGFUSE_PATH" ]]; then
  chmod +x "$CORTEX_LANGFUSE_PATH"
  info " Installed cortex-setup-langfuse.sh"
 fi
fi

# ── cortex-update.sh ───────────────────────────────────────
CORTEX_UPDATE_PATH="${SCRIPTS_DIR}/cortex-update.sh"
if [[ -f "$CORTEX_UPDATE_PATH" ]]; then
 skip "cortex-update.sh already exists"
else
 cp "$(_scripts)/cortex-update.sh" "$CORTEX_UPDATE_PATH" 2>/dev/null || \
  warn "cortex-update.sh not available (only from repo)"
 if [[ -f "$CORTEX_UPDATE_PATH" ]]; then
  chmod +x "$CORTEX_UPDATE_PATH"
  info " Installed cortex-update.sh"
 fi
fi

# ── prod-watchdog.sh ────────────────────────────────────────
PROD_WATCHDOG_PATH="${SCRIPTS_DIR}/prod-watchdog.sh"
if [[ -f "$PROD_WATCHDOG_PATH" ]]; then
 skip "prod-watchdog.sh already exists"
else
 cp "$(_scripts)/prod-watchdog.sh" "$PROD_WATCHDOG_PATH" 2>/dev/null || \
  warn "prod-watchdog.sh not available (only from repo)"
 if [[ -f "$PROD_WATCHDOG_PATH" ]]; then
  chmod +x "$PROD_WATCHDOG_PATH"
  info " Installed prod-watchdog.sh"
 fi
fi

# orch-fleet-watchdog replaces the old orch-team-health — now a general
# cron managed by the Hermes cron system. Peer agents don't need it.

# ── Auto-Save Active Sessions Script ──────────────────────────────
AUTO_SAVE_PATH="${SCRIPTS_DIR}/auto-save-sessions.py"
if [[ -f "$(_scripts)/auto-save-sessions.py" ]]; then
 cp "$(_scripts)/auto-save-sessions.py" "$AUTO_SAVE_PATH" 2>/dev/null || \
  warn "auto-save-sessions.py copy failed"
 chmod +x "$AUTO_SAVE_PATH" 2>/dev/null || true
 info " Installed auto-save-sessions.py"
fi

# ── Eval Harness Scripts ───────────────────────────────────────
# Create evals directory structure
EVALS_DIR="${CORTEX_DEPLOY_HOME}/evals"
mkdir -p "$EVALS_DIR/traces" "$EVALS_DIR/reports"
info " Created evals directory structure"

RUN_EVALS_PATH="${SCRIPTS_DIR}/run-evals.py"
if [[ -f "$(_scripts)/run-evals.py" ]]; then
 cp "$(_scripts)/run-evals.py" "$RUN_EVALS_PATH" 2>/dev/null || \
  warn "run-evals.py copy failed"
 chmod +x "$RUN_EVALS_PATH"
 info " Installed run-evals.py"
fi

ANALYZE_FAILURES_PATH="${SCRIPTS_DIR}/analyze-failures.py"
if [[ -f "$(_scripts)/analyze-failures.py" ]]; then
 cp "$(_scripts)/analyze-failures.py" "$ANALYZE_FAILURES_PATH" 2>/dev/null || \
  warn "analyze-failures.py copy failed"
 chmod +x "$ANALYZE_FAILURES_PATH"
 info " Installed analyze-failures.py"
fi

HERMES_TZ_PATH="${SCRIPTS_DIR}/hermes_tz.py"
if [[ -f "$(_scripts)/hermes_tz.py" ]]; then
 cp "$(_scripts)/hermes_tz.py" "$HERMES_TZ_PATH" 2>/dev/null || \
  warn "hermes_tz.py copy failed"
 chmod +x "$HERMES_TZ_PATH"
 info " Installed hermes_tz.py (timezone helper)"
fi

# ── Auto-Update Cron ───────────────────────────────────────────
AUTO_UPDATE_SCRIPT="${SCRIPTS_DIR}/install-cortex-update-cron.sh"
if [[ -f "$AUTO_UPDATE_SCRIPT" ]]; then
 if launchctl list com.hermes.cortex-update &>/dev/null 2>&1 || \
   systemctl --user list-timers 2>/dev/null | grep -q "cortex-update" || \
   crontab -l 2>/dev/null | grep -q "cortex-update"; then
  skip "auto-update cron already registered"
 else
  bash "$AUTO_UPDATE_SCRIPT" 2>&1 | sed 's/^/ /'
  info " Registered daily auto-update cron (3am)"
 fi
else
 warn "install-cortex-update-cron.sh not found — skipping auto-update setup"
fi

# ── Agent Learning Sender Cron ────────────────────────────────────
LEARNING_CRON_SCRIPT="${SCRIPTS_DIR}/install-send-agent-learning-cron.sh"
if [[ -f "$LEARNING_CRON_SCRIPT" ]]; then
 if launchctl list com.hermes.agent-learning-sender &>/dev/null 2>&1 || \
   systemctl --user list-timers 2>/dev/null | grep -q com.hermes.agent-learning-sender || \
   crontab -l 2>/dev/null | grep -q com.hermes.agent-learning-sender; then
  skip "agent-learning-sender cron already registered"
 else
  bash "$LEARNING_CRON_SCRIPT" 2>&1 | sed 's/^/ /'
  info " Registered agent-learning-sender cron (every 6h)"
 fi
else
 warn "install-send-agent-learning-cron.sh not found — skipping agent-learning-sender cron setup"
fi

# ── Essential Hermes Crons ──────────────────────────────────────
HERMES_CRONS_SCRIPT="${SCRIPTS_DIR}/install-crons.sh"
if [[ -f "$HERMES_CRONS_SCRIPT" ]]; then
 step "Creating essential Hermes cron jobs (auto-remediation, health, memory sync…)"
 # Verify Hermes is installed first
 if ! command -v hermes &>/dev/null && [[ ! -x "${CORTEX_DEPLOY_HOME}/hermes-agent/venv/bin/hermes" ]]; then
  warn "Hermes Agent not found — cron jobs cannot be created"
  warn " Install Hermes Agent first: https://hermes-agent.nousresearch.com/docs"
  warn " Then run: bash ${HERMES_CRONS_SCRIPT}"
  skip "Hermes not installed"
 else
  bash "$HERMES_CRONS_SCRIPT" 2>&1 | sed 's/^/ /'
  ok
 fi
else
 warn "install-crons.sh not found — skipping cron job creation"
fi

# ── Orchestrator Crons (conditional on IS_ORCHESTRATOR) ──────────
# Only installed on orchestrator machines (Moses / Esther).
# Gate via IS_ORCHESTRATOR=true in ~/hermes-cortex/.env
ORCH_CRONS_SCRIPT="${SCRIPTS_DIR}/install-orch-crons.sh"
if [[ -f "$ORCH_CRONS_SCRIPT" ]]; then
 _ORCH=false
 if [[ "${IS_ORCHESTRATOR:-false}" == "true" ]]; then
  _ORCH=true
 fi
 if ! $_ORCH; then
  ORCH_HOST="$(hostname -s 2>/dev/null || echo 'unknown')"
  if [[ "$ORCH_HOST" == "moses" || "$ORCH_HOST" == "esther" ]]; then
   _ORCH=true
  fi
 fi
 if $_ORCH; then
  step "Creating orchestrator-only cron jobs (team health, team messages…)"
  if command -v hermes &>/dev/null; then
   bash "$ORCH_CRONS_SCRIPT" 2>&1 | sed 's/^/ /'
   info "Orch crons installed"
  else
   warn "Hermes not installed — orch crons skipped"
  fi
  ok
 else
  skip "not an orchestrator (IS_ORCHESTRATOR != true)"
 fi
fi

# ── Scripts list ────────────────────────────────────────────
info "Scripts directory: ${SCRIPTS_DIR}"

# ─────────────────────────────────────────────────────────────
# 9. Seed Memory Files — Bootstrapping templates
# ─────────────────────────────────────────────────────────────
step "Seeding initial memory files (MEMORY.md, USER.md)"

# Find the template seed files
SEED_MEMORY="${SCRIPT_DIR}/docs/templates/MEMORY.seed.md"
SEED_USER="${SCRIPT_DIR}/docs/templates/USER.seed.md"
HERMES_MEMORIES="${CORTEX_DEPLOY_HOME}/memories"

# Create memory directory if it doesn't exist
mkdir -p "$HERMES_MEMORIES"

# Copy seed files only if they don't already exist (don't overwrite)
if [[ -f "$SEED_MEMORY" ]] && [[ ! -f "${HERMES_MEMORIES}/MEMORY.md" ]]; then
 cp "$SEED_MEMORY" "${HERMES_MEMORIES}/MEMORY.md"
 info " Created MEMORY.md from seed template"
else
 skip "MEMORY.md already exists or template not found"
fi

if [[ -f "$SEED_USER" ]] && [[ ! -f "${HERMES_MEMORIES}/USER.md" ]]; then
 cp "$SEED_USER" "${HERMES_MEMORIES}/USER.md"
 info " Created USER.md from seed template"
else
 skip "USER.md already exists or template not found"
fi

# Seed SOUL.md from template if it doesn't exist yet
SEED_SOUL="${SCRIPT_DIR}/docs/templates/SOUL.md"
HERMES_AGENT_DIR="${HOME}/.hermes"
if [[ -f "$SEED_SOUL" ]] && [[ ! -f "${HERMES_AGENT_DIR}/SOUL.md" ]]; then
 mkdir -p "$HERMES_AGENT_DIR"
 cp "$SEED_SOUL" "${HERMES_AGENT_DIR}/SOUL.md"
 info " Created SOUL.md from seed template"
 info " → Edit ~/.hermes/SOUL.md with your identity and behavioral principles"
else
 skip "SOUL.md already exists or template not found"
fi

# Seed memory scoring rubric
SEED_MEMORY_README="${SCRIPT_DIR}/docs/templates/memory-readme.seed.md"
MEMORY_DOC_DIR="${CORTEX_DEPLOY_HOME}/memory"
if [[ -f "$SEED_MEMORY_README" ]] && [[ ! -f "${MEMORY_DOC_DIR}/README.md" ]]; then
 mkdir -p "$MEMORY_DOC_DIR"
 cp "$SEED_MEMORY_README" "${MEMORY_DOC_DIR}/README.md"
 info " Created memory/README.md from seed template"
else
 skip "memory/README.md already exists or template not found"
fi

# Create an empty .gitkeep so the directory is clean (not git-tracked anyway)
touch "$HERMES_MEMORIES/.gitkeep"
ok

# ─────────────────────────────────────────────────────────────
# 10. Install Hermes Skills — Shared skills from the repo
# ─────────────────────────────────────────────────────────────
step "Installing Hermes skills from repo"
SKILLS_REPO="${SCRIPT_DIR}/../skills"
HERMES_SKILLS="${CORTEX_DEPLOY_HOME}/skills"
if [[ -d "$SKILLS_REPO" ]]; then
 count=0
 while IFS= read -r -d '' skill_file; do
  # Compute destination path relative to skills/ dir
  rel_path="${skill_file#$SKILLS_REPO/}"
  dest="${HERMES_SKILLS}/${rel_path}"
  dest_dir="$(dirname "$dest")"
  if [[ ! -f "$dest" ]]; then
   mkdir -p "$dest_dir"
   cp "$skill_file" "$dest"
   count=$((count + 1))
  fi
 done < <(find "$SKILLS_REPO" -name "SKILL.md" -type f -print0)
 # Also copy reference files
 while IFS= read -r -d '' ref_file; do
  rel_path="${ref_file#$SKILLS_REPO/}"
  dest="${HERMES_SKILLS}/${rel_path}"
  dest_dir="$(dirname "$dest")"
  if [[ ! -f "$dest" ]]; then
   mkdir -p "$dest_dir"
   cp "$ref_file" "$dest"
  fi
 done < <(find "$SKILLS_REPO" -path "*/references/*" -type f -print0)
 info " Installed ${count} skills (skipped existing)"
else
 skip "no skills/ directory in repo"
fi
ok

# ─────────────────────────────────────────────────────────────
# 12a. Score Pre-Commit Hooks — Install scoring hooks to all projects
# ─────────────────────────────────────────────────────────────
SCORE_HOOK_SCRIPT="${SCRIPTS_DIR}/install-score-hook.sh"
if [[ -f "$SCORE_HOOK_SCRIPT" ]]; then
 step "Installing scoring pre-commit hooks to all projects…"
 if bash "$SCORE_HOOK_SCRIPT" --all 2>&1 | tail -3; then
  ok
 else
  warn "score hook installation completed with warnings — check above"
  ok
 fi
else
 skip "install-score-hook.sh not found — run later manually"
fi

# ─────────────────────────────────────────────────────────────
# 12c. Post-Merge Hook — Auto-deploy after git pull
# ─────────────────────────────────────────────────────────────
POST_MERGE_SRC="${CORTEX_REPO_DIR}/.hermes-cortex/hooks/post-merge"
POST_MERGE_DST="${CORTEX_REPO_DIR}/.git/hooks/post-merge"
if [[ -f "$POST_MERGE_SRC" ]]; then
 step "Installing post-merge hook (auto cortex-update after git pull)…"
 cp "$POST_MERGE_SRC" "$POST_MERGE_DST"
 chmod +x "$POST_MERGE_DST"
 info " Installed: .git/hooks/post-merge → auto-runs cortex-update.sh after every pull"
else
 skip "post-merge hook not found at ${POST_MERGE_SRC}"
fi

# ─────────────────────────────────────────────────────────────
# 12b. MCP Server Registration — Loop Governance Primary Enforcer
# ─────────────────────────────────────────────────────────────
step "Registering loop-governance MCP server (loop-gov-mcp.py)"
MCP_SERVER_PATH="${SCRIPT_DIR}/mcp-servers/loop-gov-mcp.py"
if [[ -f "$MCP_SERVER_PATH" ]]; then
 if command -v hermes &>/dev/null; then
  if hermes mcp list 2>/dev/null | grep -q "loop-governance"; then
   skip "loop-governance MCP server already registered"
  else
   if hermes mcp add loop-governance --command "$(find_best_python)" --args "$MCP_SERVER_PATH" 2>/dev/null; then
    info " Registered: loop-governance MCP server"
    info " → Primary write-tool enforcer. Blocks tools without governance lock."
   else
    warn " Could not register MCP server — check hermes version"
   fi
  fi
 else
  skip "hermes CLI not found — MCP server not registered"
  info " → After installing Hermes, run:"
  info "   hermes mcp add loop-governance --command python3 --args ${MCP_SERVER_PATH}"
 fi
else
 skip "loop-gov-mcp.py not found at ${MCP_SERVER_PATH}"
fi
ok

# ─────────────────────────────────────────────────────────────
# 12. Web Cache — Local Semantic Web Cache
# ─────────────────────────────────────────────────────────────
step "Installing Web Cache (semantic web result cache)"
WEB_CACHE_REPO="${SCRIPT_DIR}/../ops/web-cache"
WEB_CACHE_DEST="${CORTEX_DEPLOY_HOME}/web-cache"
HERMES_BIN="${CORTEX_DEPLOY_HOME}/bin"
if [[ -d "$WEB_CACHE_REPO" ]]; then
 mkdir -p "$WEB_CACHE_DEST" "$HERMES_BIN"
 # Copy the Python tool
 cp "${WEB_CACHE_REPO}/web_cache.py" "$WEB_CACHE_DEST/"
 chmod +x "${WEB_CACHE_DEST}/web_cache.py"
 # Copy the wrapper script
 cp "${WEB_CACHE_REPO}/web_cache.sh" "$WEB_CACHE_DEST/"
 chmod +x "${WEB_CACHE_DEST}/web_cache.sh"
 # Create symlink in hermes bin directory
 ln -sf "${WEB_CACHE_DEST}/web_cache.sh" "${HERMES_BIN}/web_cache"
 info " Installed web cache tool"
 # Create the venv if not exists
 if [[ ! -d "${WEB_CACHE_DEST}/.venv" ]]; then
  BEST_PY=$(find_best_python)
  info " Using $BEST_PY for web-cache venv"
  $BEST_PY -m venv "${WEB_CACHE_DEST}/.venv" 2>/dev/null
  "${WEB_CACHE_DEST}/.venv/bin/pip" install sqlite-vec requests 2>/dev/null && \
   info " Created venv with sqlite-vec + requests"
 else
  skip " venv already exists"
 fi
 # Initialize the cache DB
 "${WEB_CACHE_DEST}/.venv/bin/python3" "${WEB_CACHE_DEST}/web_cache.py" stats >/dev/null 2>&1 && \
  info " Cache DB initialized"
else
 skip "no ops/web-cache/ directory in repo"
fi
ok

# ─────────────────────────────────────────────────────────────
# 12. Langfuse — LLM Observability (Docker Compose)
# ─────────────────────────────────────────────────────────────
if [[ "$CORTEX_PROFILE" == "server" ]]; then
step "Installing Langfuse (LLM observability)"

LANGFUSE_DIR="${CORTEX_HOME}/langfuse"
LANGFUSE_COMPOSE="${CORTEX_HOME}/langfuse/docker-compose.yml"

if [[ -d "$LANGFUSE_DIR" ]] && docker ps --format '{{.Names}}' 2>/dev/null | grep -q "langfuse"; then
 skip "Langfuse already running"
else
 mkdir -p "$LANGFUSE_DIR"

 # Copy docker-compose from repo if not exists
 if [[ ! -f "$LANGFUSE_COMPOSE" ]]; then
  # Check if we're in the repo
  if [[ -f "${SCRIPT_DIR}/docker-compose.langfuse.yml" ]]; then
   cp "${SCRIPT_DIR}/docker-compose.langfuse.yml" "$LANGFUSE_COMPOSE"
  else
   # Download from GitHub
   curl -fsSL "https://raw.githubusercontent.com/fleet-operator/hermes-cortex/main/ops/install/deploy/docker-compose.langfuse.yml" -o "$LANGFUSE_COMPOSE"
  fi
 fi

 # Generate secrets if .env doesn't exist
 LANGFUSE_ENV="${LANGFUSE_DIR}/.env"
 if [[ ! -f "$LANGFUSE_ENV" ]]; then
  cat > "$LANGFUSE_ENV" <<ENVFILE
# Langfuse secrets — generated by hermes-cortex installer
# WARNING: Change these if you shared access to this machine!
LANGFUSE_SALT=$(openssl rand -hex 32)
LANGFUSE_SECRET_KEY=$(openssl rand -hex 32)
LANGFUSE_NEXTAUTH_SECRET=$(openssl rand -hex 32)
LANGFUSE_POSTGRES_PASSWORD=$(openssl rand -hex 20)
LANGFUSE_CLICKHOUSE_PASSWORD=$(openssl rand -hex 16)
LANGFUSE_REDIS_AUTH=$(openssl rand -hex 32)
LANGFUSE_ENCRYPTION_KEY=$(openssl rand -hex 32)
LANGFUSE_MINIO_ACCESS_KEY=$(openssl rand -hex 16)
LANGFUSE_MINIO_SECRET_KEY=$(openssl rand -hex 32)

# Initial project API keys (auto-created on first run)
LANGFUSE_INIT_PROJECT_PUBLIC_KEY=pk-lf-$(openssl rand -hex 16)
LANGFUSE_INIT_PROJECT_SECRET_KEY=sk-lf-$(openssl rand -hex 32)
LANGFUSE_INIT_PROJECT_NAME=Hermes Agent
ENVFILE
  chmod 600 "$LANGFUSE_ENV"
 fi

 # Start Langfuse
 cd "$LANGFUSE_DIR"
 if docker compose up -d 2>&1; then
  ok
  info " Langfuse starting — wait ~30s for all containers"
 else
  warn "Docker Compose failed — install Docker Desktop or check daemon"
 fi
 cd - > /dev/null

 # Wire Hermes Agent with Langfuse integration
 CORTEX_LANGFUSE_PATH="${SCRIPTS_DIR}/cortex-setup-langfuse.sh"
 if [[ -f "$CORTEX_LANGFUSE_PATH" ]]; then
  info " Wiring Hermes Agent with Langfuse integration..."
  bash "$CORTEX_LANGFUSE_PATH" 2>&1 | sed 's/^/  /'
  info " Hermes Agent integration complete"
 else
  warn " cortex-setup-langfuse.sh not available for Hermes integration"
 fi
fi

# ─────────────────────────────────────────────────────────────
# 13. Cortex Dashboard — Flask companion app
# ─────────────────────────────────────────────────────────────
step "Installing Cortex Dashboard"

DASHBOARD_DEST="${CORTEX_DEPLOY_HOME}/dashboard"
DASHBOARD_PLIST="${CORTEX_HOME}/Library/LaunchAgents/com.hermes.cortex-dashboard.plist"

if [[ -f "$DASHBOARD_DEST/server.py" ]]; then
 skip "Cortex Dashboard already installed"
else
 mkdir -p "$DASHBOARD_DEST"

 # Copy from repo
 REPO_DASHBOARD="$(dirname "$SCRIPT_DIR")/services/dashboard"
 if [[ -d "$REPO_DASHBOARD" ]]; then
  cp -r "$REPO_DASHBOARD/"* "$DASHBOARD_DEST/"
 else
  # Download minimal version from GitHub
  curl -fsSL "https://raw.githubusercontent.com/fleet-operator/hermes-cortex/main/ops/services/dashboard/server.py" -o "$DASHBOARD_DEST/server.py"
  curl -fsSL "https://raw.githubusercontent.com/fleet-operator/hermes-cortex/main/ops/services/dashboard/com.hermes.cortex-dashboard.plist" -o "$DASHBOARD_PLIST"
  # Download static assets
  curl -fsSL "https://raw.githubusercontent.com/fleet-operator/hermes-cortex/main/ops/services/dashboard/static/index.html" -o "$DASHBOARD_DEST/static/index.html"
 fi

 # Create dedicated dashboard venv + install Flask
 if [[ ! -f "${DASHBOARD_DEST}/venv/bin/python3" ]]; then
  info " Creating dedicated dashboard venv…"
  BEST_PY=$(find_best_python)
  $BEST_PY -m venv "${DASHBOARD_DEST}/venv"
  "${DASHBOARD_DEST}/venv/bin/pip" install flask --quiet
  info " Dashboard venv ready"
 fi

 # Install service (launchd on macOS, systemd on Linux)
 if [[ "$CORTEX_OS" == "macos" ]]; then
  DASHBOARD_PLIST="${CORTEX_HOME}/Library/LaunchAgents/com.hermes.cortex-dashboard.plist"
  if [[ ! -f "$DASHBOARD_PLIST" ]]; then
   # Update paths in plist for current user
   sed "s|CORTEX_HOME|${CORTEX_HOME}|g" "${REPO_DASHBOARD}/com.hermes.cortex-dashboard.plist" > "$DASHBOARD_PLIST" 2>/dev/null || \
   cat > "$DASHBOARD_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.hermes.cortex-dashboard</string>
  <key>ProgramArguments</key>
  <array>
    <string>${DASHBOARD_DEST}/venv/bin/python3</string>
    <string>${DASHBOARD_DEST}/server.py</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${DASHBOARD_DEST}</string>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>ThrottleInterval</key>
  <integer>5</integer>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
  </dict>
  <key>StandardOutPath</key>
  <string>${CORTEX_DEPLOY_HOME}/logs/cortex-dashboard.log</string>
  <key>StandardErrorPath</key>
  <string>${CORTEX_DEPLOY_HOME}/logs/cortex-dashboard.log</string>
</dict>
</plist>
PLIST
  fi

  # Load launchd service
  launchctl unload "$DASHBOARD_PLIST" 2>/dev/null || true
  if launchctl load "$DASHBOARD_PLIST" 2>&1; then
   ok
   info " Dashboard running at http://localhost:8901"
  else
   warn "Failed to load dashboard launchd service"
  fi

 elif [[ "$CORTEX_OS" == "linux" ]]; then
  DASHBOARD_SERVICE_DIR="${HOME}/.config/systemd/user"
  DASHBOARD_SERVICE="${DASHBOARD_SERVICE_DIR}/hermes-cortex-dashboard.service"
  mkdir -p "$DASHBOARD_SERVICE_DIR"
  if [[ ! -f "$DASHBOARD_SERVICE" ]]; then
   cat > "$DASHBOARD_SERVICE" <<SYSTEMDEOF
[Unit]
Description=Hermes Cortex Dashboard
After=network-online.target

[Service]
Type=simple
ExecStart=${DASHBOARD_DEST}/venv/bin/python3 ${DASHBOARD_DEST}/server.py
WorkingDirectory=${DASHBOARD_DEST}
Restart=always
RestartSec=5
Environment=PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
StandardOutput=append:${CORTEX_DEPLOY_HOME}/logs/cortex-dashboard.log
StandardError=append:${CORTEX_DEPLOY_HOME}/logs/cortex-dashboard.log

[Install]
WantedBy=default.target
SYSTEMDEOF
  fi
  systemctl --user daemon-reload 2>/dev/null || true
  systemctl --user enable hermes-cortex-dashboard 2>/dev/null || true
  systemctl --user restart hermes-cortex-dashboard 2>/dev/null || true
  if systemctl --user is-active --quiet hermes-cortex-dashboard; then
   ok
   info " Dashboard running at http://localhost:8901"
  else
   warn "Dashboard service may not be running — check: systemctl --user status hermes-cortex-dashboard"
  fi
 fi
fi

if [[ "$CORTEX_OS" == "macos" ]]; then
 # Install Docker Desktop launchd agent (auto-start on login)
 DOCKER_PLIST="${CORTEX_HOME}/Library/LaunchAgents/com.docker.docker.plist"
 if launchctl list com.docker.docker &>/dev/null 2>&1; then
  info " Docker launch agent already loaded"
 elif [[ ! -f "$DOCKER_PLIST" ]]; then
  DOCKER_TEMPLATE="${SCRIPT_DIR}/docs/templates/com.docker.docker.plist"
  if [[ -f "$DOCKER_TEMPLATE" ]]; then
   sed "s|CORTEX_HOME|${CORTEX_HOME}|g" "$DOCKER_TEMPLATE" > "$DOCKER_PLIST"
  else
   cat > "$DOCKER_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.docker.docker</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Applications/Docker.app/Contents/MacOS/Docker</string>
    <string>--unattended</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <false/>
  <key>StandardOutPath</key>
  <string>${CORTEX_HOME}/.hermes-cortex/logs/docker-launch.log</string>
  <key>StandardErrorPath</key>
  <string>${CORTEX_HOME}/.hermes-cortex/logs/docker-launch.log</string>
</dict>
</plist>
PLIST
  fi
  chmod 644 "$DOCKER_PLIST"
  launchctl load "$DOCKER_PLIST" 2>&1
  info " Docker Desktop auto-start on login configured"
 fi

 # Install health server launchd agent (self-monitoring API)
 HEALTH_PLIST="${CORTEX_HOME}/Library/LaunchAgents/com.hermes.health-server.plist"
 HEALTH_SRC="$(_scripts)/com.hermes.health-server.plist"
 if [[ ! -f "$HEALTH_PLIST" ]]; then
  if [[ -f "$HEALTH_SRC" ]]; then
   sed "s|CORTEX_HOME|${CORTEX_HOME}|g" "$HEALTH_SRC" > "$HEALTH_PLIST"
   chmod 644 "$HEALTH_PLIST"
   launchctl load "$HEALTH_PLIST" 2>&1
   info " Health server launch agent installed"
  fi
 elif launchctl list com.hermes.health-server &>/dev/null 2>&1; then
  info " Health server launch agent already loaded"
 fi
elif [[ "$CORTEX_OS" == "linux" ]]; then
 # Install health server systemd user service (self-monitoring API)
 SYSTEMD_DIR="${HOME}/.config/systemd/user"
 HEALTH_SERVICE_SRC="$(_scripts)/com.hermes.health-server.service"
 HEALTH_SERVICE_DST="${SYSTEMD_DIR}/com.hermes.health-server.service"
 mkdir -p "$SYSTEMD_DIR"
 if [[ -f "$HEALTH_SERVICE_SRC" ]]; then
  cp "$HEALTH_SERVICE_SRC" "$HEALTH_SERVICE_DST"
  chmod 644 "$HEALTH_SERVICE_DST"
  systemctl --user daemon-reload 2>/dev/null
  if ! systemctl --user is-enabled com.hermes.health-server &>/dev/null 2>&1; then
   systemctl --user enable com.hermes.health-server 2>&1
   systemctl --user start com.hermes.health-server 2>&1
   info " Health server systemd service installed and started"
  else
   info " Health server systemd service already enabled"
  fi
 fi

 # Docker daemon is managed by the system's init — just verify it's available
 if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
  info " Docker daemon is running (managed by systemd)"
 else
  warn "Docker not detected or not running. Install it: https://docs.docker.com/engine/install/"
 fi
fi

else
 skip "Langfuse + Dashboard (non-server profile — Docker not required)"
fi

# ─────────────────────────────────────────────────────────────
# 13. Offline Knowledge Tools — cache cascade + ZIM content
# ─────────────────────────────────────────────────────────────
step "Installing offline knowledge tools (cache cascade + ZIM viewer)"

OFFLINE_REPO="${SCRIPT_DIR}/../ops/offline"
OFFLINE_DEST="${CORTEX_DEPLOY_HOME}/offline"

if [[ -d "$OFFLINE_REPO" ]]; then
 mkdir -p "$OFFLINE_DEST" "$HERMES_BIN"

 # Copy offline knowledge cascade tool
 cp "${OFFLINE_REPO}/offline_knowledge.py" "$OFFLINE_DEST/"
 chmod +x "${OFFLINE_DEST}/offline_knowledge.py"
 cp "${OFFLINE_REPO}/lessons.py" "$OFFLINE_DEST/"
 chmod +x "${OFFLINE_DEST}/lessons.py" 2>/dev/null
 cp "${OFFLINE_REPO}/offline_knowledge.sh" "$OFFLINE_DEST/"
 chmod +x "${OFFLINE_DEST}/offline_knowledge.sh"
 ln -sf "${OFFLINE_DEST}/offline_knowledge.sh" "${HERMES_BIN}/offline_knowledge"
 info " Installed offline knowledge cascade tool + lesson database"

 # Copy project-map tool
 PROJECT_MAP_REPO="$(dirname "$SCRIPT_DIR")/scripts/project-map"
 if [[ -d "$PROJECT_MAP_REPO" ]]; then
  cp "${PROJECT_MAP_REPO}/project_map.py" "$OFFLINE_DEST/"
  chmod +x "${OFFLINE_DEST}/project_map.py"
  cp "${PROJECT_MAP_REPO}/project_map.sh" "$OFFLINE_DEST/"
  chmod +x "${OFFLINE_DEST}/project_map.sh"
  ln -sf "${OFFLINE_DEST}/project_map.sh" "${HERMES_BIN}/project-map"
  info " Installed project-map static analyzer"
 fi

 # Copy session-mine tool
 if [[ -f "${OFFLINE_REPO}/session_mine.py" ]]; then
  cp "${OFFLINE_REPO}/session_mine.py" "$OFFLINE_DEST/"
  chmod +x "${OFFLINE_DEST}/session_mine.py"
  cp "${OFFLINE_REPO}/session_mine.sh" "$OFFLINE_DEST/"
  chmod +x "${OFFLINE_DEST}/session_mine.sh"
  ln -sf "${OFFLINE_DEST}/session_mine.sh" "${HERMES_BIN}/session-mine"
  info " Installed session-mining tool (lesson bootstrapping)"
 fi

 # Copy kiwix Docker compose file
 cp "${OFFLINE_REPO}/kiwix-docker-compose.yml" "$OFFLINE_DEST/"
 info " Installed kiwix-serve Docker compose"

 # Copy prep-offline script
 cp "${OFFLINE_REPO}/prep-offline.sh" "$OFFLINE_DEST/"
 chmod +x "${OFFLINE_DEST}/prep-offline.sh"
 ln -sf "${OFFLINE_DEST}/prep-offline.sh" "${HERMES_BIN}/prep-offline"
 info " Installed prep-offline content downloader"

 # Copy SKILL.md for Hermes agent
 SKILL_DEST="${HERMES_SKILLS}/software-development"
 mkdir -p "$SKILL_DEST"
 if [[ ! -f "${SKILL_DEST}/SKILL.md" ]] || ! grep -q "offline-knowledge" "${SKILL_DEST}/SKILL.md" 2>/dev/null; then
  cp "${OFFLINE_REPO}/SKILL.md" "${SKILL_DEST}/offline-knowledge.SKILL.md" 2>/dev/null || true
 fi
 info " Installed offline-knowledge skill"

 # Create offline directories for ZIM content
 mkdir -p "${HOME}/offline/zim"

 # Prompt user to run prep-offline
 printf "\n"
 info " Offline tools installed."
 info " To download ZIM content (Wikipedia, WikiMed, Wikivoyage, etc.), run:"
 info "  ${HERMES_BIN}/prep-offline"
 info " Or with a preset:"
 info "  ${HERMES_BIN}/prep-offline --mode=travel  # Jungle/vacation bundle (~6 GB)"
 info "  ${HERMES_BIN}/prep-offline --mode=build   # Dev offline bundle (~7 GB)"
 info "  ${HERMES_BIN}/prep-offline --mode=education # Kid learning bundle (~5 GB)"
 printf "\\n"

 # Build offline code search index immediately
 if [[ -f "${OFFLINE_DEST}/prep-code.sh" ]]; then
  info " Building offline code search index…"
  bash "${OFFLINE_DEST}/prep-code.sh" 2>/dev/null && info " Code index built" || warn "Code index build skipped (no source files)"
 elif [[ -f "${OFFLINE_REPO}/prep-code.sh" ]]; then
  info " Building offline code search index…"
  bash "${OFFLINE_REPO}/prep-code.sh" 2>/dev/null && info " Code index built" || warn "Code index build skipped (no source files)"
 fi
 printf "\\n"
 ok
else
 skip "no offline/ directory in repo"
fi

# ─────────────────────────────────────────────────────────────
# 14. nginx — Reverse proxy for Langfuse + Dashboard
# ─────────────────────────────────────────────────────────────
if [[ "$CORTEX_PROFILE" == "server" ]]; then
step "Installing nginx reverse proxy"
bash "$(_scripts)/install-nginx.sh"
ok
else
 skip "nginx (non-server profile — not needed)"
fi

# ─────────────────────────────────────────────────────────────
# 15. Enable Hermes Plugin
# ─────────────────────────────────────────────────────────────
step "Enabling gbrain-command plugin in Hermes config"

HERMES_CONFIG="${CORTEX_DEPLOY_HOME}/config.yaml"
if [[ -f "$HERMES_CONFIG" ]]; then
 # Check if plugin is already enabled
 if grep -q "gbrain-command" "$HERMES_CONFIG" 2>/dev/null; then
  skip "plugin already enabled in config"
 else
  # Add gbrain-command to the plugins enabled list
  if grep -q "plugins:" "$HERMES_CONFIG"; then
   # Insert into existing plugins section
   sed -i '' 's/\(enabled:.*\)/\1\n - gbrain-command/' "$HERMES_CONFIG" 2>/dev/null || \
    warn "Could not auto-edit config.yaml. Manually add 'gbrain-command' under plugins.enabled"
  else
   warn "Could not find plugins section in config.yaml. Manually add:"
   warn " plugins:"
   warn "  enabled:"
   warn "  - gbrain-command"
  fi
  ok
 fi
else
 warn "config.yaml not found at ${HERMES_CONFIG}. Plugin files are installed but not enabled."
 warn "Manually add 'gbrain-command' under plugins.enabled in your Hermes config."
fi

# ─────────────────────────────────────────────────────────────
# 16. File Permission Hardening
# ─────────────────────────────────────────────────────────────
step "Hardening file permissions on sensitive files"
# Langfuse .env (already 600 from creation, but double-check)
if [[ -f "${LANGFUSE_DIR}/.env" ]]; then
 chmod 600 "${LANGFUSE_DIR}/.env" 2>/dev/null && info " Locked langfuse .env"
fi

# Hermes config
if [[ -f "$HERMES_CONFIG" ]]; then
 chmod 600 "$HERMES_CONFIG" 2>/dev/null && info " Locked hermes config.yaml"
fi

# State database
if [[ -f "${CORTEX_DEPLOY_HOME}/state.db" ]]; then
 chmod 600 "${CORTEX_DEPLOY_HOME}/state.db" 2>/dev/null && info " Locked state.db"
fi

# Any .env files in home or brain dirs
find "${CORTEX_HOME}" -maxdepth 2 -name ".env" -o -name ".env.*" 2>/dev/null | while read -r envfile; do
 chmod 600 "$envfile" 2>/dev/null || true
done
info " All .env files locked down"
ok

# ─────────────────────────────────────────────────────────────
# 17. Bootstrap Brain — Verify & Index
# ─────────────────────────────────────────────────────────────
step "Bootstrapping brain sources (verify + index)"
BOOTSTRAP_SCRIPT="${SCRIPTS_DIR}/bootstrap-brain.sh"
if [[ -f "$BOOTSTRAP_SCRIPT" ]]; then
 bash "$BOOTSTRAP_SCRIPT" --check-only 2>&1 | sed 's/^/ /'
 # If some sources have 0 pages, suggest running full bootstrap
 if bash "$BOOTSTRAP_SCRIPT" --check-only 2>&1 | grep -q "0 pages"; then
  warn "Some brain sources have 0 indexed pages. Run:"
  warn " bash ~/.hermes-cortex/scripts/bootstrap-brain.sh"
  warn " This will init git repos, register gbrain sources, and sync."
 else
  info "All brain sources are healthy and searchable"
 fi
else
 warn "bootstrap-brain.sh not found — skipping"
fi
ok

# ─────────────────────────────────────────────────────────────
# 18. Summary & Next Steps
# ─────────────────────────────────────────────────────────────
header "INSTALLATION SUMMARY"

printf "\n${BOLD}✅ System components installed${RESET}\n"
printf " ${GREEN}•${RESET} Ollama      — LLM server (embedding: nomic-embed-text:v1.5)\n"
printf " ${GREEN}•${RESET} Bun       — JS runtime\n"
printf " ${GREEN}•${RESET} gbrain      — Knowledge brain (Postgres + pgvector)\n"
if [[ "$CORTEX_PROFILE" == "server" ]]; then
printf " ${GREEN}•${RESET} Langfuse     — LLM observability (Docker, port 3000)\n"
printf " ${GREEN}•${RESET} Cortex Dashboard — Flask companion app (port 8901)\n"
printf " ${GREEN}•${RESET} nginx      — Reverse proxy (ports 13001-13002)\\n"
fi
printf " ${GREEN}•${RESET} Brain sources  → ${BRAIN_DIR}/{%s}\n" "$(echo "${SOURCES[*]}" | tr ' ' ',')"
printf " ${GREEN}•${RESET} gbrain plugin  → /brain slash command\n"
printf " ${GREEN}•${RESET} heartbeat.py   → system health watchdog\n"
printf " ${GREEN}•${RESET} memory-to-brain-sync.py → memory sync to gbrain\\n"
printf " ${GREEN}•${RESET} bootstrap-brain.sh → post-install brain verification\n"
printf " ${GREEN}•${RESET} seed-project-brain.sh → one-command brain seeding from repos\n"
printf " ${GREEN}•${RESET} cortex-health.sh  → single green-check system readiness\n"
printf " ${GREEN}•${RESET} cortex-setup-langfuse.sh → standalone Langfuse .env generator\n"
printf " ${GREEN}•${RESET} cortex-update.sh → git pull + delta-update + service restart\\n"
printf " ${GREEN}•${RESET} hermes-update.sh → daily Hermes Agent upgrade (no_agent watchdog)\\n"
printf " ${GREEN}•${RESET} hermes-cortex-sync.sh → daily repo sync + tool re-install\\n"
printf " ${GREEN}•${RESET} prod-watchdog.sh → production site monitoring with auto-remediation\\n"
printf " ${GREEN}•${RESET} check-memory-budget.sh → MEMORY.md usage monitor\n"
printf " ${GREEN}•${RESET} memory seeds   → ~/.hermes/memories/{MEMORY,USER}.md\\n"
printf " ${GREEN}•${RESET} Hermes skills  → 12+ shared skills in ~/.hermes-cortex/skills/\\n"
printf " ${GREEN}•${RESET} Web Cache    → semantic web result cache (sqlite-vec + Ollama)\n"
printf " ${GREEN}•${RESET} Offline Knowledge → cascade cache + kiwix ZIM content viewer\n"
printf " ${GREEN}•${RESET} Launchd services:\n"
printf "          com.ollama.serve\n"
printf "          com.gbrain.sync-watch (or com.gbrain.autopilot if present)\n"
if [[ "$CORTEX_PROFILE" == "server" ]]; then
printf "          com.docker.docker\n"
printf "          com.hermes.cortex-dashboard\n"
printf "          homebrew.mxcl.nginx\n"
fi
printf "\n"

printf "${BOLD}${YELLOW}⚠ Next Steps — give this prompt to your Hermes Agent:${RESET}\n"
printf "%s${BOLD}${CYAN}" "───────────────────────────────────────────────────"
cat <<PROMPT

I've installed the Hermes Cortex system. Please finish the setup by:

1. Open ~/.hermes/memories/MEMORY.md and ~/.hermes/memories/USER.md — fill in your system topology and user profile so I know your context
2. Load the shared skills from ~/.hermes-cortex/skills/ (use skill_view(name) to browse them — includes subagent-driven-development, systematic-debugging v2.0 (6-phase feedback-loop debugging), code-review v3.0 (two-axis Standards+Spec), codebase-design (deep module vocabulary), change-test-loop, spike, plan, memory-architecture, client-brand-brand-marketing, korean-language-learning)
3. Loading the hermes-agent skill and verifying the gbrain-command plugin
4. Run ~/.hermes-cortex/scripts/bootstrap-brain.sh to ensure all brain sources are initialized, git-enabled, registered in gbrain, and synced. Note which sources have indexed pages (if any show 0 pages, add some .md files and re-sync)
5. If using Langfuse, run: bash ~/.hermes-cortex/scripts/cortex-setup-langfuse.sh --start (generates all required .env secrets and starts Docker Compose — no more failing on :? expansion)
6. Seed project brains from existing repos: ~/.hermes-cortex/scripts/seed-project-brain.sh --all (finds matching repos under ~/Developer/AI/ and fills their brain dirs with README/docs — one command from empty shell to indexed knowledge)
7. Run cortex-health.sh to confirm everything is green: bash ~/.hermes-cortex/scripts/cortex-health.sh (prints a clean status table for Ollama, Langfuse, gbrain, sync daemon, memory freshness, disk usage — exits 0 when all systems go)
8. Setting up these cron jobs (use the cronjob tool):

  a) gbrain-nightly-dream — daily at 3am:
   Schedule: 0 3 * * *
   Prompt: Run gbrain maintenance: cd ~ && ~/.bun/bin/bun ~/.bun/bin/gbrain sync --all --parallel 4 --no-pull && ~/.bun/bin/bun ~/.bun/bin/gbrain dream
   Workdir: ~

  b) system-heartbeat — every 30 minutes:
   Schedule: */30 * * * *
   Script: heartbeat.py
   no_agent: true

  c) memory-to-brain-sync — every 6 hours:
   Schedule: 0 */6 * * *
   Script: memory-to-brain-sync.py
   no_agent: true

  d) memory-budget-check — daily at 5am:
   Schedule: 0 5 * * *
   Script: check-memory-budget.sh
   no_agent: true

  e) memory-pruning — daily at 4am:
   Schedule: 0 4 * * *
   Prompt: Read your current MEMORY.md and USER.md from ~/.hermes/memories/ and prune/consolidate entries that are stale, redundant, or no longer relevant. Keep useful durable facts. Report what you removed and why.

  f) cortex-update — weekly on Sunday at 3am (auto-pull + delta-update):
   Schedule: 0 3 * * 0
   Prompt: Run cortex-update to keep the system current: bash ~/.hermes-cortex/scripts/cortex-update.sh
   no_agent: true

  g) daily-lesson-mine — daily at 2am (auto-mining from last 24h):
   Schedule: 0 2 * * *
   Script: daily-lesson-mine.sh
   no_agent: true
   Self-muting: only delivers output when new lessons are saved

  h) lesson-compound-stats — daily at 2:30am (report after mining):
   Schedule: 30 2 * * *
   Script: lesson-compound-stats.py --brief
   no_agent: true
   Output: "📊 135 lessons · 135 applications · ~33.8h saved · 7 languages"

9. Run /reset or /new to activate the /brain slash command
10. Verify brain ingestion: run "gbrain query hello" then "gbrain query --source <name> hello" — you should see different results per source if sources have content
11. (Optional) Check detailed heartbeat: bash ~/.hermes-cortex/scripts/heartbeat.py --report — watch how service status changes as you configure things

PROMPT
printf "${RESET}${BOLD}${CYAN}───────────────────────────────────────────────────${RESET}\n"

printf "\n${BOLD}📚 Quick Reference${RESET}\n"
if [[ "$CORTEX_PROFILE" == "server" ]]; then
printf " ${GREEN}•${RESET} Langfuse:    http://localhost:3000 (nginx: :13002)\\n"
printf " ${GREEN}•${RESET} Cortex Dashboard: http://localhost:8901 (nginx: :13001)\n"
printf " ${GREEN}•${RESET} 🔒 Security:   Read docs/SECURITY.md for firewall + hardening\n"
printf " ${GREEN}•${RESET} Langfuse setup:  bash cortex-setup-langfuse.sh --start (generates .env + starts)\n"
printf " ${GREEN}•${RESET} System health:  bash cortex-health.sh (green-check status)\n"
printf " ${GREEN}•${RESET} System update:  bash cortex-update.sh (pull + delta-update)\n"
fi
printf " ${GREEN}•${RESET} /brain query   — search your knowledge brain\n"
printf " ${GREEN}•${RESET} Offline query:  offline_knowledge query \"question\"\n"
printf " ${GREEN}•${RESET} Download ZIM:  prep-offline\n"
printf " ${GREEN}•${RESET} Brain dirs:   %s\n" "${BRAIN_DIR}"
printf " ${GREEN}•${RESET} Logs:      %s/logs/\n" "${CORTEX_DEPLOY_HOME}"
printf " ${GREEN}•${RESET} Scripts:     %s/scripts/\n" "${SCRIPTS_DIR}"

printf "\n${BOLD}🐚 For daily use in shell:${RESET}\n"
printf " Add to ~/.zshrc or ~/.bash_profile:\n"
printf "${YELLOW} export PATH=\"\$HOME/.bun/bin:\$HOME/.hermes-cortex/bin:\$PATH\"${RESET}\n"

# ─────────────────────────────────────────────────────────────
# Security Warnings
# ─────────────────────────────────────────────────────────────
printf "\n"
printf "${RED}${BOLD}━━━ SECURITY NOTES — PLEASE READ ━━━${RESET}\n"
printf "\n"
printf "${YELLOW}${BOLD}Important security actions for your Hermes Cortex system:${RESET}\n"
printf "\n"
printf "${BOLD} 1. Langfuse passwords${RESET}\n"
printf "   If you shared access to this machine, change all passwords in:\n"
printf "   ${YELLOW}${LANGFUSE_DIR}/.env${RESET}\n"
printf "   Generate new ones with: openssl rand -hex 32\n"
printf "\n"
printf "${BOLD} 2. Keep state.db private${RESET}\n"
printf "   ${YELLOW}~/.hermes/state.db${RESET} contains session/auth data.\n"
printf "   It is now chmod 600. Never share this file.\n"
printf "\n"
printf "${BOLD} 3. Do NOT expose services to the internet${RESET}\n"
printf "   These ports should NEVER be exposed publicly:\n"
printf "   ${YELLOW}  11434${RESET} — Ollama LLM server (local only)\n"
printf "   ${YELLOW}  3000${RESET}  — Langfuse web UI (local only)\n"
printf "   ${YELLOW}  8080${RESET}  — Any unsecured HTTP services\n"
printf "   Use nginx with HTTPS + auth if you need remote access.\n"
printf "\n"
printf "${BOLD} 4. Enable your firewall${RESET}\n"
printf "   macOS: ${YELLOW}System Settings → Network → Firewall${RESET}\n"
printf "   Linux: ${YELLOW}sudo ufw enable${RESET}\n"
printf "\n"
printf "${BOLD} 5. Read the security guide${RESET}\n"
printf "   ${YELLOW}docs/SECURITY.md${RESET} has detailed recommendations.\n"
printf "\n"
printf " ${GREEN}Stay secure!${RESET}\n"
printf "${RED}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"
printf "\n"
printf "${BOLD} ⚠️ TWO HARD RULES — Every Agent Must Follow:${RESET}\n"
printf "\n"
printf " ${BOLD}RULE 1:${RESET} USE LOOP GOVERNANCE ALWAYS\n"
printf " Every code/config/cron change requires:\n"
printf " begin_change → work → cycle_query → feedback → end_change\n"
printf " The MCP server enforces this at the tool level.\n"
printf "\n"
printf " ${BOLD}RULE 2:${RESET} SHARE IMPROVEMENTS TO THE PUBLIC REPO\n"
printf " Every improvement that benefits other agents must go\n"
printf " into the hermes-cortex repo — templates, skills, scripts,\n"
printf " docs, configs. Not just your local profile.\n"
printf "\n"

printf "\n${GREEN}${BOLD}Hermes Cortex v${VERSION} installed. Enjoy! 🧠${RESET}\n"

# Clear the EXIT trap and clean up remote temp dir

# Auto-run cortex doctor after install
DOCTOR_PATH="${CORTEX_DEPLOY_HOME:-${HOME}/.hermes-cortex}/scripts/cortex-doctor.py"
if command -v python3 &>/dev/null && [ -f "$DOCTOR_PATH" ]; then
 echo ""
 echo "━━━ Running post-install health check ━━━"
 python3 "$DOCTOR_PATH" --quiet 2>&1 || true
fi

rm -rf "${REMOTE_CLEANUP}"
trap - EXIT
