#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  cortex-update.sh — Pull + full redeploy + service restart
#
#  Copies ALL mapped files to their destinations and restarts
#  affected services. Default is full sync — no flags needed.
#
#  Usage:
#    bash cortex-update.sh                  # full redeploy (default)
#    bash cortex-update.sh --delta          # only changed files
#    bash cortex-update.sh --dry-run        # show what would change
#    bash cortex-update.sh --status         # compare local vs installed
# ─────────────────────────────────────────────────────────────
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BOLD='\033[1m'; CYAN='\033[0;36m'; RESET='\033[0m'

info()  { echo -e "${GREEN}✓${RESET} $*"; }
warn()  { echo -e "${YELLOW}⚠${RESET} $*"; }
error() { echo -e "${RED}✗${RESET} $*"; }

REPO_DIR="${REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"

# ── Detect real user (works even under sudo) ─────────────────
if [ -n "${SUDO_USER:-}" ]; then
  CORTEX_HOME="$(getent passwd "$SUDO_USER" | cut -d: -f6)"
elif [ -n "${HOME:-}" ]; then
  CORTEX_HOME="${HOME}"
else
  CORTEX_HOME="$(getent passwd "$(whoami)" | cut -d: -f6)"
fi

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
      "$HOME/hermes-cortex" \
      "$HOME/git/hermes-cortex"; do
      if [[ -f "$candidate/AGENTS.md" ]]; then
        REPO_DIR="$candidate"
        break
      fi
    done
  fi
fi
# ── Cortex environment — single source of truth ──────────────
# ~/hermes-cortex/.env is the gitignored per-machine config.
# ⚠ ~/.hermes/.env is Hermes Agent's own config — never write to it.
if [[ -f "${REPO_DIR}/.env" ]]; then
  set -a; source "${REPO_DIR}/.env"; set +a
fi

# ── Clean up stale files from old env architecture ───────────
for stale in "${HOME}/.hermes/models.env" "${HOME}/.hermes/hermes-cortex.env" "${REPO_DIR}/ops/install/deploy/hermes-services.env" "${REPO_DIR}/ops/install/deploy/nginx/hermes-services.env"; do
  if [[ -f "$stale" ]]; then
    rm -f "$stale"
    echo "  → Removed stale env file: ${stale}"
  fi
done

# Also source it if present (overrides deploy env for inbox vars)
if [[ -f "${HOME}/.hermes/.env" ]]; then
  set -a; source "${HOME}/.hermes/.env"; set +a
fi
CORTEX_DEPLOY_HOME="${CORTEX_DEPLOY_HOME:-${HOME}/.hermes-cortex}"
STATE_DIR="${CORTEX_DEPLOY_HOME}/state"
LAST_COMMIT_FILE="${STATE_DIR}/update-commit"
BUN_PATH="${HOME}/.bun/bin"
export PATH="${BUN_PATH}:$PATH"

DRY_RUN=false
STATUS_ONLY=false
FORCE_ALL=false
CLEAN_STALE=false
CHANGED=()
TO_RESTART=()
COPIED=0
SKIPPED=0
FORCE_ALL=true
DELTA=false

# Parse options
for arg in "$@"; do
  case "$arg" in
    --delta)     FORCE_ALL=false; DELTA=true ;;
    --dry-run)   DRY_RUN=true ;;
    --status)    STATUS_ONLY=true ;;
    --force-all) FORCE_ALL=true ;;
    --clean-stale) CLEAN_STALE=true ;;
    --help|-h)
      echo "Usage: bash cortex-update.sh [--dry-run|--delta|--status]"
      echo ""
      echo "  --dry-run    Show what would change without touching anything"
      echo "  --delta      Only copy changed files (default: full redeploy)"
      echo "  --status     Compare local repo vs installed files"
      exit 0
      ;;
  esac
done

# ── File-to-destination map ─────────────────────────────────
# Each entry: source_path dest_path [service_label] [restart_cmd]
# source_path is relative to REPO_DIR
#
# ⚠️  RENAME HAZARD: When you rename or move source files in the repo,
#    you MUST update the corresponding register() entry here. The sync
#    silently skips entries whose source_path doesn't exist, leaving
#    stale files in the deploy directory. After any rename:
#      1. Update this register entry
#      2. Run cortex-update.sh --force-all
#      3. Delete the stale deploy file (it won't be cleaned up automatically)
#
#    Example: inbox→bus rename (Jul 2026) left 11 stale inbox-* files
#    in deploy because the register paths weren't updated alongside the
#    repo files. Verify with: comm -23 <(ls deploy) <(ls repo paths)
MAP=()
register() {
  local s1="${1:-}" s2="${2:-}" s3="${3:-}" s4="${4:-}"
  MAP+=("${s1}|${s2}|${s3}|${s4}")
}

# Scripts → ~/.hermes-cortex/scripts/
register "ops/scripts/health/system-alert-watchdog.py"   "${CORTEX_DEPLOY_HOME}/scripts/system-alert-watchdog.py"
register "ops/scripts/hermes_models.py"            "${CORTEX_DEPLOY_HOME}/scripts/hermes_models.py"
register "ops/scripts/hermes_paths.py"             "${CORTEX_DEPLOY_HOME}/scripts/hermes_paths.py"
register "ops/scripts/install/check-system.sh"             "${CORTEX_DEPLOY_HOME}/scripts/check-system.sh"
register "ops/scripts/manage/memory-to-brain-sync.py"    "${CORTEX_DEPLOY_HOME}/scripts/memory-to-brain-sync.py"
register "ops/scripts/install/bootstrap-brain.sh"         "${CORTEX_DEPLOY_HOME}/scripts/bootstrap-brain.sh"
register "ops/scripts/health/check-memory-budget.sh"     "${CORTEX_DEPLOY_HOME}/scripts/check-memory-budget.sh"
register "ops/scripts/install/cortex-profile.sh"          "${CORTEX_DEPLOY_HOME}/scripts/cortex-profile.sh"
register "ops/scripts/install/seed-project-brain.sh"      "${CORTEX_DEPLOY_HOME}/scripts/seed-project-brain.sh"
register "ops/scripts/manage/cortex-health.sh"           "${CORTEX_DEPLOY_HOME}/scripts/cortex-health.sh"
register "ops/scripts/manage/todo-db.py"                "${CORTEX_DEPLOY_HOME}/scripts/todo-db.py"
register "ops/scripts/install/cortex-setup-langfuse.sh"   "${CORTEX_DEPLOY_HOME}/scripts/cortex-setup-langfuse.sh"
register "ops/scripts/setup-fleet-langfuse.sh"         "${CORTEX_DEPLOY_HOME}/scripts/setup-fleet-langfuse.sh"
register "ops/scripts/cortex-update.sh"           "${CORTEX_DEPLOY_HOME}/scripts/cortex-update.sh"
register "ops/scripts/install/install-ollama.sh"          "${CORTEX_DEPLOY_HOME}/scripts/install-ollama.sh"
register "ops/scripts/install/install-nginx.sh"           "${CORTEX_DEPLOY_HOME}/scripts/install-nginx.sh"
register "ops/scripts/install/install-cortex-update-cron.sh" "${CORTEX_DEPLOY_HOME}/scripts/install-cortex-update-cron.sh"
register "ops/scripts/install-crons.sh"       "${CORTEX_DEPLOY_HOME}/scripts/install-crons.sh"
register "ops/scripts/orch-bus/orch-bus-message-tracker.py"     "${CORTEX_DEPLOY_HOME}/scripts/orch-bus-message-tracker.py"
register "ops/scripts/orch-bus/orch-bus-message-tracker-alert.sh" "${CORTEX_DEPLOY_HOME}/scripts/orch-bus-message-tracker-alert.sh"
register "ops/scripts/orch-bus/orch-bus-forwarder.py"     "${CORTEX_DEPLOY_HOME}/scripts/orch-bus-forwarder.py"
register "ops/scripts/install/install-orch-crons.sh"  "${CORTEX_DEPLOY_HOME}/scripts/install-orch-crons.sh"
register "ops/scripts/install/install-score-hook.sh"       "${CORTEX_DEPLOY_HOME}/scripts/install-score-hook.sh"
register "ops/scripts/pre-commit-score"            "${CORTEX_DEPLOY_HOME}/scripts/pre-commit-score"
register "ops/scripts/pre-push-pull"               "${CORTEX_DEPLOY_HOME}/scripts/pre-push-pull"
register "ops/scripts/manage/governance-auditor.py"            "${CORTEX_DEPLOY_HOME}/scripts/governance-auditor.py"
register "ops/scripts/manage/purge-stale-governance-locks.py" "${CORTEX_DEPLOY_HOME}/scripts/purge-stale-governance-locks.py"
register "ops/scripts/manage/prune-soul-profiles.py"          "${CORTEX_DEPLOY_HOME}/scripts/prune-soul-profiles.py"
register "ops/scripts/manage/soul-merge.py"                    "${CORTEX_DEPLOY_HOME}/scripts/soul-merge.py"
register "ops/scripts/manage/soul-sync-all.sh"                 "${CORTEX_DEPLOY_HOME}/scripts/soul-sync-all.sh"
register "ops/scripts/agent/agents-doc-audit.py"          "${CORTEX_DEPLOY_HOME}/scripts/agents-doc-audit.py"
register "ops/scripts/agent/agents-md-prune-scan.py"      "${CORTEX_DEPLOY_HOME}/scripts/agents-md-prune-scan.py"
register "ops/scripts/secret-leak-detector.sh"            "${CORTEX_DEPLOY_HOME}/scripts/secret-leak-detector.sh"
register "ops/scripts/health/check-external-services.sh"   "${CORTEX_DEPLOY_HOME}/scripts/check-external-services.sh"
register "ops/scripts/secret-leak-watchdog.py"            "${CORTEX_DEPLOY_HOME}/scripts/secret-leak-watchdog.py"
register "ops/scripts/install-fallback-providers.py"    "${CORTEX_DEPLOY_HOME}/scripts/install-fallback-providers.py"
register "ops/scripts/manage/cortex-doctor.py"        "${CORTEX_DEPLOY_HOME}/scripts/cortex-doctor.py"
register "ops/scripts/manage/cortex_doctor/__init__.py" "${CORTEX_DEPLOY_HOME}/scripts/cortex_doctor/__init__.py"
register "ops/scripts/manage/cortex_doctor/bus_alert.py" "${CORTEX_DEPLOY_HOME}/scripts/cortex_doctor/bus_alert.py"
register "ops/scripts/manage/cortex_doctor/checks.py"   "${CORTEX_DEPLOY_HOME}/scripts/cortex_doctor/checks.py"
register "ops/scripts/manage/cortex_doctor/cli.py"     "${CORTEX_DEPLOY_HOME}/scripts/cortex_doctor/cli.py"
register "ops/scripts/manage/cortex_doctor/config.py"  "${CORTEX_DEPLOY_HOME}/scripts/cortex_doctor/config.py"
register "ops/scripts/manage/cortex_doctor/fix.py"     "${CORTEX_DEPLOY_HOME}/scripts/cortex_doctor/fix.py"
register "ops/scripts/manage/cortex_doctor/helpers.py" "${CORTEX_DEPLOY_HOME}/scripts/cortex_doctor/helpers.py"
register "ops/scripts/manage/cortex_doctor/results.py" "${CORTEX_DEPLOY_HOME}/scripts/cortex_doctor/results.py"

