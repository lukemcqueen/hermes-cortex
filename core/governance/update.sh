#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  Loop Governance — Update Script
#  Fetches the latest scripts from hermes-cortex repo.
#
#  Usage:
#    bash update.sh              # check for updates and apply
#    bash update.sh --check      # only check version, don't update
#    bash update.sh --force      # force re-install even if same version
#
#  Uses version from VERSION file in the source directory.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
RESET='\033[0m'

pass() { printf "  ${GREEN}✓${RESET} %s\n" "$1"; }
warn() { printf "  ${YELLOW}⚠${RESET} %s\n" "$1"; }
fail() { printf "  ${RED}✗${RESET} %s\n" "$1"; }
info() { printf "  ${BLUE}ℹ${RESET} %s\n" "$1"; }

CHECK_ONLY=0
FORCE=0
for arg in "$@"; do
  case "$arg" in
    --check) CHECK_ONLY=1 ;;
    --force) FORCE=1 ;;
  esac
done

# ── Locate installation ────────────────────────────────────
# Try multiple locations in priority order
INSTALL_DIR=""
for dir in \
  "${HOME}/.hermes-cortex/tools/loop-governance" \
  "${HOME}/.hermes-cortex/skills/software-development/loop-governance/scripts" \
  "${HOME}/hermes-cortex/core/governance"; do
  if [[ -f "${dir}/VERSION" ]]; then
    INSTALL_DIR="$dir"
    break
  fi
done

if [[ -z "$INSTALL_DIR" ]]; then
  fail "Loop governance installation not found."
  info "Clone hermes-cortex first:"
  info "  git clone https://github.com/lukemcqueen/hermes-cortex.git ~/hermes-cortex"
  info "  cd ~/hermes-cortex && bash install.sh"
  exit 1
fi

CURRENT_VERSION=$(cat "${INSTALL_DIR}/VERSION" 2>/dev/null || echo "0.0.0")
INSTALL_BACKUP="${INSTALL_DIR}/.backup-${CURRENT_VERSION}"

echo ""
echo "═ Loop Governance Update ═"
echo ""
info "Current install: ${INSTALL_DIR}"
info "Current version: ${CURRENT_VERSION}"
echo ""

# ── Determine source (repo or GitHub) ──────────────────────
REPO_DIR="${HOME}/hermes-cortex/core/governance"

if [[ -d "$REPO_DIR" && -f "${REPO_DIR}/VERSION" ]]; then
  # Local repo clone
  SOURCE_TYPE="local"
  SOURCE_DIR="$REPO_DIR"
  SOURCE_VERSION=$(cat "${REPO_DIR}/VERSION")
  info "Source: local repo ($REPO_DIR)"
else
  # Try to download from GitHub
  SOURCE_TYPE="remote"
  SOURCE_VERSION=$(curl -fsSL "https://raw.githubusercontent.com/lukemcqueen/hermes-cortex/main/core/governance/VERSION" 2>/dev/null || echo "0.0.0")
  info "Source: github.com/lukemcqueen/hermes-cortex"
fi

info "Available version: ${SOURCE_VERSION}"
echo ""

# ── Version comparison ─────────────────────────────────────
if [[ "$CURRENT_VERSION" == "$SOURCE_VERSION" && "$FORCE" != "1" ]]; then
  pass "Already at latest version ${CURRENT_VERSION}"
  if [[ "$CHECK_ONLY" == "1" ]]; then
    echo ""
    pass "Up to date"
    exit 0
  fi
  echo ""
  info "Use --force to re-install: bash update.sh --force"
  exit 0
fi

if [[ "$CHECK_ONLY" == "1" ]]; then
  echo ""
  info "Update available: ${CURRENT_VERSION} → ${SOURCE_VERSION}"
  info "Run without --check to apply: bash update.sh"
  exit 0
fi

