#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  cron-auto-remediate.sh — Diagnostics for auto-remediation
#
#  Provides structured diagnostic output for the LLM-driven
#  cron-auto-remediate job to reason about failures and apply
#  targeted fixes. Silent when nothing to report.
#
#  Actions:
#    diagnose     — check script paths, permissions, deps
#    fix-missing  — copy missing scripts from hermes-cortex repo
#    fix-perms    — fix permissions on .hermes/scripts/
#    fix-git      — fix git state in hermes-cortex
#    fix-docker   — restart docker services
#    fix-purge    — purge system caches (memory, brew, docker)
#
#  Usage: cron-auto-remediate.sh <action>
# ─────────────────────────────────────────────────────────────
set -euo pipefail

HERMES_SCRIPTS="${HOME}/.hermes/scripts"
CORTEX_REPO="${HOME}/hermes-cortex"
CORTEX_SCRIPTS="${CORTEX_REPO}/src/scripts"
ACTION="${1:-diagnose}"

case "${ACTION}" in
  # ── Diagnose ──────────────────────────────────────────────
  diagnose)
    issues=()

    # Check script presence
    for script in heartbeat.py service-recovery.py system-alert.py \
                  check-agent-messages.sh cron-auto-remediate.sh \
                  daily-lesson-mine.sh update-session-state.sh; do
      if [ ! -f "${HERMES_SCRIPTS}/${script}" ]; then
        issues+=("MISSING:${HERMES_SCRIPTS}/${script}")
      fi
    done

    # Check cortex repo
    if [ -d "${CORTEX_REPO}" ]; then
      cd "${CORTEX_REPO}"
      # Check git health
      if ! git rev-parse --git-dir >/dev/null 2>&1; then
        issues+=("GIT:not-a-repo:${CORTEX_REPO}")
      else
        # Check for conflicts
        if git status --porcelain | grep -q "^UU"; then
          issues+=("GIT:merge-conflict:${CORTEX_REPO}")
        fi
        # Check detached HEAD
        if ! git symbolic-ref -q HEAD >/dev/null 2>&1; then
          issues+=("GIT:detached-head:${CORTEX_REPO}")
        fi
        # Check for unstaged/ uncommitted changes in scripts
        DIRTY_SCRIPTS=$(git status --porcelain -- src/scripts/ 2>/dev/null | head -5)
        if [ -n "${DIRTY_SCRIPTS}" ]; then
          issues+=("GIT:dirty-scripts:${CORTEX_REPO}")
        fi
      fi
    fi

    # Check permissions
    for script in "${HERMES_SCRIPTS}"/*.sh; do
      if [ -f "${script}" ] && [ ! -x "${script}" ]; then
        issues+=("PERMS:${script}")
      fi
    done
    for script in "${HERMES_SCRIPTS}"/*.py; do
      if [ -f "${script}" ] && [ ! -x "${script}" ]; then
        issues+=("PERMS:${script}")
      fi
    done

    # Check disk space
    DISK_PCT=$(df -h / 2>/dev/null | awk 'NR==2 {gsub(/%/,"",$5); print $5}' || echo 0)
    if [ "${DISK_PCT}" -gt 85 ] 2>/dev/null; then
      issues+=("DISK:${DISK_PCT}%")
    fi

    # Check memory free percentage (macOS only)
    # memory_pressure reports "free percentage" — flag if below 15% (high pressure)
    if command -v memory_pressure >/dev/null 2>&1; then
      MEM_FREE=$(memory_pressure 2>/dev/null | grep "System-wide memory" | sed 's/.* \([0-9]*\)%/\1%/')
      if [ -n "${MEM_FREE}" ]; then
        MEM_VAL=${MEM_FREE%\%}
        if [ "${MEM_VAL}" -lt 15 ] 2>/dev/null; then
          issues+=("MEMORY:${MEM_FREE} free — high pressure")
        fi
      fi
    fi

    # Check services
    for svc_label in com.ollama.serve com.gbrain.autopilot com.gbrain.sync-watch; do
      if launchctl list "${svc_label}" >/dev/null 2>&1; then
        PID=$(launchctl list "${svc_label}" 2>/dev/null | awk '{print $1}' || echo "-")
        if [ "${PID}" = "-" ]; then
          issues+=("SERVICE:${svc_label}:down")
        fi
      fi
    done

    # Check nginx
    if command -v nginx >/dev/null 2>&1; then
      if ! nginx -t >/dev/null 2>&1; then
        issues+=("NGINX:config-invalid")
      fi
      if ! pgrep -f "nginx: master" >/dev/null 2>&1; then
        issues+=("NGINX:not-running")
      fi
    fi

    # Check web cache
    WEB_CACHE="${HOME}/.hermes/data/web_cache.sqlite"
    if [ -f "${WEB_CACHE}" ]; then
      SIZE_MB=$(du -m "${WEB_CACHE}" 2>/dev/null | cut -f1 || echo 0)
      if [ "${SIZE_MB}" -gt 200 ] 2>/dev/null; then
        issues+=("WEB-CACHE:${SIZE_MB}MB")
      fi
    fi

    # Output structured diagnostics
    if [ ${#issues[@]} -gt 0 ]; then
      echo "ISSUES:${#issues[@]}"
      for issue in "${issues[@]}"; do
        echo "  ${issue}"
      done
    fi
    ;;

  # ── Fix missing scripts ──────────────────────────────────
  fix-missing)
    fixed=0
    for script in heartbeat.py service-recovery.py system-alert.py \
                  check-agent-messages.sh daily-lesson-mine.sh \
                  update-session-state.sh langfuse-health-watchdog.py \
                  langfuse-retention-prune.py lesson-compound-stats-brief.sh \
                  llm-judge-scorer.py memory-to-brain.py memory-compress.py \
                  web-cache-backup.sh web-cache-prune.sh; do
      if [ ! -f "${HERMES_SCRIPTS}/${script}" ] && [ -f "${CORTEX_SCRIPTS}/${script}" ]; then
        cp "${CORTEX_SCRIPTS}/${script}" "${HERMES_SCRIPTS}/${script}"
        chmod +x "${HERMES_SCRIPTS}/${script}"
        echo "RESTORED:${script}"
        fixed=$((fixed + 1))
      fi
    done
    [ "${fixed}" -gt 0 ] || echo "NONE"
    ;;

  # ── Fix permissions ───────────────────────────────────────
  fix-perms)
    chmod +x "${HERMES_SCRIPTS}"/*.sh 2>/dev/null || true
    chmod +x "${HERMES_SCRIPTS}"/*.py 2>/dev/null || true
    echo "OK"
    ;;

  # ── Fix git state ─────────────────────────────────────────
  fix-git)
    if [ -d "${CORTEX_REPO}" ]; then
      cd "${CORTEX_REPO}"
      # Fix detached HEAD
      if ! git symbolic-ref -q HEAD >/dev/null 2>&1; then
        git checkout main 2>/dev/null || git checkout master 2>/dev/null || true
      fi
      # Abort any in-progress merge
      if [ -f ".git/MERGE_HEAD" ]; then
        git merge --abort 2>/dev/null || true
      fi
      git pull --ff-only origin main 2>/dev/null || git pull --ff-only origin master 2>/dev/null || true
      echo "OK"
    else
      echo "NO-REPO"
    fi
    ;;

  # ── Fix docker ────────────────────────────────────────────
  fix-docker)
    if command -v docker >/dev/null 2>&1; then
      # Prune unused resources
      docker system prune -f --volumes 2>/dev/null || true
      echo "OK"
    else
      echo "NO-DOCKER"
    fi
    ;;

  # ── Purge caches ──────────────────────────────────────────
  fix-purge)
    actions=()

    # Memory purge (macOS only)
    if command -v purge >/dev/null 2>&1; then
      purge
      actions+=("memory")
    fi

    # Brew cleanup
    if command -v brew >/dev/null 2>&1; then
      brew cleanup -s 2>/dev/null || true
      actions+=("brew")
    fi

    # Docker prune
    if command -v docker >/dev/null 2>&1; then
      docker system prune -f 2>/dev/null || true
      actions+=("docker")
    fi

    # Log cleanup (>7 days)
    find "${HOME}/.hermes/logs" -name "*.log*" -mtime +7 -delete 2>/dev/null || true
    find "${HOME}/.hermes/cron/output" -name "*.json" -mtime +30 -delete 2>/dev/null || true

    if [ ${#actions[@]} -gt 0 ]; then
      echo "PURGED:${actions[*]}"
    else
      echo "NONE"
    fi
    ;;

  *)
    echo "usage: cron-auto-remediate.sh <diagnose|fix-missing|fix-perms|fix-git|fix-docker|fix-purge>"
    exit 1
    ;;
esac