register "ops/scripts/hc/hc.py"                      "${CORTEX_DEPLOY_HOME}/scripts/hc.py"
register "ops/scripts/hc/hc"                         "${CORTEX_DEPLOY_HOME}/scripts/hc"
register "ops/scripts/health/stale-ref-watchdog.sh"            "${CORTEX_DEPLOY_HOME}/scripts/manage/stale-ref-watchdog.sh"
register "ops/scripts/cron-failure-state.sh"       "${CORTEX_DEPLOY_HOME}/scripts/cron-failure-state.sh"
register "ops/scripts/cron_failure_state.py"       "${CORTEX_DEPLOY_HOME}/scripts/cron_failure_state.py"
register "ops/scripts/install/seed-project.sh"           "${CORTEX_DEPLOY_HOME}/scripts/seed-project.sh"
register "ops/scripts/install/merge-agents-md.py"      "${CORTEX_DEPLOY_HOME}/scripts/merge-agents-md.py"
register "ops/scripts/manage/hermes-update.sh"            "${CORTEX_DEPLOY_HOME}/scripts/hermes-update.sh"
register "ops/scripts/manage/hermes-cortex-sync.sh"      "${CORTEX_DEPLOY_HOME}/scripts/hermes-cortex-sync.sh"
register "ops/scripts/manage/update-session-state.sh"    "${CORTEX_DEPLOY_HOME}/scripts/update-session-state.sh"
register "ops/scripts/manage/fleet-audit.py"             "${CORTEX_DEPLOY_HOME}/scripts/fleet-audit.py"
register "ops/scripts/manage/fleet-costs.py"             "${CORTEX_DEPLOY_HOME}/scripts/fleet-costs.py"
register "ops/scripts/manage/wave-orchestrate.py"        "${CORTEX_DEPLOY_HOME}/scripts/wave-orchestrate.py"
register "ops/scripts/manage/budget-enforcer.py"        "${CORTEX_DEPLOY_HOME}/scripts/budget-enforcer.py"
register "ops/scripts/manage/escalate-to-human.py"     "${CORTEX_DEPLOY_HOME}/scripts/escalate-to-human.py"
register "ops/scripts/manage/fleet-kill-switch.py"    "${CORTEX_DEPLOY_HOME}/scripts/fleet-kill-switch.py"
register "ops/scripts/manage/outerloop.py"               "${CORTEX_DEPLOY_HOME}/scripts/outerloop.py"
register "ops/scripts/lib/handoff_schema.py"             "${CORTEX_DEPLOY_HOME}/scripts/lib/handoff_schema.py"
register "ops/scripts/quality/adversarial-verify.py"     "${CORTEX_DEPLOY_HOME}/scripts/adversarial-verify.py"
register "ops/scripts/orch-bus/orch-bus-fleet-dispatch.py" "${CORTEX_DEPLOY_HOME}/scripts/orch-bus-fleet-dispatch.py"

# Loop-governance scripts (deployed to scripts/ for cron use)
register "core/governance/cleanup-ollama.sh"  "${CORTEX_DEPLOY_HOME}/scripts/cleanup-ollama.sh"
register "core/governance/session_cache.py"    "${CORTEX_DEPLOY_HOME}/scripts/session_cache.py"
register "core/governance/setup.sh"            "${CORTEX_DEPLOY_HOME}/scripts/setup.sh"
register "core/governance/verify.sh"           "${CORTEX_DEPLOY_HOME}/scripts/verify.sh"
register "core/governance/update.sh"           "${CORTEX_DEPLOY_HOME}/scripts/update.sh"

register "ops/scripts/health/prod-watchdog.sh"          "${CORTEX_DEPLOY_HOME}/scripts/prod-watchdog.sh"
register "ops/scripts/agent/orch-fleet-watchdog.py"   "${CORTEX_DEPLOY_HOME}/scripts/orch-fleet-watchdog.py"

# Post-commit notification + installer
register "ops/scripts/manage/post-commit-notify.sh"          "${CORTEX_DEPLOY_HOME}/scripts/post-commit-notify.sh"
register "ops/scripts/install/install-post-commit-hook.sh"    "${CORTEX_DEPLOY_HOME}/scripts/install-post-commit-hook.sh"

# Template drift checker (runs during cortex-update.sh)
register "ops/scripts/manage/template-diff-check.py"          "${CORTEX_DEPLOY_HOME}/scripts/template-diff-check.py"

# Moses bus remediation
register "ops/scripts/bus/bus-remediate.sh"  "${CORTEX_DEPLOY_HOME}/scripts/bus-remediate.sh"

# Auto-remediation scripts
register "ops/scripts/health/cron-auto-remediate.sh"     "${CORTEX_DEPLOY_HOME}/scripts/cron-auto-remediate.sh"
register "ops/scripts/agent/orch-weekly-auto-fix.py"    "${CORTEX_DEPLOY_HOME}/scripts/orch-weekly-auto-fix.py"

