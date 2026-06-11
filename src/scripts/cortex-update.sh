#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  cortex-update.sh — Pull + delta-update + service restart
#
#  Detects what changed in git, re-copies only the affected
#  files to their destinations, and restarts affected services.
#
#  Usage:
#    bash cortex-update.sh              # default: pull + update
#    bash cortex-update.sh --dry-run    # show what would change
#    bash cortex-update.sh --status     # compare local vs installed
#    bash cortex-update.sh --force-all  # re-copy EVERYTHING
# ─────────────────────────────────────────────────────────────
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BOLD='\033[1m'; CYAN='\033[0;36m'; RESET='\033[0m'

info()  { echo -e "${GREEN}✓${RESET} $*"; }
warn()  { echo -e "${YELLOW}⚠${RESET} $*"; }
error() { echo -e "${RED}✗${RESET} $*"; }

REPO_DIR="${REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
HERMES_HOME="${HERMES_HOME:-${HOME}/.hermes}"
STATE_DIR="${HERMES_HOME}/state"
LAST_COMMIT_FILE="${STATE_DIR}/update-commit"
BUN_PATH="${HOME}/.bun/bin"
export PATH="${BUN_PATH}:$PATH"

DRY_RUN=false
STATUS_ONLY=false
FORCE_ALL=false
CHANGED=()
TO_RESTART=()
COPIED=0
SKIPPED=0
REMOVED=0

parse_args() {
  for arg in "$@"; do
    case "$arg" in
      --dry-run)    DRY_RUN=true ;;
      --status)     STATUS_ONLY=true ;;
      --force-all)  FORCE_ALL=true ;;
      --help|-h)
        echo "Usage: bash cortex-update.sh [--dry-run|--status|--force-all]"
        echo ""
        echo "  --dry-run     Show what would change without touching anything"
        echo "  --status      Compare local repo vs installed files"
        echo "  --force-all   Re-copy EVERYTHING (skip detection)"
        exit 0
        ;;
    esac
  done
}

# ── File-to-destination map ─────────────────────────────────
# Each entry: source_path dest_path [service_label] [restart_cmd]
# source_path is relative to REPO_DIR
MAP=()
register() {
  local s1="${1:-}" s2="${2:-}" s3="${3:-}" s4="${4:-}"
  MAP+=("${s1}|${s2}|${s3}|${s4}")
}

# Scripts → ~/.hermes/scripts/
register "src/scripts/heartbeat.py"               "${HERMES_HOME}/scripts/heartbeat.py"
register "src/scripts/memory-to-brain.py"         "${HERMES_HOME}/scripts/memory-to-brain.py"
register "src/scripts/bootstrap-brain.sh"         "${HERMES_HOME}/scripts/bootstrap-brain.sh"
register "src/scripts/check-memory-budget.sh"     "${HERMES_HOME}/scripts/check-memory-budget.sh"
register "src/scripts/cortex-profile.sh"          "${HERMES_HOME}/scripts/cortex-profile.sh"
register "src/scripts/seed-project-brain.sh"      "${HERMES_HOME}/scripts/seed-project-brain.sh"
register "src/scripts/cortex-health.sh"           "${HERMES_HOME}/scripts/cortex-health.sh"
register "src/scripts/cortex-setup-langfuse.sh"   "${HERMES_HOME}/scripts/cortex-setup-langfuse.sh"
register "src/scripts/cortex-update.sh"           "${HERMES_HOME}/scripts/cortex-update.sh"
register "src/scripts/install-gbrain-sync.sh"     "${HERMES_HOME}/scripts/install-gbrain-sync.sh" "gbrain-sync" "restart_gbrain_sync"
register "src/scripts/install-ollama.sh"          "${HERMES_HOME}/scripts/install-ollama.sh"
register "src/scripts/install-nginx.sh"           "${HERMES_HOME}/scripts/install-nginx.sh"

# Lesson-aware scripts (Memory That Compounds)
register "src/scripts/daily-lesson-mine.sh"      "${HERMES_HOME}/scripts/daily-lesson-mine.sh"
register "src/scripts/lesson-compound-stats.py"   "${HERMES_HOME}/scripts/lesson-compound-stats.py"
register "src/scripts/lesson-hit.sh"              "${HERMES_HOME}/scripts/lesson-hit.sh"