# ── Backup current ──────────────────────────────────────────
info "Backing up current version to ${INSTALL_BACKUP}"
mkdir -p "$INSTALL_BACKUP"
cp "${INSTALL_DIR}"/*.py "$INSTALL_BACKUP"/ 2>/dev/null || true
cp "${INSTALL_DIR}"/*.sh "$INSTALL_BACKUP"/ 2>/dev/null || true
cp "${INSTALL_DIR}/VERSION" "$INSTALL_BACKUP"/ 2>/dev/null || true
pass "Backup saved"

# ── Apply update ────────────────────────────────────────────
if [[ "$SOURCE_TYPE" == "local" ]]; then
  info "Copying from local repo…"
  # Copy Python scripts
  for f in "${SOURCE_DIR}"/*.py; do
    cp "$f" "${INSTALL_DIR}/"
    pass "  $(basename "$f")"
  done
  # Copy shell scripts
  for f in "${SOURCE_DIR}"/*.sh; do
    cp "$f" "${INSTALL_DIR}/"
    chmod +x "${INSTALL_DIR}/$(basename "$f")"
    pass "  $(basename "$f")"
  done
  # Copy VERSION
  cp "${SOURCE_DIR}/VERSION" "${INSTALL_DIR}/"
  pass "  VERSION"
else
  # Remote: download tarball and extract
  info "Downloading from GitHub…"
  TMP_DIR=$(mktemp -d)
  curl -fsSL "https://github.com/lukemcqueen/hermes-cortex/archive/refs/heads/main.tar.gz" | \
    tar -xz -C "$TMP_DIR" --strip-components=3 "hermes-cortex-main/core/governance/" 2>/dev/null || {
    fail "Download failed. Check internet or mirror."
    rm -rf "$TMP_DIR"
    info "Restoring from backup…"
    cp "${INSTALL_BACKUP}"/*.py "${INSTALL_DIR}"/ 2>/dev/null || true
    cp "${INSTALL_BACKUP}"/*.sh "${INSTALL_DIR}"/ 2>/dev/null || true
    cp "${INSTALL_BACKUP}/VERSION" "${INSTALL_DIR}"/ 2>/dev/null || true
    exit 1
  }
  # Copy to install dir
  for f in "$TMP_DIR"/*.py "$TMP_DIR"/*.sh "$TMP_DIR"/VERSION; do
    if [[ -f "$f" ]]; then
      cp "$f" "${INSTALL_DIR}/"
      chmod +x "${INSTALL_DIR}/$(basename "$f")" 2>/dev/null || true
    fi
  done
  rm -rf "$TMP_DIR"
  pass "Downloaded and extracted"
fi

# ── Update symlinks ────────────────────────────────────────
BIN_DIR="${HOME}/.local/bin"
mkdir -p "$BIN_DIR"

declare -A LINKS
LINKS["score_cycle.py"]="score-cycle"
LINKS["loop_feedback.py"]="loop-feedback"
LINKS["auto_apply.py"]="auto-apply"
LINKS["loop_config.py"]="loop-config"
LINKS["skill_miner.py"]="skill-miner-wrapper"

for src in "${!LINKS[@]}"; do
  dst_name="${LINKS[$src]}"
  src_path="${INSTALL_DIR}/${src}"
  dst_path="${BIN_DIR}/${dst_name}"
  if [[ -f "$src_path" ]]; then
    ln -sf "$src_path" "$dst_path"
    chmod +x "$dst_path" 2>/dev/null || true
    pass "Symlink: ${dst_name}"
  fi
done

# ── Run verify ──────────────────────────────────────────────
if [[ -f "${INSTALL_DIR}/verify.sh" ]]; then
  echo ""
  info "Running post-update verification…"
  bash "${INSTALL_DIR}/verify.sh" --quick 2>&1 | tail -5
fi

# ── Report ──────────────────────────────────────────────────
echo ""
echo "  ── Update complete ──"
echo ""
echo "  Old version: ${CURRENT_VERSION}"
echo "  New version: ${SOURCE_VERSION}"
echo "  Location:    ${INSTALL_DIR}"
echo ""
info "If anything broke, restore from backup:"
info "  cp ${INSTALL_BACKUP}/* ${INSTALL_DIR}/"
echo ""