# System watchdog scripts (no_agent cron jobs)
register "ops/scripts/health/service-recovery.py"        "${CORTEX_DEPLOY_HOME}/scripts/service-recovery.py"
register "ops/scripts/platform_utils.py"          "${CORTEX_DEPLOY_HOME}/scripts/platform_utils.py"
# Agent daily bible reading (deployed from profile scripts)
register "profiles/personal/scripts/agent-daily-bible-reading.py" "${CORTEX_DEPLOY_HOME}/scripts/agent-daily-bible-reading.py"
register "ops/scripts/health/langfuse-health-watchdog.py" "${CORTEX_DEPLOY_HOME}/scripts/langfuse-health-watchdog.py"
register "ops/scripts/manage/llm-judge-scorer.py"         "${CORTEX_DEPLOY_HOME}/scripts/llm-judge-scorer.py"
register "ops/scripts/health/model-health-watchdog.py"    "${CORTEX_DEPLOY_HOME}/scripts/model-health-watchdog.py"
register "ops/scripts/manage/offline-code-index-cron.sh" "${CORTEX_DEPLOY_HOME}/scripts/offline-code-index-cron.sh"
register "ops/scripts/manage/harvest-lessons.sh"         "${CORTEX_DEPLOY_HOME}/scripts/harvest-lessons.sh"
register "core/governance/skill_miner.py"                "${CORTEX_DEPLOY_HOME}/scripts/skill_miner.py"
register "ops/scripts/health/swap-refresh.py"            "${CORTEX_DEPLOY_HOME}/scripts/swap-refresh.py"
register "ops/scripts/health/cron-quality-watchdog.py"    "${CORTEX_DEPLOY_HOME}/scripts/cron-quality-watchdog.py"
register "ops/scripts/agent/agent-cron-failure-scanner.py" "${CORTEX_DEPLOY_HOME}/scripts/agent-cron-failure-scanner.py"
register "ops/scripts/health/scoring-activity-watchdog.py" "${CORTEX_DEPLOY_HOME}/scripts/scoring-activity-watchdog.py"
register "ops/scripts/state_tracker.py"             "${CORTEX_DEPLOY_HOME}/scripts/state_tracker.py"
register "ops/scripts/health/check-certs.py"               "${CORTEX_DEPLOY_HOME}/scripts/check-certs.py"
# daily-bible-reading.sh was deleted from repo — replaced by agent-daily-bible-reading.py
register "ops/scripts/bus/generate-bus-wrappers.py"      "${CORTEX_DEPLOY_HOME}/scripts/generate-bus-wrappers.py"
register "ops/scripts/manage/nginx-security-scanner.sh"    "${CORTEX_DEPLOY_HOME}/scripts/nginx-security-scanner.sh"
register "ops/scripts/manage/nginx-threat-pipeline.sh"     "${CORTEX_DEPLOY_HOME}/scripts/nginx-threat-pipeline.sh"
register "ops/scripts/manage/deploy-blocked-ips.sh"        "${CORTEX_DEPLOY_HOME}/scripts/deploy-blocked-ips.sh"
register "ops/scripts/agent/agent-remediate-apply.py"  "${CORTEX_DEPLOY_HOME}/scripts/agent-remediate-apply.py"
register "ops/scripts/agent/agent-apply-fixes.py"      "${CORTEX_DEPLOY_HOME}/scripts/agent-apply-fixes.py"
register "ops/scripts/agent/agent-ip-submission.sh"      "${CORTEX_DEPLOY_HOME}/scripts/agent-ip-submission.sh"
register "ops/scripts/agent/agent-worker.py"             "${CORTEX_DEPLOY_HOME}/scripts/agent-worker.py"
register "ops/scripts/agent/contact-moses.sh"            "${CORTEX_DEPLOY_HOME}/scripts/contact-moses.sh"
register "ops/scripts/agent/install-worker.sh"      "${CORTEX_DEPLOY_HOME}/scripts/install-worker.sh"
# Pre-commit hook — deployed to hooks/ (not scripts/) for git's core.hooksPath
register ".hermes-cortex/hooks/pre-commit"  "${CORTEX_DEPLOY_HOME}/hooks/pre-commit"
# Post-merge hook — auto-runs cortex-update.sh --force-all after every git pull
register ".hermes-cortex/hooks/post-merge"   "${CORTEX_DEPLOY_HOME}/hooks/post-merge"

# Deploy scripts (nginx security pipeline) — now deployed to /usr/local/sbin/
# by deploy_system_scripts() below. Old register entries removed.

# Deployment-specific cron scripts
register "ops/scripts/manage/auto-save-sessions.py"      "${CORTEX_DEPLOY_HOME}/scripts/auto-save-sessions.py"
register "ops/scripts/agent/agent-health-monitor.py"    "${CORTEX_DEPLOY_HOME}/scripts/agent-health-monitor.py"
register "ops/scripts/manage/gbrain-nightly-dream.sh"   "${CORTEX_DEPLOY_HOME}/scripts/gbrain-nightly-dream.sh"
register "ops/scripts/manage/gbrain-update-sync.sh"     "${CORTEX_DEPLOY_HOME}/scripts/gbrain-update-sync.sh"
register "ops/scripts/manage/gbrain-wrapper.sh"         "${CORTEX_DEPLOY_HOME}/scripts/gbrain-wrapper.sh"
register "ops/scripts/manage/gbrain-doctor-summary.py"   "${CORTEX_DEPLOY_HOME}/scripts/gbrain-doctor-summary.py"
register "ops/scripts/manage/send-skill-report.py"       "${CORTEX_DEPLOY_HOME}/scripts/send-skill-report.py"
register "ops/scripts/state_tracker.py"           "${CORTEX_DEPLOY_HOME}/scripts/state_tracker.py"

register "mcp-servers/agent-bus-mcp.py"                "${CORTEX_DEPLOY_HOME}/scripts/agent-bus-mcp.py"

# Inbox MCP tools
# Inbox→bus renamed scripts (source files moved to ops/scripts/bus/)
# inbox-flag.py retained at ops/scripts/inbox/ for BWC
register "ops/scripts/inbox/inbox-flag.py"              "${CORTEX_DEPLOY_HOME}/scripts/inbox-flag.py"
register "ops/scripts/bus/bus-processor.py"        "${CORTEX_DEPLOY_HOME}/scripts/bus-processor.py"
register "ops/scripts/bus/bus-remediate.sh"        "${CORTEX_DEPLOY_HOME}/scripts/bus-remediate.sh"
register "ops/scripts/bus/generate-bus-wrappers.py"     "${CORTEX_DEPLOY_HOME}/scripts/generate-bus-wrappers.py"
register "ops/scripts/install/setup-agent-bus.sh"       "${CORTEX_DEPLOY_HOME}/scripts/setup-agent-bus.sh"

# Bus monitoring tools (fleet-wide)
register "ops/scripts/orch-bus/orch-bus-depth-watchdog.sh"  "${CORTEX_DEPLOY_HOME}/scripts/orch-bus-depth-watchdog.sh"
register "ops/scripts/orch-bus/orch-bus-audit-watchdog.py"     "${CORTEX_DEPLOY_HOME}/scripts/orch-bus-audit-watchdog.py"
register "ops/scripts/orch-bus/orch-bus-recover-timeouts.sh"   "${CORTEX_DEPLOY_HOME}/scripts/orch-bus-recover-timeouts.sh"
register "ops/scripts/manage/loop-gov-mcp.sh"            "${CORTEX_DEPLOY_HOME}/scripts/loop-gov-mcp.sh"
# agent-inbox-monitor.sh and orch-inbox-processor.py replaced by bus equivalents above
# (ops/scripts/bus/agent-bus-monitor.sh, ops/scripts/bus/bus-processor.py)
# NOTE: check-agent-messages.sh was renamed to orch-check-agent-messages.sh (local only, not in repo)
# The crontab on this server was updated to use the correct name.
#register "ops/scripts/agent/check-agent-messages.sh"    "${CORTEX_DEPLOY_HOME}/scripts/check-agent-messages.sh"
register "ops/scripts/manage/ek-session-snapshot.py"     "${CORTEX_DEPLOY_HOME}/scripts/ek-session-snapshot.py"

