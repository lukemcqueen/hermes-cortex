#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  seed-project-brain.sh — Seed empty brain dirs from project repos
#
#  After install, brain directories exist but are empty. This
#  script auto-populates them from project repository content
#  (README, ARCHITECTURE.md, docs/), registers mycortex sources,
#  and syncs them so the agent has indexed knowledge immediately.
#
#  It detects projects by:
#    1. Matching brain dir names to repos under ~/Developer/AI/<name>/
#    2. Manual --project=<name> flag
#
#  Usage:
#    bash seed-project-brain.sh --list
#    bash seed-project-brain.sh --all
#    bash seed-project-brain.sh --project=<name>
#    bash seed-project-brain.sh --project=<name> --reposcan
# ─────────────────────────────────────────────────────────────
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BOLD='\033[1m'; RESET='\033[0m'
BRAIN_DIR="${HOME}/brain"
DEV_DIR="${DEV_DIR:-${HOME}/Developer/AI}"
MYCORTEX_CLI="${HOME}/.hermes-cortex/scripts/mycortex"
BUN_PATH="${HOME}/.bun/bin"
ACTION=""
FILTER_PROJECT=""

info()  { echo -e "${GREEN}✓${RESET} $*"; }
warn()  { echo -e "${YELLOW}⚠${RESET} $*"; }
error() { echo -e "${RED}✗${RESET} $*"; }

export PATH="${BUN_PATH}:$PATH"

# Parse args
for arg in "$@"; do
  case "$arg" in
    --list)            ACTION="list" ;;
    --all)             ACTION="all" ;;
    --project=*)       FILTER_PROJECT="${arg#*=}"; ACTION="seed" ;;
    --project)         echo "Use --project=<name> (with equals sign)"; exit 1 ;;
    --reposcan)        ;;
    --help|-h)
      echo "Usage: bash seed-project-brain.sh [--list|--all|--project=<name>]"
      echo ""
      echo "  --list              List brain dirs that are empty or have matching repos"
      echo "  --all               Seed all empty brain dirs that have matching repos"
      echo "  --project=<name>    Seed a specific project brain"
      exit 0
      ;;
  esac
done

# ── Helpers ────────────────────────────────────────────────

# Count non-git, non-hidden, non-index .md files in a brain dir
count_brain_pages() {
  local dir="$1"
  find "$dir" -name '*.md' -not -path '*/.git/*' -not -name 'index.md' -maxdepth 3 2>/dev/null | wc -l | tr -d ' '
}

# Check if a mycortex source is registered (leading spaces in sources list)
is_source_registered() {
  local name="$1"
  "$MYCORTEX_CLI" sources list 2>/dev/null | grep -q "\"name\": \"${name}\""
}

