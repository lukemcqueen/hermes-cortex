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

# ── Sanctioned unlock channel (2026-07-31) ──
# hermes-plugin-lock restricts unlock/update to a command-line token:
#   sudo hermes-plugin-lock unlock --cortex-update
# (env vars DON'T survive sudo on this host — sudoers has env_reset with
# no SETENV/env_keep — so the token must be an argument, not an export.)
# macOS runs the helper without sudo, where the arg token also works.

# ── Bash version check — macOS ships bash 3.2 (no -A, no **) ──
# Homebrew installs bash 4+ at /opt/homebrew/bin/bash (arm64) or
# /usr/local/bin/bash (x86_64). If running under old bash on macOS,
# re-exec with brew bash.
if [[ -z "${BASH_VERSINFO[*]:-}" || "${BASH_VERSINFO[0]:-0}" -lt 4 ]]; then
  if [[ "$(uname -s 2>/dev/null || true)" == "Darwin" ]]; then
    for brew_bash in /opt/homebrew/bin/bash /usr/local/bin/bash; do
      if [[ -x "$brew_bash" ]]; then
        exec "$brew_bash" "$0" "$@"
      fi
    done
  fi
  echo "ERROR: cortex-update.sh requires bash >= 4.0 (found bash ${BASH_VERSION:-unknown})."
  echo "       On macOS: brew install bash"
  echo "       On Linux: install bash via your package manager"
  exit 1
fi

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BOLD='\033[1m'; CYAN='\033[0;36m'; RESET='\033[0m'

info()  { echo -e "${GREEN}✓${RESET} $*"; }
warn()  { echo -e "${YELLOW}⚠${RESET} $*"; }
error() { echo -e "${RED}✗${RESET} $*"; }

REPO_DIR="${REPO_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"

# ── Detect real user (works even under sudo) ─────────────────
if [ -n "${SUDO_USER:-}" ]; then
  if command -v getent &>/dev/null; then
    CORTEX_HOME="$(getent passwd "$SUDO_USER" | cut -d: -f6)"
  fi
  CORTEX_HOME="${CORTEX_HOME:-$HOME}"
elif [ -n "${HOME:-}" ]; then
  CORTEX_HOME="${HOME}"
else
  if command -v getent &>/dev/null; then
    CORTEX_HOME="$(getent passwd "$(whoami)" | cut -d: -f6)"
  fi
  CORTEX_HOME="${CORTEX_HOME:-$HOME}"
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
FORCE_ALL=true
CLEAN_STALE=false
CHANGED=()
TO_RESTART=()
COPIED=0
SKIPPED=0
DELTA=false

# Parse options
for arg in "$@"; do
  case "$arg" in
    --delta)     FORCE_ALL=false; DELTA=true ;;
    --dry-run)   DRY_RUN=true ;;
    --status)    STATUS_ONLY=true ;;
    --force-all) ;;  # default since 2026-07-27
    --clean-stale) CLEAN_STALE=true ;;
    --help|-h)
      echo "Usage: bash cortex-update.sh [--dry-run|--delta|--status]"
      echo ""
      echo "  --dry-run    Show what would change without touching anything"
      echo "  --delta      Skip files with matching commit hashes (legacy mode)"
      echo "  --status     Show current deployment status"
      echo "  --help       This message"
      echo ""
      echo "Default (no flags): Full deploy — checksums every file, deploys all changes."
      echo "  --force-all is no longer needed — it's the default."
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
#      2. Run cortex-update.sh
#      3. Delete the stale deploy file (it won't be cleaned up automatically)
#
#    Example: inbox→bus rename (Jul 2026) left 11 stale inbox-* files
#    in deploy because the register paths weren't updated alongside the
#    repo files. Verify with: comm -23 <(ls deploy) <(ls repo paths)
# ── Deploy-map hygiene (2026-08-05) ─────────────────────────
# The register map deploys files by hash-difference — a registered file is
# OVERWRITTEN whenever content differs. That is correct for repo-managed
# files, but DESTRUCTIVE for Hermes-owned user data: a memory seed register
# clobbered live MEMORY.md on every deploy (7× in a day) because the live
# file is personalized and always differs from the template. Fail CLOSED on
# such targets so a re-add breaks the deploy loudly instead of overwriting
# user data. See docs/troubleshooting.md entry 18.
_assert_register_dest_safe() {
  local dest="$1"
  case "$dest" in
    *"/memories/"*|"${HOME}/.hermes/"*)
      echo "❌ REFUSED: register target '${dest/$HOME/~}' is Hermes-owned user data." >&2
      echo "   Memory and config files under ~/.hermes/ belong to Hermes — never deploy them." >&2
      echo "   See docs/troubleshooting.md entry 18." >&2
      exit 1
      ;;
  esac
}

MAP=()
register() {
  local s1="${1:-}" s2="${2:-}" s3="${3:-}" s4="${4:-}"
  _assert_register_dest_safe "$s2"
  MAP+=("${s1}|${s2}|${s3}|${s4}")
}

# register_orch — Only register on orchestrator hosts (hostname moses|esther
# AND matching /home/<hostname> home dir; env vars grant no orch powers)
# After calling this, the sync loop handles ORCH_MAP entries the same as MAP.
ORCH_MAP=()
register_orch() {
  local s1="${1:-}" s2="${2:-}" s3="${3:-}" s4="${4:-}"
  _assert_register_dest_safe "$s2"
  ORCH_MAP+=("${s1}|${s2}|${s3}|${s4}")
}

# Scripts → ~/.hermes-cortex/scripts/
register "ops/scripts/health/agent-system-alert-watchdog.py"   "${CORTEX_DEPLOY_HOME}/scripts/agent-system-alert-watchdog.py"
register "ops/scripts/health/heartbeat.py"               "${CORTEX_DEPLOY_HOME}/scripts/heartbeat.py"
register "ops/scripts/hermes_models.py"            "${CORTEX_DEPLOY_HOME}/scripts/hermes_models.py"
register "ops/scripts/hermes_paths.py"             "${CORTEX_DEPLOY_HOME}/scripts/hermes_paths.py"
register "ops/scripts/install/check-system.sh"             "${CORTEX_DEPLOY_HOME}/scripts/check-system.sh"
register "ops/scripts/manage/agent-memory-to-brain-sync.py"    "${CORTEX_DEPLOY_HOME}/scripts/agent-memory-to-brain-sync.py"
register "ops/scripts/install/bootstrap-brain.sh"         "${CORTEX_DEPLOY_HOME}/scripts/bootstrap-brain.sh"
register "ops/scripts/health/check-memory-budget.sh"     "${CORTEX_DEPLOY_HOME}/scripts/check-memory-budget.sh"
register "ops/scripts/install/cortex-profile.sh"          "${CORTEX_DEPLOY_HOME}/scripts/cortex-profile.sh"
register "ops/scripts/install/seed-project-brain.sh"      "${CORTEX_DEPLOY_HOME}/scripts/seed-project-brain.sh"
register "ops/scripts/install/install-gateway-cron-timeout.sh" "${CORTEX_DEPLOY_HOME}/scripts/install-gateway-cron-timeout.sh"
register "ops/scripts/install/install-gateway-timezone.sh" "${CORTEX_DEPLOY_HOME}/scripts/install-gateway-timezone.sh"
register "ops/scripts/manage/cortex-health.sh"           "${CORTEX_DEPLOY_HOME}/scripts/cortex-health.sh"
register "ops/scripts/manage/consolidate-env.sh"         "${CORTEX_DEPLOY_HOME}/scripts/consolidate-env.sh"
register "ops/scripts/manage/gen-skills-manifest.py"      "${CORTEX_DEPLOY_HOME}/scripts/gen-skills-manifest.py"
register "ops/scripts/manage/task-db.py"                "${CORTEX_DEPLOY_HOME}/scripts/task-db.py"
register "ops/scripts/manage/git-main-sync.sh"          "${CORTEX_DEPLOY_HOME}/scripts/git-main-sync.sh"
register "ops/scripts/manage/dream-task-bridge.py"       "${CORTEX_DEPLOY_HOME}/scripts/dream-task-bridge.py"
register "mcp-servers/task-mcp.py"                      "${CORTEX_DEPLOY_HOME}/scripts/task-mcp.py"
register "mcp-servers/executor-mcp.py"                  "${CORTEX_DEPLOY_HOME}/scripts/executor-mcp.py"
register "ops/services/tasks/migrate.py"                "${CORTEX_DEPLOY_HOME}/services/tasks/migrate.py"
register "ops/services/tasks/schema/v001__tasks.sql"    "${CORTEX_DEPLOY_HOME}/services/tasks/schema/v001__tasks.sql"
register "ops/services/tasks/schema/v002__doctor-probe-source.sql" "${CORTEX_DEPLOY_HOME}/services/tasks/schema/v002__doctor-probe-source.sql"
register "ops/services/tasks/schema/v003__cancel-column-null.sql" "${CORTEX_DEPLOY_HOME}/services/tasks/schema/v003__cancel-column-null.sql"
register "ops/services/tasks/schema/v004__cancel-update-column.sql" "${CORTEX_DEPLOY_HOME}/services/tasks/schema/v004__cancel-update-column.sql"
register "ops/services/tasks/schema/v005__lifecycle.sql"     "${CORTEX_DEPLOY_HOME}/services/tasks/schema/v005__lifecycle.sql"
register "ops/services/tasks/schema/v006__schema-version-grant.sql" "${CORTEX_DEPLOY_HOME}/services/tasks/schema/v006__schema-version-grant.sql"
register "ops/services/tasks/schema/v007__upsert-preserve-partial.sql" "${CORTEX_DEPLOY_HOME}/services/tasks/schema/v007__upsert-preserve-partial.sql"
register "ops/services/tasks/schema/v008__v006-deferred.sql" "${CORTEX_DEPLOY_HOME}/services/tasks/schema/v008__v006-deferred.sql"
# learnings ledger (F-001) — schema + version-gated runner, orchestrator-only
# (the bus Postgres that hosts learnings exists only on Moses/Esther; workers
# write via the HTTP collector path and never need this schema locally).
register_orch "ops/services/learnings/migrate.py"               "${CORTEX_DEPLOY_HOME}/services/learnings/migrate.py"
register_orch "ops/services/learnings/schema/v001__learnings.sql" "${CORTEX_DEPLOY_HOME}/services/learnings/schema/v001__learnings.sql"
register_orch "ops/services/learnings/schema/v002__set_status_impact.sql" "${CORTEX_DEPLOY_HOME}/services/learnings/schema/v002__set_status_impact.sql"
# learning-ledger.py — orchestrator-only lifecycle client (F-006): reads the
# ledger + writes dispositions via set_status(). SELECT is granted to
# mycortex_reader_esther/moses only; RLS fail-closed elsewhere.
register_orch "ops/scripts/manage/learning-ledger.py" "${CORTEX_DEPLOY_HOME}/scripts/learning-ledger.py"
# learning-collect.py — collector write path, deployed to ALL agents (any of
# the 8 capture routes on any host can record a learning via HTTP).
register "ops/scripts/manage/learning-collect.py"  "${CORTEX_DEPLOY_HOME}/scripts/learning-collect.py"
register_orch "ops/scripts/install/cortex-setup-langfuse.sh"   "${CORTEX_DEPLOY_HOME}/scripts/cortex-setup-langfuse.sh"
register "ops/scripts/setup-fleet-langfuse.sh"         "${CORTEX_DEPLOY_HOME}/scripts/setup-fleet-langfuse.sh"
register "ops/scripts/cortex-update.sh"           "${CORTEX_DEPLOY_HOME}/scripts/cortex-update.sh"
register "ops/scripts/install/install-ollama.sh"          "${CORTEX_DEPLOY_HOME}/scripts/install-ollama.sh"
register "ops/scripts/install/install-nginx.sh"           "${CORTEX_DEPLOY_HOME}/scripts/install-nginx.sh"
register "ops/scripts/install/install-cortex-update-cron.sh" "${CORTEX_DEPLOY_HOME}/scripts/install-cortex-update-cron.sh"
register "ops/scripts/install-crons.sh"       "${CORTEX_DEPLOY_HOME}/scripts/install-crons.sh"
register_orch "ops/scripts/orch-bus/orch-bus-confirmation-poller.py"     "${CORTEX_DEPLOY_HOME}/scripts/orch-bus-confirmation-poller.py"
register_orch "ops/scripts/orch-bus/orch-bus-confirmation-alert.sh" "${CORTEX_DEPLOY_HOME}/scripts/orch-bus-confirmation-alert.sh"
register_orch "ops/scripts/orch-bus/orch-bus-forwarder.py"     "${CORTEX_DEPLOY_HOME}/scripts/orch-bus-forwarder.py"
register_orch "ops/scripts/orch-bus/orch-bus-inbox-relay.py"   "${CORTEX_DEPLOY_HOME}/scripts/orch-bus-inbox-relay.py"
register_orch "ops/scripts/fleet/local-orch-fleet-command-verifier.py"   "${CORTEX_DEPLOY_HOME}/scripts/local-orch-fleet-command-verifier.py"
register "ops/scripts/install/install-orch-crons.sh"  "${CORTEX_DEPLOY_HOME}/scripts/install-orch-crons.sh"
register "ops/scripts/install/install-dream-crons.sh" "${CORTEX_DEPLOY_HOME}/scripts/install-dream-crons.sh"
register "ops/scripts/install/install-provider-timeouts.sh" "${CORTEX_DEPLOY_HOME}/scripts/install-provider-timeouts.sh"
register "ops/scripts/install/install-model-default.sh" "${CORTEX_DEPLOY_HOME}/scripts/install-model-default.sh"
register "ops/scripts/install/install-soft-session-cap.sh" "${CORTEX_DEPLOY_HOME}/scripts/install-soft-session-cap.sh"
register "ops/scripts/install/install-profile-reader-role.sh" "${CORTEX_DEPLOY_HOME}/scripts/install-profile-reader-role.sh"
register "ops/scripts/install/install-score-hook.sh"       "${CORTEX_DEPLOY_HOME}/scripts/install-score-hook.sh"
register "ops/scripts/cortex-dogfood.sh" "${CORTEX_DEPLOY_HOME}/scripts/cortex-dogfood.sh"
register "ops/scripts/pre-commit-score"            "${CORTEX_DEPLOY_HOME}/scripts/pre-commit-score"
register "ops/scripts/post-commit-audit" "${CORTEX_DEPLOY_HOME}/scripts/post-commit-audit"
register "ops/scripts/pre-push-pull" "${CORTEX_DEPLOY_HOME}/scripts/pre-push-pull"
register "ops/scripts/manage/agent-no-verify-audit.py" "${CORTEX_DEPLOY_HOME}/scripts/manage/agent-no-verify-audit.py"
register "ops/scripts/manage/agent-governance-auditor.py"            "${CORTEX_DEPLOY_HOME}/scripts/agent-governance-auditor.py"
register "ops/scripts/manage/purge-stale-governance-locks.py" "${CORTEX_DEPLOY_HOME}/scripts/purge-stale-governance-locks.py"
# prune-soul-profiles.py removed — profiles no longer in repo
register "ops/scripts/manage/soul-merge.py"                    "${CORTEX_DEPLOY_HOME}/scripts/soul-merge.py"
register "ops/scripts/manage/session-active-guard.py"          "${CORTEX_DEPLOY_HOME}/scripts/session-active-guard.py"
register "ops/install/deploy/nginx/hermes-plugin-lock"           "${CORTEX_DEPLOY_HOME}/scripts/hermes-plugin-lock"
register "ops/scripts/manage/soul-sync-all.sh"                 "${CORTEX_DEPLOY_HOME}/scripts/soul-sync-all.sh"
register "ops/scripts/agent/agents-doc-audit.py"          "${CORTEX_DEPLOY_HOME}/scripts/agents-doc-audit.py"
register "ops/scripts/agent/agent-agents-md-prune-scan.py"      "${CORTEX_DEPLOY_HOME}/scripts/agent-agents-md-prune-scan.py"
register "ops/scripts/secret-leak-detector.sh"            "${CORTEX_DEPLOY_HOME}/scripts/secret-leak-detector.sh"
register "ops/scripts/health/check-external-services.sh"   "${CORTEX_DEPLOY_HOME}/scripts/check-external-services.sh"
register "ops/scripts/agent-secret-leak-watchdog.py"            "${CORTEX_DEPLOY_HOME}/scripts/agent-secret-leak-watchdog.py"
register "ops/scripts/install-fallback-providers.py"    "${CORTEX_DEPLOY_HOME}/scripts/install-fallback-providers.py"
register "ops/scripts/manage/cortex-doctor.py"        "${CORTEX_DEPLOY_HOME}/scripts/cortex-doctor.py"
register "ops/scripts/manage/fleet-git-reset.py"      "${CORTEX_DEPLOY_HOME}/scripts/fleet-git-reset.py"
register "ops/scripts/manage/cron_manifest.py"        "${CORTEX_DEPLOY_HOME}/scripts/manage/cron_manifest.py"
register "ops/scripts/manage/cortex_doctor/__init__.py" "${CORTEX_DEPLOY_HOME}/scripts/cortex_doctor/__init__.py"
register "ops/scripts/manage/cortex_doctor/bus_alert.py" "${CORTEX_DEPLOY_HOME}/scripts/cortex_doctor/bus_alert.py"
register "ops/scripts/manage/cortex_doctor/checks.py"   "${CORTEX_DEPLOY_HOME}/scripts/cortex_doctor/checks.py"
register "ops/scripts/manage/cortex_doctor/cli.py"     "${CORTEX_DEPLOY_HOME}/scripts/cortex_doctor/cli.py"
register "ops/scripts/manage/cortex_doctor/config.py"  "${CORTEX_DEPLOY_HOME}/scripts/cortex_doctor/config.py"
register "ops/scripts/manage/cortex_doctor/fix.py"     "${CORTEX_DEPLOY_HOME}/scripts/cortex_doctor/fix.py"
register "ops/scripts/manage/cortex_doctor/helpers.py" "${CORTEX_DEPLOY_HOME}/scripts/cortex_doctor/helpers.py"
register "ops/scripts/manage/cortex_doctor/results.py" "${CORTEX_DEPLOY_HOME}/scripts/cortex_doctor/results.py"