# Fleet watchdog — cross-agent health polling (orch, deployed by install-orch-crons.sh)
register "ops/scripts/agent/orch-fleet-watchdog.py"      "${CORTEX_DEPLOY_HOME}/scripts/orch-fleet-watchdog.py"
register "ops/scripts/agent/agent-gbrain-doctor.sh"       "${CORTEX_DEPLOY_HOME}/scripts/agent-gbrain-doctor.sh"

# gbrain autopilot — systemd user service (replaces old sync-watch cron/launchd)
register "ops/install/deploy/gbrain-autopilot.service"       "${HOME}/.config/systemd/user/gbrain-autopilot.service" "restart_gbrain_sync"
register "ops/scripts/install/install-gbrain-sync.sh"    "${CORTEX_DEPLOY_HOME}/scripts/install-gbrain-sync.sh"

# Orchestrator health report — periodic agent fleet snapshot (no_agent cron)
register "ops/scripts/agent/orch-health-report.py"       "${CORTEX_DEPLOY_HOME}/scripts/orch-health-report.py"

# Cron cost tracking — SQLite store + deployment script
register "ops/scripts/cost_store.py"               "${CORTEX_DEPLOY_HOME}/scripts/cost_store.py"
register "ops/scripts/install/install-cron-cost-tracking.py" "${CORTEX_DEPLOY_HOME}/scripts/install-cron-cost-tracking.py"

# Health monitoring
register "ops/scripts/change-validate.sh"                  "${CORTEX_DEPLOY_HOME}/scripts/change-validate.sh"
register "ops/scripts/pre-commit-doc-audit.sh"            "${CORTEX_DEPLOY_HOME}/scripts/pre-commit-doc-audit.sh"
register "ops/scripts/health/health-vector.py"            "${CORTEX_DEPLOY_HOME}/scripts/health-vector.py"
register "ops/scripts/health/health-vector-push.sh"       "${CORTEX_DEPLOY_HOME}/scripts/health-vector-push.sh"
register "ops/scripts/health/report-agent-health.py"      "${CORTEX_DEPLOY_HOME}/scripts/report-agent-health.py"
register "ops/scripts/manage/request-skill-reports.sh"    "${CORTEX_DEPLOY_HOME}/scripts/request-skill-reports.sh"

# Shared model config loader (imported by many scripts)

# Bus sensor and health tools (fleet-wide)
register "ops/scripts/orch-bus/orch-bus-health-check.py"  "${CORTEX_DEPLOY_HOME}/scripts/orch-bus-health-check.py"
register "ops/scripts/orch-bus/orch-bus-watch.py"         "${CORTEX_DEPLOY_HOME}/scripts/orch-bus-watch.py"
register "ops/scripts/orch-bus/orch-bus-watch.sh"         "${CORTEX_DEPLOY_HOME}/scripts/orch-bus-watch.sh"
register "ops/scripts/orch-bus/orch-bus-mcp.py"           "${CORTEX_DEPLOY_HOME}/scripts/orch-bus-mcp.py"
register "ops/scripts/orch-bus/orch-bus-readiness-check.py" "${CORTEX_DEPLOY_HOME}/scripts/orch-bus-readiness-check.py"
register "ops/scripts/orch-bus/orch-bus-git-auth-check.py" "${CORTEX_DEPLOY_HOME}/scripts/orch-bus-git-auth-check.py"
register "ops/scripts/orch-bus/orch-clean-health-queue.py" "${CORTEX_DEPLOY_HOME}/scripts/orch-clean-health-queue.py"
register "ops/scripts/orch-bus/orch-bus-generate-wrappers.py" "${CORTEX_DEPLOY_HOME}/scripts/orch-bus-generate-wrappers.py"
register "ops/scripts/orch-bus/orch-bus-test.py"            "${CORTEX_DEPLOY_HOME}/scripts/orch-bus-test.py"

# Fleet agent message handler (polls inbox for UPDATE_REQUEST etc.)
register "ops/scripts/agent/agent-message-handler.py" "${CORTEX_DEPLOY_HOME}/scripts/agent-message-handler.py"
register "ops/scripts/agent/agent-diagnostic.py"       "${CORTEX_DEPLOY_HOME}/scripts/agent-diagnostic.py"

# Timezone helper (required by monitoring scripts)
register "ops/scripts/hermes_tz.py"                "${CORTEX_DEPLOY_HOME}/scripts/hermes_tz.py"

# Remediation sensor (companion to agent-auto-remediate cron)
register "ops/scripts/health/remediation-sensor.py"       "${CORTEX_DEPLOY_HOME}/scripts/remediation-sensor.py"

# Eval harness (agent reliability patterns)
register "ops/scripts/manage/run-evals.py"                "${CORTEX_DEPLOY_HOME}/scripts/run-evals.py"
register "ops/scripts/manage/analyze-failures.py"         "${CORTEX_DEPLOY_HOME}/scripts/analyze-failures.py"

# Agent learning sender
register "ops/scripts/manage/send-agent-learning.sh"      "${CORTEX_DEPLOY_HOME}/scripts/send-agent-learning.sh"

# Skill collection pipeline
register "ops/scripts/manage/collect-agent-skills.sh"     "${CORTEX_DEPLOY_HOME}/scripts/collect-agent-skills.sh"

# Migration scripts
register "ops/scripts/manage/migrate-orch-bus-names.sh"   "${CORTEX_DEPLOY_HOME}/scripts/migrate-orch-bus-names.sh"
register "ops/scripts/manage/request-skill-reports.sh"    "${CORTEX_DEPLOY_HOME}/scripts/request-skill-reports.sh"
register "ops/scripts/manage/process-skill-reports.py"    "${CORTEX_DEPLOY_HOME}/scripts/process-skill-reports.py"
register "ops/scripts/manage/agent-learning-collector.py" "${CORTEX_DEPLOY_HOME}/scripts/agent-learning-collector.py"
# orch-bus-* scripts are orchestrator-only — run from repo path
# Shared bus library for fleet scripts
register "ops/scripts/lib/cortex_bus.py" "${CORTEX_DEPLOY_HOME}/scripts/lib/cortex_bus.py"

# Agent inbox check is DEPRECATED — replaced by MCP tools. File retained in deploy for reference.

# Lesson-aware scripts (Memory That Compounds)
register "ops/scripts/manage/daily-lesson-mine.sh"      "${CORTEX_DEPLOY_HOME}/scripts/daily-lesson-mine.sh"
register "ops/scripts/manage/lesson-compound-stats.py"   "${CORTEX_DEPLOY_HOME}/scripts/lesson-compound-stats.py"
register "ops/scripts/manage/lesson-hit.sh"              "${CORTEX_DEPLOY_HOME}/scripts/lesson-hit.sh"
register "ops/scripts/manage/fix-cron-duplicates.py"  "${CORTEX_DEPLOY_HOME}/scripts/manage/fix-cron-duplicates.py"

# Offline tools
register "ops/offline/offline_knowledge.py"       "${CORTEX_DEPLOY_HOME}/offline/offline_knowledge.py"
register "ops/offline/offline_knowledge.sh"       "${CORTEX_DEPLOY_HOME}/offline/offline_knowledge.sh"
register "ops/offline/offline_code.py"            "${CORTEX_DEPLOY_HOME}/offline/offline_code.py"
register "ops/offline/offline_code.sh"            "${CORTEX_DEPLOY_HOME}/offline/offline_code.sh"
register "ops/offline/kiwix-docker-compose.yml"   "${CORTEX_DEPLOY_HOME}/offline/kiwix-docker-compose.yml"
register "ops/offline/prep-offline.sh"            "${CORTEX_DEPLOY_HOME}/offline/prep-offline.sh"
register "ops/offline/session_mine.py"            "${CORTEX_DEPLOY_HOME}/offline/session_mine.py"
register "ops/scripts/hermes_paths.py"             "${CORTEX_DEPLOY_HOME}/offline/hermes_paths.py"
register "ops/offline/lessons.py"                 "${CORTEX_DEPLOY_HOME}/offline/lessons.py"
register "ops/offline/migrate_fts_reasoning.sql"  "${CORTEX_DEPLOY_HOME}/offline/migrate_fts_reasoning.sql"
register "ops/offline/auto-update.sh"             "${CORTEX_DEPLOY_HOME}/offline/auto-update.sh"

