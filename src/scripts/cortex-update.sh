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
HERMES_HOME="${HERMES_HOME:-${HOME}/.hermes-cortex}"
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

# Scripts → ~/.hermes-cortex/scripts/
register "src/scripts/system-alert-watchdog.py"   "${HERMES_HOME}/scripts/system-alert-watchdog.py"
register "src/scripts/hermes_models.py"            "${HERMES_HOME}/scripts/hermes_models.py"
register "src/scripts/hermes_paths.py"             "${HERMES_HOME}/scripts/hermes_paths.py"
register "src/scripts/check-system.sh"             "${HERMES_HOME}/scripts/check-system.sh"
register "src/scripts/memory-to-brain-sync.py"    "${HERMES_HOME}/scripts/memory-to-brain-sync.py"
register "src/scripts/bootstrap-brain.sh"         "${HERMES_HOME}/scripts/bootstrap-brain.sh"
register "src/scripts/check-memory-budget.sh"     "${HERMES_HOME}/scripts/check-memory-budget.sh"
register "src/scripts/cortex-profile.sh"          "${HERMES_HOME}/scripts/cortex-profile.sh"
register "src/scripts/seed-project-brain.sh"      "${HERMES_HOME}/scripts/seed-project-brain.sh"
register "src/scripts/cortex-health.sh"           "${HERMES_HOME}/scripts/cortex-health.sh"
register "src/scripts/cortex-setup-langfuse.sh"   "${HERMES_HOME}/scripts/cortex-setup-langfuse.sh"
register "src/scripts/cortex-update.sh"           "${HERMES_HOME}/scripts/cortex-update.sh"
register "src/scripts/install-ollama.sh"          "${HERMES_HOME}/scripts/install-ollama.sh"
register "src/scripts/install-nginx.sh"           "${HERMES_HOME}/scripts/install-nginx.sh"
register "src/scripts/install-cortex-update-cron.sh" "${HERMES_HOME}/scripts/install-cortex-update-cron.sh"
register "src/scripts/install-crons.sh"       "${HERMES_HOME}/scripts/install-crons.sh"
register "src/scripts/install-orch-crons.sh"  "${HERMES_HOME}/scripts/install-orch-crons.sh"
register "src/scripts/install-score-hook.sh"       "${HERMES_HOME}/scripts/install-score-hook.sh"
register "src/scripts/pre-commit-score"            "${HERMES_HOME}/scripts/pre-commit-score"
register "src/scripts/pre-push-pull"               "${HERMES_HOME}/scripts/pre-push-pull"
register "src/scripts/score-auditor.py"            "${HERMES_HOME}/scripts/score-auditor.py"
register "src/scripts/agents-doc-audit.py"          "${HERMES_HOME}/scripts/agents-doc-audit.py"
register "src/scripts/check-external-services.sh"   "${HERMES_HOME}/scripts/check-external-services.sh"
register "src/scripts/cortex-doctor.py"              "${HERMES_HOME}/scripts/cortex-doctor.py"
register "src/scripts/cron-failure-state.sh"       "${HERMES_HOME}/scripts/cron-failure-state.sh"
register "src/scripts/cron_failure_state.py"       "${HERMES_HOME}/scripts/cron_failure_state.py"
register "src/scripts/seed-project.sh"           "${HERMES_HOME}/scripts/seed-project.sh"
register "src/scripts/hermes-update.sh"            "${HERMES_HOME}/scripts/hermes-update.sh"
register "src/scripts/hermes-cortex-sync.sh"      "${HERMES_HOME}/scripts/hermes-cortex-sync.sh"
register "src/scripts/update-session-state.sh"    "${HERMES_HOME}/scripts/update-session-state.sh"

# Loop-governance scripts (deployed to scripts/ for cron use)
register "src/loop-governance/cleanup-ollama.sh"  "${HERMES_HOME}/scripts/cleanup-ollama.sh"
register "src/loop-governance/inbox_watcher.py"    "${HERMES_HOME}/scripts/inbox_watcher.py"
register "src/loop-governance/session_cache.py"    "${HERMES_HOME}/scripts/session_cache.py"
register "src/loop-governance/setup.sh"            "${HERMES_HOME}/scripts/setup.sh"
register "src/loop-governance/skill_miner.py"      "${HERMES_HOME}/scripts/skill_miner.py"
register "src/loop-governance/skill-miner-wrapper" "${HERMES_HOME}/scripts/skill-miner-wrapper"
register "src/loop-governance/update.sh"           "${HERMES_HOME}/scripts/update.sh"

