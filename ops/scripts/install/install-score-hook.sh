#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  install-score-hook.sh — Deploy pre-commit hook (secondary logger)
#
#  NOTE: The MCP server (loop-gov-mcp.py) is the PRIMARY
#  enforcement layer. This hook is a secondary logger that
#  auto-scores on git commit for DB population.
#
#  Installs the pre-commit-score hook into one or more git
#  repositories. Auto-detects repos under common dev dirs,
#  or accepts explicit paths.
#
#  Usage:
#    bash install-score-hook.sh                          # auto-detect + install
#    bash install-score-hook.sh --list                   # show detected repos
#    bash install-score-hook.sh --path ~/my/project      # specific repo
#    bash install-score-hook.sh --all                    # scan all known projects
#    bash install-score-hook.sh --remove                 # remove hooks
#    bash install-score-hook.sh --check                  # check which have hooks
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}" )" && pwd)"
HOOK_SOURCE="${SCRIPT_DIR}/pre-commit-score"
HOOK_NAME="pre-commit"
PUSH_HOOK_SOURCE="${SCRIPT_DIR}/pre-push-pull"
PUSH_HOOK_NAME="pre-push"
AUTO_SCAN_DIRS=(
  "$HOME/Developer"
  "$HOME/hermes-cortex"
  "$HOME/Sites"
)

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; RESET='\033[0m'
info()   { printf "${GREEN}✓${RESET} %s\n" "$*"; }
warn()   { printf "${YELLOW}⚠${RESET} %s\n" "$*"; }
error()  { printf "${RED}✗${RESET} %s\n" "$*"; }

INSTALLED=0
SKIPPED=0
REMOVED=0
MODE="install"

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --list|--check) MODE="list"; shift ;;
      --remove) MODE="remove"; shift ;;
      --path) MODE="install-path"; TARGET_PATH="$2"; shift 2 ;;
      --all) MODE="install-all"; shift ;;
      *) error "Unknown option: $1"; exit 1 ;;
    esac
  done
}
parse_args "$@"

# Verify hook source exists
if [[ ! -f "$HOOK_SOURCE" ]]; then
  # Try relative to repo root
  HOOK_SOURCE="${HOME}/hermes-cortex/ops/scripts/pre-commit-score"
fi
if [[ ! -f "$HOOK_SOURCE" ]]; then
  error "Hook template not found at pre-commit-score"
  error "Expected at: ${HOOK_SOURCE}"
  exit 1
fi

# ── Find git repos ──────────────────────────────────────────
find_repos() {
  local dir="${1:-.}"
  find "$dir" -maxdepth 4 -type d -name ".git" -not -path "*/node_modules/*" \
    -not -path "*/.venv/*" -not -path "*/__pycache__/*" \
    -not -path "*/.hermes*" -not -path "*/brain/*" \
    -not -path "*/.bun/*" -not -path "*/go/pkg/*" \
    -exec dirname {} \; 2>/dev/null || true
}

install_hook() {
  local repo="$1"
  local hook_dest="${repo}/.git/hooks/${HOOK_NAME}"

  # Check if core.hooksPath is set for this repo — if so, install there instead
  local hooks_dir
  hooks_dir=$(git -C "$repo" config --get core.hooksPath 2>/dev/null || true)
  if [[ -n "$hooks_dir" ]]; then
    # Expand $HOME if present in the path
    hooks_dir="${hooks_dir/#\~/$HOME}"
    hook_dest="${hooks_dir}/${HOOK_NAME}"
  fi

  # Check if hook already exists and is up to date
  if [[ -f "$hook_dest" ]]; then
    if grep -q "pre-commit-score" "$hook_dest" 2>/dev/null; then
      # Already installed — check if source is newer
      if [[ "$HOOK_SOURCE" -nt "$hook_dest" ]]; then
        cp "$HOOK_SOURCE" "$hook_dest"
        chmod +x "$hook_dest"
        info "Updated hook: $(basename "$repo")"
        INSTALLED=$((INSTALLED + 1))
      else
        SKIPPED=$((SKIPPED + 1))
      fi
      return
    fi
  fi

  cp "$HOOK_SOURCE" "$hook_dest"
  chmod +x "$hook_dest"
  info "Installed hook: $(basename "$repo")"
  INSTALLED=$((INSTALLED + 1))
}