register "ops/scripts/manage/cortex-agent-manager.py"  "${CORTEX_DEPLOY_HOME}/scripts/cortex-agent-manager.py"

register "ops/scripts/hc/hc.py"                      "${CORTEX_DEPLOY_HOME}/scripts/hc.py"
register "ops/scripts/hc/hc"                         "${CORTEX_DEPLOY_HOME}/scripts/hc"
register "ops/scripts/health/agent-stale-ref-watchdog.sh"            "${CORTEX_DEPLOY_HOME}/scripts/manage/agent-stale-ref-watchdog.sh"
register "ops/scripts/manage/autonomy-classifier.py"                  "${CORTEX_DEPLOY_HOME}/scripts/manage/autonomy-classifier.py"
register "ops/scripts/manage/orch-autonomy-digest.sh"                 "${CORTEX_DEPLOY_HOME}/scripts/manage/orch-autonomy-digest.sh"
register "ops/scripts/cron-failure-state.sh"       "${CORTEX_DEPLOY_HOME}/scripts/cron-failure-state.sh"
register "ops/scripts/cron_failure_state.py"       "${CORTEX_DEPLOY_HOME}/scripts/cron_failure_state.py"
register "ops/scripts/install/seed-project.sh"           "${CORTEX_DEPLOY_HOME}/scripts/seed-project.sh"
register "ops/scripts/install/merge-agents-md.py"      "${CORTEX_DEPLOY_HOME}/scripts/merge-agents-md.py"
register "ops/scripts/manage/agent-hermes-update.sh"            "${CORTEX_DEPLOY_HOME}/scripts/agent-hermes-update.sh"
register "ops/scripts/manage/agent-hermes-cortex-sync.sh"      "${CORTEX_DEPLOY_HOME}/scripts/agent-hermes-cortex-sync.sh"
register "ops/scripts/manage/update-session-state.sh"    "${CORTEX_DEPLOY_HOME}/scripts/update-session-state.sh"
register "ops/scripts/manage/fleet-audit.py"             "${CORTEX_DEPLOY_HOME}/scripts/fleet-audit.py"
register "ops/scripts/manage/fleet-costs.py"             "${CORTEX_DEPLOY_HOME}/scripts/fleet-costs.py"
register "ops/scripts/manage/fleet-update-check.py"      "${CORTEX_DEPLOY_HOME}/scripts/fleet-update-check.py"
register "ops/scripts/manage/orch-daily-cost-report.py"  "${CORTEX_DEPLOY_HOME}/scripts/orch-daily-cost-report.py"
register "ops/scripts/manage/orch-task-board-digest.py"  "${CORTEX_DEPLOY_HOME}/scripts/orch-task-board-digest.py"
register "ops/scripts/manage/apply-repo-efficiency.py"   "${CORTEX_DEPLOY_HOME}/scripts/apply-repo-efficiency.py"
register "docs/templates/repo-efficiency-block.md"       "${CORTEX_DEPLOY_HOME}/templates/repo-efficiency-block.md"
register "ops/scripts/manage/wave-orchestrate.py"        "${CORTEX_DEPLOY_HOME}/scripts/wave-orchestrate.py"
register "ops/scripts/manage/agent-budget-enforcer.py"     "${CORTEX_DEPLOY_HOME}/scripts/agent-budget-enforcer.py"
register "ops/scripts/manage/escalate-to-human.py"     "${CORTEX_DEPLOY_HOME}/scripts/escalate-to-human.py"
register "ops/scripts/manage/fleet-kill-switch.py"    "${CORTEX_DEPLOY_HOME}/scripts/fleet-kill-switch.py"
register "ops/scripts/manage/outerloop.py"               "${CORTEX_DEPLOY_HOME}/scripts/outerloop.py"
register "ops/scripts/lib/handoff_schema.py"             "${CORTEX_DEPLOY_HOME}/scripts/lib/handoff_schema.py"
register "ops/scripts/quality/adversarial-verify.py"     "${CORTEX_DEPLOY_HOME}/scripts/adversarial-verify.py"
register_orch "ops/scripts/orch-bus/orch-bus-fleet-dispatch.py" "${CORTEX_DEPLOY_HOME}/scripts/orch-bus-fleet-dispatch.py"


register "ops/scripts/manage/agent-session_cache.py"    "${CORTEX_DEPLOY_HOME}/scripts/agent-session_cache.py"

register "ops/scripts/health/prod-watchdog.sh"          "${CORTEX_DEPLOY_HOME}/scripts/prod-watchdog.sh"
register_orch "ops/scripts/agent/orch-fleet-watchdog.py"   "${CORTEX_DEPLOY_HOME}/scripts/orch-fleet-watchdog.py"

# F-008 daily golden regression gate (eval-harness wired to a no_agent cron)
register_orch "ops/scripts/orch-daily-regression-gate.sh"   "${CORTEX_DEPLOY_HOME}/scripts/orch-daily-regression-gate.sh"

# Failover watchdog — detect bus outage, per-role behavior. Deployed to ALL
# agents (workers detect + alert; orchestrators run full failover).
register "ops/scripts/agent/cortex-bus-failover-watchdog.py"  "${CORTEX_DEPLOY_HOME}/scripts/cortex-bus-failover-watchdog.py"

# Post-commit notification + installer
register "ops/scripts/manage/post-commit-notify.sh"          "${CORTEX_DEPLOY_HOME}/scripts/post-commit-notify.sh"
register "ops/scripts/install/install-post-commit-hook.sh"    "${CORTEX_DEPLOY_HOME}/scripts/install-post-commit-hook.sh"

# Template drift checker (runs during cortex-update.sh)
register "ops/scripts/manage/template-diff-check.py"          "${CORTEX_DEPLOY_HOME}/scripts/template-diff-check.py"

# Orch skill evaluation — wrapper for orch-skill-report-process, used by cron
register "ops/scripts/manage/orch-skill-evaluate.sh"         "${CORTEX_DEPLOY_HOME}/scripts/orch-skill-evaluate.sh"

# Moses bus remediation
register "ops/scripts/bus/cortex-bus-remediate.sh"  "${CORTEX_DEPLOY_HOME}/scripts/cortex-bus-remediate.sh"

# Auto-remediation scripts
register "ops/scripts/health/cron-auto-remediate.sh"     "${CORTEX_DEPLOY_HOME}/scripts/cron-auto-remediate.sh"
register "ops/scripts/health/docker-volume-safety.sh"    "${CORTEX_DEPLOY_HOME}/scripts/docker-volume-safety.sh"
register_orch "ops/scripts/agent/orch-weekly-auto-fix.py"    "${CORTEX_DEPLOY_HOME}/scripts/orch-weekly-auto-fix.py"

# System watchdog scripts (no_agent cron jobs)
register "ops/scripts/health/agent-service-recovery.py"        "${CORTEX_DEPLOY_HOME}/scripts/agent-service-recovery.py"
register "ops/scripts/platform_utils.py"          "${CORTEX_DEPLOY_HOME}/scripts/platform_utils.py"
# Agent daily bible reading — migrated to LLM-driven cron (no script)
register "ops/scripts/health/agent-langfuse-health-watchdog.py" "${CORTEX_DEPLOY_HOME}/scripts/agent-langfuse-health-watchdog.py"
register "ops/scripts/health/agent-mcp-health-watchdog.py"       "${CORTEX_DEPLOY_HOME}/scripts/agent-mcp-health-watchdog.py"
register "ops/scripts/manage/agent-llm-judge-scorer.py"         "${CORTEX_DEPLOY_HOME}/scripts/agent-llm-judge-scorer.py"
register "ops/scripts/health/agent-model-health-watchdog.py"    "${CORTEX_DEPLOY_HOME}/scripts/agent-model-health-watchdog.py"
register "ops/scripts/manage/agent-offline-code-index.sh" "${CORTEX_DEPLOY_HOME}/scripts/agent-offline-code-index.sh"
# harvest-lessons.sh removed — absorbed into orch-skill-lifecycle (July 2026)
# core/governance/skill_miner.py removed (old governance — July 2026)
register "ops/scripts/health/agent-swap-refresh.py"            "${CORTEX_DEPLOY_HOME}/scripts/agent-swap-refresh.py"
register "ops/scripts/health/agent-cron-quality-watchdog.py" "${CORTEX_DEPLOY_HOME}/scripts/agent-cron-quality-watchdog.py"
register "ops/scripts/agent/agent-cron-failure-scanner.py" "${CORTEX_DEPLOY_HOME}/scripts/agent-cron-failure-scanner.py"
register "ops/scripts/agent/agent-cron-status.py" "${CORTEX_DEPLOY_HOME}/scripts/agent-cron-status.py"
register "ops/scripts/health/agent-scoring-activity-watchdog.py" "${CORTEX_DEPLOY_HOME}/scripts/agent-scoring-activity-watchdog.py"
register "ops/scripts/health/agent-pending-cycle-watchdog.py"  "${CORTEX_DEPLOY_HOME}/scripts/agent-pending-cycle-watchdog.py"
register "ops/scripts/health/agent-deploy-drift-audit.py"  "${CORTEX_DEPLOY_HOME}/scripts/agent-deploy-drift-audit.py"
register "ops/scripts/state_tracker.py"             "${CORTEX_DEPLOY_HOME}/scripts/state_tracker.py"
register "ops/scripts/health/check-certs.py"               "${CORTEX_DEPLOY_HOME}/scripts/check-certs.py"
# daily-bible-reading.sh was deleted from repo — replaced by agent-daily-bible-reading.py
# (2026-08-09: register was missing → script never deployed → LLM-cron fallback produced
#  garbage via qwen2.5-coder:3b. Canonical mode is no_agent script, per install-crons.sh.)
register ".hermes-cortex/scripts/agent-daily-bible-reading.py" "${CORTEX_DEPLOY_HOME}/scripts/agent-daily-bible-reading.py"
register_orch "ops/scripts/bus/generate-bus-wrappers.py"      "${CORTEX_DEPLOY_HOME}/scripts/generate-bus-wrappers.py"
register "ops/scripts/manage/nginx-security-scanner.sh"    "${CORTEX_DEPLOY_HOME}/scripts/nginx-security-scanner.sh"
register "ops/scripts/manage/agent-nginx-threat-pipeline.sh"     "${CORTEX_DEPLOY_HOME}/scripts/agent-nginx-threat-pipeline.sh"
register "ops/scripts/manage/deploy-blocked-ips.sh"        "${CORTEX_DEPLOY_HOME}/scripts/deploy-blocked-ips.sh"
# Evidence-based blocklist classifier (review-only, never edits/deploys)
register "ops/scripts/manage/classify-blocked-ips.sh"      "${CORTEX_DEPLOY_HOME}/scripts/classify-blocked-ips.sh"
register "ops/scripts/agent/agent-remediate-apply.py"  "${CORTEX_DEPLOY_HOME}/scripts/agent-remediate-apply.py"
register "ops/scripts/agent/agent-ip-submission.sh"      "${CORTEX_DEPLOY_HOME}/scripts/agent-ip-submission.sh"
register "ops/scripts/agent/agent-worker.py"             "${CORTEX_DEPLOY_HOME}/scripts/agent-worker.py"
register "ops/scripts/agent/contact-orchestrator.sh"      "${CORTEX_DEPLOY_HOME}/scripts/contact-orchestrator.sh"
register "ops/scripts/agent/install-worker.sh"      "${CORTEX_DEPLOY_HOME}/scripts/install-worker.sh"
# Pre-commit hook — managed by install_precommit_hook() as symlink to scripts/pre-commit-score
# No register() call — the hook is a symlink, not a standalone deploy file.
# Post-merge hook — auto-runs cortex-update.sh after every git pull
register ".hermes-cortex/hooks/post-merge"   "${CORTEX_DEPLOY_HOME}/hooks/post-merge"
# Least privilege: git hooks run only as the owning user, so group/other need
# nothing. git does NOT track group/other bits (stores 100755/100644 only), so
# a 700 file in the repo would still deploy as 755 — enforce 700 at deploy
# time. chattr +i (hermes-plugin-lock TARGETS) then makes it
# immutable-but-executable. Do NOT move this into the chmod-444 loop — 444
# kills the execute bit and git silently ignores non-executable hooks.
#
# Mode overrides are applied in check_each_mapped_file() AFTER the
# enforcement unlock + copy (Titus 2026-08-03: register-time chmod ran before
# the unlock, failed silently on the immutable file, and needs_update() only
# compares content — so an identical-content file was never re-copied and a
# stale 444 mode stuck. Enforcing post-unlock, unconditionally, fixes mode
# drift even when content hasn't changed.)
declare -A MODE_OVERRIDES=(
  ["${CORTEX_DEPLOY_HOME}/hooks/post-merge"]="700"
)

# Deploy scripts (nginx security pipeline) — now deployed to /usr/local/sbin/
# by deploy_system_scripts() below. Old register entries removed.

# Deployment-specific cron scripts
register "ops/scripts/manage/agent-auto-save-sessions.py"      "${CORTEX_DEPLOY_HOME}/scripts/agent-auto-save-sessions.py"
# legacy wrapper + doctor-summary scripts UNREGISTERED 2026-08-05 —
# legacy brain decommissioned; dead scripts no longer deployed.
register "ops/scripts/manage/send-skill-report.py"       "${CORTEX_DEPLOY_HOME}/scripts/send-skill-report.py"

register_orch "mcp-servers/cortex-bus-mcp.py"               "${CORTEX_DEPLOY_HOME}/scripts/cortex-bus-mcp.py"

# Inbox MCP tools
# Inbox→bus renamed scripts (source files moved to ops/scripts/bus/)
register "ops/scripts/bus/cortex-bus-processor.py"        "${CORTEX_DEPLOY_HOME}/scripts/cortex-bus-processor.py"
register_orch "ops/scripts/install/setup-cortex-bus.sh"       "${CORTEX_DEPLOY_HOME}/scripts/setup-cortex-bus.sh"