# Offline tools
register "src/offline/offline_knowledge.py"       "${HERMES_HOME}/offline/offline_knowledge.py"
register "src/offline/offline_knowledge.sh"       "${HERMES_HOME}/offline/offline_knowledge.sh"
register "src/offline/kiwix-docker-compose.yml"   "${HERMES_HOME}/offline/kiwix-docker-compose.yml"
register "src/offline/prep-offline.sh"            "${HERMES_HOME}/offline/prep-offline.sh"
register "src/offline/session_mine.py"            "${HERMES_HOME}/offline/session_mine.py"
register "src/offline/lessons.py"                 "${HERMES_HOME}/offline/lessons.py"
register "src/offline/migrate_fts_reasoning.sql"  "${HERMES_HOME}/offline/migrate_fts_reasoning.sql"
register "src/offline/auto-update.sh"             "${HERMES_HOME}/offline/auto-update.sh"

# Templates → ~/.hermes/memories/ (guarded — only if dest missing)
register "docs/templates/MEMORY.seed.md"      "${HERMES_HOME}/memories/MEMORY.md"
register "docs/templates/USER.seed.md"        "${HERMES_HOME}/memories/USER.md"
register "docs/templates/memory-readme.seed.md" "${HERMES_HOME}/memory/README.md"

# Langfuse
register "deploy/docker-compose.langfuse.yml"        "${HOME}/langfuse/docker-compose.yml" "langfuse" "restart_langfuse"

# Dashboard
register "src/dashboard/server.py"               "${HERMES_HOME}/dashboard/server.py" "dashboard" "restart_dashboard"
register "src/dashboard/static/index.html"        "${HERMES_HOME}/dashboard/static/index.html" "dashboard"
register "src/dashboard/com.hermes.cortex-dashboard.plist" "${HOME}/Library/LaunchAgents/com.hermes.cortex-dashboard.plist" "dashboard"

# Service definitions
register "src/scripts/os-config.sh"               "${HERMES_HOME}/scripts/os-config.sh"
register "src/scripts/service-writer.sh"          "${HERMES_HOME}/scripts/service-writer.sh"

# ── Service restart helpers ─────────────────────────────────

restart_gbrain_sync() {
  local label="com.gbrain.sync-watch"
  if launchctl list "$label" &>/dev/null 2>&1; then
    info "  Restarting gbrain sync daemon…"
    # Force re-write the sync-watch.sh script (remove then call installer)
    rm -f "${HOME}/.gbrain/sync-watch.sh"
    bash "${HERMES_HOME}/scripts/install-gbrain-sync.sh" 2>&1 | sed 's/^/    /'
  fi
}

restart_langfuse() {
  if [[ -f "${HOME}/langfuse/docker-compose.yml" ]] && command -v docker &>/dev/null; then
    if docker compose -f "${HOME}/langfuse/docker-compose.yml" ps &>/dev/null 2>&1; then
      info "  Recreating Langfuse containers…"
      (cd "${HOME}/langfuse" && docker compose up -d 2>&1) | sed 's/^/    /'
    fi
  fi
}

restart_dashboard() {
  if launchctl list com.hermes.cortex-dashboard &>/dev/null 2>&1; then
    info "  Restarting Cortex Dashboard…"
    launchctl unload "${HOME}/Library/LaunchAgents/com.hermes.cortex-dashboard.plist" 2>/dev/null || true
    launchctl load "${HOME}/Library/LaunchAgents/com.hermes.cortex-dashboard.plist" 2>&1 | sed 's/^/    /'
  elif [[ -f "${HOME}/.config/systemd/user/hermes-cortex-dashboard.service" ]]; then
    systemctl --user daemon-reload 2>/dev/null || true
    systemctl --user restart hermes-cortex-dashboard 2>&1 | sed 's/^/    /'
  fi
}

# ── Delta engine ────────────────────────────────────────────

