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

REPO_DIR="${REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
# Walk up to find repo root (signature file: AGENTS.md at the root)
while [[ "$REPO_DIR" != "/" && ! -f "$REPO_DIR/AGENTS.md" ]]; do
  REPO_DIR="$(dirname "$REPO_DIR")"
done
# If we hit / without finding AGENTS.md, try common repo locations
if [[ "$REPO_DIR" == "/" ]]; then
  # CORTEX_REPO env var (set by agents) takes priority
  if [[ -n "${CORTEX_REPO:-}" && -f "$CORTEX_REPO/AGENTS.md" ]]; then
    REPO_DIR="$CORTEX_REPO"
  else
    for candidate in \
      "$HOME/hermes-cortex" \
      "$HOME/src/hermes-cortex" \
      "$HOME/git/hermes-cortex"; do
      if [[ -f "$candidate/AGENTS.md" ]]; then
        REPO_DIR="$candidate"
        break
      fi
    done
  fi
fi
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
register "src/scripts/install-cortex-update-cron.sh" "${HERMES_HOME}/scripts/install-cortex-update-cron.sh"
register "src/scripts/install-hermes-crons.sh"       "${HERMES_HOME}/scripts/install-hermes-crons.sh"
register "src/scripts/prod-watchdog.sh"          "${HERMES_HOME}/scripts/prod-watchdog.sh"
register "src/scripts/check-agent-messages.sh"    "${HERMES_HOME}/scripts/check-agent-messages.sh"

# Post-commit notification + installer
register "scripts/post-commit-notify.sh"          "${HERMES_HOME}/scripts/post-commit-notify.sh"
register "scripts/install-post-commit-hook.sh"    "${HERMES_HOME}/scripts/install-post-commit-hook.sh"

# Moses inbox remediation
register "scripts/moses-inbox-remediate.sh"       "${HERMES_HOME}/scripts/moses-inbox-remediate.sh"

# Auto-remediation scripts
register "src/scripts/cron-auto-remediate.sh"     "${HERMES_HOME}/scripts/cron-auto-remediate.sh"
register "scripts/weekly-auto-fix.py"              "${HERMES_HOME}/scripts/weekly-auto-fix.py"

# System watchdog scripts (no_agent cron jobs)
register "src/scripts/system-alert.py"            "${HERMES_HOME}/scripts/system-alert.py"
register "src/scripts/service-recovery.py"        "${HERMES_HOME}/scripts/service-recovery.py"
register "src/scripts/langfuse-health-watchdog.py" "${HERMES_HOME}/scripts/langfuse-health-watchdog.py"
register "src/scripts/llm-judge-scorer.py"         "${HERMES_HOME}/scripts/llm-judge-scorer.py"

# Health monitoring
register "src/scripts/health-server.py"            "${HERMES_HOME}/scripts/health-server.py" "health-server"
register "src/scripts/agent-health-monitor.py"     "${HERMES_HOME}/scripts/agent-health-monitor.py"
register "src/scripts/report-agent-health.py"      "${HERMES_HOME}/scripts/report-agent-health.py"
register "src/scripts/platform_utils.py"           "${HERMES_HOME}/scripts/platform_utils.py"
register "src/scripts/com.hermes.health-server.plist" "${HOME}/Library/LaunchAgents/com.hermes.health-server.plist" "health-server" "restart_health_server"

# Agent learning sender
register "src/scripts/send-agent-learning.sh"      "${HERMES_HOME}/scripts/send-agent-learning.sh"

# Skill collection pipeline
register "src/scripts/collect-agent-skills.sh"     "${HERMES_HOME}/scripts/collect-agent-skills.sh"
register "src/scripts/request-skill-reports.sh"    "${HERMES_HOME}/scripts/request-skill-reports.sh"
register "src/scripts/process-skill-reports.py"    "${HERMES_HOME}/scripts/process-skill-reports.py"
register "src/scripts/moses-inbox.conf.template"   "${HERMES_HOME}/moses-inbox.conf.template"

# Agent inbox check (used by install.sh for cron setup)
register "src/agent-inbox/agent-inbox-check.sh"    "${HERMES_HOME}/scripts/agent-inbox-check.sh"

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

# Agent Inbox
register "src/agent-inbox/server.py"              "${HERMES_HOME}/agent-inbox/server.py" "agent-inbox" "restart_agent_inbox"
register "src/agent-inbox/com.hermes.agent-inbox.plist" "${HOME}/Library/LaunchAgents/com.hermes.agent-inbox.plist" "agent-inbox"

# Service definitions
register "src/scripts/os-config.sh"               "${HERMES_HOME}/scripts/os-config.sh"
register "src/scripts/service-writer.sh"          "${HERMES_HOME}/scripts/service-writer.sh"

