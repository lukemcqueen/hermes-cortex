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
#    check        — alias for diagnose
#    fix-missing  — copy missing scripts from hermes-cortex repo
#    fix-perms    — fix permissions on .hermes-cortex/scripts/
#    fix-git      — fix git state in hermes-cortex
#    fix-docker   — restart docker services
#    fix-purge    — purge system caches (memory, brew, docker)
#    fix-certs    — check and renew SSL certificates (certbot)
#
#  Usage: cron-auto-remediate.sh <action>
# ─────────────────────────────────────────────────────────────
set -euo pipefail

HERMES_SCRIPTS="${HOME}/.hermes-cortex/scripts"
CORTEX_REPO="${HOME}/hermes-cortex"
CORTEX_SCRIPTS="${CORTEX_REPO}/src/scripts"
ACTION="${1:-diagnose}"

case "${ACTION}" in
  # ── Diagnose / Check ─────────────────────────────────────
  diagnose|check)
    issues=()

    # Check script presence
    for script in service-recovery.py system-alert-watchdog.py \
                  orch-team-messages.sh cron-auto-remediate.sh \
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

    # Check memory free percentage
    # macOS: memory_pressure reports "free percentage" — flag if below 15% (high pressure)
    # Linux: free command — flag if used >85%
    if command -v memory_pressure >/dev/null 2>&1; then
      # macOS
      MEM_FREE=$(memory_pressure 2>/dev/null | grep "System-wide memory" | sed 's/.* \([0-9]*\)%/\1%/')
      if [ -n "${MEM_FREE}" ]; then
        MEM_VAL=${MEM_FREE%\%}
        if [ "${MEM_VAL}" -lt 15 ] 2>/dev/null; then
          issues+=("MEMORY:${MEM_FREE} free — high pressure")
        fi
      fi
    elif command -v free >/dev/null 2>&1; then
      # Linux
      MEM_USED=$(free | awk '/^Mem:/ {printf "%.0f", $3/$2 * 100}')
      if [ "${MEM_USED}" -gt 85 ] 2>/dev/null; then
        issues+=("MEMORY:${MEM_USED}% used — high usage")
      fi
    fi

    # Check services — platform-aware dispatch
    # macOS: launchctl
    # Linux: systemctl --user (checks autopilot which handles sync internally)
    if command -v launchctl >/dev/null 2>&1; then
      # macOS
      for svc_label in com.ollama.serve com.gbrain.autopilot; do
        if launchctl list "${svc_label}" >/dev/null 2>&1; then
          PID=$(launchctl list "${svc_label}" 2>/dev/null | awk '{print $1}' 2>/dev/null || echo "-")
          if [ "${PID}" = "-" ]; then
            issues+=("SERVICE:${svc_label}:down")
          fi
        fi
      done
    elif command -v systemctl >/dev/null 2>&1; then
      # Linux — check system-level first, then user-level
      # Ollama: system-level service on most Linux distros
      if ! systemctl is-active ollama >/dev/null 2>&1; then
        # Fallback: user-level unit
        if ! systemctl --user is-active ollama >/dev/null 2>&1; then
          issues+=("SERVICE:ollama.service:down")
        fi
      fi
      # Gbrain autopilot (handles sync, extract, embed, lint internally)
      if ! systemctl --user is-active gbrain-autopilot >/dev/null 2>&1; then
        issues+=("SERVICE:gbrain-autopilot:down")
      fi
    fi

    # Check nginx — use sudo for system-wide config test
    if command -v nginx >/dev/null 2>&1; then
      # Try sudo -n first (non-interactive), fall back to direct test
      if ! sudo -n nginx -t >/dev/null 2>&1; then
        if ! nginx -t >/dev/null 2>&1; then
          issues+=("NGINX:config-invalid")
        fi
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
    for script in service-recovery.py system-alert-watchdog.py \
                  orch-team-messages.sh daily-lesson-mine.sh \
                  update-session-state.sh langfuse-health-watchdog.py \
                  langfuse-retention-prune.py lesson-compound-stats-brief.sh \
                  llm-judge-scorer.py memory-to-brain-sync.py memory-compress.py \
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

  # ── Fix SSL certificates ──────────────────────────────────
  fix-certs)
    # SSL cert renewal — sudoers configured for gisu/kustos/joseph
    # Uses sudo -n for non-interactive sudo (NOPASSWD in sudoers)
    # Certbot runs as root via sudo, accesses /etc/letsencrypt safely
    certs_ok=0
    certs_renewed=0
    certs_expiring=0

    CERT_DIR="/etc/letsencrypt/live"
    if [ ! -d "${CERT_DIR}" ]; then
      echo "NO-CERT-DIR"
      exit 0
    fi

    for domain_dir in "${CERT_DIR}"/*/; do
      cert_file="${domain_dir}fullchain.pem"
      if [ ! -f "${cert_file}" ]; then
        continue
      fi

      # Get expiry date using openssl (cross-platform)
      expiry_date=$(openssl x509 -enddate -noout -in "${cert_file}" 2>/dev/null | cut -d= -f2)
      if [ -z "${expiry_date}" ]; then
        echo "CERT_ERROR:${domain_dir}:cannot-read-expiry"
        continue
      fi

      # Calculate days until expiry using Python (cross-platform)
      days_left=$(python3 -c "
from datetime import datetime, timezone
import sys
try:
    expiry = datetime.strptime('${expiry_date}', '%b %d %H:%M:%S %Y %Z').replace(tzinfo=timezone.utc)
    days = (expiry - datetime.now(timezone.utc)).days
    print(days)
except Exception as e:
    print(-1)
" 2>/dev/null)

      if [ "${days_left}" -lt 0 ] 2>/dev/null; then
        echo "CERT_ERROR:${domain_dir}:parse-failed"
        continue
      fi

      domain=$(basename "${domain_dir}")

      if [ "${days_left}" -lt 30 ]; then
        # Renew cert — certbot needs sudo for /etc/letsencrypt
        echo "RENEWING:${domain}:${days_left}d"
        if sudo -n certbot renew --cert-name "${domain}" --quiet 2>/dev/null; then
          certs_renewed=$((certs_renewed + 1))
          echo "RENEWED:${domain}"
        else
          # Try without sudo (might work if user has direct access)
          if certbot renew --cert-name "${domain}" --quiet 2>/dev/null; then
            certs_renewed=$((certs_renewed + 1))
            echo "RENEWED:${domain}"
          else
            echo "RENEW_FAILED:${domain}"
          fi
        fi
      else
        certs_ok=$((certs_ok + 1))
      fi
    done

    echo "CERTS_OK:${certs_ok}"
    echo "CERTS_RENEWED:${certs_renewed}"
    ;;

  # ── Fix gbrain PGLite WASM issues ───────────────────────────
  fix-gbrain)
    # PGLite WASM failures on Linux require upstream fix or engine switch
    # This action provides diagnostics and workaround options
    echo "GBRAIN_DIAGNOSTIC:"
    
    # Check gbrain installation
    if ! command -v gbrain >/dev/null 2>&1; then
      echo "  gbrain: not installed"
      exit 0
    fi
    
    # Check gbrain config
    GBRAIN_HOME="${HOME}/.gbrain"
    if [ -f "${GBRAIN_HOME}/config.toml" ]; then
      engine=$(grep -E "^engine\s*=" "${GBRAIN_HOME}/config.toml" 2>/dev/null | cut -d= -f2 | tr -d ' "')
      echo "  engine: ${engine:-pglite}"
    fi
    
    # Run gbrain doctor and capture health score
    health_output=$(gbrain doctor 2>&1 | grep "Overall health score" || echo "unknown")
    echo "  health: ${health_output}"
    
    # Check for WASM error patterns
    sync_output=$(gbrain sync --all --no-pull 2>&1 || true)
    if echo "${sync_output}" | grep -qi "pglite failed to initialize its wasm runtime"; then
      echo "  wasm_status: FAILED - PGLite WASM runtime error"
      echo "  workaround: Switch to PostgreSQL engine:"
      echo "    gbrain init --engine postgres --postgres-url 'postgresql://user:pass@host:5432/dbname'"
      echo "  upstream_issue: https://github.com/garrytan/gbrain/issues/223"
    elif echo "${sync_output}" | grep -qi "aborted.*wasm"; then
      echo "  wasm_status: FAILED - WASM aborted"
      echo "  workaround: Switch to PostgreSQL engine or upgrade glibc"
    else
      echo "  wasm_status: OK"
    fi
    ;;

  # ── Check SSL certificate permissions (SECURITY-AWARE) ───────────────────
  fix-ssl-perms)
    # SSL certs should remain at restrictive permissions (700 root:root)
    # This check verifies certbot can renew via sudoers, NOT by widening permissions
    # SECURITY: Never chmod 755/644 on SSL certs — exposes private keys
    echo "SSL_PERM_CHECK:"
    
    cert_dirs=("/etc/letsencrypt/live" "/etc/letsencrypt/archive" "/etc/letsencrypt/renewal")
    perms_ok=1
    
    for dir in "${cert_dirs[@]}"; do
      if [ -d "${dir}" ]; then
        perms=$(stat -c "%a" "${dir}" 2>/dev/null || stat -f "%Lp" "${dir}" 2>/dev/null || echo "unknown")
        if [ "${perms}" = "700" ] || [ "${perms}" = "750" ]; then
          echo "  OK: ${dir} (${perms}) — correctly restricted"
        else
          echo "  WARNING: ${dir} (${perms}) — should be 700 or 750"
          perms_ok=0
        fi
      fi
    done
    
    # Check cert files
    if [ -d "/etc/letsencrypt/live" ]; then
      for domain_dir in /etc/letsencrypt/live/*/; do
        if [ -d "${domain_dir}" ]; then
          domain=$(basename "${domain_dir}")
          for cert_file in fullchain.pem privkey.pem; do
            cert_path="${domain_dir}${cert_file}"
            if [ -f "${cert_path}" ]; then
              perms=$(stat -c "%a" "${cert_path}" 2>/dev/null || stat -f "%Lp" "${cert_path}" 2>/dev/null || echo "unknown")
              if [ "${perms}" = "600" ] || [ "${perms}" = "640" ]; then
                echo "  OK: ${cert_path} (${perms}) — correctly restricted"
              else
                echo "  WARNING: ${cert_path} (${perms}) — should be 600 or 640"
                perms_ok=0
              fi
            fi
          done
        fi
      done
    fi
    
    if [ "${perms_ok}" -eq 1 ]; then
      echo ""
      echo "  SSL cert permissions are SECURE (restrictive)."
      echo "  For non-root certbot renewal, add to sudoers (visudo):"
      echo "    ${USER} ALL=(ALL) NOPASSWD: /usr/bin/certbot renew"
      echo "    ${USER} ALL=(ALL) NOPASSWD: /usr/sbin/nginx -t"
      echo "    ${USER} ALL=(ALL) NOPASSWD: /usr/sbin/nginx -s reload"
      echo ""
      echo "  Or use certbot's built-in systemd timer (runs as root):"
      echo "    sudo systemctl enable certbot.timer"
      echo "    sudo systemctl start certbot.timer"
    else
      echo ""
      echo "  WARNING: Some SSL permissions are too permissive."
      echo "  To restore secure permissions (requires sudo):"
      echo "    sudo chmod 700 /etc/letsencrypt/live/ /etc/letsencrypt/archive/ /etc/letsencrypt/renewal/"
      echo "    sudo chmod 600 /etc/letsencrypt/live/*/fullchain.pem /etc/letsencrypt/live/*/privkey.pem"
      echo "    sudo chown root:root /etc/letsencrypt/live/*/privkey.pem"
    fi
    ;;

  # ── Check certbot lock/log permissions (SECURITY-AWARE) ──────────────────
  fix-certbot-perms)
    # Certbot lock files should remain restricted — use sudoers for non-root renewal
    # SECURITY: Do not widen lock file permissions; use sudoers or systemd timer
    echo "CERTBOT_PERM_CHECK:"
    
    lock_file="/var/log/letsencrypt/.certbot.lock"
    log_dir="/var/log/letsencrypt"
    
    # Check lock file (should be 600 or 640 root:root — this is CORRECT)
    if [ -f "${lock_file}" ]; then
      perms=$(stat -c "%a" "${lock_file}" 2>/dev/null || echo "unknown")
      owner=$(stat -c "%U" "${lock_file}" 2>/dev/null || echo "unknown")
      if [ "${owner}" = "root" ]; then
        echo "  OK: ${lock_file} (${perms}, ${owner}) — correctly restricted"
        echo "  For non-root certbot, add to sudoers instead of changing permissions."
      else
        echo "  WARNING: ${lock_file} owned by ${owner} — should be root"
      fi
    fi
    
    # Check log directory
    if [ -d "${log_dir}" ]; then
      owner=$(stat -c "%U" "${log_dir}" 2>/dev/null || echo "unknown")
      if [ "${owner}" = "root" ]; then
        echo "  OK: ${log_dir} (owner: ${owner}) — correctly restricted"
      else
        echo "  INFO: ${log_dir} owned by ${owner}"
      fi
    fi
    
    echo ""
    echo "  SECURE APPROACH: Keep restrictive permissions, use sudoers for renewal:"
    echo "    sudo visudo"
    echo "    Add: ${USER} ALL=(ALL) NOPASSWD: /usr/bin/certbot renew --non-interactive"
    echo ""
    echo "  ALTERNATIVE: Use certbot's systemd timer (runs as root automatically):"
    echo "    sudo systemctl enable certbot.timer"
    echo "    sudo systemctl start certbot.timer"
    echo "    # Timer runs /usr/lib/systemd/system/certbot.service as root"
    ;;

  *)
    echo "usage: cron-auto-remediate.sh <diagnose|check|fix-missing|fix-perms|fix-git|fix-docker|fix-purge|fix-certs|fix-gbrain|fix-ssl-perms|fix-certbot-perms>"
    echo ""
    echo "Actions:"
    echo "  diagnose        — check script paths, permissions, deps"
    echo "  check           — alias for diagnose"
    echo "  fix-missing     — copy missing scripts from hermes-cortex repo"
    echo "  fix-perms       — fix permissions on .hermes-cortex/scripts/"
    echo "  fix-git         — fix git state in hermes-cortex"
    echo "  fix-docker      — restart docker services"
    echo "  fix-purge       — purge system caches (memory, brew, docker)"
    echo "  fix-certs       — check and renew SSL certificates (certbot)"
    echo "  fix-gbrain      — diagnose gbrain/PGLite WASM issues"
    echo "  fix-ssl-perms   — check SSL cert permissions (reports what needs sudo)"
    echo "  fix-certbot-perms — check certbot lock/log permissions"
    exit 1
    ;;
esac