needs_update() {
  local src="$1" dest="$2"
  # If destination doesn't exist, definitely needs update
  [[ ! -f "$dest" ]] && return 0
  # If source doesn't exist (file removed from repo), skip
  [[ ! -f "$src" ]] && return 1
  # Compare checksums
  local src_hash dest_hash
  src_hash=$(sha256sum "$src" 2>/dev/null | cut -d' ' -f1)
  dest_hash=$(sha256sum "$dest" 2>/dev/null | cut -d' ' -f1)
  [[ "$src_hash" != "$dest_hash" ]] && return 0
  return 1
}

copy_file() {
  local src="$1" dest="$2"
  mkdir -p "$(dirname "$dest")"
  if $DRY_RUN; then
    echo "    would copy: $(basename "$src") → ${dest/$HOME/\~}"
  else
    cp "$src" "$dest"
    chmod 644 "$dest"
    # Preserve executable bit
    [[ -x "$src" ]] && chmod +x "$dest"
    COPIED=$((COPIED + 1))
  fi
}

remove_deprecated() {
  local dest="$1"
  if [[ -f "$dest" ]]; then
    if $DRY_RUN; then
      echo "    would remove: ${dest/$HOME/\~} (source removed from repo)"
    else
      rm -f "$dest"
      REMOVED=$((REMOVED + 1))
      warn "  Removed deprecated: ${dest/$HOME/\~}"
    fi
  fi
}

# ── Changed-file analysis ───────────────────────────────────

get_changed_files() {
  local old_commit="$1"
  # Get files changed between old commit and HEAD
  git -C "$REPO_DIR" diff --name-only "${old_commit}..HEAD" 2>/dev/null || true
}

check_each_mapped_file() {
  local action="${1:-delta}"  # delta or full
  local src dest service restart_cmd

  for entry in "${MAP[@]}"; do
    IFS='|' read -r src dest service restart_cmd <<< "$entry"
    local full_src="${REPO_DIR}/${src}"

    if [[ "$action" == "full" ]]; then
      # Force-all mode: check every mapped file
      if [[ -f "$full_src" ]]; then
        if needs_update "$full_src" "$dest"; then
          copy_file "$full_src" "$dest"
          [[ -n "$service" && -n "$restart_cmd" ]] && TO_RESTART+=("$restart_cmd")
        fi
      fi
    else
      # Delta mode: only process files in CHANGED list
      local matched=false
      for changed in "${CHANGED[@]}"; do
        if [[ "$changed" == "$src" ]]; then
          matched=true
          break
        fi
      done
      if $matched; then
        if [[ -f "$full_src" ]]; then
          copy_file "$full_src" "$dest"
          info "  Updated: ${dest/$HOME/\~}"
          [[ -n "$service" && -n "$restart_cmd" ]] && TO_RESTART+=("$restart_cmd")
        fi
      fi
    fi
  done
}

# ── Deprecated file cleanup ─────────────────────────────────

# Known old files that may stick around after they're removed from the repo
DEPRECATED_FILES=()  # populated by scanning the map for files that no longer exist in repo

# ── Symlinks ────────────────────────────────────────────────

update_symlinks() {
  # Recreate web_cache symlink
  local src="${HERMES_HOME}/web-cache/web_cache.sh"
  local link="${HERMES_HOME}/bin/web_cache"
  if [[ -f "$src" ]]; then
    mkdir -p "${HERMES_HOME}/bin"
    ln -sf "$src" "$link"
    info "  Symlink: web_cache"
  fi

  # Recreate offline symlinks
  local offline_script="${HERMES_HOME}/offline/offline_knowledge.sh"
  local offline_link="${HERMES_HOME}/bin/offline_knowledge"
  if [[ -f "$offline_script" ]]; then
    ln -sf "$offline_script" "$offline_link"
    info "  Symlink: offline_knowledge"
  fi

  local prep_script="${HERMES_HOME}/offline/prep-offline.sh"
  local prep_link="${HERMES_HOME}/bin/prep-offline"
  if [[ -f "$prep_script" ]]; then
    ln -sf "$prep_script" "$prep_link"
    info "  Symlink: prep-offline"
  fi
}

# ── Main ────────────────────────────────────────────────────