register "src/scripts/prod-watchdog.sh"          "${HERMES_HOME}/scripts/prod-watchdog.sh"
register "src/scripts/orch-team-messages.sh"    "${HERMES_HOME}/scripts/orch-team-messages.sh"

# Post-commit notification + installer
register "src/scripts/post-commit-notify.sh"          "${HERMES_HOME}/scripts/post-commit-notify.sh"
register "src/scripts/install-post-commit-hook.sh"    "${HERMES_HOME}/scripts/install-post-commit-hook.sh"

# Template drift checker (runs during cortex-update.sh)
register "src/scripts/template-diff-check.py"          "${HERMES_HOME}/scripts/template-diff-check.py"

# Moses inbox remediation
register "src/scripts/orch-inbox-remediate.sh"  "${HERMES_HOME}/scripts/orch-inbox-remediate.sh"

# Auto-remediation scripts
register "src/scripts/cron-auto-remediate.sh"     "${HERMES_HOME}/scripts/cron-auto-remediate.sh"
register "src/scripts/orch-weekly-auto-fix.py"    "${HERMES_HOME}/scripts/orch-weekly-auto-fix.py"

# System watchdog scripts (no_agent cron jobs)
register "src/scripts/service-recovery.py"        "${HERMES_HOME}/scripts/service-recovery.py"
register "src/scripts/platform_utils.py"          "${HERMES_HOME}/scripts/platform_utils.py"
register "src/scripts/agent-daily-bible-reading.py" "${HERMES_HOME}/scripts/agent-daily-bible-reading.py"
register "src/scripts/langfuse-health-watchdog.py" "${HERMES_HOME}/scripts/langfuse-health-watchdog.py"
register "src/scripts/llm-judge-scorer.py"         "${HERMES_HOME}/scripts/llm-judge-scorer.py"
register "src/scripts/model-health-watchdog.py"    "${HERMES_HOME}/scripts/model-health-watchdog.py"
register "src/scripts/offline_code_index_cron.sh"  "${HERMES_HOME}/scripts/offline_code_index_cron.sh"
register "src/scripts/cron-quality-watchdog.py"    "${HERMES_HOME}/scripts/cron-quality-watchdog.py"
register "src/scripts/agent-cron-failure-scanner.py" "${HERMES_HOME}/scripts/agent-cron-failure-scanner.py"
register "src/scripts/scoring-activity-watchdog.py" "${HERMES_HOME}/scripts/scoring-activity-watchdog.py"
register "src/scripts/state_tracker.py"             "${HERMES_HOME}/scripts/state_tracker.py"
register "src/scripts/check-certs.py"               "${HERMES_HOME}/scripts/check-certs.py"
register "src/scripts/daily-bible-reading.sh"       "${HERMES_HOME}/scripts/daily-bible-reading.sh"
register "src/scripts/generate-inbox-wrappers.py"   "${HERMES_HOME}/scripts/generate-inbox-wrappers.py"
register "src/scripts/nginx-security-scanner.sh"    "${HERMES_HOME}/scripts/nginx-security-scanner.sh"
register "src/scripts/nginx-threat-pipeline.sh"     "${HERMES_HOME}/scripts/nginx-threat-pipeline.sh"
register "src/scripts/agent-remediate-apply.py"  "${HERMES_HOME}/scripts/agent-remediate-apply.py"
register "src/scripts/agent-apply-fixes.py"      "${HERMES_HOME}/scripts/agent-apply-fixes.py"
register "src/scripts/agent-ip-submission.sh"      "${HERMES_HOME}/scripts/agent-ip-submission.sh"

# Deploy scripts (nginx security pipeline) — now deployed to /usr/local/sbin/
# by deploy_system_scripts() below. Old register entries removed.

# Deployment-specific cron scripts
register "src/scripts/auto-save-sessions.py"      "${HERMES_HOME}/scripts/auto-save-sessions.py"
register "src/scripts/agent-health-monitor.py"    "${HERMES_HOME}/scripts/agent-health-monitor.py"
register "src/scripts/gbrain-nightly-dream.sh"   "${HERMES_HOME}/scripts/gbrain-nightly-dream.sh"
register "src/scripts/gbrain-update-sync.sh"     "${HERMES_HOME}/scripts/gbrain-update-sync.sh"
register "src/scripts/gbrain-wrapper.sh"         "${HERMES_HOME}/scripts/gbrain-wrapper.sh"
register "src/scripts/gbrain-doctor-summary.py"   "${HERMES_HOME}/scripts/gbrain-doctor-summary.py"
register "src/scripts/harvest-lessons.sh"         "${HERMES_HOME}/scripts/harvest-lessons.sh"
register "src/scripts/send-skill-report.py"       "${HERMES_HOME}/scripts/send-skill-report.py"
register "src/scripts/state_tracker.py"           "${HERMES_HOME}/scripts/state_tracker.py"