# A2A Agent Card generator — generates agent identity cards for bus registry
register "ops/services/bus/agent-card/generate-agent-card.py"         "${CORTEX_DEPLOY_HOME}/scripts/generate-agent-card.py"
register "ops/services/bus/agent-card/agent-card.json"                "${CORTEX_DEPLOY_HOME}/bus/agent-card.json"

# Templates → ~/.hermes/memories/ (guarded — only if dest missing)
register "docs/templates/MEMORY.seed.md"      "${CORTEX_DEPLOY_HOME}/memories/MEMORY.md"
register "docs/templates/USER.seed.md"        "${CORTEX_DEPLOY_HOME}/memories/USER.md"
register "docs/templates/memory-readme.seed.md" "${CORTEX_DEPLOY_HOME}/memory/README.md"

# Langfuse
register "ops/install/deploy/docker-compose.langfuse.yml"        "${HOME}/langfuse/docker-compose.yml" "langfuse" "restart_langfuse"

# Dashboard
register "ops/services/dashboard/server.py"               "${CORTEX_DEPLOY_HOME}/dashboard/server.py" "dashboard" "restart_dashboard"
register "ops/services/dashboard/static/index.html"        "${CORTEX_DEPLOY_HOME}/dashboard/static/index.html" "dashboard"
register "ops/services/dashboard/com.hermes.cortex-dashboard.plist" "${HOME}/Library/LaunchAgents/com.hermes.cortex-dashboard.plist" "dashboard"

# Agent Bus
register "ops/services/agent-bus/server.py"              "${CORTEX_DEPLOY_HOME}/bus/server.py" "agent-bus" "restart_agent_bus"
register "ops/services/agent-bus/nginx.conf"             "${CORTEX_DEPLOY_HOME}/bus/nginx.conf"

# Service definitions
register "ops/scripts/install/os-config.sh"               "${CORTEX_DEPLOY_HOME}/scripts/os-config.sh"
register "ops/scripts/install/service-writer.sh"          "${CORTEX_DEPLOY_HOME}/scripts/service-writer.sh"

restart_agent_bus() {
  # macOS launchd
  if launchctl list com.hermes.agent-bus 2>/dev/null | grep -q "PID"; then
    info "  Restarting Agent Bus (launchd)…"
    launchctl bootout gui/$(id -u) "${HOME}/Library/LaunchAgents/com.hermes.agent-bus.plist" 2>/dev/null || true
    launchctl bootstrap gui/$(id -u) "${HOME}/Library/LaunchAgents/com.hermes.agent-bus.plist" 2>/dev/null || true
    return
  fi
  # Linux systemd
  if systemctl --user is-active --quiet hermes-agent-bus 2>/dev/null; then
    info "  Restarting Agent Bus (systemd)…"
    systemctl --user daemon-reload 2>/dev/null || true
    systemctl --user restart hermes-agent-bus 2>&1 | sed 's/^/    /'
  fi
}

# ── gbrain upgrade ────────────────────────────────────────

update_gbrain_binary() {
  info "Checking gbrain version…"
  local before
  before=$(gbrain version 2>/dev/null || echo "none")
  gbrain upgrade 2>&1 | sed 's/^/    /'
  local after
  after=$(gbrain version 2>/dev/null || echo "none")
  if [[ "$before" != "$after" ]]; then
    info "gbrain upgraded: $before → $after"
  else
    info "gbrain already current: $after"
  fi
}

# ── Service restart helpers ─────────────────────────────────