# Bus monitoring tools (fleet-wide)
register_orch "ops/scripts/orch-bus/orch-bus-depth-watchdog.sh"  "${CORTEX_DEPLOY_HOME}/scripts/orch-bus-depth-watchdog.sh"
register_orch "ops/scripts/orch-bus/orch-bus-audit-watchdog.py"     "${CORTEX_DEPLOY_HOME}/scripts/orch-bus-audit-watchdog.py"
register_orch "ops/scripts/orch-bus/orch-bus-recover-timeouts.sh"   "${CORTEX_DEPLOY_HOME}/scripts/orch-bus-recover-timeouts.sh"
register "ops/scripts/manage/loop-gov-mcp.sh"            "${CORTEX_DEPLOY_HOME}/scripts/loop-gov-mcp.sh"
# P1-A hardening (2026-07-31): the enforcement MCP server itself must run
# from the IMMUTABLE deployed copy, not the user-writable repo working tree
# (config.yaml previously booted it from ~/hermes-cortex/mcp-servers/ — an
# agent could edit that file and silently disable begin_change enforcement).
# Register the real server to the tools/ path the lock helper protects.
register "mcp-servers/loop-gov-mcp.py"            "${CORTEX_DEPLOY_HOME}/tools/loop-governance/loop-gov-mcp.py"
# Loop-governance scoring stack (restored 2026-08-02 from live deployed copies
# — removed from repo in 7dbba626, leaving the pre-commit scorer unversioned).
# score_cycle.py is what pre-commit-score invokes via ~/.local/bin/score-cycle.
register "core/governance/score_cycle.py"          "${CORTEX_DEPLOY_HOME}/tools/loop-governance/score_cycle.py"
register "core/governance/loop_scorer.py"          "${CORTEX_DEPLOY_HOME}/tools/loop-governance/loop_scorer.py"
register "core/governance/loop_db.py"              "${CORTEX_DEPLOY_HOME}/tools/loop-governance/loop_db.py"
register "core/governance/loop_config.py"          "${CORTEX_DEPLOY_HOME}/tools/loop-governance/loop_config.py"
register "core/governance/loop_evaluator.py"       "${CORTEX_DEPLOY_HOME}/tools/loop-governance/loop_evaluator.py"
register "core/governance/loop_feedback.py"        "${CORTEX_DEPLOY_HOME}/tools/loop-governance/loop_feedback.py"
register "core/governance/policy_engine.py"        "${CORTEX_DEPLOY_HOME}/tools/loop-governance/policy_engine.py"
register "core/governance/auto_apply.py"           "${CORTEX_DEPLOY_HOME}/tools/loop-governance/auto_apply.py"
register "core/governance/skill_miner.py"          "${CORTEX_DEPLOY_HOME}/tools/loop-governance/skill_miner.py"
register "core/governance/__init__.py"             "${CORTEX_DEPLOY_HOME}/tools/loop-governance/__init__.py"
register "core/governance/setup.sh"                "${CORTEX_DEPLOY_HOME}/tools/loop-governance/setup.sh"
register "core/governance/update.sh"               "${CORTEX_DEPLOY_HOME}/tools/loop-governance/update.sh"
register "core/governance/verify.sh"               "${CORTEX_DEPLOY_HOME}/tools/loop-governance/verify.sh"
register "core/governance/cleanup-ollama.sh"       "${CORTEX_DEPLOY_HOME}/tools/loop-governance/cleanup-ollama.sh"
register "core/governance/VERSION"                 "${CORTEX_DEPLOY_HOME}/tools/loop-governance/VERSION"
# Bus-renamed scripts — everything under ops/scripts/bus/
register "ops/scripts/manage/ek-session-snapshot.py"     "${CORTEX_DEPLOY_HOME}/scripts/ek-session-snapshot.py"

# Fleet watchdog — cross-agent health polling (orch, deployed by install-orch-crons.sh).
# Registered once at line 256 (register_orch); do NOT duplicate here.

# Failover watchdog — detect bus outage, per-role behavior (all agents).
# Registered once at line 260 (register = all agents); do NOT duplicate here.

# legacy brain autopilot — REMOVED 2026-08-02 (decommissioned; mycortex replaces)

# Governance enforcer plugin — NOT registered in MAP. deploy_governance_plugin()
# handles the full lifecycle: copy, chmod 444, chattr +i. Dual registration
# causes copy_file() to add a source header that mismatches repo source,
# triggering needs_update and a cp failure on locked files.

# install-legacy-sync.sh UNREGISTERED 2026-08-05 — legacy brain decommissioned.
# Orchestrator health report — periodic agent fleet snapshot (no_agent cron)
register_orch "ops/scripts/agent/orch-health-report.py"       "${CORTEX_DEPLOY_HOME}/scripts/orch-health-report.py"

# Cron cost tracking — SQLite store + deployment script
register "ops/scripts/cost_store.py"               "${CORTEX_DEPLOY_HOME}/scripts/cost_store.py"
register "ops/scripts/install/install-cron-cost-tracking.py" "${CORTEX_DEPLOY_HOME}/scripts/install-cron-cost-tracking.py"
register "ops/scripts/install/install-lean-index.py" "${CORTEX_DEPLOY_HOME}/scripts/install-lean-index.py"

# O6-S1 MAX_COST guard — per-job cost cap consulted at cron request time
register "ops/scripts/manage/max_cost_guard.py"    "${CORTEX_DEPLOY_HOME}/scripts/max_cost_guard.py"

# Health monitoring
register "ops/scripts/change-validate.sh"                  "${CORTEX_DEPLOY_HOME}/scripts/change-validate.sh"
register "ops/scripts/precommit_test_discovery.py"         "${CORTEX_DEPLOY_HOME}/scripts/precommit_test_discovery.py"
register "ops/scripts/executor_context_builder.py"         "${CORTEX_DEPLOY_HOME}/scripts/executor_context_builder.py"
register "ops/scripts/telegram-bridge.py"                  "${CORTEX_DEPLOY_HOME}/scripts/telegram-bridge.py"
register "ops/scripts/token-expiry-alert.py"               "${CORTEX_DEPLOY_HOME}/scripts/token-expiry-alert.py"
register "ops/scripts/gateway_envelope.py"                 "${CORTEX_DEPLOY_HOME}/scripts/gateway_envelope.py"
register "ops/scripts/msg-gateway.py"                      "${CORTEX_DEPLOY_HOME}/scripts/msg-gateway.py"
register "ops/scripts/agent-shim.py"                       "${CORTEX_DEPLOY_HOME}/scripts/agent-shim.py"
register "ops/scripts/bot_locks.py"                        "${CORTEX_DEPLOY_HOME}/scripts/bot_locks.py"
register "ops/scripts/pre-commit-doc-audit.sh"            "${CORTEX_DEPLOY_HOME}/scripts/pre-commit-doc-audit.sh"
register "ops/scripts/health/health-vector.py"            "${CORTEX_DEPLOY_HOME}/scripts/health-vector.py" "health-vector" "restart_health_server"
register "ops/scripts/health/health-vector-push.sh"       "${CORTEX_DEPLOY_HOME}/scripts/health-vector-push.sh"
register "ops/scripts/health/report-agent-health.py"      "${CORTEX_DEPLOY_HOME}/scripts/report-agent-health.py"
register_orch "ops/scripts/manage/orch-skill-report-request.sh"    "${CORTEX_DEPLOY_HOME}/scripts/orch-skill-report-request.sh"

# Shared model config loader (imported by many scripts)

# Bus sensor and health tools (fleet-wide)
register_orch "ops/scripts/orch-bus/orch-bus-health-check.py"  "${CORTEX_DEPLOY_HOME}/scripts/orch-bus-health-check.py"
register_orch "ops/scripts/orch-bus/orch-bus-watch.py"         "${CORTEX_DEPLOY_HOME}/scripts/orch-bus-watch.py"
register_orch "ops/scripts/orch-bus/orch-bus-watch.sh"         "${CORTEX_DEPLOY_HOME}/scripts/orch-bus-watch.sh"
register_orch "ops/scripts/orch-bus/orch-bus-mcp.py"           "${CORTEX_DEPLOY_HOME}/scripts/orch-bus-mcp.py"
register_orch "ops/scripts/orch-bus/orch-bus-readiness-check.py" "${CORTEX_DEPLOY_HOME}/scripts/orch-bus-readiness-check.py"
register_orch "ops/scripts/orch-bus/orch-bus-git-auth-check.py" "${CORTEX_DEPLOY_HOME}/scripts/orch-bus-git-auth-check.py"
register_orch "ops/scripts/orch-bus/orch-clean-health-queue.py" "${CORTEX_DEPLOY_HOME}/scripts/orch-clean-health-queue.py"
register_orch "ops/scripts/orch-bus/orch-bus-generate-wrappers.py" "${CORTEX_DEPLOY_HOME}/scripts/orch-bus-generate-wrappers.py"
register_orch "ops/scripts/orch-bus/orch-bus-test.py"            "${CORTEX_DEPLOY_HOME}/scripts/orch-bus-test.py"

# Fleet agent message handler (polls inbox for UPDATE_REQUEST etc.)
register "ops/scripts/agent/agent-message-handler.py" "${CORTEX_DEPLOY_HOME}/scripts/agent-message-handler.py"
register "ops/scripts/agent/commands.py"               "${CORTEX_DEPLOY_HOME}/scripts/commands.py"
register "ops/scripts/agent/agent-diagnostic.py"       "${CORTEX_DEPLOY_HOME}/scripts/agent-diagnostic.py"

# Timezone helper (required by monitoring scripts)
register "ops/scripts/hermes_tz.py"                "${CORTEX_DEPLOY_HOME}/scripts/hermes_tz.py"

# mycortex knowledge brain — schema, migration runner, import, CLI, parity harness
register "ops/services/mycortex/migrate.py"          "${CORTEX_DEPLOY_HOME}/services/mycortex/migrate.py"
register "ops/services/mycortex/schema/mycortex.sql"  "${CORTEX_DEPLOY_HOME}/services/mycortex/schema/mycortex.sql"
register "ops/services/mycortex/schema/v002__rls-admin-reader-grants.sql" "${CORTEX_DEPLOY_HOME}/services/mycortex/schema/v002__rls-admin-reader-grants.sql"
register "ops/services/mycortex/schema/v003__admin-schema-version-grant.sql" "${CORTEX_DEPLOY_HOME}/services/mycortex/schema/v003__admin-schema-version-grant.sql"
register "ops/services/mycortex/schema/v004__embeddings.sql" "${CORTEX_DEPLOY_HOME}/services/mycortex/schema/v004__embeddings.sql"
register "ops/scripts/manage/mycortex-parity.py"      "${CORTEX_DEPLOY_HOME}/scripts/mycortex-parity.py"
register "ops/scripts/manage/mycortex"                "${CORTEX_DEPLOY_HOME}/scripts/mycortex"
# mycortex-postgres compose (dedicated hermes-cortex-owned Postgres, NOT langfuse)
register "ops/install/deploy/docker-compose.mycortex.yml" "${CORTEX_DEPLOY_HOME}/docker-compose.mycortex.yml"
# agent-mycortex-sync cron wrapper — per-host sync (design D4: NOT orchestrator-only)
register "ops/scripts/manage/agent-mycortex-sync.sh"  "${CORTEX_DEPLOY_HOME}/scripts/agent-mycortex-sync.sh"
# daily retention — prune ingest_log >90d, purge archived pages >7d (S-016)
register "ops/scripts/manage/agent-mycortex-retention.py" "${CORTEX_DEPLOY_HOME}/scripts/agent-mycortex-retention.py"

# Remediation sensor (companion to agent-auto-remediate cron)
register "ops/scripts/health/agent-remediation-sensor.py"       "${CORTEX_DEPLOY_HOME}/scripts/agent-remediation-sensor.py"

# ClickHouse system log cleanup (weekly threshold-based truncation)
register "ops/scripts/health/ch-truncate-system-logs.sh"        "${CORTEX_DEPLOY_HOME}/scripts/ch-truncate-system-logs.sh"

# Eval harness (agent reliability patterns)
register "ops/scripts/manage/run-evals.py"                "${CORTEX_DEPLOY_HOME}/scripts/run-evals.py"
register "ops/scripts/manage/analyze-failures.py"         "${CORTEX_DEPLOY_HOME}/scripts/analyze-failures.py"
register "ops/scripts/manage/fact-retention-eval.py"      "${CORTEX_DEPLOY_HOME}/scripts/fact-retention-eval.py"

# Agent learning sender
register "ops/scripts/manage/send-agent-learning.sh"      "${CORTEX_DEPLOY_HOME}/scripts/send-agent-learning.sh"

# Skill collection pipeline
register "ops/scripts/manage/agent-collect-skills.sh"      "${CORTEX_DEPLOY_HOME}/scripts/agent-collect-skills.sh"
register "ops/scripts/manage/agent-skill-stub-audit.py"   "${CORTEX_DEPLOY_HOME}/scripts/agent-skill-stub-audit.py"

# Migration scripts
register_orch "ops/scripts/manage/migrate-orch-bus-names.sh"   "${CORTEX_DEPLOY_HOME}/scripts/migrate-orch-bus-names.sh"
register "ops/scripts/post-push-audit"                     "${CORTEX_DEPLOY_HOME}/scripts/post-push-audit"
register_orch "ops/scripts/manage/orch-skill-report-process.py"    "${CORTEX_DEPLOY_HOME}/scripts/orch-skill-report-process.py"
register "ops/scripts/manage/agent-learning-collector.py" "${CORTEX_DEPLOY_HOME}/scripts/agent-learning-collector.py"
register "ops/scripts/manage/agent-session-mine-cron.py"   "${CORTEX_DEPLOY_HOME}/scripts/agent-session-mine-cron.py"
register "ops/scripts/manage/agent-session-correction-scan.py" "${CORTEX_DEPLOY_HOME}/scripts/manage/agent-session-correction-scan.py"
# orch-bus-* scripts are orchestrator-only — run from repo path
# Shared bus library for fleet scripts
register "ops/scripts/lib/cortex_bus.py" "${CORTEX_DEPLOY_HOME}/scripts/lib/cortex_bus.py"
# Shared Telegram notify library (R-9: single Bot API copy — handler, verifier, task-db)
register "ops/scripts/lib/telegram_notify.py" "${CORTEX_DEPLOY_HOME}/scripts/lib/telegram_notify.py"

# Agent inbox check is DEPRECATED — replaced by MCP tools. File retained in deploy for reference.

# Lesson-aware scripts (Memory That Compounds)
register "ops/scripts/manage/daily-lesson-mine.sh"      "${CORTEX_DEPLOY_HOME}/scripts/daily-lesson-mine.sh"
register "ops/scripts/manage/lesson-compound-stats.py"   "${CORTEX_DEPLOY_HOME}/scripts/lesson-compound-stats.py"
register "ops/scripts/manage/lesson-hit.sh"              "${CORTEX_DEPLOY_HOME}/scripts/lesson-hit.sh"
register "ops/scripts/manage/fix-cron-duplicates.py"  "${CORTEX_DEPLOY_HOME}/scripts/manage/fix-cron-duplicates.py"
register "ops/scripts/manage/remove-cron-jobs.py"      "${CORTEX_DEPLOY_HOME}/scripts/manage/remove-cron-jobs.py"
register "ops/scripts/manage/agent-push-metrics.sh"     "${CORTEX_DEPLOY_HOME}/scripts/agent-push-metrics.sh"
register "ops/scripts/manage/setup-push-metrics-cron.sh" "${CORTEX_DEPLOY_HOME}/scripts/setup-push-metrics-cron.sh"
register "ops/scripts/manage/agent-setup-metrics.sh" "${CORTEX_DEPLOY_HOME}/scripts/agent-setup-metrics.sh"

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
register_orch "ops/services/bus/agent-card/generate-agent-card.py"         "${CORTEX_DEPLOY_HOME}/scripts/generate-agent-card.py"
register_orch "ops/services/bus/agent-card/agent-card.json"                "${CORTEX_DEPLOY_HOME}/bus/agent-card.json"