# ── Install pre-push hook ───────────────────────────────
install_push_hook() {
  local repo="$1"
  local push_dest="${repo}/.git/hooks/${PUSH_HOOK_NAME}"

  # Respect core.hooksPath for push hook too
  local hooks_dir
  hooks_dir=$(git -C "$repo" config --get core.hooksPath 2>/dev/null || true)
  if [[ -n "$hooks_dir" ]]; then
    hooks_dir="${hooks_dir/#\~/$HOME}"
    push_dest="${hooks_dir}/${PUSH_HOOK_NAME}"
  fi

  if [[ ! -f "$PUSH_HOOK_SOURCE" ]]; then
    return
  fi

  if [[ -f "$push_dest" ]]; then
    if grep -q "pre-push-pull" "$push_dest" 2>/dev/null; then
      if [[ "$PUSH_HOOK_SOURCE" -nt "$push_dest" ]]; then
        cp "$PUSH_HOOK_SOURCE" "$push_dest"
        chmod +x "$push_dest"
        info "Updated push hook: $(basename "$repo")"
        INSTALLED=$((INSTALLED + 1))
      fi
      return
    fi
  fi

  cp "$PUSH_HOOK_SOURCE" "$push_dest"
  chmod +x "$push_dest"
  info "Installed push hook: $(basename "$repo")"
  INSTALLED=$((INSTALLED + 1))
}

remove_hook() {
  local repo="$1"
  local hook_dest="${repo}/.git/hooks/${HOOK_NAME}"

  if [[ -f "$hook_dest" ]] && grep -q "pre-commit-score" "$hook_dest" 2>/dev/null; then
    rm "$hook_dest"
    info "Removed hook: $(basename "$repo")"
    REMOVED=$((REMOVED + 1))
  fi

  # Also remove pre-push hook
  local push_dest="${repo}/.git/hooks/${PUSH_HOOK_NAME}"
  if [[ -f "$push_dest" ]] && grep -q "pre-push-pull" "$push_dest" 2>/dev/null; then
    rm "$push_dest"
    info "Removed push hook: $(basename "$repo")"
  fi
}

list_hooks() {
  local repo="$1"
  local hook_dest="${repo}/.git/hooks/${HOOK_NAME}"
  local name
  name=$(basename "$repo")

  if [[ -f "$hook_dest" ]] && grep -q "pre-commit-score" "$hook_dest" 2>/dev/null; then
    echo "  ✅  $name"
  else
    echo "  ❌  $name"
  fi
}

# ── Dispatch ─────────────────────────────────────────────────
if [[ "$MODE" == "list" ]]; then
  echo ""
  echo "Score hook status:"
  echo ""
  for dir in "${AUTO_SCAN_DIRS[@]}"; do
    [[ -d "$dir" ]] || continue
    while IFS= read -r repo; do
      list_hooks "$repo"
    done < <(find_repos "$dir")
  done
  exit 0
fi

if [[ "$MODE" == "remove" ]]; then
  echo ""
  echo "Removing score hooks..."
  echo ""
  for dir in "${AUTO_SCAN_DIRS[@]}"; do
    [[ -d "$dir" ]] || continue
    while IFS= read -r repo; do
      remove_hook "$repo"
    done < <(find_repos "$dir")
  done
  echo ""
  info "Removed: ${REMOVED} hook(s)"
  exit 0
fi

if [[ "$MODE" == "install-path" ]]; then
  if [[ ! -d "${TARGET_PATH}/.git" ]]; then
    error "Not a git repository: ${TARGET_PATH}"
    exit 1
  fi
  install_hook "$TARGET_PATH"
  install_push_hook "$TARGET_PATH"
  echo ""
  info "Done — installed hooks for $(basename "$TARGET_PATH")"
  exit 0
fi

# ── Default: auto-detect and install ─────────────────────────
echo ""
echo "Installing score hooks..."
echo ""
for dir in "${AUTO_SCAN_DIRS[@]}"; do
  [[ -d "$dir" ]] || continue
  while IFS= read -r repo; do
    install_hook "$repo"
  done < <(find_repos "$dir")

  # Install pre-push hook independently of pre-commit status
  while IFS= read -r repo; do
    install_push_hook "$repo"
  done < <(find_repos "$dir")
done

echo ""
info "Installed: ${INSTALLED}  |  Already current: ${SKIPPED}"
if [[ "$INSTALLED" -gt 0 ]]; then
  echo ""
  echo "  Next steps:"
  echo "    - Bypass flags (SKIP_SCORE, SKIP_PRE_PUSH) have been REMOVED."
  echo "      Use --no-verify for true emergencies only."
  echo "    - Re-run this script after cloning new repos"
  echo "    - Run with --check to see current hook status"
fi