# ── Service restart helpers ─────────────────────────────────

restart_gbrain_sync() {
  local autopilot_label="com.gbrain.autopilot"
  local sync_label="com.gbrain.sync-watch"
  # gbrain autopilot is the preferred sync daemon (handles sync internally).
  # Only restart sync-watch if autopilot is absent.
  if [[ "$CORTEX_OS" == "macos" ]]; then
    if launchctl list "$autopilot_label" &>/dev/null 2>&1; then
      info "  gbrain autopilot present — reloading service…"
      launchctl kickstart "gui/$(id -u)/$autopilot_label" 2>/dev/null || {
        launchctl unload "$HOME/Library/LaunchAgents/$autopilot_label.plist" 2>/dev/null || true
        launchctl load "$HOME/Library/LaunchAgents/$autopilot_label.plist" 2>/dev/null || true
      }
      return 0
    fi
    if launchctl list "$sync_label" &>/dev/null 2>&1; then
      info "  Restarting gbrain sync daemon…"
      rm -f "${HOME}/.gbrain/sync-watch.sh"
      bash "${HERMES_HOME}/scripts/install-gbrain-sync.sh" 2>&1 | sed 's/^/    /'
      return 0
    fi
  fi
  # Linux fallback: systemd
  if systemctl --user list-units --type=service --state=running 2>/dev/null \
        | grep -q "gbrain-sync"; then
    info "  Restarting gbrain sync (systemd)…"
    rm -f "${HOME}/.gbrain/sync-watch.sh"
    bash "${HERMES_HOME}/scripts/install-gbrain-sync.sh" 2>&1 | sed 's/^/    /'
    systemctl --user daemon-reload 2>/dev/null || true
    systemctl --user restart gbrain-sync 2>&1 | sed 's/^/    /'
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

restart_agent_inbox() {
  if launchctl list com.hermes.agent-inbox &>/dev/null 2>&1; then
    info "  Restarting Agent Inbox…"
    local plist="${HOME}/Library/LaunchAgents/com.hermes.agent-inbox.plist"
    launchctl unload "$plist" 2>/dev/null || true
    # Create venv if missing
    local inbox_dir="${HERMES_HOME}/agent-inbox"
    if [[ ! -d "${inbox_dir}/venv" ]]; then
      python3 -m venv "${inbox_dir}/venv" 2>/dev/null || true
      "${inbox_dir}/venv/bin/pip" install fastapi uvicorn python-multipart 2>/dev/null || true
    fi
    launchctl load "$plist" 2>&1 | sed 's/^/    /'
  elif [[ -f "${HOME}/.config/systemd/user/hermes-agent-inbox.service" ]]; then
    info "  Restarting Agent Inbox (systemd)…"
    systemctl --user daemon-reload 2>/dev/null || true
    systemctl --user restart hermes-agent-inbox 2>&1 | sed 's/^/    /'
  fi
}

restart_health_server() {
  if launchctl list com.hermes.health-server &>/dev/null 2>&1; then
    info "  Restarting Health Server…"
    launchctl unload "${HOME}/Library/LaunchAgents/com.hermes.health-server.plist" 2>/dev/null || true
    # Ensure the log dir exists
    mkdir -p "${HOME}/.hermes/health-server"
    launchctl load "${HOME}/Library/LaunchAgents/com.hermes.health-server.plist" 2>&1 | sed 's/^/    /'
    info "  Health Server restarted"
  elif [[ -f "${HOME}/.config/systemd/user/hermes-health-server.service" ]]; then
    info "  Restarting Health Server (systemd)…"
    systemctl --user daemon-reload 2>/dev/null || true
    systemctl --user restart hermes-health-server 2>&1 | sed 's/^/    /'
  elif [[ -f "${HOME}/.hermes/scripts/health-server.py" ]]; then
    # First-time: launchctl not registered yet, load it
    info "  Loading Health Server for the first time…"
    mkdir -p "${HOME}/.hermes/health-server"
    launchctl load "${HOME}/Library/LaunchAgents/com.hermes.health-server.plist" 2>&1 | sed 's/^/    /'
    info "  Health Server loaded"
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
  if command -v sha256sum &>/dev/null; then
    src_hash=$(sha256sum "$src" 2>/dev/null | cut -d' ' -f1)
    dest_hash=$(sha256sum "$dest" 2>/dev/null | cut -d' ' -f1)
  elif command -v shasum &>/dev/null; then
    src_hash=$(shasum -a 256 "$src" 2>/dev/null | cut -d' ' -f1)
    dest_hash=$(shasum -a 256 "$dest" 2>/dev/null | cut -d' ' -f1)
  else
    # No checksum tool — compare mtime
    [[ "$src" -nt "$dest" ]] && return 0
    return 1
  fi
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

# ── Skill Sync ───────────────────────────────────────────────
# Copies SKILL.md files and references/ from repo src/skills/
# to ~/.hermes/skills/. Uses the delta engine — only copies
# files whose checksums differ from installed versions.
sync_skills() {
  local skill_repo="${REPO_DIR}/src/skills"
  local skill_dest="${HERMES_HOME}/skills"
  [[ -d "$skill_repo" ]] || { info "  No src/skills/ in repo — skipping skill sync"; return 0; }

  local synced=0 skipped=0
  mkdir -p "$skill_dest"

  # Sync all SKILL.md files
  while IFS= read -r -d '' skill_file; do
    local rel_path="${skill_file#$skill_repo/}"
    local dest="${skill_dest}/${rel_path}"
    mkdir -p "$(dirname "$dest")"

    if needs_update "$skill_file" "$dest"; then
      copy_file "$skill_file" "$dest"
      synced=$((synced + 1))
    else
      skipped=$((skipped + 1))
    fi
  done < <(find "$skill_repo" -name "SKILL.md" -type f -print0)

  # Sync reference files
  while IFS= read -r -d '' ref_file; do
    local rel_path="${ref_file#$skill_repo/}"
    local dest="${skill_dest}/${rel_path}"
    mkdir -p "$(dirname "$dest")"

    if needs_update "$ref_file" "$dest"; then
      copy_file "$ref_file" "$dest"
    fi
  done < <(find "$skill_repo" -path "*/references/*" -type f -print0)

  info "  Skills: ${synced} updated, ${skipped} unchanged"
}

# ── Operator Notification ────────────────────────────────────
# Writes machine-readable and human-readable notification files
# after an update. Reads state from LAST_COMMIT_FILE and globals.
write_notification_files() {
  local timestamp
  timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  local hostname="${HOSTNAME:-$(hostname 2>/dev/null || echo 'unknown')}"
  local old_ref new_ref

  old_ref="$(cat "${LAST_COMMIT_FILE}" 2>/dev/null || echo 'none')"
  new_ref="$(git -C "${REPO_DIR}" rev-parse HEAD 2>/dev/null || echo 'none')"

  # Build restarted services list from TO_RESTART
  local services="[]"
  if [[ ${#TO_RESTART[@]} -gt 0 ]]; then
    services="["
    local first=true
    for s in "${TO_RESTART[@]}"; do
      $first || services+=", "
      first=false
      services+="\"${s#restart_}\""
    done
    services+="]"
  fi

  # last-update.json — machine-readable
  cat > "${STATE_DIR}/last-update.json" <<JSON
{
  "timestamp": "${timestamp}",
  "hostname": "${hostname}",
  "before": "${old_ref}",
  "after": "${new_ref}",
  "files_updated": ${COPIED:-0},
  "files_removed": ${REMOVED:-0},
  "services_restarted": ${services},
  "dry_run": ${DRY_RUN:-false},
  "summary_file": "${STATE_DIR}/last-update.txt"
}
JSON

  # last-update.txt — human-readable (stdout-friendly format)
  {
    echo "━━━ Cortex Update — ${timestamp} ━━━"
    echo "Host: ${hostname}"
    echo "Repo: ${new_ref:0:8} (was ${old_ref:0:8})"
    echo "Files: ${COPIED:-0} updated, ${REMOVED:-0} removed"
    if [[ ${#TO_RESTART[@]} -gt 0 ]]; then
      echo "Restarted: ${TO_RESTART[*]#restart_}"
    fi
  } > "${STATE_DIR}/last-update.txt"
  chmod 644 "${STATE_DIR}/last-update.json" "${STATE_DIR}/last-update.txt" 2>/dev/null || true
}

# ── nginx Config Deploy ──────────────────────────────────────
# Deploys hermes-services.conf and hermes-zone-defs.conf with
# OS-aware path substitution. Uses sudo on Linux for /etc/nginx/.
deploy_nginx_configs() {
  [[ -n "${CORTEX_SKIP_NGINX:-}" ]] && { info "CORTEX_SKIP_NGINX set — skipping nginx deploy"; return 0; }
  local nginx_src_dir="${REPO_DIR}/deploy/nginx"
  [[ -d "$nginx_src_dir" ]] || return 0

  local config_dir="${NGINX_CONFIG_DIR:-}"
  local brew_dir="${NGINX_BREW_DIR:-}"
  local log_dir="${NGINX_LOG_DIR:-}"
  local htpasswd="${NGINX_HTPASSWD:-}"

  # If OS config not loaded, try to determine paths from REPO_DIR
  if [[ -z "$config_dir" ]]; then
    local os_script="${REPO_DIR}/src/scripts/os-config.sh"
    [[ -f "$os_script" ]] && source "$os_script" 2>/dev/null || true
    config_dir="${NGINX_CONFIG_DIR:-}"
    brew_dir="${NGINX_BREW_DIR:-}"
    log_dir="${NGINX_LOG_DIR:-}"
    htpasswd="${NGINX_HTPASSWD:-}"
  fi

  [[ -z "$config_dir" || -z "$brew_dir" ]] && { info "  nginx paths unknown — skipping nginx deploy"; return 0; }

  local files_copied=0

  # 1. hermes-zone-defs.conf — no substitution needed, copy directly
  local zone_src="${nginx_src_dir}/hermes-zone-defs.conf"
  local zone_dst="${brew_dir}/hermes-zone-defs.conf"
  if needs_update "$zone_src" "$zone_dst"; then
    if command -v sudo &>/dev/null && [[ "$brew_dir" == /etc/* ]]; then
      sudo mkdir -p "$brew_dir" 2>/dev/null || true
      sudo cp "$zone_src" "$zone_dst"
      sudo chmod 644 "$zone_dst"
    else
      mkdir -p "$brew_dir" 2>/dev/null || true
      cp "$zone_src" "$zone_dst"
    fi
    info "  Updated: hermes-zone-defs.conf → ${zone_dst}"
    files_copied=$((files_copied + 1))
  fi

  # 2. hermes-services.conf — substitute placeholders, then write
  local conf_src="${nginx_src_dir}/hermes-services.conf"
  local conf_dst="${config_dir}/hermes-services.conf"
  if needs_update "$conf_src" "$conf_dst"; then
    local tmpfile
    tmpfile="$(mktemp)" || return 1
    < "$conf_src" sed \
      -e "s|__NGINX_CONFIG_DIR__|${config_dir}|g" \
      -e "s|__NGINX_LOG_DIR__|${log_dir}|g" \
      -e "s|__HTPASSWD_FILE__|${htpasswd}|g" > "$tmpfile"
    if command -v sudo &>/dev/null && [[ "$config_dir" == /etc/* ]]; then
      sudo mkdir -p "$(dirname "$conf_dst")" 2>/dev/null || true
      sudo cp "$tmpfile" "$conf_dst"
      sudo chmod 644 "$conf_dst"
    else
      mkdir -p "$(dirname "$conf_dst")" 2>/dev/null || true
      cp "$tmpfile" "$conf_dst"
    fi
    rm -f "$tmpfile"
    info "  Updated: hermes-services.conf → ${conf_dst} (OS-aware paths)"
    files_copied=$((files_copied + 1))
  fi

  [[ "$files_copied" -eq 0 ]] && return 0

  # 3. Test and reload nginx
  local nginx_test="nginx -t"
  local nginx_reload="nginx -s reload"
  if [[ "$brew_dir" == /etc/* ]]; then
    nginx_test="sudo -n nginx -t"
    nginx_reload="sudo systemctl reload nginx || sudo nginx -s reload"
  fi

  if eval "$nginx_test" 2>/dev/null; then
    eval "$nginx_reload" 2>/dev/null || true
    info "  nginx config test passed — reloaded"
  else
    warn "  nginx config test failed — check ${conf_dst}"
  fi
}

# ── Main ────────────────────────────────────────────────────

main() {
  parse_args "$@"
  register

  # Source OS config for nginx path variables (NGINX_CONFIG_DIR, NGINX_LOG_DIR, NGINX_HTPASSWD)
  local os_config="${HERMES_HOME}/scripts/os-config.sh"
  [[ -f "$os_config" ]] && source "$os_config" 2>/dev/null || true

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
      warn "Git pull --ff-only failed — trying --rebase fallback…"
      git -C "$REPO_DIR" pull --rebase origin main 2>&1 | sed 's/^/  /' || {
        warn "Git pull failed — check your connection or local changes"
        warn "  cd ${REPO_DIR} && git status"
        exit 1
      }
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
    CHANGED=()
    while IFS= read -r line; do
      CHANGED+=("$line")
    done < <(get_changed_files "$old_commit")
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

  # Sync skills from repo (all SKILL.md + references/, only changed files)
  sync_skills

  # Deploy nginx configs (OS-aware path substitution, sudo on Linux)
  deploy_nginx_configs

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
        restart_agent_inbox) restart_agent_inbox ;;
        *)                   warn "Unknown restart command: $cmd" ;;
      esac
    done
  fi

  # Save commit
  mkdir -p "$STATE_DIR"
  echo "$new_commit" > "$LAST_COMMIT_FILE"
  info "State saved: ${new_commit:0:8}"

  # Write notification files (monitored by operator dashboard / messenger)
  write_notification_files

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
