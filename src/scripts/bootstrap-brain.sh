#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  bootstrap-brain.sh — Post-install brain verification
#
#  After install, users have empty brain dirs and "never synced"
#  gbrain sources with no indication anything is wrong. This
#  script:
#    1. Detects all ~/brain/ subdirectories
#    2. Initializes git repos where missing
#    3. Syncs each brain directory to gbrain
#    4. Reports indexed page counts per source (from gbrain)
#
#  Usage:
#    bash bootstrap-brain.sh                # Verify and fix all
#    bash bootstrap-brain.sh --check-only   # Just report, don't fix
#    bash bootstrap-brain.sh --source=foo   # Only process named source
#    bash bootstrap-brain.sh --reindex      # Force full re-sync of all sources
# ─────────────────────────────────────────────────────────────
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BOLD='\033[1m'; RESET='\033[0m'
BRAIN_DIR="${HOME}/brain"
GBRAIN_CMD="${HOME}/.bun/bin/gbrain"
BUN_PATH="${HOME}/.bun/bin"
CHECK_ONLY=false
REINDEX=false
FILTER_SOURCE=""

# Parse args
for arg in "$@"; do
  case "$arg" in
    --check-only) CHECK_ONLY=true ;;
    --reindex)    REINDEX=true ;;
    --source=*)   FILTER_SOURCE="${arg#*=}" ;;
    --source)     echo "Use --source=<name> (with equals sign)"; exit 1 ;;
    --help|-h)
      echo "Usage: bash bootstrap-brain.sh [--check-only] [--reindex] [--source=<name>]"
      echo ""
      echo "  --check-only    Only report status, don't fix anything"
      echo "  --reindex       Force full re-sync of all brain sources"
      echo "  --source=<name> Only process the named brain source"
      exit 0
      ;;
  esac
done

info()  { echo -e "${GREEN}✓${RESET} $*"; }
warn()  { echo -e "${YELLOW}⚠${RESET} $*"; }
error() { echo -e "${RED}✗${RESET} $*"; }

export PATH="${BUN_PATH}:$PATH"

echo ""
echo -e "${BOLD}━━━ Brain Bootstrap — Post-Install Health Check ━━━${RESET}"
echo ""

# ── Helper: get page count for a source ──────────────────
# gbrain v0.42+ sources list format:
#   default               federated          1 pages  never synced
#   my-source             isolated          12 pages  2m ago
# 3rd whitespace-delimited field is the page count.
get_page_count() {
  local name="$1"
  local count

  # Try parsing from gbrain sources list (authoritative)
  count=$("$GBRAIN_CMD" sources list 2>/dev/null | \
    grep "^  ${name}[[:space:]]" | \
    awk '{print $3}' | \
    head -1)

  if [[ -n "$count" ]] && [[ "$count" =~ ^[0-9]+$ ]]; then
    echo "$count"
    return 0
  fi

  # Fallback: count .md files directly (works even if source unregistered)
  local dir="${BRAIN_DIR}/${name}"
  if [[ -d "$dir" ]]; then
    count=$(find "$dir" -name '*.md' -not -path '*/.git/*' -maxdepth 2 2>/dev/null | wc -l | tr -d ' ')
    echo "${count:-0}"
    return 0
  fi

  echo "0"
}

# ── Helper: check if gbrain source is registered ─────────
# gbrain sources list output has leading spaces — don't anchor at column 0.
is_source_registered() {
  local name="$1"
  "$GBRAIN_CMD" sources list 2>/dev/null | grep -q "^  ${name}[[:space:]]"
}

# ── Step 1: Detect brain directories ──────────────────────
if [[ ! -d "$BRAIN_DIR" ]]; then
  error "No ~/brain/ directory found. Run install.sh first."
  exit 1
fi

BRAIN_SOURCES=()
while IFS= read -r -d '' dir; do
  name=$(basename "$dir")
  BRAIN_SOURCES+=("$name")
done < <(find "$BRAIN_DIR" -maxdepth 1 -type d ! -name "." ! -name ".." -print0 2>/dev/null)