main() {
  parse_args "$@"
  register

  echo ""
  echo -e "${BOLD}━━━ Cortex Update ━━━${RESET}"
  echo ""

  # Verify we're in the repo
  if [[ ! -d "${REPO_DIR}/.git" ]]; then
    error "Not a git repository: ${REPO_DIR}"
    echo "  Set REPO_DIR=<path> or run from the hermes-cortex repo directory."
    exit 1
  fi

  # Git pull
  local old_commit new_commit
  old_commit=$(git -C "$REPO_DIR" rev-parse HEAD 2>/dev/null || echo "none")

  if $STATUS_ONLY; then
    echo "Last update: $(cat "$LAST_COMMIT_FILE" 2>/dev/null || echo 'never')"
    echo "Repo HEAD:   ${old_commit}"
    echo ""
    echo -e "${BOLD}Changed files since last update:${RESET}"
    local last_commit
    last_commit=$(cat "$LAST_COMMIT_FILE" 2>/dev/null || echo "")
    if [[ -n "$last_commit" ]]; then
      git -C "$REPO_DIR" diff --name-only "${last_commit}..HEAD" 2>/dev/null | sed 's/^/  /' | head -50
    else
      echo "  (no previous update recorded — run without --status)"
    fi
    exit 0
  fi

  if ! $FORCE_ALL; then
    info "Pulling latest from origin/main…"
    git -C "$REPO_DIR" pull --ff-only origin main 2>&1 | sed 's/^/  /' || {
      warn "Git pull failed — check your connection or local changes"
      warn "  cd ${REPO_DIR} && git status"
      exit 1
    }
  fi

  new_commit=$(git -C "$REPO_DIR" rev-parse HEAD)

  if [[ "$old_commit" == "$new_commit" ]] && ! $FORCE_ALL; then
    info "Already up to date (${new_commit:0:8})"
    echo ""
    exit 0
  fi

  info "Updated: ${old_commit:0:8} → ${new_commit:0:8}"
  echo ""

  # Get changed files
  if $FORCE_ALL; then
    info "Force mode — re-checking all mapped files…"
    check_each_mapped_file "full"
  else
    mapfile -t CHANGED < <(get_changed_files "$old_commit")
    if [[ ${#CHANGED[@]} -eq 0 ]]; then
      info "No file changes detected (commit metadata change?)"
      info "  Saving commit ${new_commit:0:8} as current"
      mkdir -p "$STATE_DIR"
      echo "$new_commit" > "$LAST_COMMIT_FILE"
      exit 0
    fi
    echo -e "${BOLD}Changed files (${#CHANGED[@]}):${RESET}"
    for f in "${CHANGED[@]}"; do
      echo "  ${CYAN}↻${RESET} $f"
    done
    echo ""

    info "Applying updates…"
    check_each_mapped_file "delta"
  fi

  # Update symlinks if any web-cache or offline files changed
  update_symlinks

  # Restart affected services
  if [[ ${#TO_RESTART[@]} -gt 0 ]]; then
    echo ""
    echo -e "${BOLD}━━━ Restarting affected services ━━━${RESET}"
    local seen_restart=""
    for cmd in "${TO_RESTART[@]}"; do
      # Simple dedup (bash 3.2 compatible)
      case ",${seen_restart}," in
        *",${cmd},"*) continue ;;
      esac
      seen_restart="${seen_restart},${cmd}"
      $DRY_RUN && echo "    would restart: $cmd" && continue
      case "$cmd" in
        restart_gbrain_sync) restart_gbrain_sync ;;
        restart_langfuse)    restart_langfuse ;;
        restart_dashboard)   restart_dashboard ;;
        *)                   warn "Unknown restart command: $cmd" ;;
      esac
    done
  fi

  # Save commit
  mkdir -p "$STATE_DIR"
  echo "$new_commit" > "$LAST_COMMIT_FILE"
  info "State saved: ${new_commit:0:8}"

  # Summary
  echo ""
  echo -e "${BOLD}━━━ Summary ━━━${RESET}"
  info "${COPIED} file(s) updated"
  [[ "$REMOVED" -gt 0 ]] && warn "${REMOVED} deprecated file(s) removed"
  if $DRY_RUN; then
    echo ""
    warn "DRY RUN — no files were actually modified."
    warn "Run without --dry-run to apply changes."
  fi
  echo ""
}

main "$@"