# Seed a brain directory from a project repo
seed_brain() {
  local name="$1"
  local brain_dir="${BRAIN_DIR}/${name}"
  local repo_dir="${DEV_DIR}/${name}"

  echo ""
  echo -e "${BOLD}[${name}]${RESET}"

  # Check brain dir exists
  if [[ ! -d "$brain_dir" ]]; then
    warn "  Brain dir not found: ${brain_dir}"
    return 1
  fi

  # Check repo dir exists
  if [[ ! -d "$repo_dir" ]]; then
    warn "  Repo not found: ${repo_dir}"
    return 1
  fi

  # Check if brain already has content
  local existing_pages
  existing_pages=$(count_brain_pages "$brain_dir")
  if [[ "$existing_pages" -gt 0 ]]; then
    info "  Already has ${existing_pages} page(s) — skipping"
    return 0
  fi

  local seeded=0

  # Copy README.md
  if [[ -f "${repo_dir}/README.md" ]]; then
    cp "${repo_dir}/README.md" "${brain_dir}/references/README.md" 2>/dev/null
    echo "  → README.md"
    seeded=$((seeded + 1))
  fi

  # Copy ARCHITECTURE.md or ARCH.md
  for arch_file in ARCHITECTURE.md ARCH.md architecture.md; do
    if [[ -f "${repo_dir}/${arch_file}" ]]; then
      cp "${repo_dir}/${arch_file}" "${brain_dir}/references/${arch_file}" 2>/dev/null
      echo "  → ${arch_file}"
      seeded=$((seeded + 1))
      break
    fi
  done

  # Copy docs/ directory (top-level .md files only, avoid huge trees)
  if [[ -d "${repo_dir}/docs" ]]; then
    local doc_count=0
    mkdir -p "${brain_dir}/sources"
    for doc_file in "${repo_dir}/docs/"*.md; do
      if [[ -f "$doc_file" ]]; then
        cp "$doc_file" "${brain_dir}/sources/" 2>/dev/null
        doc_count=$((doc_count + 1))
      fi
    done
    if [[ "$doc_count" -gt 0 ]]; then
      echo "  → ${doc_count} doc(s) from docs/"
      seeded=$((seeded + doc_count))
    fi
  fi

  # Copy .github/ directory (CONTRIBUTING, SECURITY, etc.)
  if [[ -d "${repo_dir}/.github" ]]; then
    for gh_file in "${repo_dir}/.github/"*.md; do
      if [[ -f "$gh_file" ]]; then
        cp "$gh_file" "${brain_dir}/sources/" 2>/dev/null
        seeded=$((seeded + 1))
      fi
    done
  fi

  if [[ "$seeded" -eq 0 ]]; then
    warn "  No seedable content found in ${repo_dir}"
    return 0
  fi

  info "  Seeded ${seeded} file(s)"

  # Init git if needed
  if [[ ! -d "${brain_dir}/.git" ]]; then
    git -C "$brain_dir" init 2>/dev/null && echo "  Git init"
  fi

  # Git commit
  git -C "$brain_dir" add -A 2>/dev/null || true
  git -C "$brain_dir" commit -m "seed: auto-populated from ${name} repo" 2>/dev/null || true

  # Register mycortex source
  if ! is_source_registered "$name"; then
    "$MYCORTEX_CLI" sources add "$name" "$brain_dir" 2>/dev/null && echo "  mycortex source registered"
  fi

  # Sync
  "$MYCORTEX_CLI" sync --source "$name" 2>/dev/null && echo "  Synced to mycortex"
  # Report pages
  local final_pages
  final_pages=$(count_brain_pages "$brain_dir")
  info  "${final_pages} page(s) now indexed"
  return 0
}

# ── Main ───────────────────────────────────────────────────
echo ""
echo -e "${BOLD}━━━ Seed Project Brain ━━━${RESET}"

if [[ "$ACTION" == "list" ]]; then
  echo ""
  echo "Brain dirs and their matching repos:"
  echo ""
  for brain_dir in "$BRAIN_DIR"/*/; do
    name=$(basename "$brain_dir")
    pages=$(count_brain_pages "$brain_dir")
    repo_present="no"
    [[ -d "${DEV_DIR}/${name}" ]] && repo_present="yes"
    if [[ "$pages" -eq 0 ]]; then
      echo -e "  ${YELLOW}◌${RESET} ${name} — ${pages} pages, repo: ${repo_present}"
    else
      echo -e "  ${GREEN}●${RESET} ${name} — ${pages} pages, repo: ${repo_present}"
    fi
  done
  echo ""
  echo "Run with --all to seed empty ones that have matching repos."
  exit 0

elif [[ "$ACTION" == "all" ]]; then
  echo ""
  for brain_dir in "$BRAIN_DIR"/*/; do
    name=$(basename "$brain_dir")
    [[ -n "$FILTER_PROJECT" && "$name" != "$FILTER_PROJECT" ]] && continue
    pages=$(count_brain_pages "$brain_dir")
    if [[ "$pages" -eq 0 && -d "${DEV_DIR}/${name}" ]]; then
      seed_brain "$name" || true
    fi
  done
  echo ""

elif [[ "$ACTION" == "seed" && -n "$FILTER_PROJECT" ]]; then
  seed_brain "$FILTER_PROJECT" || true
  echo ""

else
  echo "No action specified. Use --list, --all, or --project=<name>"
  echo "  bash seed-project-brain.sh --help for details"
  exit 1
fi