# Inbox MCP tools
register "src/scripts/inbox-mcp.sh"               "${HERMES_HOME}/scripts/inbox-mcp.sh"
register "src/scripts/inbox-mcp-updated.py"       "${HERMES_HOME}/scripts/inbox-mcp-updated.py"
register "src/scripts/inbox-flag.py"              "${HERMES_HOME}/scripts/inbox-flag.py"
register "src/scripts/inbox-watch.sh"             "${HERMES_HOME}/scripts/inbox-watch.sh"
register "src/scripts/setup-agent-inbox.sh"       "${HERMES_HOME}/scripts/setup-agent-inbox.sh"
register "src/scripts/loop-gov-mcp.sh"            "${HERMES_HOME}/scripts/loop-gov-mcp.sh"
register "src/scripts/agent-inbox-monitor.sh"     "${HERMES_HOME}/scripts/agent-inbox-monitor.sh"
register "src/scripts/orch-inbox-processor.py"   "${HERMES_HOME}/scripts/orch-inbox-processor.py"
register "src/scripts/check-agent-messages.sh"    "${HERMES_HOME}/scripts/check-agent-messages.sh"
register "src/scripts/ek-session-snapshot.py"     "${HERMES_HOME}/scripts/ek-session-snapshot.py"

# Orchestrator health polling (Moses primary, Esther backup)
register "src/scripts/orch-team-health.py"         "${HERMES_HOME}/scripts/orch-team-health.py"

# Cron cost tracking — SQLite store + deployment script
register "src/scripts/cost_store.py"               "${HERMES_HOME}/scripts/cost_store.py"
register "src/scripts/install-cron-cost-tracking.py" "${HERMES_HOME}/scripts/install-cron-cost-tracking.py"

# Health monitoring
register "src/scripts/health-server.py"            "${HERMES_HOME}/scripts/health-server.py" "health-server"
register "src/scripts/health-vector.py"            "${HERMES_HOME}/scripts/health-vector.py"
register "src/scripts/report-agent-health.py"      "${HERMES_HOME}/scripts/report-agent-health.py"
register "src/scripts/com.hermes.health-server.plist" "${HOME}/Library/LaunchAgents/com.hermes.health-server.plist" "health-server" "restart_health_server"
register "src/scripts/com.hermes.health-server.service" "${HOME}/.config/systemd/user/com.hermes.health-server.service" "health-server" "restart_health_server"

# Timezone helper (required by monitoring scripts)
register "src/scripts/hermes_tz.py"                "${HERMES_HOME}/scripts/hermes_tz.py"

# Remediation sensor (companion to agent-auto-remediate cron)
register "src/scripts/remediation-sensor.py"       "${HERMES_HOME}/scripts/remediation-sensor.py"

# Inbox monitoring
register "src/scripts/inbox-sensor.py"             "${HERMES_HOME}/scripts/inbox-sensor.py"

# Eval harness (agent reliability patterns)
register "src/scripts/run-evals.py"                "${HERMES_HOME}/scripts/run-evals.py"
register "src/scripts/analyze-failures.py"         "${HERMES_HOME}/scripts/analyze-failures.py"

# Agent learning sender
register "src/scripts/send-agent-learning.sh"      "${HERMES_HOME}/scripts/send-agent-learning.sh"

# Skill collection pipeline
register "src/scripts/collect-agent-skills.sh"     "${HERMES_HOME}/scripts/collect-agent-skills.sh"
register "src/scripts/request-skill-reports.sh"    "${HERMES_HOME}/scripts/request-skill-reports.sh"
register "src/scripts/process-skill-reports.py"    "${HERMES_HOME}/scripts/process-skill-reports.py"
# Agent inbox connection config — user creates manually

# MCP inbox proxy — sudo'd HTTPS proxy with root-owned client cert
register "src/scripts/mcp-inbox-proxy"              "${HERMES_HOME}/scripts/mcp-inbox-proxy"

# Agent inbox check (used by install.sh for cron setup)
register "src/agent-inbox/agent-inbox-check.sh"    "${HERMES_HOME}/scripts/agent-inbox-check.sh"