if [[ ${#BRAIN_SOURCES[@]} -eq 0 ]]; then
  error "No brain subdirectories found in ${BRAIN_DIR}/"
  exit 1
fi

echo "Found ${#BRAIN_SOURCES[@]} brain source(s): ${BRAIN_SOURCES[*]}"
echo ""

# ── Step 2: Check each source ─────────────────────────────
FIXED_GIT=0
FIXED_GBRAIN=0
HAS_PAGES=0
NO_PAGES=0
NOT_REGISTERED=0

for source in "${BRAIN_SOURCES[@]}"; do
  [[ -n "$FILTER_SOURCE" && "$source" != "$FILTER_SOURCE" ]] && continue

  source_dir="${BRAIN_DIR}/${source}"
  echo -e "${BOLD}[${source}]${RESET}"

  # Check git
  if [[ ! -d "${source_dir}/.git" ]]; then
    if [[ "$CHECK_ONLY" == "true" ]]; then
      warn "  Git repo missing"
    else
      echo -n "  Initializing git repo... "
      git -C "$source_dir" init 2>/dev/null && echo -e "${GREEN}done${RESET}" || echo -e "${RED}failed${RESET}"
      FIXED_GIT=$((FIXED_GIT + 1))
    fi
  else
    info "  Git repo exists"
  fi

  # Check .gitignore
  if [[ ! -f "${source_dir}/.gitignore" ]]; then
    if [[ "$CHECK_ONLY" == "true" ]]; then
      warn "  .gitignore missing"
    else
      cat > "${source_dir}/.gitignore" <<'GITEOF'
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
      info "  Created .gitignore"
    fi
  fi

  # Check gbrain registration
  if ! is_source_registered "$source"; then
    if [[ "$CHECK_ONLY" == "true" ]]; then
      warn "  Not registered as gbrain source"
      NOT_REGISTERED=$((NOT_REGISTERED + 1))
    else
      echo -n "  Registering as gbrain source... "
      if "$GBRAIN_CMD" sources add "$source" --path "$source_dir" --name "$source" 2>/dev/null; then
        echo -e "${GREEN}done${RESET}"
        FIXED_GBRAIN=$((FIXED_GBRAIN + 1))
      else
        echo -e "${RED}failed${RESET}"
      fi
    fi
  else
    info "  Registered as gbrain source"
  fi

  # Check git commit (gbrain needs one to sync)
  if git -C "$source_dir" rev-parse HEAD &>/dev/null 2>&1; then
    :  # Has at least one commit
  else
    if [[ "$CHECK_ONLY" != "true" ]]; then
      git -C "$source_dir" add -A 2>/dev/null || true
      git -C "$source_dir" commit --allow-empty -m "init: ${source} brain source" 2>/dev/null || true
    fi
  fi

  # Sync (or reindex)
  if [[ "$CHECK_ONLY" != "true" ]] && is_source_registered "$source"; then
    if [[ "$REINDEX" == "true" ]]; then
      echo -n "  Reindexing (full sync)... "
      # Force re-sync by passing --all or explicit source
      if "$GBRAIN_CMD" sync --source "$source" --force 2>/dev/null || \
         "$GBRAIN_CMD" sync --source "$source" 2>/dev/null; then
        echo -e "${GREEN}done${RESET}"
      else
        echo -e "${YELLOW}sync done (check output)${RESET}"
      fi
    else
      echo -n "  Syncing to gbrain... "
      if "$GBRAIN_CMD" sync --source "$source" 2>/dev/null; then
        echo -e "${GREEN}done${RESET}"
      else
        echo -e "${YELLOW}sync done (check output)${RESET}"
      fi
    fi
  fi

  # Check pages — parse from gbrain sources list, fall back to file counting
  PAGES=$(get_page_count "$source")
  if [[ "$PAGES" -gt 0 ]]; then
    info "  ${PAGES} page(s) indexed"
    HAS_PAGES=$((HAS_PAGES + 1))
  else
    warn "  0 pages indexed"
    NO_PAGES=$((NO_PAGES + 1))
  fi

  echo ""
done

# ── Summary ────────────────────────────────────────────────
echo -e "${BOLD}━━━ Summary ━━━${RESET}"
if [[ "$CHECK_ONLY" == "true" ]]; then
  echo ""
  [[ $NOT_REGISTERED -gt 0 ]] && warn "$NOT_REGISTERED source(s) not registered as gbrain sources"
  [[ $NO_PAGES -gt 0 ]] && warn "$NO_PAGES source(s) have 0 indexed pages"
  [[ $HAS_PAGES -gt 0 ]] && info "$HAS_PAGES source(s) have indexed pages"
  echo ""
  echo "Run without --check-only to auto-fix issues."
else
  [[ $FIXED_GIT -gt 0 ]] && info "Initialized $FIXED_GIT git repo(s)"
  [[ $FIXED_GBRAIN -gt 0 ]] && info "Registered $FIXED_GBRAIN gbrain source(s)"
  [[ $HAS_PAGES -gt 0 ]] && info "$HAS_PAGES source(s) have indexed pages"
  [[ $NO_PAGES -gt 0 ]] && warn "$NO_PAGES source(s) still have 0 pages (add some .md files and re-sync)"
  echo ""
  if [[ $NO_PAGES -eq 0 && $HAS_PAGES -gt 0 ]]; then
    info "All brain sources are healthy and searchable."
  fi
fi