restart_gbrain_sync() {
  local autopilot_label="com.gbrain.autopilot"
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
    local inbox_dir="${CORTEX_DEPLOY_HOME}/agent-inbox"
    if [[ ! -d "${inbox_dir}/venv" ]]; then
      python3.12 -m venv "${inbox_dir}/venv" 2>/dev/null || python3 -m venv "${inbox_dir}/venv" 2>/dev/null || true
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
  info "  health-server.py has been removed — use health-vector.service instead."
  info "  Run: systemctl --user restart health-vector.service"
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
    if [[ "$dest" == "${CORTEX_DEPLOY_HOME}/scripts/"* ]]; then
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

# Scans deploy dir for files not in MAP and removes them
clean_stale_deploys() {
  local cleaned=0
  info "🧹 Scanning for stale deploy files..."

  # Files to preserve even if not registered (cron-referenced)
  local preserve=(
    "model-health-watchdog.py"
    "harvest-lessons.sh"
    "offline-code-index-cron.sh"
    "skill_miner.py"
    "swap-refresh.py"
    "nginx-threat-pipeline.sh"
  )

  # Build list of all registered destinations
  local dests=()
  for entry in "${MAP[@]}"; do
    local dest
    IFS='|' read -r _ dest _ _ <<< "$entry"
    # NOTE: MAP stores already-expanded paths (bash expands ${VAR} at register time).
    # The old `\$` pattern substitution here was broken on bash 3.2.57 (macOS) —
    # it incorrectly appended the replacement value even when the pattern
    # didn't match, corrupting paths. Removed as unnecessary.
    dests+=("$dest")
  done

  # Scan the scripts dir for files not in the dest list
  local scan_dir="${CORTEX_DEPLOY_HOME}/scripts"
  if [[ -d "$scan_dir" ]]; then
    while IFS= read -r -d '' f; do
      local match=false
      # Check registered destinations
      for d in "${dests[@]}"; do
        if [[ "$f" == "$d" ]]; then
          match=true
          break
        fi
      done
      # Check preserve list (cron-referenced scripts)
      if ! $match; then
        local basename="${f##*/}"
        for p in "${preserve[@]}"; do
          if [[ "$basename" == "$p" ]]; then
            match=true
            break
          fi
        done
      fi
      if ! $match; then
        local size
        size=$(stat -c%s "$f" 2>/dev/null || stat -f%z "$f" 2>/dev/null || echo "?")
        if $DRY_RUN; then
          info "  [dry-run] Would remove stale: ${f/$HOME/~} (${size} bytes)"
        else
          rm -f "$f"
          info "  🗑️  Removed stale: ${f/$HOME/~} (${size} bytes)"
          ((cleaned++))
        fi
      fi
    done < <(find "$scan_dir" -type f \( -name '*.py' -o -name '*.sh' \) -print0)
  fi

  if $DRY_RUN; then
    info "  Dry-run complete — ${cleaned} would be removed"
  elif [[ $cleaned -gt 0 ]]; then
    info "  Cleaned ${cleaned} stale file(s)"
  else
    info "  No stale files found"
  fi
}

# ── Symlinks ────────────────────────────────────────────────

update_symlinks() {
  # Recreate web_cache symlink
  local src="${CORTEX_DEPLOY_HOME}/web-cache/web_cache.sh"
  local link="${CORTEX_DEPLOY_HOME}/bin/web_cache"
  if [[ -f "$src" ]]; then
    mkdir -p "${CORTEX_DEPLOY_HOME}/bin"
    ln -sf "$src" "$link"
    info "  Symlink: web_cache"
  fi

  # Recreate offline symlinks
  local offline_script="${CORTEX_DEPLOY_HOME}/offline/offline_knowledge.sh"
  local offline_link="${CORTEX_DEPLOY_HOME}/bin/offline_knowledge"
  if [[ -f "$offline_script" ]]; then
    ln -sf "$offline_script" "$offline_link"
    info "  Symlink: offline_knowledge"
  fi

  local prep_script="${CORTEX_DEPLOY_HOME}/offline/prep-offline.sh"
  local prep_link="${CORTEX_DEPLOY_HOME}/bin/prep-offline"
  if [[ -f "$prep_script" ]]; then
    ln -sf "$prep_script" "$prep_link"
    info "  Symlink: prep-offline"
  fi

  # Recreate offline_code symlink
  local code_script="${CORTEX_DEPLOY_HOME}/offline/offline_code.sh"
  local code_link="${CORTEX_DEPLOY_HOME}/bin/offline_code"
  if [[ -f "$code_script" ]]; then
    mkdir -p "${CORTEX_DEPLOY_HOME}/bin"
    ln -sf "$code_script" "$code_link"
    info "  Symlink: offline_code"
  fi
}

# ── Skill Sync ───────────────────────────────────────────────
# Copies SKILL.md files and references/ from repo skills/ directories
# to ~/.hermes/skills/. Uses the delta engine — only copies
# files whose checksums differ from installed versions.
# Syncs from TWO locations:
#   1. $REPO_DIR/skills/              — canonical global skills (categorized)
#   2. $REPO_DIR/.hermes-cortex/skills/ — project-level overrides (flat)
sync_skills() {
  local skill_dest="${CORTEX_DEPLOY_HOME}/skills"
  local synced=0 skipped=0
  mkdir -p "$skill_dest"

  # ── Pass 1: Root-level skills/ (canonical global skills) ──
  local root_skills="${REPO_DIR}/skills"
  if [[ -d "$root_skills" ]]; then
    while IFS= read -r -d '' skill_file; do
      local rel_path="${skill_file#$root_skills/}"
      local dest="${skill_dest}/${rel_path}"
      mkdir -p "$(dirname "$dest")"

      if needs_update "$skill_file" "$dest"; then
        copy_file "$skill_file" "$dest"
        synced=$((synced + 1))
      else
        skipped=$((skipped + 1))
      fi
    done < <(find "$root_skills" -name "SKILL.md" -type f -print0)

    # Sync reference files
    while IFS= read -r -d '' ref_file; do
      local rel_path="${ref_file#$root_skills/}"
      local dest="${skill_dest}/${rel_path}"
      mkdir -p "$(dirname "$dest")"

      if needs_update "$ref_file" "$dest"; then
        copy_file "$ref_file" "$dest"
      fi
    done < <(find "$root_skills" -path "*/references/*" -type f -print0)
  fi

  # ── Pass 2: Project-level overrides (.hermes-cortex/skills/) ──
  local override_skills="${REPO_DIR}/.hermes-cortex/skills"
  if [[ ! -d "$override_skills" ]]; then
    info "  Skills: ${synced} updated, ${skipped} unchanged"
    return 0
  fi

  while IFS= read -r -d '' skill_file; do
    local rel_path="${skill_file#$override_skills/}"
    local dest="${skill_dest}/${rel_path}"
    mkdir -p "$(dirname "$dest")"

    if needs_update "$skill_file" "$dest"; then
      copy_file "$skill_file" "$dest"
      synced=$((synced + 1))
    else
      skipped=$((skipped + 1))
    fi
  done < <(find "$override_skills" -name "SKILL.md" -type f -print0)

  # Sync reference files
  while IFS= read -r -d '' ref_file; do
    local rel_path="${ref_file#$override_skills/}"
    local dest="${skill_dest}/${rel_path}"
    mkdir -p "$(dirname "$dest")"

    if needs_update "$ref_file" "$dest"; then
      copy_file "$ref_file" "$dest"
    fi
  done < <(find "$override_skills" -path "*/references/*" -type f -print0)

  info "  Skills: ${synced} updated, ${skipped} unchanged"
}

# ── Code Corpus Sync ───────────────────────────────────────
# Syncs the offline code-corpus directory from repo to agent.
# Uses rsync-style copy with checksum check. Only updates
# changed files to minimize unnecessary re-indexing.
sync_code_corpus() {
  local corpus_src="${REPO_DIR}/ops/offline/code-corpus"
  local corpus_dest="${CORTEX_DEPLOY_HOME}/offline/code-corpus"
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
  local nginx_src_dir="${REPO_DIR}/ops/install/deploy/nginx"
  [[ -d "$nginx_src_dir" ]] || return 0

  local config_dir="${NGINX_CONFIG_DIR:-}"
  local brew_dir="${NGINX_ROOT:-}"
  local log_dir="${NGINX_LOG_DIR:-}"
  local htpasswd="${NGINX_HTPASSWD:-}"

  # If OS config not loaded, try to determine paths from REPO_DIR
  if [[ -z "$config_dir" ]]; then
    local os_script="${REPO_DIR}/ops/scripts/install/os-config.sh"
    [[ -f "$os_script" ]] && source "$os_script" 2>/dev/null || true
    config_dir="${NGINX_CONFIG_DIR:-}"
    brew_dir="${NGINX_ROOT:-}"
    log_dir="${NGINX_LOG_DIR:-}"
    htpasswd="${NGINX_HTPASSWD:-}"
  fi

  [[ -z "$config_dir" || -z "$brew_dir" ]] && { info "  nginx paths unknown — skipping nginx deploy"; return 0; }

  local files_copied=0

  # 1. hermes-zone-defs.conf — no substitution needed, copy directly
  local zone_src="${nginx_src_dir}/hermes-zone-defs.conf"
  local zone_dst="${brew_dir}/hermes-zone-defs.conf"
  if needs_update "$zone_src" "$zone_dst"; then
    info "  Updated template: ${zone_src}"
    info "  Deploy with: sudo cp ${zone_src} ${zone_dst}"
    files_copied=$((files_copied + 1))
  fi

  # 2. hermes-services.conf — substitute placeholders, then diff against deployed
  local conf_src="${nginx_src_dir}/hermes-services.conf"
  local conf_dst="${config_dir}/hermes-services.conf"

  # On Linux, write to sites-available/ and symlink in sites-enabled/
  # On macOS, servers/ acts as both (no available/enabled split)
  local available_dir="${config_dir}"
  if [[ "$config_dir" == */sites-enabled ]]; then
    available_dir="${config_dir%/sites-enabled}/sites-available"
  fi
  local conf_available="${available_dir}/hermes-services.conf"

  # Cleanup: detect stale macOS-style servers/ dir on Linux
  if [[ -d "${config_dir%/sites-enabled}/servers" ]]; then
    local stale_servers="${config_dir%/sites-enabled}/servers/hermes-services.conf"
    if [[ -f "$stale_servers" ]]; then
      warn "  Stale file detected: ${stale_servers}"
      warn "  Remove with: sudo rm ${stale_servers}"
      warn "  (macOS-style path — nginx on Linux uses sites-available/ instead)"
    fi
  fi

  [[ ! -f "$conf_src" ]] && return 0

  local tmpfile="/tmp/hermes-services-processed.conf"
  # Clean any leftover from a previous run
  rm -f "$tmpfile"

  # Port prefix: template ships as 13xxx (generic default).
  # Set CORTEX_NGINX_PORT_PREFIX to your agent's prefix:
  #   13 = generic/default (no change)
  #   12 = Joseph
  #   14 = Esther
  local port_prefix="${CORTEX_NGINX_PORT_PREFIX:-13}"

  # ── Read existing config (preserve ports/SSL unless forced) ──
  local existing_ssl_cert="" existing_ssl_key=""
  if [[ -f "$conf_dst" && -z "${CORTEX_FORCE_DEPLOY:-}" ]]; then
    # POSIX-safe SSL cert extraction (macOS BSD tools don't support grep -P)
    existing_ssl_cert=$(sed -n 's/^[[:space:]]*ssl_certificate[[:space:]]\{1,\}\([^;]*\);/\1/p' "$conf_dst" | head -1) || true
    existing_ssl_key=$(sed -n 's/^[[:space:]]*ssl_certificate_key[[:space:]]\{1,\}\([^;]*\);/\1/p' "$conf_dst" | head -1) || true
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
  if [[ -z "$ssl_cert" && -f "${CORTEX_HOME}/certs/fullchain.pem" && -f "${CORTEX_HOME}/certs/privkey.pem" ]]; then
    ssl_cert="${CORTEX_HOME}/certs/fullchain.pem"; ssl_key="${CORTEX_HOME}/certs/privkey.pem"
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
    -e "s|/etc/nginx/|${brew_dir}/|g" \
    -e "s|__NGINX_CONFIG_DIR__|${config_dir}|g" \
    -e "s|__NGINX_BREW_DIR__|${brew_dir}|g" \
    -e "s|__NGINX_LOG_DIR__|${log_dir}|g" \
    -e "s|__HTPASSWD_FILE__|${htpasswd}|g" \
    -e "s|__CORTEX_HOME__|${CORTEX_HOME}|g" \
    -e "s|__SSL_CERT__|${ssl_cert:-__SSL_CERT__}|g" \
    -e "s|__SSL_CERT_KEY__|${ssl_key:-__SSL_CERT_KEY__}|g" \
    -e "/listen[[:space:]]/s|127\\.0\\.0\\.1:13\\([0-9][0-9][0-9]\\)|127.0.0.1:${port_prefix}\\1|g" \
    -e "/listen[[:space:]]/s|listen 13\\([0-9][0-9][0-9]\\) ssl|listen ${port_prefix}\\1 ssl|g" > "$tmpfile"

  # ── Port preservation (must happen before deploy) ──
  # Preserve custom port ranges (12xxx Joseph, 14xxx Esther, etc.)
  if [[ -f "$conf_dst" ]]; then
    local live_prefix template_prefix
    # POSIX-safe extraction (macOS BSD tools don't support grep -P)
    live_prefix=$(sed -n 's/^[[:space:]]*listen[[:space:]]\{1,\}\(127\.0\.0\.1:\)\?[0-9]\{2\}\([0-9]\{3\}\)\( ssl\)\?;/\2/p' "$conf_dst" | head -1) || true
    template_prefix=$(sed -n 's/^[[:space:]]*listen[[:space:]]\{1,\}\(127\.0\.0\.1:\)\?[0-9]\{2\}\([0-9]\{3\}\)\( ssl\)\?;/\2/p' "$tmpfile" | head -1) || true
    if [[ -n "$live_prefix" && -n "$template_prefix" && "$live_prefix" != "$template_prefix" ]]; then
      sed -i '' "s/:${template_prefix}/:${live_prefix}/g" "$tmpfile"
      info "  Preserved port range ${template_prefix}xxx → ${live_prefix}xxx"
    fi
  fi

  # ── Diff processed config against deployed — skip if unchanged ──
  if [[ -f "$conf_dst" ]] && diff -q "$tmpfile" "$conf_dst" &>/dev/null; then
    info "  nginx config unchanged — skipping deploy"
    rm -f "$tmpfile"
  else
    # ── Config differs — tell user how to deploy ──
    info "  Config generated: ${tmpfile}"
    info "  Deploy with:"
    info "    sudo cp ${tmpfile} ${conf_available}"
    if [[ "$config_dir" != "$available_dir" ]]; then
      info "    sudo ln -sf ${conf_available} ${conf_dst}"
    fi
    info "    sudo nginx -t && sudo nginx -s reload"
    files_copied=$((files_copied + 1))
  fi

  [[ "$files_copied" -eq 0 ]] && return 0
  info "  nginx configs updated — run the deploy commands above to apply"
}

# ── System Scripts Deploy ───────────────────────────────────────
# Deploys admin scripts to /usr/local/sbin/ (root-owned, NOPASSWD-safe).
# Uses sudo on Linux for the root-owned path.
deploy_system_scripts() {
  # Allow skipping nginx-related system scripts (e.g. on servers without sudo)
  [[ -n "${CORTEX_SKIP_NGINX:-}" ]] && { info "CORTEX_SKIP_NGINX set — skipping system script deploy"; return 0; }
  local deploy_dir="/usr/local/sbin"
  local src_dir="${REPO_DIR}/ops/install/deploy/nginx"
  local scripts=("install-nginx-full.sh" "hermes-nginx-clean-restart")
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
  local home_link="${CORTEX_DEPLOY_HOME}/scripts/install-nginx-full.sh"
  local agent_link="${CORTEX_HOME}/.hermes-cortex/scripts/install-nginx-full.sh"
  [[ -f "$home_link" ]] && rm -f "$home_link"
  [[ -f "$agent_link" ]] && rm -f "$agent_link"
}

# ── Stale Service Detector ─────────────────────────────────
# Detects known-dead services that should have been removed.
# Runs on every agent after every update — both Linux + macOS.
detect_stale_services() {
  # No stale services to detect — old standalone server was merged into bus
  :
}

# ── Post-update service verification ─────────────────────────

verify_services() {
  # After an update, verify important services are still managed and running
  detect_stale_services
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

# Pin local hooks for repos with their own hook scripts
# BEFORE setting global hooksPath. This preserves deploy bare repo
# hooks (post-receive, update) that would otherwise be overridden.
pin_repos_with_own_hooks() {
  local shared_hooks_dir="${CORTEX_DEPLOY_HOME}/hooks"
  local pinned=0
  local tmp_gitlist
  tmp_gitlist=$(mktemp) || return 1

  # Strategy: find .git dirs in common repo locations, then check if each
  # has repo-specific hooks. We scope the search to user-writable areas
  # to avoid /proc, /sys, /dev noise.
  #
  # A single find invocation covers both working-tree .git dirs
  # AND bare repos (e.g. myrepo.git/ which git treats as .git itself).
  # --maxdepth 8 avoids crawling deep node_modules, venvs, and caches.
  #
  # Uses a temp file instead of process substitution <() for macOS
  # bash 3.2 compatibility (bash 3.2 does not support <() syntax).
  {
    # Search home directories, /opt, /srv, /var, /Users for git repos
    # Limited depth to avoid crawling deep dependency trees
    # macOS: ~/Developer, ~/Sites, ~/git live under /Users
    for base in /home /opt /srv /var/www /var/repo /Users; do
      if [[ -d "$base" ]]; then
        # find may return non-zero on permissioned subdirectories (e.g.
        # /var/www without read access). These are expected access errors
        # for a non-root search — not a pipeline failure. || true signals
        # that find's exit code is not meaningful for flow control here.
        find "$base" \( -name ".git" -type d -o -name "*.git" -type d \) -maxdepth 8 -print0 2>/dev/null || true
      fi
    done
  } > "$tmp_gitlist"

  while IFS= read -r -d '' git_dir; do
    local hooks_path="${git_dir}/hooks"
    
    # Skip if hooks dir doesn't exist or is empty
    [[ ! -d "$hooks_path" ]] && continue
    
    # Skip if this isn't a valid git repo (e.g. orphaned .git backup copies)
    git --git-dir="$git_dir" rev-parse --git-dir &>/dev/null || continue
    
    # Count non-hidden, non-trivial hook files (not just sample files)
    local hook_count
    hook_count=$(find "$hooks_path" -maxdepth 1 -type f ! -name '.*' ! -name '*.sample' 2>/dev/null | wc -l)
    [[ "$hook_count" -eq 0 ]] && continue
    
    # Check if this repo already has a local hooksPath set
    local current_local
    current_local=$(git --git-dir="$git_dir" config --local core.hooksPath 2>/dev/null || echo "")
    
    if [[ "$current_local" != "$hooks_path" ]]; then
      git --git-dir="$git_dir" config --local core.hooksPath "$hooks_path"
      pinned=$((pinned + 1))
      info "Pinned local hooks for $(dirname "$git_dir")"
    fi
  done < "$tmp_gitlist"

  rm -f "$tmp_gitlist"

  if [[ "$pinned" -gt 0 ]]; then
    info "  → ${pinned} repo(s) with local hooks preserved"
  fi
}

install_precommit_hook() {
  local hooks_dir="${CORTEX_DEPLOY_HOME}/hooks"
  local hook_src="${CORTEX_DEPLOY_HOME}/scripts/pre-commit-score"
  local push_src="${CORTEX_DEPLOY_HOME}/scripts/pre-push-pull"

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
  #
  # IMPORTANT: pin_repos_with_own_hooks() must run BEFORE this so any
  # repo with its own hooks (e.g. bare deploy repos with post-receive)
  # gets a local core.hooksPath override that preserves its behavior.
  local current_hooks_path
  current_hooks_path=$(git config --global core.hooksPath 2>/dev/null || echo "")
  if [[ "$current_hooks_path" != "$hooks_dir" ]]; then
    git config --global core.hooksPath "$hooks_dir"
    info "Set git global hooksPath → ${hooks_dir/$HOME/\\~}"
    info "  → All repos on this machine now use the scoring hook"
  fi
}

main() {
  # Args already parsed at top
  register

  # Source OS config for nginx path variables (NGINX_CONFIG_DIR, NGINX_LOG_DIR, NGINX_HTPASSWD)
  local os_config="${CORTEX_DEPLOY_HOME}/scripts/os-config.sh"
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

  # Sync AGENTS.md to ~/.hermes/ so fleet agents read the same rules
  local hermes_home="${HERMES_HOME:-${HOME}/.hermes}"
  if needs_update "${REPO_DIR}/AGENTS.md" "${hermes_home}/AGENTS.md"; then
    copy_file "${REPO_DIR}/AGENTS.md" "${hermes_home}/AGENTS.md"
    info "  AGENTS.md synced to ~/.hermes/"
  fi

  # Sync skills.yaml from template — actual content sync, not timestamp suppression
  local template_yaml="${REPO_DIR}/docs/templates/skills.yaml"
  local skills_yaml="${CORTEX_DEPLOY_HOME}/skills.yaml"
  if [[ -f "$template_yaml" && -f "$skills_yaml" ]]; then
    if ! diff -q "$template_yaml" "$skills_yaml" >/dev/null 2>&1; then
      copy_file "$template_yaml" "$skills_yaml"
      info "  skills.yaml synced from template"
    fi
  fi

  # Sync offline code corpus from repo
  sync_code_corpus

  deploy_nginx_configs

  # Deploy system scripts to /usr/local/sbin/ (root-owned, NOPASSWD-safe)
  deploy_system_scripts

  # Check and upgrade gbrain binary (every run, not just when template changes)
  update_gbrain_binary

  # Merge template updates into agent SOUL.md (preserves customizations)
  local soul_merge="${CORTEX_DEPLOY_HOME}/scripts/soul-merge.py"
  if [[ -f "$soul_merge" ]]; then
    if python3 "$soul_merge" --check >/dev/null 2>&1; then
      : # up to date — silent
    else
      info "Merging template updates into SOUL.md..."
      python3 "$soul_merge" 2>&1 | sed 's/^/    /'
      COPIED=$((COPIED + 1))
    fi
  fi

  # Sync ALL agent SOUL.md profiles with template
  local soul_sync_all="${CORTEX_DEPLOY_HOME}/scripts/soul-sync-all.sh"
  if [[ -f "$soul_sync_all" ]]; then
    info "Syncing all agent SOUL.md profiles..."
    bash "$soul_sync_all" 2>&1 | sed 's/^/    /' || true
  fi

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

  # Ensure ~/.hermes/scripts/ points to ~/.hermes-cortex/scripts/
  # (cron security guard resolves this directory and checks script
  # paths against it — a directory-level symlink means both sides
  # of the check land in the same tree, no core agent patch needed)
  _HERMES_AGENT_SCRIPTS="${HOME}/.hermes/scripts"
  _CORTEX_DEPLOY_SCRIPTS="${CORTEX_DEPLOY_HOME}/scripts"
  # Safety guard: skip symlink dance when both paths resolve to the same directory.
  # This happens when CORTEX_DEPLOY_HOME is already set to ~/.hermes — rm -rf would
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
      info "Linked ~/.hermes-cortex/scripts/ (directory symlink)"
    else
      warn "~/.hermes/scripts/ has unique files: $_UNIQUE — not replacing"
    fi
  elif [ ! -e "$_HERMES_AGENT_SCRIPTS" ]; then
    ln -sf "$_CORTEX_DEPLOY_SCRIPTS" "$_HERMES_AGENT_SCRIPTS"
    info "Created ~/.hermes/scripts/ symlink"
  fi

  # Pin repos with their own hooks before setting global hooksPath
  pin_repos_with_own_hooks

  # Install pre-commit scoring hook in repo
  install_precommit_hook

  # Write notification files (monitored by operator dashboard / messenger)
  write_notification_files

  # Summary
  echo ""
  echo -e "${BOLD}━━━ Summary ━━━${RESET}"
  info "${COPIED} file(s) updated"
  [[ "${REMOVED:-0}" -gt 0 ]] && warn "${REMOVED} deprecated file(s) removed"
  if $DRY_RUN; then
    echo ""
    warn "DRY RUN — no files were actually modified."
    warn "Run without --dry-run to apply changes."
  fi
  echo ""

  # Post-update service verification
  verify_services

  # Auto-clean stale deploy files after force-all
  clean_stale_deploys

  # Install/update universal crons (idempotent — skips existing)
  if command -v hermes &>/dev/null; then
    CORTEX_DEPLOY_HOME="${CORTEX_DEPLOY_HOME}" bash "${CORTEX_DEPLOY_HOME}/scripts/install-crons.sh" 2>/dev/null && \
      info "Crons up to date" || warn "Cron install skipped (no hermes CLI?)"

    # ── Orchestrator-only crons (team health, soul refinement, etc.) ──
    # Guard: AGENT_TYPE env var, or IS_ORCHESTRATOR, or hostname fallback
    _ORCH=false
    if [[ "${AGENT_TYPE:-}" == "orchestrator" ]]; then
      _ORCH=true
    elif [[ "${IS_ORCHESTRATOR:-false}" == "true" ]]; then
      _ORCH=true
    fi
    if ! $_ORCH; then
      ORCH_HOST=$(hostname -s 2>/dev/null || echo "unknown")
      case "$ORCH_HOST" in
        moses|esther) _ORCH=true ;;
      esac
    fi
    if $_ORCH; then
      CORTEX_DEPLOY_HOME="${CORTEX_DEPLOY_HOME}" bash "${CORTEX_DEPLOY_HOME}/scripts/install-orch-crons.sh" 2>/dev/null && \
        info "Orch crons up to date" || warn "Orch cron install skipped"
    else
      # ── Non-orch guard: detect accidentally installed orch crons ──
      if command -v hermes &>/dev/null && hermes cron --help &>/dev/null 2>&1; then
        local _found
        _found=$(hermes cron list --all 2>/dev/null | grep -E "orch-(team-messages|team-health|gbrain-doctor)" || true)
        if [[ -n "$_found" ]]; then
          warn "Orch crons detected on non-orch agent — remove with:"
          warn "  bash ${CORTEX_DEPLOY_HOME}/scripts/install-orch-crons.sh --uninstall"
          echo "$_found"
        fi
      fi
    fi
  else
    info "Hermes not found — skip cron install (run install-crons.sh after Hermes setup)"
  fi

  # ── Clean stale governance locks ─────────────────────────
  # First pass: clean locks whose heartbeat has exceeded TTL
  for _lock in "$STATE_DIR"/.governance-*.json; do
    [ -f "$_lock" ] || continue
    local _lock_age _lock_heartbeat
    _lock_age=$(stat -c %Y "$_lock" 2>/dev/null || echo 0)
    _lock_heartbeat=$(python3 -c "import json; print(json.load(open('$_lock')).get('heartbeat_at','')[:19])" 2>/dev/null || echo "")
    if [[ -n "$_lock_heartbeat" ]]; then
      local _heartbeat_epoch
      _heartbeat_epoch=$(date -d "$_lock_heartbeat" +%s 2>/dev/null || echo 0)
      local _now
      _now=$(date +%s)
      if [[ $(( _now - _heartbeat_epoch )) -gt 3600 ]]; then
        rm -f "$_lock"
        info "Cleaned stale governance lock: $_lock"
      fi
    fi
  done

  # Second pass: clean legacy slug-based lock files (upgrade from v1→v2)
  # These use the old naming scheme .governance-{slug}.json or .governance-generic.json
  # and are superseded by session-scoped locks. Check content for absence of
  # session_id field to distinguish legacy from session-scoped locks.
  for _legacy_lock in "$STATE_DIR"/.governance-*.json; do
    [ -f "$_legacy_lock" ] || continue
    local _has_session
    _has_session=$(python3 -c "
import json
try:
    s = json.load(open('$_legacy_lock'))
    print('yes' if 'session_id' in s and s['session_id'] else 'no')
except: print('no')
" 2>/dev/null || echo "no")
    # Legacy locks have no session_id — clean them unconditionally
    if [[ "$_has_session" == "no" ]]; then
      local _has_heartbeat_repo
      _has_heartbeat_repo=$(python3 -c "
import json
try:
    s = json.load(open('$_legacy_lock'))
    hb = s.get('heartbeat_at', '')
    task = s.get('task_id', '')
    slug = s.get('repo_slug', '')
    print(f'hb={hb}|task={task}|slug={slug}')
except: print('error')
" 2>/dev/null || echo "error")
      rm -f "$_legacy_lock"
      info "Cleaned legacy governance lock (upgrade): $_legacy_lock — $_has_heartbeat_repo"
    fi
  done

  # ── Auto-run doctor after update ─────────────────────────
  info "Running doctor to verify installation…"
  python3 "${CORTEX_DEPLOY_HOME}/scripts/cortex-doctor.py" --quiet 2>&1 || true

  echo ""
}

main "$@"