# Lesson-aware scripts (Memory That Compounds)
register "src/scripts/daily-lesson-mine.sh"      "${HERMES_HOME}/scripts/daily-lesson-mine.sh"
register "src/scripts/lesson-compound-stats.py"   "${HERMES_HOME}/scripts/lesson-compound-stats.py"
register "src/scripts/lesson-hit.sh"              "${HERMES_HOME}/scripts/lesson-hit.sh"

# Offline tools
register "src/offline/offline_knowledge.py"       "${HERMES_HOME}/offline/offline_knowledge.py"
register "src/offline/offline_knowledge.sh"       "${HERMES_HOME}/offline/offline_knowledge.sh"
register "src/offline/offline_code.py"            "${HERMES_HOME}/offline/offline_code.py"
register "src/offline/offline_code.sh"            "${HERMES_HOME}/offline/offline_code.sh"
register "src/offline/kiwix-docker-compose.yml"   "${HERMES_HOME}/offline/kiwix-docker-compose.yml"
register "src/offline/prep-offline.sh"            "${HERMES_HOME}/offline/prep-offline.sh"
register "src/offline/session_mine.py"            "${HERMES_HOME}/offline/session_mine.py"
register "src/offline/lessons.py"                 "${HERMES_HOME}/offline/lessons.py"
register "src/offline/migrate_fts_reasoning.sql"  "${HERMES_HOME}/offline/migrate_fts_reasoning.sql"
register "src/offline/auto-update.sh"             "${HERMES_HOME}/offline/auto-update.sh"

# A2A Agent-to-Agent Protocol
register "src/a2a/generate-agent-card.py"         "${HERMES_HOME}/scripts/generate-agent-card.py"
register "src/a2a/agent-card.json"                "${HERMES_HOME}/a2a/agent-card.json"
register "src/mcp-servers/a2a-mcp.py"              "${HERMES_HOME}/mcp-servers/a2a-mcp.py"
register "src/a2a/a2a-server.py"                     "${HERMES_HOME}/scripts/a2a-server.py"
register "docs/templates/a2a-server.service"          "${HERMES_HOME}/templates/a2a-server.service"

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
  # gbrain autopilot is the preferred sync daemon (handles sync, extract,
  # embed, lint, and backlinks internally every ~150s).
  if [[ "$CORTEX_OS" == "macos" ]]; then
    if launchctl list "$autopilot_label" &>/dev/null 2>&1; then
      info "  Reloading gbrain autopilot…"
      launchctl kickstart "gui/$(id -u)/$autopilot_label" 2>/dev/null || {
        launchctl unload "$HOME/Library/LaunchAgents/$autopilot_label.plist" 2>/dev/null || true
        launchctl load "$HOME/Library/LaunchAgents/$autopilot_label.plist" 2>/dev/null || true
      }
    else
      warn "  gbrain autopilot not registered — run 'gbrain autopilot --install' first"
    fi
  fi
  # Linux: restart autopilot systemd service
  if systemctl --user is-active --quiet gbrain-autopilot 2>/dev/null; then
    info "  Restarting gbrain autopilot (systemd)…"
    systemctl --user restart gbrain-autopilot 2>&1 | sed 's/^/    /'
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
    info "  Restarting Health Server (launchd)…"
    launchctl unload "${HOME}/Library/LaunchAgents/com.hermes.health-server.plist" 2>/dev/null || true
    mkdir -p "${HOME}/.hermes-cortex/health-server"
    launchctl load "${HOME}/Library/LaunchAgents/com.hermes.health-server.plist" 2>&1 | sed 's/^/    /'
    info "  Health Server restarted"
  elif systemctl --user is-enabled com.hermes.health-server &>/dev/null 2>&1 || \
       [[ -f "${HOME}/.config/systemd/user/com.hermes.health-server.service" ]]; then
    info "  Restarting Health Server (systemd)…"
    systemctl --user daemon-reload 2>/dev/null || true
    systemctl --user enable com.hermes.health-server 2>/dev/null || true
    systemctl --user restart com.hermes.health-server 2>&1 | sed 's/^/    /'
    info "  Health Server restarted"
  elif [[ -f "${HOME}/.hermes-cortex/scripts/health-server.py" ]]; then
    # First-time on macOS: launchctl not registered yet, load it
    info "  Loading Health Server for the first time…"
    mkdir -p "${HOME}/.hermes-cortex/health-server"
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
    # Fallback: .py and .sh files in scripts dir must be executable for no_agent cron jobs
    if [[ "$dest" == "${HERMES_HOME}/scripts/"* ]]; then
      case "$dest" in
        *.py|*.sh) chmod +x "$dest" ;;
      esac
    fi
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

  # Recreate offline_code symlink
  local code_script="${HERMES_HOME}/offline/offline_code.sh"
  local code_link="${HERMES_HOME}/bin/offline_code"
  if [[ -f "$code_script" ]]; then
    mkdir -p "${HERMES_HOME}/bin"
    ln -sf "$code_script" "$code_link"
    info "  Symlink: offline_code"
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