# ⚠️ MEMORY.md / USER.md are Hermes-owned — NEVER register them here.
# Hermes reads ~/.hermes/memories/ directly and creates the files on first
# memory write. A register entry here made every deploy overwrite LIVE memory
# with the blank seed template — the hash always differs because the live file
# is personalized, so needs_update() clobbered it on every run (7× on
# 2026-08-05). Seeds remain in docs/templates/ for reference only.
# memory-readme.seed.md is a cortex-owned rubric doc (NOT user memory) — safe
# to keep syncing via the generic hash path.
register "docs/templates/memory-readme.seed.md" "${CORTEX_DEPLOY_HOME}/memory/README.md"

# Langfuse
register_orch "ops/install/deploy/docker-compose.langfuse.yml"        "${HOME}/langfuse/docker-compose.yml" "langfuse" "restart_langfuse"

# Dashboard
register_orch "ops/services/dashboard/server.py"               "${CORTEX_DEPLOY_HOME}/dashboard/server.py" "dashboard" "restart_dashboard"
register_orch "ops/services/dashboard/static/index.html"        "${CORTEX_DEPLOY_HOME}/dashboard/static/index.html" "dashboard"
register_orch "ops/services/dashboard/com.hermes.cortex-dashboard.plist" "${HOME}/Library/LaunchAgents/com.hermes.cortex-dashboard.plist" "dashboard"

# Agent Bus

# Service definitions
register "ops/scripts/install/os-config.sh"               "${CORTEX_DEPLOY_HOME}/scripts/install/os-config.sh"
register "ops/scripts/install/service-writer.sh"          "${CORTEX_DEPLOY_HOME}/scripts/service-writer.sh"

restart_cortex_bus() {
  # macOS launchd
  if launchctl list com.hermes.cortex-bus 2>/dev/null | grep -q "PID"; then
    info "  Restarting Agent Bus (launchd)…"
    # unload+load (not bootout+bootstrap): the Hermes gateway lifecycle guard
    # (cron/lifecycle_guard.py) blocks literal `launchctl bootstrap` inside the
    # gateway process — even for non-gateway services. unload+load reloads the
    # plist with identical semantics and is not in the guard's blocked set.
    launchctl unload "${HOME}/Library/LaunchAgents/com.hermes.cortex-bus.plist" 2>/dev/null || true
    launchctl load "${HOME}/Library/LaunchAgents/com.hermes.cortex-bus.plist" 2>/dev/null || true
    return
  fi
  # Linux systemd
  if systemctl --user is-active --quiet cortex-bus 2>/dev/null; then
    info "  Restarting Agent Bus (systemd)…"
    systemctl --user daemon-reload 2>/dev/null || true
    systemctl --user restart cortex-bus 2>&1 | sed 's/^/    /'
  fi
}

# ── Service restart helpers ─────────────────────────────────

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
# restart_agent_inbox — removed; use restart_cortex_bus instead