# ── Code Corpus Sync ───────────────────────────────────────
# Syncs the offline code-corpus directory from repo to agent.
# Uses rsync-style copy with checksum check. Only updates
# changed files to minimize unnecessary re-indexing.
sync_code_corpus() {
  local corpus_src="${REPO_DIR}/src/offline/code-corpus"
  local corpus_dest="${HERMES_HOME}/offline/code-corpus"
  [[ -d "$corpus_src" ]] || { info "  No code-corpus/ in repo — skipping"; return 0; }

  mkdir -p "$corpus_dest"
  local synced=0 skipped=0

  while IFS= read -r -d '' src_file; do
    local rel_path="${src_file#$corpus_src/}"
    local dest="${corpus_dest}/${rel_path}"
    mkdir -p "$(dirname "$dest")"

    if needs_update "$src_file" "$dest"; then
      copy_file "$src_file" "$dest"
      synced=$((synced + 1))
    else
      skipped=$((skipped + 1))
    fi
  done < <(find "$corpus_src" -name '*.md' -type f -print0)

  info "  Code corpus: ${synced} new/updated, ${skipped} unchanged"
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

  # On Linux, write to sites-available/ and symlink in sites-enabled/
  # On macOS, servers/ acts as both (no available/enabled split)
  local available_dir="${config_dir}"
  if [[ "$config_dir" == */sites-enabled ]]; then
    available_dir="${config_dir%/sites-enabled}/sites-available"
  fi
  local conf_available="${available_dir}/hermes-services.conf"

  if needs_update "$conf_src" "$conf_dst"; then
    local tmpfile
    tmpfile="$(mktemp)" || return 1

    # Port prefix: template ships as 13xxx (generic default).
    # Set CORTEX_NGINX_PORT_PREFIX to your agent's prefix:
    #   13 = generic/default (no change)
    #   12 = Joseph
    #   14 = Esther
    local port_prefix="${CORTEX_NGINX_PORT_PREFIX:-13}"

    # ── Read existing config (preserve ports/SSL unless forced) ──
    local existing_ssl_cert="" existing_ssl_key=""
    if [[ -f "$conf_dst" && -z "${CORTEX_FORCE_DEPLOY:-}" ]]; then
      existing_ssl_cert=$(grep -oP 'ssl_certificate\s+\K\S+' "$conf_dst" 2>/dev/null | head -1 | sed 's/;$//')
      existing_ssl_key=$(grep -oP 'ssl_certificate_key\s+\K\S+' "$conf_dst" 2>/dev/null | head -1 | sed 's/;$//')
      [[ "$existing_ssl_cert" == "__SSL_CERT__" ]] && existing_ssl_cert=""
      [[ "$existing_ssl_key" == "__SSL_CERT_KEY__" ]] && existing_ssl_key=""
    fi

    # ── SSL cert resolution (only if not preserved) ──────
    local ssl_cert="$existing_ssl_cert" ssl_key="$existing_ssl_key"
    if [[ -z "$ssl_cert" ]]; then
    if [[ -n "${CORTEX_SSL_CERT_PATH:-}" && -n "${CORTEX_SSL_CERT_KEY_PATH:-}" ]]; then
      # Trust the user's env var paths — nginx -t will catch any invalid paths
      ssl_cert="$CORTEX_SSL_CERT_PATH"
      ssl_key="$CORTEX_SSL_CERT_KEY_PATH"
    elif [[ -d /etc/letsencrypt/live ]]; then
      local le_domain="${CORTEX_SSL_DOMAIN:-}"
      if [[ -n "$le_domain" && -f "/etc/letsencrypt/live/$le_domain/fullchain.pem" ]]; then
        ssl_cert="/etc/letsencrypt/live/$le_domain/fullchain.pem"
        ssl_key="/etc/letsencrypt/live/$le_domain/privkey.pem"
      else
        # Scan all Let's Encrypt dirs, take first valid
        for le_dir in /etc/letsencrypt/live/*/; do
          local c="${le_dir}fullchain.pem" k="${le_dir}privkey.pem"
          if [[ -f "$c" && -f "$k" ]]; then
            ssl_cert="$c"; ssl_key="$k"; break
          fi
        done
      fi
    fi
    # Fall back to self-signed ~/certs/
    if [[ -z "$ssl_cert" && -f "${HOME}/certs/fullchain.pem" && -f "${HOME}/certs/privkey.pem" ]]; then
      ssl_cert="${HOME}/certs/fullchain.pem"; ssl_key="${HOME}/certs/privkey.pem"
    fi
    fi  # closes 'if [[ -z "$ssl_cert" ]]' (already preserved from live config)

    if [[ -n "$ssl_cert" ]]; then
      if [[ "$ssl_cert" == "$existing_ssl_cert" && -n "$existing_ssl_cert" ]]; then
        info "  Preserved SSL cert: ${ssl_cert}"
      else
        info "  SSL cert: ${ssl_cert}"
      fi
    else
      warn "  No SSL certs found — __SSL_CERT__ placeholders left unchanged"
    fi

    < "$conf_src" sed \
      -e "s|__NGINX_CONFIG_DIR__|${config_dir}|g" \
      -e "s|__NGINX_LOG_DIR__|${log_dir}|g" \
      -e "s|__HTPASSWD_FILE__|${htpasswd}|g" \
      -e "s|__CORTEX_HOME__|${HOME}|g" \
      -e "s|__SSL_CERT__|${ssl_cert:-__SSL_CERT__}|g" \
      -e "s|__SSL_CERT_KEY__|${ssl_key:-__SSL_CERT_KEY__}|g" \
      -e "/listen[[:space:]]/s|127\\.0\\.0\\.1:13\\([0-9][0-9][0-9]\\)|127.0.0.1:${port_prefix}\\1|g" > "$tmpfile"
    if command -v sudo &>/dev/null && [[ "$config_dir" == /etc/* ]]; then
      # ── Preserve custom port ranges (12xxx Joseph, 14xxx Esther, etc.) ──
      if [[ -f "$conf_dst" ]]; then
        local live_prefix template_prefix
        live_prefix=$(grep -oP 'listen\s+127\.0\.0\.1:\K[0-9]{2}(?=[0-9]{3})' "$conf_dst" | head -1)
        template_prefix=$(grep -oP 'listen\s+127\.0\.0\.1:\K[0-9]{2}(?=[0-9]{3})' "$tmpfile" | head -1)
        if [[ -n "$live_prefix" && -n "$template_prefix" && "$live_prefix" != "$template_prefix" ]]; then
          sed -i "s/:${template_prefix}/:${live_prefix}/g" "$tmpfile"
          info "  Preserved port range ${template_prefix}xxx → ${live_prefix}xxx"
        fi
      fi
      # Write to sites-available (Linux) or servers/ (macOS)
      sudo mkdir -p "$(dirname "$conf_available")" 2>/dev/null || true
      sudo cp "$tmpfile" "$conf_available"
      sudo chmod 644 "$conf_available"
      info "  Updated: ${conf_available}"
    else
      # Write to sites-available (Linux) or servers/ (macOS)
      mkdir -p "$(dirname "$conf_available")" 2>/dev/null || true
      cp "$tmpfile" "$conf_available"
      info "  Updated: ${conf_available}"
    fi
    # Symlink sites-enabled -> sites-available when they differ (Linux convention)
    if [[ "$config_dir" != "$available_dir" ]]; then
      if command -v sudo &>/dev/null && [[ "$config_dir" == /etc/* ]]; then
        sudo mkdir -p "$config_dir" 2>/dev/null || true
        sudo ln -sf "$conf_available" "$conf_dst"
      else
        mkdir -p "$config_dir" 2>/dev/null || true
        ln -sf "$conf_available" "$conf_dst"
      fi
      info "  Symlinked: ${conf_dst} → ${conf_available}"
    fi
    rm -f "$tmpfile"
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

# ── System Scripts Deploy ───────────────────────────────────────
# Deploys admin scripts to /usr/local/sbin/ (root-owned, NOPASSWD-safe).
# Uses sudo on Linux for the root-owned path.
deploy_system_scripts() {
  local deploy_dir="/usr/local/sbin"
  local src_dir="${REPO_DIR}/deploy/nginx"
  local scripts=("hermes-security-apply" "hermes-nginx-clean-restart")
  local files_copied=0

  [[ -d "$src_dir" ]] || return 0

  for script in "${scripts[@]}"; do
    local src="${src_dir}/${script}"
    local dest="${deploy_dir}/${script}"
    [[ ! -f "$src" ]] && continue
    if needs_update "$src" "$dest"; then
      if command -v sudo &>/dev/null; then
        sudo mkdir -p "$deploy_dir" 2>/dev/null || true
        if sudo cp "$src" "$dest" 2>/dev/null; then
          sudo chown root:root "$dest" 2>/dev/null || true
          sudo chmod 755 "$dest" 2>/dev/null || true
          info "  Deployed: ${script} → ${deploy_dir}/"
          files_copied=$((files_copied + 1))
        else
          warn "  Skipped ${script} — sudo not available for ${deploy_dir}/ (add NOPASSWD entry)"
        fi
      else
        mkdir -p "$deploy_dir" 2>/dev/null || true
        cp "$src" "$dest"
        chmod 755 "$dest"
        info "  Deployed: ${script} → ${deploy_dir}/"
        files_copied=$((files_copied + 1))
      fi
    fi
  done

  [[ "$files_copied" -eq 0 ]] && return 0

  # Remove old local copies — canonical version is now in /usr/local/sbin/
  local home_link="${HERMES_HOME}/scripts/hermes-security-apply"
  local agent_link="${HOME}/.hermes/scripts/hermes-security-apply"
  [[ -f "$home_link" ]] && rm -f "$home_link"
  [[ -f "$agent_link" ]] && rm -f "$agent_link"
}

# ── Post-update service verification ─────────────────────────

verify_services() {
  # After an update, verify important services are still managed and running
  local os
  os=$(uname -s)

  if [[ "$os" == "Darwin" ]]; then
    local any_missing=0
    for label in com.ollama.serve com.gbrain.autopilot com.hermes.gateway com.hermes.cortex-dashboard com.hermes.agent-inbox; do
      if ! launchctl list "$label" &>/dev/null 2>&1; then
        warn "$label: not registered with launchd"
        any_missing=$((any_missing + 1))
      fi
    done
    if [[ "$any_missing" -eq 0 ]]; then
      info "All cortex services managed by launchd"
    else
      warn "$any_missing service(s) may need reinstall — run install.sh or check ~/Library/LaunchAgents/"
    fi
  elif [[ "$os" == "Linux" ]]; then
    local any_unmanaged=0 any_inactive=0 managed=0
    for unit in ollama gbrain-autopilot hermes-gateway hermes-cortex-dashboard; do
      # Check system-level first, fall back to user-level
      if systemctl is-active --quiet "$unit" 2>/dev/null || systemctl --user is-active --quiet "$unit" 2>/dev/null; then
        managed=$((managed + 1))
      elif systemctl is-enabled --quiet "$unit" 2>/dev/null || systemctl --user is-enabled --quiet "$unit" 2>/dev/null; then
        any_inactive=$((any_inactive + 1))
        warn "$unit: systemd unit exists but inactive — run: systemctl start $unit"
      else
        any_unmanaged=$((any_unmanaged + 1))
        warn "$unit: not managed by systemd — may need: install.sh or service-writer.sh"
      fi
    done
    if [[ "$any_unmanaged" -eq 0 && "$any_inactive" -eq 0 ]]; then
      info "All $managed cortex services managed by systemd (active)"
    fi
    # Detect unmanaged processes (skip ollama — already covered by the service loop above)
    local hermes_pid
    hermes_pid=$(pgrep -f "hermes_cli.main" 2>/dev/null || true)
    if [[ -n "$hermes_pid" ]] && ! systemctl --user is-active --quiet hermes-gateway 2>/dev/null; then
      warn "⚠ Hermes Gateway running (PID $hermes_pid) but NOT managed by systemd"
    fi
  fi
}

# ── Main ────────────────────────────────────────────────────

install_precommit_hook() {
  local hooks_dir="${HERMES_HOME}/hooks"
  local hook_src="${HERMES_HOME}/scripts/pre-commit-score"
  local push_src="${HERMES_HOME}/scripts/pre-push-pull"

  [[ ! -f "$hook_src" ]] && return 0  # script not deployed yet, skip

  mkdir -p "$hooks_dir"

  # Deploy pre-commit-score to shared hooks dir
  local hook_dest="${hooks_dir}/pre-commit"
  if needs_update "$hook_src" "$hook_dest"; then
    cp "$hook_src" "$hook_dest"
    chmod +x "$hook_dest"
    info "Deployed shared pre-commit hook: ${hook_dest/$HOME/\\~}"
  fi

  # Deploy pre-push-pull to shared hooks dir
  if [[ -f "$push_src" ]]; then
    local push_dest="${hooks_dir}/pre-push"
    if needs_update "$push_src" "$push_dest"; then
      cp "$push_src" "$push_dest"
      chmod +x "$push_dest"
      info "Deployed shared pre-push hook: ${push_dest/$HOME/\\~}"
    fi
  fi

  # Set global hooksPath — this makes ALL git repos on this machine
  # use the shared hooks dir. Per-repo .git/hooks/ is overridden.
  local current_hooks_path
  current_hooks_path=$(git config --global core.hooksPath 2>/dev/null || echo "")
  if [[ "$current_hooks_path" != "$hooks_dir" ]]; then
    git config --global core.hooksPath "$hooks_dir"
    info "Set git global hooksPath → ${hooks_dir/$HOME/\\~}"
    info "  → All repos on this machine now use the scoring hook"
  fi
}

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

  # Sync offline code corpus from repo
  sync_code_corpus

  # Check template drift — warn if local SOUL.md is stale
  if python3 "${HERMES_HOME}/scripts/template-diff-check.py" 2>/dev/null; then
    :  # up to date — silent
  else
    warn "Template drift: run with --status to see details"
    warn "  Update ~/.hermes/SOUL.md to match the template"
  fi

  # Deploy nginx configs (OS-aware path substitution, sudo on Linux)
  deploy_nginx_configs

  # Deploy system scripts to /usr/local/sbin/ (root-owned, NOPASSWD-safe)
  deploy_system_scripts

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

  # Ensure HERMES_HOME/scripts/ → .hermes-cortex/scripts/ symlink
  # (cron security guard resolves this directory and checks script
  # paths against it — a directory-level symlink means both sides
  # of the check land in the same tree, no core agent patch needed)
  _HERMES_AGENT_SCRIPTS="${HOME}/.hermes/scripts"
  _CORTEX_DEPLOY_SCRIPTS="${HERMES_HOME}/scripts"
  # Safety guard: skip symlink dance when both paths resolve to the same directory.
  # This happens when HERMES_HOME is already set to ~/.hermes — rm -rf would
  # delete all installed scripts and create a self-referential symlink.
  if [ "$(cd "$_HERMES_AGENT_SCRIPTS" 2>/dev/null && pwd)" = "$(cd "$_CORTEX_DEPLOY_SCRIPTS" 2>/dev/null && pwd)" ]; then
    :
  elif [ -d "$_HERMES_AGENT_SCRIPTS" ] && [ ! -L "$_HERMES_AGENT_SCRIPTS" ]; then
    _UNIQUE=$(comm -23 \
      <(cd "$_HERMES_AGENT_SCRIPTS" && ls *.py *.sh 2>/dev/null | sort) \
      <(cd "$_CORTEX_DEPLOY_SCRIPTS" && ls *.py *.sh 2>/dev/null | sort))
    if [ -z "$_UNIQUE" ]; then
      rm -rf "$_HERMES_AGENT_SCRIPTS"
      ln -sf "$_CORTEX_DEPLOY_SCRIPTS" "$_HERMES_AGENT_SCRIPTS"
      info "Linked ~/.hermes/scripts/ → cortex (directory symlink)"
    else
      warn "~/.hermes/scripts/ has unique files: $_UNIQUE — not replacing"
    fi
  elif [ ! -e "$_HERMES_AGENT_SCRIPTS" ]; then
    ln -sf "$_CORTEX_DEPLOY_SCRIPTS" "$_HERMES_AGENT_SCRIPTS"
    info "Created ~/.hermes/scripts/ → cortex symlink"
  fi

  # Install pre-commit scoring hook in repo
  install_precommit_hook

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

  # Post-update service verification
  verify_services

  # Install/update universal crons (idempotent — skips existing)
  if command -v hermes &>/dev/null; then
    HERMES_HOME="${HERMES_HOME}" bash "${HERMES_HOME}/scripts/install-crons.sh" 2>/dev/null && \
      info "Crons up to date" || warn "Cron install skipped (no hermes CLI?)"

    # ── Orchestrator-only crons (team health, soul refinement, etc.) ──
    # Only run on orchestrator machines (hostname: moses or esther)
    ORCH_HOST=$(hostname -s 2>/dev/null || echo "unknown")
    case "$ORCH_HOST" in
      moses|esther)
        HERMES_HOME="${HERMES_HOME}" bash "${HERMES_HOME}/scripts/install-orch-crons.sh" 2>/dev/null && \
          info "Orch crons up to date" || warn "Orch cron install skipped" ;;
    esac
  else
    info "Hermes not found — skip cron install (run install-crons.sh after Hermes setup)"
  fi
  echo ""
}

main "$@"