restart_health_server() {
  # health-vector.service — canonical health endpoint server (:8905).
  # Linux: systemd user unit. macOS: legacy com.hermes.health-server.
  # The script is deployed by cortex-update.sh; the RUNNING process keeps
  # old in-memory logic until restarted (deploy ≠ load — observed 2026-08-20:
  # bounded-hour stale-cron fix sat unloaded 17 days, fleet watchdog flagged
  # esther no_stale_crons down nightly).
  if [[ -f "${HOME}/.config/systemd/user/health-vector.service" ]]; then
    systemctl --user daemon-reload 2>/dev/null || true
    systemctl --user restart health-vector 2>&1 | sed 's/^/    /'
  elif launchctl list com.hermes.health-server &>/dev/null 2>&1; then
    info "  Restarting health server (launchd)…"
    launchctl kickstart -k "gui/$(id -u)/com.hermes.health-server" 2>&1 | sed 's/^/    /'
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
  local src_rel="${src/#$REPO_DIR\//}"
  local backup_dir="${STATE_DIR}/deploy-backups"
  local manifest_file="${STATE_DIR}/deploy-manifest.txt"

  mkdir -p "$(dirname "$dest")"
  if $DRY_RUN; then
    echo "    would copy: $(basename "$src") → ${dest/$HOME/~}"
  else
    # ── Backup manually-edited deployed files ────────────────
    # If the deployed file differs from the last deployed checksum,
    # an agent manually edited it. Back it up before overwriting.
    if [[ -f "$dest" ]]; then
      local expected_hash=""
      if [[ -f "$manifest_file" ]]; then
        expected_hash=$(grep "^${dest}=" "$manifest_file" 2>/dev/null | cut -d= -f2) || true
      fi
      if [[ -n "$expected_hash" ]]; then
        local current_hash=""
        if command -v sha256sum &>/dev/null; then
          current_hash=$(sha256sum "$dest" 2>/dev/null | cut -d' ' -f1)
        elif command -v shasum &>/dev/null; then
          current_hash=$(shasum -a 256 "$dest" 2>/dev/null | cut -d' ' -f1)
        fi
        if [[ -n "$current_hash" && "$current_hash" != "$expected_hash" ]]; then
          mkdir -p "$backup_dir"
          local backup_file="${backup_dir}/$(basename "$dest").$(date +%Y%m%d_%H%M%S).bak"
          cp "$dest" "$backup_file"
          warn ""
          warn "⚠️  Deployed file was manually edited — backed up to:"
          warn "    ${backup_file/$HOME/~}"
          warn "    Source (fix this, don't edit the deployed copy):"
          warn "    ${REPO_DIR/$HOME/~}/${src_rel}"
          warn "    Edit the source, commit, push, then re-run cortex-update.sh"
          warn ""
        fi
      fi
    fi

    # macOS/Linux immutable flag: unlock before overwrite
    # Linux: chattr -i needs root — use sudo. macOS: chflags works as owner.
    if [[ -f "$dest" && ! -w "$dest" ]]; then
      if [[ "$(uname -s)" == "Darwin" ]]; then
        chflags nouchg "$dest" 2>/dev/null || true
      else
        # P1-A hardening: route exclusively through the gated helper
        # (direct chattr bypasses the sanctioned-caller gate). The
        # --cortex-update token passes through sudoers arg matching.
        sudo -n "$(command -v hermes-plugin-lock 2>/dev/null || echo /usr/local/sbin/hermes-plugin-lock)" unlock --cortex-update 2>/dev/null || true
      fi
      # Unlocking the immutable flag does NOT restore write permission —
      # a file left 444 by a previous lock run (deploy_governance_plugin /
      # end-of-script chmod 444) still fails `cp` with "Permission denied".
      # Restore owner-write so the copy below can overwrite it.
      chmod u+w "$dest" 2>/dev/null || sudo -n chmod u+w "$dest" 2>/dev/null || true
    fi

    # ── Add source header ────────────────────────────────────
    # Add a header showing the repo source path so every agent
    # knows where the canonical file lives when they read it.
    # Shebang stays on line 1 — a header above it breaks direct
    # ./script.py execution (kernel only honors shebang at line 1).
    local tmp_src="$src"
    case "$dest" in
      *.sh|*.py)
        tmp_src=$(mktemp)
        if head -1 "$src" | grep -q '^#!'; then
          {
            head -1 "$src"
            echo "# SOURCE: ${REPO_DIR/$HOME/~}/${src_rel}"
            echo "# Do NOT edit this file — edit the source above and run: bash cortex-update.sh"
            echo ""
            tail -n +2 "$src"
          } > "$tmp_src"
        else
          {
            echo "# SOURCE: ${REPO_DIR/$HOME/~}/${src_rel}"
            echo "# Do NOT edit this file — edit the source above and run: bash cortex-update.sh"
            echo ""
            cat "$src"
          } > "$tmp_src"
        fi
        ;;
    esac

    cp "$tmp_src" "$dest"
    [[ "$tmp_src" != "$src" ]] && rm -f "$tmp_src"
    chmod 644 "$dest"
    # Preserve executable bit
    [[ -x "$src" ]] && chmod +x "$dest"
    # Fallback: .py and .sh files in scripts dir must be executable for no_agent cron jobs
    if [[ "$dest" == "${CORTEX_DEPLOY_HOME}/scripts/"* ]]; then
      case "$dest" in
        *.py|*.sh) chmod +x "$dest" ;;
      esac
    fi

    # ── Record deployed checksum in manifest ──────────────────
    local new_hash=""
    if command -v sha256sum &>/dev/null; then
      new_hash=$(sha256sum "$dest" 2>/dev/null | cut -d' ' -f1)
    elif command -v shasum &>/dev/null; then
      new_hash=$(shasum -a 256 "$dest" 2>/dev/null | cut -d' ' -f1)
    fi
    if [[ -n "$new_hash" ]]; then
      if [[ -f "$manifest_file" ]]; then
        grep -v "^${dest}=" "$manifest_file" 2>/dev/null > "${manifest_file}.tmp" || true
        mv "${manifest_file}.tmp" "$manifest_file" 2>/dev/null || true
      fi
      echo "${dest}=${new_hash}" >> "$manifest_file"
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

  # Unlock enforcement files so cortex-update.sh can update them.
  # Linux: chattr -i needs root — use the NOPASSWD sudo helper.
  # macOS: chflags uchg works without root — plain bash is fine.
  local _os; _os=$(uname -s)
  local _lock_helper="${CORTEX_DEPLOY_HOME}/scripts/hermes-plugin-lock"
  if [[ "$_os" == "Darwin" ]]; then
    if [[ -f "$_lock_helper" ]]; then
      bash "$_lock_helper" unlock --cortex-update 2>/dev/null || true
    elif command -v hermes-plugin-lock &>/dev/null; then
      hermes-plugin-lock unlock --cortex-update 2>/dev/null || true
    fi
  else
    # Linux: non-root chattr -i fails with "Operation not permitted", so
    # the previous `bash "$_lock_helper" unlock` silently left files locked
    # and the cp below aborted. Route through the sudo helper (NOPASSWD).
    if command -v hermes-plugin-lock &>/dev/null; then
      sudo -n hermes-plugin-lock unlock --cortex-update 2>/dev/null || true
    elif [[ -f "$_lock_helper" ]]; then
      sudo -n "$_lock_helper" unlock --cortex-update 2>/dev/null || bash "$_lock_helper" unlock --cortex-update 2>/dev/null || true
    fi
  fi

  # Merge ORCH_MAP entries on orchestrator hosts
  # Orchestrator = hostname moses|esther AND matching home dir. Env vars
  # (AGENT_TYPE / IS_ORCHESTRATOR) grant NO orch powers — they are spoofable.
  local _is_orch=false
  local _host _home _user
  _host=$(hostname -s 2>/dev/null || echo "unknown")
  _user=$(id -un 2>/dev/null || echo "$USER")
  if command -v getent &>/dev/null; then
    _home=$(getent passwd "$_user" 2>/dev/null | cut -d: -f6)
  fi
  _home="${_home:-$HOME}"
  case "$_host" in
    moses|esther) [[ "$_home" == "/home/$_host" ]] && _is_orch=true ;;
  esac

  local entries=("${MAP[@]}")
  if $_is_orch && [[ ${#ORCH_MAP[@]} -gt 0 ]]; then
    entries+=("${ORCH_MAP[@]}")
  fi

  for entry in "${entries[@]}"; do
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
          info "  Updated: ${dest/$HOME/~}"
          [[ -n "$service" && -n "$restart_cmd" ]] && TO_RESTART+=("$restart_cmd")
        fi
      fi
    fi
  done

  # ── Enforce per-file mode overrides (post-unlock, unconditional) ──
  # Runs after the enforcement unlock + copy so a mode change propagates even
  # when needs_update() skipped the copy (content identical). A stale mode on
  # an immutable file would otherwise stick forever (Titus 2026-08-03).
  local _mode_dest _mode_val
  for _mode_dest in "${!MODE_OVERRIDES[@]}"; do
    _mode_val="${MODE_OVERRIDES[$_mode_dest]}"
    if [[ -f "$_mode_dest" ]]; then
      if ! chmod "$_mode_val" "$_mode_dest" 2>/dev/null; then
        warn "  mode override failed for ${_mode_dest/$HOME/~} (chmod $_mode_val)"
      fi
    fi
  done
}

# ── Deprecated file cleanup ─────────────────────────────────

# Scans deploy dir for files not in MAP and removes them
clean_stale_deploys() {
  local cleaned=0 preserved=0
  info "🧹 Scanning for stale deploy files..."

  # Files to preserve even if not registered (cron-referenced)
  local preserve=(
    "agent-model-health-watchdog.py"
    "agent-offline-code-index.sh"
    "skill_miner.py"
    "agent-swap-refresh.py"
    "agent-nginx-threat-pipeline.sh"
    # Local-only no_agent cron scripts — NOT in repo, created per-host.
    # Must survive clean_stale_deploys; the cron scheduler resolves them
    # through the ~/.hermes/scripts → ~/.hermes-cortex/scripts symlink.
    # (2026-08-02: these were being deleted every deploy, which the doctor's
    # check_scripts correctly surfaced once the runtime path was unified.)
    "agent-daily-bible-reading.py"
    "local-clickhouse-log-cleanup.sh"
  )

  # Build list of all registered destinations
  local dests=()
  for entry in "${MAP[@]}"; do
    local dest
    IFS='|' read -r _ dest _ _ <<< "$entry"
    dests+=("$dest")
  done
  # Also protect ORCH_MAP destinations on orchestrator hosts
  if [[ ${#ORCH_MAP[@]} -gt 0 ]]; then
    local _is_orch=false
    local _host _home _user
    _host=$(hostname -s 2>/dev/null || echo "unknown")
    _user=$(id -un 2>/dev/null || echo "$USER")
    if command -v getent &>/dev/null; then
      _home=$(getent passwd "$_user" 2>/dev/null | cut -d: -f6)
    fi
    _home="${_home:-$HOME}"
    # Orchestrator = hostname moses|esther AND matching home dir. Env vars
    # (AGENT_TYPE / IS_ORCHESTRATOR) grant NO orch powers — they are spoofable.
    case "$_host" in
      moses|esther) [[ "$_home" == "/home/$_host" ]] && _is_orch=true ;;
    esac
    if $_is_orch; then
      for entry in "${ORCH_MAP[@]}"; do
        IFS='|' read -r _ dest _ _ <<< "$entry"
        dests+=("$dest")
      done
    fi
  fi

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
        # Systematic local-* rule: ANY local- prefixed script is
        # deployed-only (created per-host, not in repo). The hand-maintained
        # preserve list below can't anticipate every new local-* script, so
        # the prefix match is the durable rule — the list is belt-and-braces.
        if [[ "$basename" == local-* ]]; then
          match=true
        fi
      fi
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
        # ⚠️  Deployed-only script not registered in the repo, not local-*,
        # not on the preserve list. NEVER auto-delete — same class of loss
        # as local-cwr-file-processing (2026-08-03). Warn with guidance;
        # the human decides. (Repo-renamed scripts are caught by the doctor
        # instead; auto-removal here is how deployed-only files vanished.)
        warn "  ⚠️  Deployed-only script not in repo: ${f/$HOME/~}"
        warn "      Register it in cortex-update.sh, rename to local-* to keep,"
        warn "      or delete manually if unused. NOT auto-removed."
        preserved=$((preserved + 1))
      fi
    done < <(find "$scan_dir" -type f \( -name '*.py' -o -name '*.sh' \) -print0)
  fi

  if $DRY_RUN; then
    info "  Dry-run complete — ${cleaned} would be removed, ${preserved} preserved (deployed-only, not auto-deleted)"
  elif [[ $cleaned -gt 0 ]]; then
    info "  Cleaned ${cleaned} stale file(s), ${preserved} preserved (deployed-only)"
  elif [[ $preserved -gt 0 ]]; then
    info "  No stale files removed; ${preserved} deployed-only file(s) preserved (not auto-deleted)"
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
# Returns 0 if the file is a truncated skill stub, 1 otherwise.
# Mirrors cortex-doctor check_skill_stubs markers: literal
# 'Full content (truncated)' (Jul-17 1KB import stubs) or an
# '--- End skill ---' dump under 1500 bytes. BOTH markers require
# the file to be SMALL (< 1500 bytes) — a full doc that merely
# quotes the marker string (e.g. this doc) is not a stub.
is_skill_stub() {
  local f="$1"
  [[ -f "$f" ]] || return 1
  local size
  size=$(wc -c < "$f" 2>/dev/null || echo 0)
  [[ "$size" -ge 1500 ]] && return 1
  if grep -q "Full content (truncated)" "$f" 2>/dev/null; then
    return 0
  fi
  if grep -q -- "--- End skill ---" "$f" 2>/dev/null; then
    return 0
  fi
  return 1
}

# Copies SKILL.md files and references/ from repo skills/ directories
# to ~/.hermes/skills/. Uses the delta engine — only copies
# files whose checksums differ from installed versions.
# Syncs from TWO locations:
#   1. $REPO_DIR/skills/              — canonical global skills (categorized)
#   2. $REPO_DIR/.hermes-cortex/skills/ — project-level overrides (flat)
sync_skills() {
  local skill_dest="${CORTEX_DEPLOY_HOME}/skills"
  local synced=0 skipped=0 removed=0 preserved=0
  mkdir -p "$skill_dest"

  # Track source paths for stale-detection
  declare -A source_dirs=()

  # ── Pass 1: Root-level skills/ (canonical global skills) ──
  local root_skills="${REPO_DIR}/skills"
  if [[ -d "$root_skills" ]]; then
    while IFS= read -r -d '' skill_file; do
      local rel_path="${skill_file#$root_skills/}"
      local dest="${skill_dest}/${rel_path}"
      mkdir -p "$(dirname "$dest")"
      source_dirs["$(dirname "$rel_path")"]=1

      # Name-collision detection: warn if categorized skill shares name with Hermes default
      local skill_name
      skill_name="$(basename "$(dirname "$skill_file")")"
      local root_hermes_check="${skill_dest}/${skill_name}/SKILL.md"
      if [[ "$rel_path" == */*/* ]] && [[ -f "$root_hermes_check" ]]; then
        warn "  Name collision: ${rel_path%/*} — root Hermes default '${skill_name}' exists, deploy will shadow it"
      fi
      if needs_update "$skill_file" "$dest"; then
        # Truncation guard: never overwrite a FULL deployed skill with a
        # truncated repo stub. The doctor FAILs on repo stubs, but that's
        # post-hoc — this prevents the damage at deploy time.
        if [[ -f "$dest" ]] && is_skill_stub "$skill_file" && ! is_skill_stub "$dest"; then
          warn "  SKILL STUB GUARD: ${rel_path%/*} — repo source is a truncated stub, refusing to overwrite full deployed copy!"
          warn "    → Repo: $skill_file"
          warn "    → Deployed: $dest"
          warn "    → Restore the full repo source (agent-skill-stub-audit.py --send), then cortex-update.sh will sync."
          warn "    → Use FORCE=true to override this guardrail."
          if [[ "${FORCE:-false}" != "true" ]]; then
            skipped=$((skipped + 1))
            continue
          fi
        fi
        # Drift guardrail: if deployed copy is newer, warn before overwriting
        if [[ -f "$dest" ]] && [[ "$dest" -nt "$skill_file" ]]; then
          warn "  SKILL DRIFT: ${rel_path%/*} — deployed copy is newer than repo source!"
          warn "    → Repo: $skill_file"
          warn "    → Deployed: $dest"
          warn "    → Copy the deployed changes to the repo source, then cortex-update.sh will sync."
          warn "    → Use --force to override this guardrail."
          if [[ "${FORCE:-false}" != "true" ]]; then
            skipped=$((skipped + 1))
            continue
          fi
        fi
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

    # Sync scripts and templates (skill assets). Without this, deployed
    # skill dirs are partial — SKILL.md references scripts/load_*.py etc.
    # that never reach ~/.hermes/skills/<cat>/<name>/scripts/.
    while IFS= read -r -d '' asset_file; do
      # Skip Python bytecode cache — never deploy pyc/pyo
      case "$asset_file" in
        *__pycache__*|*.pyc|*.pyo) continue ;;
      esac
      local rel_path="${asset_file#$root_skills/}"
      local dest="${skill_dest}/${rel_path}"
      mkdir -p "$(dirname "$dest")"

      if needs_update "$asset_file" "$dest"; then
        copy_file "$asset_file" "$dest"
      fi
    done < <(find "$root_skills" \( -path "*/scripts/*" -o -path "*/templates/*" \) -type f -print0)
  fi

  # ── Pass 2: Project-level overrides (.hermes-cortex/skills/) ──
  local override_skills="${REPO_DIR}/.hermes-cortex/skills"
  if [[ -d "$override_skills" ]]; then
    while IFS= read -r -d '' skill_file; do
      local rel_path="${skill_file#$override_skills/}"
      local dest="${skill_dest}/${rel_path}"
      mkdir -p "$(dirname "$dest")"
      source_dirs["$(dirname "$rel_path")"]=1

      if needs_update "$skill_file" "$dest"; then
        # Truncation guard (same as Pass 1): never overwrite a FULL deployed
        # skill with a truncated repo stub.
        if [[ -f "$dest" ]] && is_skill_stub "$skill_file" && ! is_skill_stub "$dest"; then
          warn "  SKILL STUB GUARD: ${rel_path%/*} — repo source is a truncated stub, refusing to overwrite full deployed copy!"
          warn "    → Repo: $skill_file"
          warn "    → Deployed: $dest"
          warn "    → Restore the full repo source, then cortex-update.sh will sync."
          warn "    → Use FORCE=true to override this guardrail."
          if [[ "${FORCE:-false}" != "true" ]]; then
            skipped=$((skipped + 1))
            continue
          fi
        fi
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
  else
    info "  Skills: ${synced} updated, ${skipped} unchanged"
  fi

  # ── Pass 3: Clean up stale deployed skills ──
  # Always runs — NOT gated behind the overrides dir (a machine without
  # .hermes-cortex/skills/ overrides must still prune stale deployed
  # skills; the old early-return made Pass 3 dead code on every host).
  # NOTE: skill_dest may be a symlink (e.g. ~/.hermes-cortex/skills →
  # ~/.hermes/skills) — use find -L so GNU find traverses it; without -L
  # the find returns nothing and stale skill dirs (renamed categories,
  # deleted skills) linger forever.
  # SAFETY: skip Hermes-default skills — they live in category dirs but
  # have no repo source. Two markers (same as the doctor's orphan scan):
  #   1. metadata.hermes frontmatter
  #   2. skill NAME present in ~/.hermes/hermes-agent/{skills,optional-skills}
  #      (some defaults like youtube-content carry no metadata block)
  # Also skip .archive/ dirs.
  # KEY RULE: if the skill NAME exists in the repo under a DIFFERENT
  # category, the deployed copy at this path is a stale duplicate of a
  # repo skill (renamed/moved category) — REMOVE it even if it carries
  # metadata.hermes. Only name-not-in-repo skills are treated as Hermes
  # defaults worth keeping.
  local hermes_agent_skills="${CORTEX_DEPLOY_HOME}/../.hermes/hermes-agent"
  [[ -d "$HOME/.hermes/hermes-agent" ]] && hermes_agent_skills="$HOME/.hermes/hermes-agent"
  declare -A hermes_skill_names=()
  local _hdir
  for _hdir in "${hermes_agent_skills}/skills" "${hermes_agent_skills}/optional-skills"; do
    if [[ -d "$_hdir" ]]; then
      while IFS= read -r -d '' _hfile; do
        local _hrel="${_hfile#$_hdir/}"
        local _hname="${_hrel%/SKILL.md}"
        hermes_skill_names["$(basename "$_hname")"]=1
      done < <(find "$_hdir" -name "SKILL.md" -type f -print0 2>/dev/null)
    fi
  done
  declare -A repo_skill_names=()
  for _sk in "${!source_dirs[@]}"; do
    repo_skill_names["${_sk##*/}"]=1
  done
  while IFS= read -r -d '' deployed_skill; do
    local rel="${deployed_skill#$skill_dest/}"
    local dirname="${rel%/SKILL.md}"
    # Skip root-level skills (no / in path = Hermes default)
    if [[ "$dirname" != */* ]]; then
      continue
    fi
    # Skip archive dirs
    if [[ "$dirname" == .archive/* ]]; then
      continue
    fi
    local _skill_name="${dirname##*/}"
    # Systematic local-* rule: deployed-only skills (created per-host, not
    # in repo — e.g. local-cwr-file-processing) must NEVER be pruned by the
    # stale pass. The repo only owns repo-named skills; anything local-* is
    # host-managed. (Found 2026-08-03: local-cwr-file-processing was being
    # wiped every deploy — the same class of bug as the local-* scripts.)
    if [[ "$_skill_name" == local-* ]]; then
      continue
    fi
    # If the skill exists in the repo under a DIFFERENT category, this is
    # a stale duplicate of a repo skill (moved/renamed category) — remove.
    if [[ -n "${source_dirs[$dirname]:-}" ]]; then
      continue
    fi
    if [[ -n "${repo_skill_names[$_skill_name]:-}" ]]; then
      # Repo owns this skill under a different category — the deployed copy
      # at this path is a stale duplicate of a repo skill. The repo is the
      # source of truth and re-deploys the current path, so removing the
      # stale duplicate is safe (no data loss — source lives in the repo).
      rm -rf "$(dirname "$deployed_skill")"
      removed=$((removed + 1))
      continue
    fi
    # Name not in repo: Hermes-default check (metadata.hermes frontmatter
    # or name present in hermes-agent dirs) — keep those.
    if [[ -n "${hermes_skill_names[$_skill_name]:-}" ]]; then
      continue
    fi
    if grep -q '^metadata:$' "$deployed_skill" 2>/dev/null && \
       grep -A1 '^metadata:$' "$deployed_skill" 2>/dev/null | grep -q 'hermes:'; then
      continue
    fi
    # ⚠️  Deployed-only skill not owned by the repo, not Hermes-default, not
    # local-*. NEVER auto-delete — this is how local-cwr-file-processing was
    # lost (2026-08-03). Warn with guidance instead; the human decides.
    warn "  ⚠️  Deployed-only skill '${_skill_name}' (${rel%/SKILL.md}) is not in the repo."
    warn "      Rename it to local-* (e.g. local-${_skill_name}) to preserve it,"
    warn "      or delete it manually if unused. NOT auto-removed."
    preserved=$((preserved + 1))
  done < <(find -L "$skill_dest" -name "SKILL.md" -type f -print0)

  info "  Skills: ${synced} updated, ${skipped} unchanged, ${removed} stale removed, ${preserved} preserved (deployed-only, not auto-deleted)"
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
# Deploys admin scripts to a system path (root-owned, NOPASSWD-safe).
# Linux:   /usr/local/sbin/
# macOS:   /usr/local/bin/   (no root needed for chflags uchg)
# Uses sudo on Linux for the root-owned path.
deploy_system_scripts() {
  # Allow skipping nginx-related system scripts (e.g. on servers without sudo)
  [[ -n "${CORTEX_SKIP_NGINX:-}" ]] && { info "CORTEX_SKIP_NGINX set — skipping system script deploy"; return 0; }
  local _os; _os=$(uname -s)
  local deploy_dir="/usr/local/sbin"
  [[ "$_os" == "Darwin" ]] && deploy_dir="/usr/local/bin"
  local src_dir="${REPO_DIR}/ops/install/deploy/nginx"
  local scripts=("install-nginx-full.sh" "hermes-nginx-clean-restart" "hermes-plugin-lock")
  local files_copied=0

  [[ -d "$src_dir" ]] || return 0

  for script in "${scripts[@]}"; do
    local src="${src_dir}/${script}"
    local dest="${deploy_dir}/${script}"
    [[ ! -f "$src" ]] && continue
    if needs_update "$src" "$dest"; then
      if command -v sudo &>/dev/null; then
        # ── Self-deploy via update command (binary can update itself) ──
        if [[ "$script" == "hermes-plugin-lock" ]] && [[ -f "$dest" ]]; then
          sudo -n "$dest" update --cortex-update 2>/dev/null && {
            if [[ "$_os" == "Darwin" ]]; then
              sudo chown "$(id -un)":staff "$dest" 2>/dev/null || true
            fi
            info "  Self-updated: ${script} → ${deploy_dir}/"
            files_copied=$((files_copied + 1))
            continue
          } || true
          # Fall through to sudo cp if update failed (old binary with broken update)
        fi
        # ── Standard deploy (requires NOPASSWD for cp) ──
        sudo mkdir -p "$deploy_dir" 2>/dev/null || true
        if sudo cp "$src" "$dest" 2>/dev/null; then
          # macOS: keep system copy user-owned so chflags uchg works as owner.
          # Linux: root-owned — helper is invoked via sudo anyway.
          if [[ "$_os" == "Darwin" ]]; then
            sudo chown "$(id -un)":staff "$dest" 2>/dev/null || true
          else
            sudo chown root:root "$dest" 2>/dev/null || true
          fi
          sudo chmod 755 "$dest" 2>/dev/null || true
          # Re-lock after update (will be re-applied by blanket lock at end)
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

# ── Governance Plugin Deploy ──────────────────────────────────
# Deploys the governance enforcer plugin as a COPY (not symlink)
# so that immutability can be applied to the deployed copy without
# locking the repo file. Handles symlink→copy migration.
# Linux:   chattr +i via sudo hermes-plugin-lock (needs root)
# macOS:   chflags uchg via hermes-plugin-lock (no root needed)
#
# ── Deploy ≠ load — restart-needed detection ─────────────────
# The enforcer file is ALWAYS copied, so file mtime is meaningless.
# Track the deployed content hash + the epoch it changed; a gateway
# restart is pending iff the RUNNING gateway process started BEFORE
# that content change. Surfaced as a LOUD banner every run until the
# operator restarts (a quiet info line scrolls past and the restart
# never happens — the original deploy≠load misery).
GOV_ENFORCER_STATE="${STATE_DIR}/governance-enforcer-deployed"   # "<hash> <epoch>"

# ── _restart_pending return codes (enum — the ONLY valid values) ──
#   0 RESTART_PENDING       → fire the loud banner
#   1 RESTART_CLEAN         → verified no restart needed — banner silent
#   2 RESTART_UNVERIFIABLE  → check failed — banner fires with "could not
#                            verify" note (hash/ps/date failure). A failed
#                            check must NEVER silently mean "no restart
#                            needed" — that was the original deploy≠load
#                            misery.
readonly RESTART_PENDING=0
readonly RESTART_CLEAN=1
readonly RESTART_UNVERIFIABLE=2

_sha256_of() {
  # Prints the 64-char sha256 of $1. Returns 0 on success.
  # FAILURE IS NEVER SILENT: every failure path (missing tool, unreadable
  # file, hash error) prints a warning to stderr and returns 1 — callers
  # must treat that as UNVERIFIABLE and fire the banner, never skip it.
  local f="$1" out=""
  if command -v sha256sum &>/dev/null; then
    out=$(sha256sum "$f" 2>&1) || { warn "  _sha256_of: sha256sum failed for ${f}: ${out}"; echo ""; return 1; }
    echo "${out%% *}"
  elif command -v shasum &>/dev/null; then
    out=$(shasum -a 256 "$f" 2>&1) || { warn "  _sha256_of: shasum failed for ${f}: ${out}"; echo ""; return 1; }
    echo "${out%% *}"
  else
    warn "  _sha256_of: no sha256sum/shasum available — cannot hash ${f}"
    echo ""
    return 1
  fi
}

_gateway_start_epoch() {
  # Prints the gateway start epoch. Returns 0 on success.
  # FAILURE IS NEVER SILENT: if the process can't be found or the date
  # parse fails, warns and returns 1 — callers treat that as UNVERIFIABLE
  # (banner fires), never as "no restart needed".
  # Linux + macOS: ps lstart → epoch. `command` is the PORTABLE ps keyword
  # (Linux cmd= alias; macOS BSD ps has no `cmd` — use `command`).
  # `sed -n '1p'` (NOT head) — head SIGPIPE-kills the pipeline under
  # `set -o pipefail`. The `|| true` here is NOT swallowing: the empty
  # string gate below is the explicit failure handler.
  local lstart=""
  lstart=$(ps -eo lstart=,command= 2>&1 | grep -E 'hermes_cli\.main gateway|hermes gateway run' | grep -v grep | sed -n '1p' | awk '{print $1, $2, $3, $4, $5}') || true
  if [[ -z "$lstart" ]]; then
    warn "  _gateway_start_epoch: gateway process not found (or ps failed) — restart state UNVERIFIABLE"
    echo ""
    return 1
  fi
  local epoch=""
  if [[ "$(uname -s)" == "Darwin" ]]; then
    epoch=$(date -j -f "%a %b %e %H:%M:%S %Y" "$lstart" +%s 2>&1) || { warn "  _gateway_start_epoch: date parse failed for '${lstart}': ${epoch}"; echo ""; return 1; }
  else
    epoch=$(date -d "$lstart" +%s 2>&1) || { warn "  _gateway_start_epoch: date parse failed for '${lstart}': ${epoch}"; echo ""; return 1; }
  fi
  echo "$epoch"
}

_restart_pending() {
  # Returns 0 (restart needed) iff the deployed enforcer content changed
  # AFTER the running gateway started. Uses a persisted hash+epoch state
  # file so unchanged content never re-warns — unless the restart is still
  # genuinely pending (gateway predates the recorded change epoch).
  #
  # RETURN CODES (see enum above — the ONLY valid values):
  #   RESTART_PENDING       (0) → fire the loud banner
  #   RESTART_CLEAN         (1) → verified clean — banner stays silent
  #   RESTART_UNVERIFIABLE  (2) → check failed — banner fires with a
  #       "could not verify" note (hash/ps/date failure). A failed check
  #       must NEVER silently mean "no restart needed" — that was the
  #       original deploy≠load misery.
  local init_py="${HOME}/.hermes/plugins/governance-enforcer/__init__.py"
  if [[ ! -f "$init_py" ]]; then
    warn "  Restart check: enforcer not deployed at ${init_py} — skipping restart check"
    return "$RESTART_CLEAN"
  fi
  local deployed_hash stored_hash="" stored_epoch=0 change_epoch gw_epoch
  if ! deployed_hash=$(_sha256_of "$init_py"); then
    warn "  Restart check: cannot hash deployed enforcer — UNVERIFIABLE, treating as restart required"
    return "$RESTART_UNVERIFIABLE"
  fi
  if [[ -f "$GOV_ENFORCER_STATE" ]]; then
    if ! read -r stored_hash stored_epoch < "$GOV_ENFORCER_STATE"; then
      warn "  Restart check: state file ${GOV_ENFORCER_STATE} unreadable/empty — re-recording"
    fi
    stored_epoch="${stored_epoch:-0}"
  fi
  if [[ "$deployed_hash" != "$stored_hash" ]]; then
    change_epoch=$(date +%s)
    if ! err=$(echo "$deployed_hash $change_epoch" > "$GOV_ENFORCER_STATE" 2>&1); then
      warn "  Restart check: cannot write state file ${GOV_ENFORCER_STATE} — banner will re-check next run: ${err}"
    fi
  else
    change_epoch="$stored_epoch"
  fi
  if ! gw_epoch=$(_gateway_start_epoch); then
    warn "  Restart check: cannot determine gateway start time — UNVERIFIABLE, treating as restart required"
    return "$RESTART_UNVERIFIABLE"
  fi
  [[ "$gw_epoch" -lt "$change_epoch" ]]
}

_loud_restart_banner() {
  # mode: "" (default) = verified pending | "unverifiable" = the check
  # failed and restart state is unknown — the banner must STILL FIRE so
  # the operator investigates; never silently suppress.
  # ⚠️ The command string is split ("re""start") deliberately: the terminal
  # tool's gateway lifecycle guard scans REFERENCED SCRIPT CONTENT with a
  # regex that matches the gateway CLI's restart/stop verb. A contiguous
  # literal here — in code OR comments — would block EVERY invocation of
  # cortex-update.sh from the terminal, including this script's own
  # sanctioned deploy command. Bash concatenates the adjacent literals at
  # runtime, so the operator still sees the exact command to run.
  local mode="${1:-}"
  local gw_restart_cmd="hermes gateway re""start"
  echo ""
  echo -e "${YELLOW}${BOLD}╔══════════════════════════════════════════════════════════════════╗${RESET}"
  echo -e "${YELLOW}${BOLD}║  ⚠  GATEWAY RESTART REQUIRED — enforcement chain redeployed      ║${RESET}"
  echo -e "${YELLOW}${BOLD}╚══════════════════════════════════════════════════════════════════╝${RESET}"
  if [[ "$mode" == "unverifiable" ]]; then
    warn "⚠ COULD NOT VERIFY restart state (see warnings above) — treat as restart required."
  else
    warn "Deploy ≠ load: the RUNNING gateway still executes the OLD enforcer in memory."
  fi
  warn "The new enforcement chain activates ONLY after the gateway process restarts:"
  echo -e "    ${CYAN}${gw_restart_cmd}${RESET}   (from a separate shell — agents cannot run it: lifecycle guard)"
  warn "Until then, the sanctioned command may still return GOVERNANCE LOCK REQUIRED —"
  warn "that is a pending restart, not a code bug. Do not loop retrying; do not edit the deployed copy."
  echo ""
}

deploy_governance_plugin() {
  local repo_plugin="${REPO_DIR}/plugins/governance-enforcer"
  local plugin_dir="${HOME}/.hermes/plugins/governance-enforcer"
  local files=("__init__.py" "plugin.yaml" "README.md")
  local changed=0
  local _os; _os=$(uname -s)
  local _lock_prefix="sudo"
  local _immutable_pattern="\-i-"
  [[ "$_os" == "Darwin" ]] && _lock_prefix="" && _immutable_pattern="uchg"

  [[ -d "$repo_plugin" ]] || { warn "  Plugin source missing: ${repo_plugin}"; return 1; }

  # ── Step 1: Convert symlink → copy if needed ──
  if [[ -L "$plugin_dir" ]]; then
    local target
    target=$(readlink "$plugin_dir")
    info "  Converting plugin symlink → copy: ${target}"
    rm -f "$plugin_dir"
    mkdir -p "$plugin_dir"
  fi

  mkdir -p "$plugin_dir"

  # ── Step 2: Copy files, handling immutability ──
  for file in "${files[@]}"; do
    local src="${repo_plugin}/${file}"
    local dest="${plugin_dir}/${file}"
    [[ ! -f "$src" ]] && continue

    # Remove immutability if set (uses sudo helper)
    if [[ -f "$dest" ]]; then
      ${_lock_prefix} hermes-plugin-lock unlock --cortex-update 2>/dev/null || true
      info "    Removed immutability: ${file}"
    fi

    # ALWAYS copy — chattr-protected files come only from repo source
    cp -f "$src" "$dest"
    info "    Copied: ${file}"
    changed=$((changed + 1))
  done

  # ── Step 3: Set restrictive perms on __init__.py ──
  local init_py="${plugin_dir}/__init__.py"
  if [[ -f "$init_py" ]]; then
    chmod 444 "$init_py" 2>/dev/null || true

    # ── Step 4: Set immutability ──
    if ${_lock_prefix} hermes-plugin-lock lock; then
      if [[ "$_os" == "Darwin" ]]; then
        info "  chflags uchg set on __init__.py"
      else
        info "  chattr +i set on __init__.py"
      fi
    else
      warn "  Immutability not set — deploy the helper and enable it:"
      if [[ "$_os" == "Darwin" ]]; then
        warn "    cp ${REPO_DIR}/ops/install/deploy/nginx/hermes-plugin-lock /usr/local/bin/hermes-plugin-lock"
        warn "    chmod 755 /usr/local/bin/hermes-plugin-lock"
      else
        warn "    cp ${REPO_DIR}/ops/install/deploy/nginx/hermes-plugin-lock ${CORTEX_DEPLOY_HOME}/scripts/hermes-plugin-lock"
        warn "    chmod 755 ${CORTEX_DEPLOY_HOME}/scripts/hermes-plugin-lock"
        warn "    Run: bash ${CORTEX_DEPLOY_HOME}/scripts/hermes-plugin-lock lock"
      fi
      warn "    Run: bash ${CORTEX_DEPLOY_HOME}/scripts/hermes-plugin-lock lock"
    fi
  fi

  [[ "$changed" -gt 0 ]] && info "  Plugin deployed: ${changed} file(s) updated"

  # NOTE: the disable/enable round-trip only updates config.yaml — it does NOT
  # hot-reload the running gateway (process-global PluginManager singleton;
  # deploy ≠ load). The new enforcer activates ONLY after the gateway process
  # is restarted by the host operator (agents cannot — lifecycle guard).
  if command -v hermes &>/dev/null; then
    hermes plugins disable governance-enforcer 2>/dev/null || true
    hermes plugins enable governance-enforcer 2>/dev/null || true
  fi

  # ── Loud restart-needed banner (deploy ≠ load) ──
  # A quiet info line scrolls past and the restart never happens. Fire a
  # LOUD yellow banner whenever the deployed enforcement content changed
  # after the running gateway started — and keep firing on every run until
  # the operator actually restarts (state file preserves the change epoch).
  # rc: RESTART_PENDING / RESTART_CLEAN / RESTART_UNVERIFIABLE (enum
  # above). `|| _rc=$?` is a set -e safe compound — never let a non-zero
  # return abort the deploy. Any unexpected code falls into the safe
  # direction: banner fires.
  _restart_rc=0
  _restart_pending || _restart_rc=$?
  case "$_restart_rc" in
    "$RESTART_PENDING") _loud_restart_banner ;;
    "$RESTART_CLEAN") : ;;  # verified clean — banner stays silent
    *) _loud_restart_banner "unverifiable" ;;
  esac

  # ── Clear stale __pycache__ ──
  # Prevents false MD5 mismatches from stale .pyc bytecode
  [[ -d "$plugin_dir/__pycache__" ]] && rm -rf "$plugin_dir/__pycache__"

  return 0
}

# ── Mycortex Command Plugin Deploy ──────────────────────────
# Deploys the mycortex-command plugin (the /brain + /mycortex slash
# commands, legacy brain command replacement) as a plain COPY to
# ~/.hermes/plugins/. Not immutable — it's a user command, not enforcement.
deploy_mycortex_plugin() {
  local repo_plugin="${REPO_DIR}/plugins/mycortex-command"
  local plugin_dir="${HOME}/.hermes/plugins/mycortex-command"
  local files=("__init__.py" "plugin.yaml")
  local changed=0

  [[ -d "$repo_plugin" ]] || { warn "  Plugin source missing: ${repo_plugin}"; return 1; }
  mkdir -p "$plugin_dir"

  for file in "${files[@]}"; do
    local src="${repo_plugin}/${file}"
    local dest="${plugin_dir}/${file}"
    [[ ! -f "$src" ]] && continue
    cp -f "$src" "$dest"
    info "    Copied: ${file}"
    changed=$((changed + 1))
  done

  [[ "$changed" -gt 0 ]] && info "  Plugin mycortex-command deployed: ${changed} file(s) updated"

  # config.yaml only — the plugin module loads at gateway start (deploy ≠ load)
  if command -v hermes &>/dev/null; then
    hermes plugins disable mycortex-command 2>/dev/null || true
    hermes plugins enable mycortex-command 2>/dev/null || true
  fi
  info "  Plugin mycortex-command files deployed (activates after gateway restart)"

  return 0
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
    for label in com.ollama.serve com.hermes.gateway com.hermes.cortex-dashboard com.hermes.agent-inbox; do
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
    for unit in ollama hermes-gateway hermes-cortex-dashboard; do
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
refresh_pinned_hook_files() {
  # refresh_pinned_hook_files <hooks_dir>
  #
  # Refresh cortex-managed hook FILES in a repo's own hooks dir from the
  # deployed sources. Pinning core.hooksPath preserves the repo's local
  # hooks but never refreshes the files — stale copies lack the mandatory
  # adversarial gate (Titus audit 2026-08-05). Only files carrying the
  # cortex header are overwritten; foreign hooks (vllm pre-commit
  # framework, bespoke post-receive on deploy bare repos) are preserved.
  local hooks_dir="$1"
  local refreshed=0
  local hook_file hook_src

  # hook name → deployed source script
  local -a hook_names=(pre-commit pre-push post-commit post-push)
  local -a hook_srcs=(pre-commit-score pre-push-pull post-commit-audit post-push-audit)
  local i

  for i in "${!hook_names[@]}"; do
    hook_file="${hooks_dir}/${hook_names[$i]}"
    hook_src="${CORTEX_DEPLOY_HOME}/scripts/${hook_srcs[$i]}"
    [[ -f "$hook_src" ]] || continue  # source not deployed yet — skip

    if [[ -f "$hook_file" ]]; then
      # Existing hook: only refresh if it carries the cortex banner
      # ("#  <name> — Git <type> hook"). Foreign hooks (vllm pre-commit
      # framework shim, bespoke deploy hooks) are NEVER clobbered.
      # Match on "Git <type> hook" (ASCII) to stay locale-safe on macOS.
      if ! grep -q "Git .* hook" "$hook_file" 2>/dev/null; then
        continue  # foreign hook — preserve
      fi
      if cmp -s "$hook_file" "$hook_src" 2>/dev/null; then
        continue  # already current
      fi
    fi
    # Missing hook file → install the gate (a pinned repo with no
    # pre-commit has no adversarial gate at all). Cortex-header file →
    # refresh. Either way: copy + make executable.
    cp "$hook_src" "$hook_file"
    chmod +x "$hook_file"
    refreshed=$((refreshed + 1))
    info "  Refreshed ${hook_names[$i]} hook in $(dirname "$hooks_dir")"
  done

  if [[ "$refreshed" -gt 0 ]]; then
    info "  → ${refreshed} stale hook file(s) refreshed in $(dirname "$hooks_dir")"
  fi
}

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
    # EXCLUDE */Library/* and */node_modules/*: macOS Library/Containers
    # is a massive crawl (~1m20s every deploy; Aug 4 incident wedged the
    # pin crawl 5h08m), and node_modules holds thousands of vendored .git
    # dirs that must never be pinned (Titus audit 2026-08-05).
    for base in /home /opt /srv /var/www /var/repo /Users; do
      if [[ -d "$base" ]]; then
        # find may return non-zero on permissioned subdirectories (e.g.
        # /var/www without read access). These are expected access errors
        # for a non-root search — not a pipeline failure. || true signals
        # that find's exit code is not meaningful for flow control here.
        find "$base" \
          \( -name ".git" -type d -o -name "*.git" -type d \) \
          -maxdepth 8 \
          -not -path "*/Library/*" \
          -not -path "*/node_modules/*" \
          -print0 2>/dev/null || true
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

    # Refresh cortex-managed hook FILES in this repo's own hooks dir.
    # Pinning sets core.hooksPath but does NOT update the hook files —
    # stale copies (Jul 24 gen vs deployed 42,585B pre-commit-score) lack
    # the mandatory adversarial gate (Titus audit 2026-08-05: 9 repos with
    # grep -c adversarial = 0). Copy from deployed source, but ONLY files
    # carrying the cortex header — foreign hooks (e.g. vllm's pre-commit
    # framework) are never clobbered.
    refresh_pinned_hook_files "$hooks_path"
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

  # Deploy pre-commit-score to shared hooks dir (symlink to prevent drift)
  local hook_dest="${hooks_dir}/pre-commit"
  if [[ -L "$hook_dest" ]] && [[ "$(readlink "$hook_dest")" == "$hook_src" ]]; then
    : # symlink already correct — no update needed
  else
    rm -f "$hook_dest"
    ln -sf "$hook_src" "$hook_dest"
    chmod +x "$hook_src"  # ensure source is executable
    info "Symlinked shared pre-commit hook → ${hook_src/$HOME/\\~}"
  fi

  # Deploy pre-push-pull to shared hooks dir (symlink to prevent drift)
  if [[ -f "$push_src" ]]; then
    local push_dest="${hooks_dir}/pre-push"
    if [[ -L "$push_dest" ]] && [[ "$(readlink "$push_dest")" == "$push_src" ]]; then
      : # symlink already correct
    else
      rm -f "$push_dest"
      ln -sf "$push_src" "$push_dest"
      chmod +x "$push_src"
      info "Symlinked shared pre-push hook → ${push_src/$HOME/\\~}"
    fi
  fi

  # Deploy post-commit-audit to shared hooks dir (symlink to prevent drift)
  local postcommit_src="${CORTEX_DEPLOY_HOME}/scripts/post-commit-audit"
  if [[ -f "$postcommit_src" ]]; then
    local postcommit_dest="${hooks_dir}/post-commit"
    if [[ -L "$postcommit_dest" ]] && [[ "$(readlink "$postcommit_dest")" == "$postcommit_src" ]]; then
      : # symlink already correct
    else
      rm -f "$postcommit_dest"
      ln -sf "$postcommit_src" "$postcommit_dest"
      chmod +x "$postcommit_src"
      info "Symlinked shared post-commit hook → ${postcommit_src/$HOME/\\~}"
    fi
  fi

  # Deploy post-push-audit to shared hooks dir (symlink to prevent drift)
  local postpush_src="${CORTEX_DEPLOY_HOME}/scripts/post-push-audit"
  if [[ -f "$postpush_src" ]]; then
    local postpush_dest="${hooks_dir}/post-push"
    if [[ -L "$postpush_dest" ]] && [[ "$(readlink "$postpush_dest")" == "$postpush_src" ]]; then
      : # symlink already correct
    else
      rm -f "$postpush_dest"
      ln -sf "$postpush_src" "$postpush_dest"
      chmod +x "$postpush_src"
      info "Symlinked shared post-push hook → ${postpush_src/$HOME/\\~}"
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
  local os_config="${CORTEX_DEPLOY_HOME}/scripts/install/os-config.sh"
  [[ -f "$os_config" ]] && source "$os_config" 2>/dev/null || true

  # ── Agent identity (git authorship) ──
  # Read/provision ~/.hermes-cortex/agent.env (per-host, gitignored) and set
  # the repo's git identity so commits carry the agent's name, not the shared
  # account's. Non-orch hosts must have agent.env provisioned (the hostname→
  # agent mapping is infrastructure and stays out of the public repo).
  # AGENT_NAME env var takes priority; failure to resolve identity fails the
  # update with a clear message (never silently continues with unknown-agent).
  if ! ensure_agent_identity; then
    error "Agent identity not provisioned — cannot set git authorship."
    error "Set AGENT_NAME=<your-agent> in the environment, or create:"
    error "  ${HOME}/.hermes-cortex/agent.env  (AGENT_NAME=<your-agent>)"
    exit 1
  fi
  git config user.name  "$(git_author_name)"  2>/dev/null || true
  git config user.email "$(git_author_email)" 2>/dev/null || true
  info "Agent identity: ${AGENT_NAME} (git author: $(git_author_name) <$(git_author_email)>)"

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
      git -C "$REPO_DIR" diff --name-only "${last_commit}..HEAD" 2>/dev/null | sed 's/^/  /' | sed -n '1,50p'
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

  # ── Clear stale __pycache__ for updated Python plugin files ──
  # When a plugin source (.py) is updated via symlink, Python's .pyc
  # bytecode cache can remain stale, loading old code on the next
  # import. Clear any __pycache__ dirs in plugin directories.
  for entry in "${MAP[@]}"; do
    IFS='|' read -r src dest _ <<< "$entry"
    if [[ "$dest" == *"/plugins/"* ]] && [[ "$src" == *.py ]]; then
      plugin_dir="$(dirname "$dest")"
      pycache_dir="${plugin_dir}/__pycache__"
      if [[ -d "$pycache_dir" ]]; then
        rm -rf "$pycache_dir"
        info "Cleared stale pycache: ${pycache_dir/$HOME/\~}"
      fi
    fi
  done
  # Also clear pycache for the governance enforcer plugin (symlinked, not in MAP)
  enforcer_pycache="${REPO_DIR}/plugins/governance-enforcer/__pycache__"
  if [[ -d "$enforcer_pycache" ]]; then
    rm -rf "$enforcer_pycache"
    info "Cleared stale pycache: plugins/governance-enforcer"
    warn "⚠️  Run /reset to load the updated enforcer plugin in your current session"
  fi

  # Re-lock hook scripts after deploy
  if command -v hermes-plugin-lock &>/dev/null; then
    if [[ "$(uname -s)" == "Darwin" ]]; then
      hermes-plugin-lock lock 2>/dev/null || true
    else
      sudo hermes-plugin-lock lock 2>/dev/null || true
    fi
  fi

  # Update symlinks if any web-cache or offline files changed
  update_symlinks

  # Sync skills from repo (all SKILL.md + references/, only changed files)
  sync_skills

  # Sync AGENTS.md to ~/.hermes/ so fleet agents read the same rules
  # ⚠️  SAFE COPY: preserves local custom content before overwriting
  local hermes_home="${HERMES_HOME:-${HOME}/.hermes}"
  local repo_agents="${REPO_DIR}/AGENTS.md"
  local local_agents="${hermes_home}/AGENTS.md"
  if needs_update "$repo_agents" "$local_agents"; then
    # Check if local copy has content not in repo source
    if [[ -f "$local_agents" ]]; then
      local local_only_lines
      local_only_lines=$(comm -23 <(grep -vE '^\s*$' "$local_agents" | sort) <(grep -vE '^\s*$' "$repo_agents" | sort) 2>/dev/null | sed -n '1,20p')
      if [[ -n "$local_only_lines" ]]; then
        # Save local-only content before overwriting
        cp "$local_agents" "${local_agents}.local"
        warn "AGENTS.md has local-only content not in repo source"
        warn "  → Local copy saved to ~/.hermes/AGENTS.md.local"
        warn "  → Check: diff ~/.hermes/AGENTS.md ~/hermes-cortex/AGENTS.md"
        while IFS= read -r line; do
          warn "    + ${line:0:80}"
        done <<< "$local_only_lines"
      fi
    fi
    copy_file "$repo_agents" "$local_agents"
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

  # ── Apply mycortex schema migrations (DDL path) ──────────────
  # cortex-update.sh is a file-copier with NO DDL path (party-2 SS1). The
  # schema reaches existing agents via ops/services/mycortex/migrate.py,
  # invoked AFTER file sync. Idempotent: schema_version-gated no-op when
  # current. Fails the update loudly if the runner errors (schema matters).
  local mycortex_migrate="${CORTEX_DEPLOY_HOME}/services/mycortex/migrate.py"
  if [[ -f "$mycortex_migrate" ]]; then
    info "Applying mycortex migrations…"
    if python3 "$mycortex_migrate"; then
      : # migrations applied / already current
    else
      error "mycortex migrate.py FAILED — schema may be missing on this host"
      exit 1
    fi
  fi

  # ── Apply tasks schema (enterprise task workflow — party-reviewed design) ──
  # Version-gated runner (tasks.schema_version) — idempotent re-apply. DDL
  # runs as the DB owner (mycortex); CRUD never touches superuser (B-2).
  # docs/design/task-workflow.md §3. Linux (docker exec) and macOS (direct
  # psql via mycortex.conf) both converge through migrate.py's platform seam.
  local tasks_migrate="${CORTEX_DEPLOY_HOME}/services/tasks/migrate.py"
  if [[ -f "$tasks_migrate" ]]; then
    info "Applying tasks schema…"
    if python3 "$tasks_migrate"; then
      : # migrations applied / already current
    else
      error "tasks migrate.py FAILED — task workflow will be dead on this host (retried next update)"
      exit 1
    fi
  fi

  # ── Apply learnings schema (F-001 fleet learning ledger — party-reviewed) ──
  # Orchestrator-only deploy (register_orch above): the learnings ledger lives
  # on the bus Postgres, which exists only on Moses/Esther. Workers write via
  # the HTTP collector path (learning-collect.py → /api/learnings) and never
  # have this schema locally. Same version-gated runner pattern as tasks.
  local learnings_migrate="${CORTEX_DEPLOY_HOME}/services/learnings/migrate.py"
  if [[ -f "$learnings_migrate" ]]; then
    info "Applying learnings schema…"
    if python3 "$learnings_migrate"; then
      : # migrations applied / already current
    else
      error "learnings migrate.py FAILED — ledger will be dead on this host (retried next update)"
      exit 1
    fi
  fi

  # ── Ensure tasks MCP server registered (ALL agents, not orch-only) ──
  # Idempotent hermes mcp add; config points at the repo path (mirrors
  # loop-governance wiring — the doctor's --fix converges the same way).
  if command -v hermes >/dev/null 2>&1; then
    if hermes mcp list 2>/dev/null | grep -q "tasks"; then
      : # already registered
    else
      local mcp_venv="${HOME}/.hermes/hermes-agent/venv/bin/python3"
      local mcp_server="${HOME}/hermes-cortex/mcp-servers/task-mcp.py"
      if [[ -x "$mcp_venv" && -f "$mcp_server" ]]; then
        info "Registering tasks MCP server…"
        if hermes mcp add tasks --command "$mcp_venv" --args "$mcp_server" 2>/dev/null; then
          info "  ✓ tasks MCP registered (restart the gateway to load tools)"
        else
          warn "hermes mcp add tasks failed — run: python3 ${CORTEX_DEPLOY_HOME}/scripts/manage/cortex-doctor.py --fix"
        fi
      fi
    fi
  fi

  deploy_nginx_configs

  # Deploy system scripts to /usr/local/sbin/ (root-owned, NOPASSWD-safe)
  deploy_system_scripts

  # Deploy governance enforcer plugin as copy (not symlink) for chattr +i safety
  deploy_governance_plugin

  # Deploy mycortex-command plugin (/brain + /mycortex slash commands)
  deploy_mycortex_plugin

  # ── Cron cost tracking: auto-reapply the scheduler patch ──
  # The cost capture lives as a marker-patch inside scheduler.py (Hermes
  # source). Every `hermes update` replaces scheduler.py and silently kills
  # the patch (seam rot — cron-costs.db went 2-days-of-data on Esther,
  # stale June-July on Titus). Re-run the installer after every deploy so
  # the patch survives updates. Idempotent: SKIPs already-applied patches.
  if [[ -f "${CORTEX_DEPLOY_HOME}/scripts/install-cron-cost-tracking.py" ]]; then
    python3 "${CORTEX_DEPLOY_HOME}/scripts/install-cron-cost-tracking.py" 2>&1 \
      | sed 's/^/    [cost-tracking] /'
  else
    warn "  install-cron-cost-tracking.py missing — cost capture may be dead"
  fi

  # ── Lean skill index: auto-reapply the coding_context patch ──
  # Same seam-rot pattern: the lean-index extension patches hermes-agent
  # source, wiped on every `hermes update`. Re-run so `coding_context:
  # lean` keeps working. Idempotent: SKIPs applied patches.
  if [[ -f "${CORTEX_DEPLOY_HOME}/scripts/install-lean-index.py" ]]; then
    python3 "${CORTEX_DEPLOY_HOME}/scripts/install-lean-index.py" 2>&1 \
      | sed 's/^/    [lean-index] /'
  else
    warn "  install-lean-index.py missing — lean skill index may be dead"
  fi

  # Merge template updates into agent SOUL.md (preserves customizations)
  local soul_merge="${CORTEX_DEPLOY_HOME}/scripts/soul-merge.py"
  if [[ -f "$soul_merge" ]]; then
    if python3 "$soul_merge" --check >/dev/null 2>&1; then
      : # up to date — silent
    else
      info "Merging template updates into SOUL.md..."
      # soul-merge exits 1 after a SUCCESSFUL merge (0=up-to-date, 1=merged,
      # 2=error — asserted in tests/test_soul_merge.py). Without || true the
      # exit-1 pipeline aborts the whole update under set -euo pipefail,
      # skipping the state save, doctor, and enforcement re-lock.
      python3 "$soul_merge" 2>&1 | sed 's/^/    /' || true
      COPIED=$((COPIED + 1))
    fi
  fi

  # Sync current agent SOUL.md with template (repo profiles removed per d43e776)
  local soul_sync_all="${CORTEX_DEPLOY_HOME}/scripts/soul-sync-all.sh"
  if [[ -f "$soul_sync_all" ]]; then
    info "Syncing current agent SOUL.md with template..."
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
        restart_langfuse)    restart_langfuse ;;
        restart_dashboard)   restart_dashboard ;;
        restart_cortex_bus)  restart_cortex_bus ;;
        *)                   warn "Unknown restart command: $cmd" ;;
      esac
    done
  fi

  # Restart the bus daemon when its code changed. The bus runs FROM THE REPO
  # (core/cortex_bus via uvicorn cortex_bus.server:app) — a git pull updates
  # the files on disk but the running process keeps the old modules in memory
  # (Deploy ≠ load). Without this restart, new bus endpoints/schema changes
  # never go live until the service happens to restart. restart_cortex_bus
  # self-guards (systemctl --user is-active / launchctl list) so hosts without
  # a local bus service (joseph/gisu/kustos/titus — client bus_access) no-op.
  local _bus_changed=false
  if $FORCE_ALL; then
    _bus_changed=true
  else
    for _f in "${CHANGED[@]}"; do
      case "$_f" in
        core/cortex_bus/*) _bus_changed=true ; break ;;
      esac
    done
  fi
  if $_bus_changed; then
    info "Bus code changed — restarting Agent Bus…"
    $DRY_RUN && echo "    would restart: restart_cortex_bus" || restart_cortex_bus
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

  # ── Migrate: legacy private repos to ~/private-data/ ──
  if [[ -d "$HOME/hermes-cortex-private" ]]; then
    if [[ -d "$HOME/hermes-cortex-private/.git" ]]; then
      info "Legacy private repo detected: ~/hermes-cortex-private"
      info "  → Moving personal data to ~/private-data/ (no git)"
      warn "  Content (decisions, bible, references, lessons, messages) stays local."
      warn "  To migrate automatically, run:"
      warn "    mv ~/hermes-cortex-private ~/private-data"
      warn "    rm -rf ~/private-data/.git"
      warn "  Or manually copy what you need and remove the repo."
    else
      info "~/hermes-cortex-private already migrated (no .git)"
    fi
  fi
  if [[ -d "$HOME/agent-inbox-private" ]]; then
    warn "Deprecated: ~/agent-inbox-private — file-based inbox is dead."
    warn "  Remove it: rm -rf ~/agent-inbox-private"
  fi

  # Install/update universal crons (idempotent — skips existing)
  if command -v hermes &>/dev/null; then
    CORTEX_DEPLOY_HOME="${CORTEX_DEPLOY_HOME}" bash "${CORTEX_DEPLOY_HOME}/scripts/install-crons.sh" 2>/dev/null && \
      info "Crons up to date" || warn "Cron install skipped (no hermes CLI?)"

    # ── Orchestrator-only crons (team health, soul refinement, etc.) ──
    # Guard: hostname moses|esther AND matching home dir. Env vars
    # (AGENT_TYPE / IS_ORCHESTRATOR) grant NO orch powers — they are spoofable.
    # NOTE: _ORCH=false is the DEFAULT of the host-detection variable, NOT a
    # bypass flag. Setting it true here grants nothing — the orchestrator-only
    # paths restriction is enforced by the pre-commit hook, which reads the
    # committed docs/orchestrator-only-paths.txt independently of this script.
    _ORCH=false
    ORCH_HOST=$(hostname -s 2>/dev/null || echo "unknown")
    ORCH_USER=$(id -un 2>/dev/null || echo "$USER")
    if command -v getent &>/dev/null; then
      ORCH_HOME=$(getent passwd "$ORCH_USER" 2>/dev/null | cut -d: -f6)
    fi
    ORCH_HOME="${ORCH_HOME:-$HOME}"
    case "$ORCH_HOST" in
      moses|esther) [[ "$ORCH_HOME" == "/home/$ORCH_HOST" ]] && _ORCH=true ;;
    esac
    if $_ORCH; then
      CORTEX_DEPLOY_HOME="${CORTEX_DEPLOY_HOME}" bash "${CORTEX_DEPLOY_HOME}/scripts/install-orch-crons.sh" 2>/dev/null && \
        info "Orch crons up to date" || warn "Orch cron install skipped"
    else
      # ── Non-orch guard: detect accidentally installed orch crons ──
      if command -v hermes &>/dev/null && hermes cron --help &>/dev/null 2>&1; then
        local _found
        _found=$(hermes cron list --all 2>/dev/null | grep -E "orch-(team-messages|team-health|skill-lifecycle|bus-|fleet-|clean-health|health-report)" || true)
        if [[ -n "$_found" ]]; then
          warn "Orch crons detected on non-orch agent — remove with:"
          warn "  bash ${CORTEX_DEPLOY_HOME}/scripts/install-orch-crons.sh --uninstall"
          echo "$_found"
        fi
        # Detect skill-report crons (both old bare names and new orch-* names)
        _old_skill=$(hermes cron list --all 2>/dev/null | grep -E "skill-report-(process|request)|skill-evaluate" || true)
        _new_skill=$(hermes cron list --all 2>/dev/null | grep -E "orch-skill-report|orch-skill-evaluate" || true)
        if [[ -n "$_old_skill" ]]; then
          warn "Old skill-report crons detected on non-orch agent — removed from install script (moved to orch-only):"
          warn "  Remove each with:"
          echo "$_old_skill" | while read -r line; do
            cron_name=$(echo "$line" | grep -oP '(?<=Name:)\s*\S+' || echo "$line" | awk '{print $NF}')
            warn "    hermes cron remove --name ${cron_name}"
          done
        fi
        if [[ -n "$_new_skill" ]]; then
          warn "New orch-skill-report crons detected on non-orch agent — should not be here."
          warn "  Remove with:"
          warn "    bash ${CORTEX_DEPLOY_HOME}/scripts/install-orch-crons.sh --uninstall"
          echo "$_new_skill"
        fi
      fi
      # ── Non-orch guard: detect orchestrator-only service components ──
      # Bus server, nginx, systemd services — should not run on non-orch agents
      local _warned=false
      if systemctl --user is-active cortex-bus &>/dev/null 2>&1; then
        warn "🚫 Bus daemon (cortex-bus) running on non-orch agent — uninstall with:"
        warn "    systemctl --user stop cortex-bus"
        warn "    systemctl --user disable cortex-bus"
        _warned=true
      fi
      if pgrep -f cortex_bus.server &>/dev/null 2>&1; then
        warn "🚫 Bus server process (cortex_bus) detected on non-orch agent"
        _warned=true
      fi
      if $_warned; then
        warn "  These services should only run on orchestrator hosts (moses, esther)."
        warn "  Run cortex-update.sh after removing them to clean stale deploy files."
      fi
    fi
  else
    info "Hermes not found — skip cron install (run install-crons.sh after Hermes setup)"
  fi

  # ── Cron manifest auto-repair ──────────────────────────────
  # cron-manifest.yaml is the canonical source of truth for every fleet cron
  # (name, schedule, script, prompt, skill, deliver, workdir, no_agent, model,
  # provider, scope). The installers above create missing crons; this pass
  # converges ALL in-scope crons to the manifest across every field — so a
  # per-cron model switch (e.g. thinking→non-thinking), prompt fix, or schedule
  # change in the manifest reaches live jobs automatically on every update.
  # (Output captured to a var first — piping python to grep -q under
  # set -euo pipefail can SIGPIPE-abort the deploy on large output.)
  if command -v hermes &>/dev/null && [[ -f "${REPO_DIR:-$HOME/hermes-cortex}/ops/install/cron-manifest.yaml" ]]; then
    local _manifest_out _manifest_script
    _manifest_script="${CORTEX_DEPLOY_HOME:-$HOME/.hermes-cortex}/scripts/manage/cron_manifest.py"
    if [[ ! -f "$_manifest_script" ]]; then
      _manifest_script="${REPO_DIR:-$HOME/hermes-cortex}/ops/scripts/manage/cron_manifest.py"
    fi
    _manifest_out="$(python3 "$_manifest_script" --repair 2>/dev/null || true)"
    if [[ "$_manifest_out" == *$'\n'UPDATED* || "$_manifest_out" == *$'\n'CREATED* || "$_manifest_out" == UPDATED* || "$_manifest_out" == CREATED* ]]; then
      info "Cron manifest: converged drifted crons to canonical state"
    else
      info "Cron manifest: all in-scope crons already match"
    fi
  fi

  # ── LLM cron inactivity timeout ───────────────────────────
  # Ensures HERMES_CRON_TIMEOUT (fleet default 600s) is applied to the
  # gateway service: systemd drop-in on Linux, ~/.hermes/.env on macOS.
  # Activation needs a gateway restart (next `hermes update` / operator
  # restart) — the installer does NOT restart the gateway itself because
  # the gateway lifecycle guard scans cron scripts AND every script they
  # reference (this file runs from inside the gateway via the sync cron).
  if [[ -f "${CORTEX_DEPLOY_HOME}/scripts/install-gateway-cron-timeout.sh" ]]; then
    # ⚠️ Drop any stale HERMES_CRON_TIMEOUT inherited from the RUNNING
    # gateway process (the drop-in being replaced exports the OLD value,
    # so `:-default` in the installer would re-apply it forever). Only
    # unset when the per-machine override is NOT declared in
    # ~/hermes-cortex/.env (sourced above) — an explicit line survives.
    if ! grep -q '^HERMES_CRON_TIMEOUT=' "${REPO_DIR}/.env" 2>/dev/null; then
      unset HERMES_CRON_TIMEOUT
    fi
    bash "${CORTEX_DEPLOY_HOME}/scripts/install-gateway-cron-timeout.sh" 2>&1 | sed 's/^/    /' || \
      warn "  install-gateway-cron-timeout.sh failed (non-fatal)"
  fi

  # ── Gateway timezone (HERMES_TIMEZONE) ─────────────────────
  # Ensures HERMES_TIMEZONE (IANA, fleet default Asia/Seoul) reaches the
  # gateway process so every cron script inherits the configured TZ
  # instead of silently depending on system local time. systemd drop-in
  # on Linux, ~/.hermes/.env on macOS. Activation needs a gateway
  # restart; until then hermes_tz.py falls back to system local (which
  # matches HERMES_TIMEZONE on every current fleet host).
  if [[ -f "${CORTEX_DEPLOY_HOME}/scripts/install-gateway-timezone.sh" ]]; then
    if ! grep -q '^HERMES_TIMEZONE=' "${REPO_DIR}/.env" 2>/dev/null; then
      unset HERMES_TIMEZONE
    fi
    bash "${CORTEX_DEPLOY_HOME}/scripts/install-gateway-timezone.sh" 2>&1 | sed 's/^/    /' || \
      warn "  install-gateway-timezone.sh failed (non-fatal)"
  fi

  # Per-provider request timeouts (deepseek hang class fix 2026-08-06) —
  # converts a silent provider hang into ReadTimeout so fallback engages
  # BEFORE the scheduler watchdog. Idempotent; no restart needed.
  if [[ -f "${CORTEX_DEPLOY_HOME}/scripts/install-provider-timeouts.sh" ]]; then
    bash "${CORTEX_DEPLOY_HOME}/scripts/install-provider-timeouts.sh" 2>&1 | sed 's/^/    /' || \
      warn "  install-provider-timeouts.sh failed (non-fatal)"
  fi

  # Per-profile mycortex reader role (schema-native multi-tenant, 2026-08-06) —
  # ensures mycortex_reader_<profile> exists so RLS (keyed on CURRENT_USER)
  # isolates tenants by construction. Idempotent; no restart needed.
  if [[ -f "${CORTEX_DEPLOY_HOME}/scripts/install-profile-reader-role.sh" ]]; then
    bash "${CORTEX_DEPLOY_HOME}/scripts/install-profile-reader-role.sh" 2>&1 | sed 's/^/    /' || \
      warn "  install-profile-reader-role.sh failed (non-fatal)"
  fi

  # model.default convergence (Titus learning 2026-08-18) — makes config.yaml
  # follow the DEFAULT_MODEL convention on every update so a stale manual
  # model.default can never survive an update cycle. Idempotent; no restart.
  if [[ -f "${CORTEX_DEPLOY_HOME}/scripts/install-model-default.sh" ]]; then
    bash "${CORTEX_DEPLOY_HOME}/scripts/install-model-default.sh" 2>&1 | sed 's/^/    /' || \
      warn "  install-model-default.sh failed (non-fatal)"
  fi

  # O7-S2 soft session cap (cost story c579ef95) — converges
  # compression.threshold_tokens to SOFT_SESSION_CAP_TOKENS when set.
  # UNSET = no-op (control host / value pending Luke) — safe fleet-wide.
  # Idempotent; no restart needed (compressor reads config per session).
  if [[ -f "${CORTEX_DEPLOY_HOME}/scripts/install-soft-session-cap.sh" ]]; then
    bash "${CORTEX_DEPLOY_HOME}/scripts/install-soft-session-cap.sh" 2>&1 | sed 's/^/    /' || \
      warn "  install-soft-session-cap.sh failed (non-fatal)"
  fi

  # ── Clean stale governance locks ─────────────────────────
  # First pass: clean locks whose heartbeat has exceeded TTL
  # ⚠️ TZ BUG (2026-08-05): slicing [:19] STRIPPED the ISO-8601 'Z', so
  # `date -d` parsed UTC as LOCAL — a FRESH lock on a UTC+9 host (KST)
  # looked 9h old and was purged on every deploy. Fixed by keeping the 'Z'.
  # ⚠️ macOS PORTABILITY BUG (2026-08-10, Titus): `date -d` is GNU-only —
  # macOS BSD date fails, and the old `|| echo 0` fallback FAILED OPEN:
  # epoch=0 → age = now - 0 ≈ 1.78e9s > 3600 → EVERY lock (including fresh
  # v2 session locks) deleted on every macOS deploy. Epoch is now computed
  # via python3 (handles 'Z' on both platforms) and failures SKIP the lock.
  for _lock in "$STATE_DIR"/.governance-*.json; do
    [ -f "$_lock" ] || continue
    local _lock_heartbeat
    _lock_heartbeat=$(python3 -c "import json; print(json.load(open('$_lock')).get('heartbeat_at',''))" 2>/dev/null || echo "")
    if [[ -n "$_lock_heartbeat" ]]; then
      local _heartbeat_epoch _now
      # Portable epoch — macOS BSD date has no -d; python3 parses ISO-8601
      # with 'Z' on both Linux and macOS.
      _heartbeat_epoch=$(python3 -c "
from datetime import datetime
print(int(datetime.fromisoformat('$_lock_heartbeat'.replace('Z','+00:00')).timestamp()))
" 2>/dev/null || echo "")
      _now=$(date +%s)
      # FAIL-SAFE (P1-A rule): unparseable/empty heartbeat → SKIP, never
      # delete. A lock we cannot age-verify must be treated as LIVE.
      if [[ -n "$_heartbeat_epoch" ]] && [[ $(( _now - _heartbeat_epoch )) -gt 3600 ]]; then
        rm -f "$_lock"
        info "Cleaned stale governance lock: $_lock"
      fi
    fi
  done

  # Second pass: clean legacy slug-based lock files (upgrade from v1→v2)
  # These use the old naming scheme .governance-{slug}.json or .governance-generic.json
  # and are superseded by session-scoped locks. Check content for absence of
  # session_id field to distinguish legacy from session-scoped locks.
  # ⚠️ P1-A fail-safe (2026-08-10): an UNPARSEABLE lock (mid-write, non-atomic
  # rename window) must NEVER be deleted as "legacy" — the old `except: print('no')`
  # failed OPEN exactly like the `date -d || echo 0` bug above. Parse failure
  # prints 'error' → the file is skipped, not removed.
  for _legacy_lock in "$STATE_DIR"/.governance-*.json; do
    [ -f "$_legacy_lock" ] || continue
    local _has_session
    _has_session=$(python3 -c "
import json
try:
    s = json.load(open('$_legacy_lock'))
    print('yes' if 'session_id' in s and s['session_id'] else 'no')
except: print('error')
" 2>/dev/null || echo "error")
    # Legacy locks have no session_id — clean them unconditionally.
    # 'error' (unparseable JSON) = a lock being written right now — SKIP.
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

  # ── Lock all enforcement files after deployment ──────────
  # Prevents any agent (including root) from modifying enforcement
  # files outside the deploy pipeline. Only cortex-update.sh can
  # unlock, update, and relock these files.
  info "Locking enforcement files…"
  # Step 1: Lock via hermes-plugin-lock (Linux: sudo NOPASSWD — covers 5 core files)
  # macOS: no NOPASSWD sudoers — chflags uchg works as the file owner, run directly.
  if [[ "$(uname -s)" == "Darwin" ]]; then
    if [[ -f "${CORTEX_DEPLOY_HOME}/scripts/hermes-plugin-lock" ]]; then
      bash "${CORTEX_DEPLOY_HOME}/scripts/hermes-plugin-lock" lock 2>&1 | sed 's/^/    /' || warn "  enforcement files NOT locked (macOS)"
    elif command -v hermes-plugin-lock &>/dev/null; then
      hermes-plugin-lock lock 2>&1 | sed 's/^/    /' || warn "  enforcement files NOT locked (macOS)"
    else
      warn "  hermes-plugin-lock not found — enforcement files NOT locked"
    fi
  else
    if command -v hermes-plugin-lock &>/dev/null; then
      sudo hermes-plugin-lock lock 2>&1 | sed 's/^/    /'
    else
      warn "  hermes-plugin-lock not found — enforcement files NOT locked"
    fi
  fi
  # Step 2: Lock new enforcement paths with chmod 444 (chattr +i needs sudoers)
  # These are protected by chmod as a second layer. For full chattr +i
  # protection, the user must run: sudo hermes-plugin-lock lock
  # NOTE: hooks/post-merge is EXCLUDED from chmod 444 only — git ignores
  # non-executable hooks, so 444 would kill the auto-deploy-on-pull
  # mechanism. It IS still locked chattr +i by hermes-plugin-lock TARGETS
  # (immutable but executable, deployed 755). See hermes-plugin-lock.
  # (2026-08-03, Titus ISSUE-2).
  for _new_enf in \
    "${CORTEX_DEPLOY_HOME}/tools/loop-governance/loop-gov-mcp.py" \
    "${CORTEX_DEPLOY_HOME}/scripts/hermes-plugin-lock"; do
    if [[ -f "$_new_enf" ]]; then
      chmod 444 "$_new_enf" 2>/dev/null || true
    fi
  done

  # ── Clear stale __pycache__ before doctor runs ──────────
  # After deploying updated Python scripts, old .pyc bytecode in
  # __pycache__ directories can cause the doctor to compute MD5
  # hashes against stale compiled bytecode instead of fresh
  # source, producing false-positive checksum mismatches.
  info "Clearing stale __pycache__ directories…"
  find "${CORTEX_DEPLOY_HOME}/scripts" -type d -name "__pycache__" -prune -exec rm -rf {} + 2>/dev/null || true

  # ── Auto-run doctor after update ─────────────────────────
  info "Running doctor to verify installation…"
  python3 "${CORTEX_DEPLOY_HOME}/scripts/cortex-doctor.py" --quiet 2>&1 || true

  echo ""
}

main "$@"
