#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  install-nginx-full.sh — One-shot nginx full deploy script
#
#  Installs: nginx configs, SSL certs, blocked IPs, fail2ban filter.
#  Used for fresh installs and full deploys (NOT the daily pipeline).
#  Atomic: validates before reloading. Safe to re-run.
#
#  Sources:
#    ~/hermes-cortex/deploy/nginx/blocked_ips.add   (IPs to block)
#    ~/hermes-cortex/deploy/nginx/nginx-badbots.conf (fail2ban filter)
#
#  Targets: (OS-aware — derived from uname -s)
#    Linux:    /etc/nginx/              (nginx configs)
#              /etc/fail2ban/filter.d/   (fail2ban filter)
#    macOS x86_64: /usr/local/etc/nginx/
#    macOS arm64:  /opt/homebrew/etc/nginx/
#
#  Usage:
#    sudo install-nginx-full.sh
# ─────────────────────────────────────────────────────────────
set -euo pipefail

# ── Source derivation ───────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -n "${SUDO_USER:-}" ]; then
  CORTEX_REPO="${CORTEX_REPO:-$(getent passwd "$SUDO_USER" | cut -d: -f6)/hermes-cortex}"
  CORTEX_HOME="$(getent passwd "$SUDO_USER" | cut -d: -f6)"
else
  CORTEX_REPO="${CORTEX_REPO:-${HOME}/hermes-cortex}"
  CORTEX_HOME="${HOME}"
fi

# ── Source user environment ──────────────────────────────────
CORTEX_ENV="${CORTEX_REPO}/.env"
[ -f "$CORTEX_ENV" ] && { set -a; source "$CORTEX_ENV"; set +a; }

# ── OS-aware nginx & fail2ban paths ─────────────────────────
case "$(uname -s)" in
  Darwin)
    if [[ "$(uname -m)" == "arm64" ]]; then
      NGINX_DIR="/opt/homebrew/etc/nginx"
      NGINX_HTPASSWD="${NGINX_DIR}/.htpasswd"
      NGINX_CONFIG_DIR="${NGINX_DIR}/servers"
      FAIL2BAN_DIR="/opt/homebrew/etc/fail2ban"
      NGINX_LOG_DIR="/opt/homebrew/var/log/nginx"
    else
      NGINX_DIR="/usr/local/etc/nginx"
      NGINX_HTPASSWD="${NGINX_DIR}/.htpasswd"
      NGINX_CONFIG_DIR="${NGINX_DIR}/servers"
      FAIL2BAN_DIR="/usr/local/etc/fail2ban"
      NGINX_LOG_DIR="/usr/local/var/log/nginx"
    fi
    NGINX_AVAILABLE_DIR="${NGINX_CONFIG_DIR}"  # macOS: no sites-available, write directly
    ;;
  Linux)
    NGINX_DIR="/etc/nginx"
    NGINX_HTPASSWD="${NGINX_DIR}/.hermes-htpasswd"
    NGINX_CONFIG_DIR="${NGINX_DIR}/sites-enabled"
    NGINX_AVAILABLE_DIR="${NGINX_DIR}/sites-available"
    FAIL2BAN_DIR="/etc/fail2ban"
    NGINX_LOG_DIR="/var/log/nginx"
    ;;
esac

BACKUP_DIR="/etc/hermes-cortex-backups/$(date +%Y%m%d-%H%M%S)"
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

BLOCKED_IPS="${CORTEX_REPO}/deploy/nginx/blocked_ips.add"
ALLOW_IPS_MANUAL="${NGINX_DIR}/allow-ips-manual.conf"
BADBOTS_CONF="${CORTEX_REPO}/deploy/nginx/nginx-badbots.conf"
ZONE_DEFS="${NGINX_DIR}/hermes-zone-defs.conf"
SERVICES_CONF="${NGINX_DIR}/sites-enabled/hermes-services.conf"

echo "━━━ Hermes Security Deploy — ${TIMESTAMP} ━━━"

# ── Source SSL cert paths from .env ──
CORTEX_ENV="${CORTEX_REPO}/.env"
if [ -f "$CORTEX_ENV" ]; then
  set -a; source "$CORTEX_ENV"; set +a
fi

# ── Ensure repo exists ──
if [ ! -d "$CORTEX_REPO" ]; then
  echo "✗ Cortex repo not found at ${CORTEX_REPO}"
  exit 1
fi

# ── Step 1: Backup ──
echo ""
echo "── Step 1: Backup ──"
mkdir -p "$BACKUP_DIR"
for f in "$ZONE_DEFS" "$SERVICES_CONF" "${FAIL2BAN_DIR}/filter.d/nginx-badbots.conf" "${FAIL2BAN_DIR}/jail.local"; do
  if [ -f "$f" ]; then
    cp "$f" "$BACKUP_DIR/"
    echo "  ✓ Backed up: $f"
  fi
done
echo "  → Backup at: ${BACKUP_DIR}"

# ── Step 2: Deploy nginx configs ──
echo ""
echo "── Step 2: Nginx configs ──"

# hermes-zone-defs.conf — include the health rate-limit zone if present
# (the source file in the repo should already have it)
for src in "${CORTEX_REPO}/deploy/nginx/hermes-zone-defs.conf" "${CORTEX_REPO}/deploy/nginx/hermes-services.conf"; do
  base=$(basename "$src")
  # Only deploy if source file exists in the deploy directory
  # For now, zone defs and services live in the repo and are managed via git
  if [ -f "$src" ]; then
    if [ "$base" = "hermes-zone-defs.conf" ]; then
      cp "$src" "$ZONE_DEFS"
      echo "  ✓ Deployed: ${base}"
    elif [ "$base" = "hermes-services.conf" ]; then
      mkdir -p "${NGINX_CONFIG_DIR}"

      # ── Read existing config (preserve ports/SSL unless forced) ──
      existing_conf="${NGINX_AVAILABLE_DIR}/${base}"
      existing_port_prefix="" existing_ssl_cert="" existing_ssl_key=""
      force_deploy="${CORTEX_FORCE_DEPLOY:-}"
      if [[ -f "$existing_conf" && -z "$force_deploy" ]]; then
        existing_port_prefix=$(grep -oP 'listen\s+(?:127\.0\.0\.1:)?\K[0-9]{2}(?=[0-9]{3}\b)' "$existing_conf" | head -1)
        existing_ssl_cert=$(grep -oP 'ssl_certificate\s+\K\S+' "$existing_conf" | head -1 | sed 's/;$//')
        existing_ssl_key=$(grep -oP 'ssl_certificate_key\s+\K\S+' "$existing_conf" | head -1 | sed 's/;$//')
        # Only keep if not a placeholder
        [[ "$existing_ssl_cert" == "__SSL_CERT__" ]] && existing_ssl_cert=""
        [[ "$existing_ssl_key" == "__SSL_CERT_KEY__" ]] && existing_ssl_key=""
      fi

      # ── Port prefix ────────────────────────────────────
      port_prefix="${CORTEX_NGINX_PORT_PREFIX:-${existing_port_prefix:-13}}"
      if [[ -n "$existing_port_prefix" && -z "$force_deploy" ]]; then
        if [[ "$port_prefix" == "$existing_port_prefix" ]]; then
          echo "  ✓ Preserved port prefix: ${port_prefix}xxx"
        else
          echo "  ✓ Using CORTEX_NGINX_PORT_PREFIX: ${port_prefix}xxx (config had ${existing_port_prefix}xxx)"
        fi
      fi

      # ── SSL cert resolution (only if not preserved) ────
      ssl_cert="$existing_ssl_cert" ssl_key="$existing_ssl_key"
      if [[ -z "$ssl_cert" ]]; then
        if [ -n "${CORTEX_SSL_CERT_PATH:-}" ] && [ -n "${CORTEX_SSL_CERT_KEY_PATH:-}" ]; then
          # Trust the user's env var paths — nginx -t will catch invalid paths
          ssl_cert="$CORTEX_SSL_CERT_PATH"
          ssl_key="$CORTEX_SSL_CERT_KEY_PATH"
        elif [ -d /etc/letsencrypt/live ]; then
          le_domain="${CORTEX_SSL_DOMAIN:-}"
          if [ -n "$le_domain" ] && [ -f "/etc/letsencrypt/live/${le_domain}/fullchain.pem" ]; then
            ssl_cert="/etc/letsencrypt/live/${le_domain}/fullchain.pem"
            ssl_key="/etc/letsencrypt/live/${le_domain}/privkey.pem"
          else
            for le_dir in /etc/letsencrypt/live/*/; do
              if [ -f "${le_dir}fullchain.pem" ] && [ -f "${le_dir}privkey.pem" ]; then
                ssl_cert="${le_dir}fullchain.pem"
                ssl_key="${le_dir}privkey.pem"
                break
              fi
            done
          fi
        fi
        if [ -z "$ssl_cert" ] && [ -f "${CORTEX_HOME}/certs/fullchain.pem" ] && [ -f "${CORTEX_HOME}/certs/privkey.pem" ]; then
          ssl_cert="${CORTEX_HOME}/certs/fullchain.pem"
          ssl_key="${CORTEX_HOME}/certs/privkey.pem"
        fi
      fi

      if [ -n "$ssl_cert" ]; then
        if [[ "$ssl_cert" == "$existing_ssl_cert" && -n "$existing_ssl_cert" ]]; then
          echo "  ✓ Preserved SSL cert: ${ssl_cert}"
        else
          echo "  ✓ SSL cert: ${ssl_cert}"
        fi
      else
        echo "  ⚠ No SSL certs found — __SSL_CERT__ placeholders left unchanged"
      fi

      # Write to sites-available (Linux) or servers/ (macOS)
      mkdir -p "${NGINX_AVAILABLE_DIR}"

      < "$src" sed \
        -e "s|__NGINX_CONFIG_DIR__|${NGINX_CONFIG_DIR}|g" \
        -e "s|__NGINX_LOG_DIR__|${NGINX_LOG_DIR}|g" \
        -e "s|__HTPASSWD_FILE__|${NGINX_HTPASSWD}|g" \
        -e "s|__CORTEX_HOME__|${CORTEX_HOME}|g" \
        -e "s|__SSL_CERT__|${ssl_cert:-__SSL_CERT__}|g" \
        -e "s|__SSL_CERT_KEY__|${ssl_key:-__SSL_CERT_KEY__}|g" \
        -e "/listen[[:space:]]/s|127\\.0\\.0\\.1:13\\([0-9][0-9][0-9]\\)|127.0.0.1:${port_prefix}\\1|g" \
        -e "/listen[[:space:]]/s|listen[[:space:]]*13\\([0-9][0-9][0-9]\\)|listen ${port_prefix}\\1|g" \
        > "${NGINX_AVAILABLE_DIR}/${base}"
      echo "  ✓ Deployed: ${NGINX_AVAILABLE_DIR}/${base} (paths substituted)"

      # Symlink from sites-enabled -> sites-available on Linux
      if [ "${NGINX_AVAILABLE_DIR}" != "${NGINX_CONFIG_DIR}" ]; then
        mkdir -p "${NGINX_CONFIG_DIR}"
        ln -sf "${NGINX_AVAILABLE_DIR}/${base}" "${NGINX_CONFIG_DIR}/${base}"
        echo "  ✓ Symlinked: ${NGINX_CONFIG_DIR}/${base} → ${NGINX_AVAILABLE_DIR}/${base}"
      fi
    fi
  fi
done

# ── Step 3: Deduplicate includes ──
echo ""
echo "── Step 3: Deduplicate includes ──"
for conf in "$ZONE_DEFS" "$SERVICES_CONF"; do
  if [ -f "$conf" ]; then
    # Check for duplicate 'include hermes-zone-defs.conf' lines
    dupes=$(grep -c "^include hermes-zone-defs.conf" "$conf" 2>/dev/null || true)
    if [ "$dupes" -gt 1 ]; then
      # Remove all but first occurrence
      awk '!/^include hermes-zone-defs.conf/ || !seen++' "$conf" > "${conf}.tmp"
      mv "${conf}.tmp" "$conf"
      echo "  ✓ Deduped ${conf} (removed $((dupes-1)) duplicate include)"
    else
      echo "  ✓ ${conf}: clean"
    fi
  fi
done

# ── Step 4: Append blocked IPs (batch-processed for speed) ──
echo ""
echo "── Step 4: Blocked IPs ──"
BLOCK_FILE="${NGINX_DIR}/blocked_ips.conf"
touch "$BLOCK_FILE"

if [ -f "$BLOCKED_IPS" ]; then
  # Batch process: one pipeline instead of per-IP grep calls
  # Pipeline: strip comments/blanks → validate IPv4 → reject private → remove duplicates
  NEW_IPS=$(mktemp)
  # shellcheck disable=SC2002
  cat "$BLOCKED_IPS" | \
    grep -vE '^\s*(#|$)' | \
    grep -E '^[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}$' | \
    grep -vE '^(127\.|10\.|0\.|172\.(1[6-9]|2[0-9]|3[0-1])\.|192\.168\.)' | \
    grep -vxF -f <(sed -n 's/^deny //;s/;$//p' "$BLOCK_FILE" 2>/dev/null) \
    > "$NEW_IPS" || true

  # Strip any IPs that are manually allow-listed (fail2ban protection override)
  if [ -f "$ALLOW_IPS_MANUAL" ]; then
    STRIPPED_IPS=$(mktemp)
    grep -oP 'allow\s+\K[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' "$ALLOW_IPS_MANUAL" 2>/dev/null | \
      grep -vxF -f - "$NEW_IPS" > "$STRIPPED_IPS" || true
    mv "$STRIPPED_IPS" "$NEW_IPS"
    echo "  ✓ Stripped allow-listed IPs from block list"
  fi

  ADDED=$(wc -l < "$NEW_IPS")
  if [ "$ADDED" -gt 0 ]; then
    sed 's/^/deny /; s/$/;/' "$NEW_IPS" >> "$BLOCK_FILE"
  fi
  rm -f "$NEW_IPS"

  echo "  ✓ ${ADDED} new IPs added"
fi

# Ensure blocked_ips.conf and allow-ips-manual.conf are included in services config
if ! grep -q "include blocked_ips.conf" "$SERVICES_CONF" 2>/dev/null; then
  echo "  ⚠ blocked_ips.conf not yet included in nginx config — add manually or through install.sh"
fi
if ! grep -q "include allow-ips-manual.conf" "$SERVICES_CONF" 2>/dev/null; then
  echo "  ⚠ allow-ips-manual.conf not included in nginx config — update cortex-update.sh or template"
fi

# ── Step 5: Install fail2ban filter ──
echo ""
echo "── Step 5: fail2ban filter ──"
if [ -f "$BADBOTS_CONF" ]; then
  cp "$BADBOTS_CONF" "${FAIL2BAN_DIR}/filter.d/nginx-badbots.conf"
  echo "  ✓ Filter installed"

  # Ensure jail is configured
  JAIL_FILE="${FAIL2BAN_DIR}/jail.local"
  if [ -f "$JAIL_FILE" ]; then
    if ! grep -q "nginx-badbots" "$JAIL_FILE" 2>/dev/null; then
      cat >> "$JAIL_FILE" <<JAIL

[nginx-badbots]
enabled  = true
port     = http,https
filter   = nginx-badbots
logpath  = ${NGINX_LOG_DIR}/*-access.log
maxretry = 3
bantime  = 86400
findtime = 3600
JAIL
      echo "  ✓ Jail entry added to jail.local"
    else
      echo "  ✓ Jail already configured"
    fi
  else
    cat > "$JAIL_FILE" <<JAIL
[DEFAULT]
bantime = 1h
findtime = 10m
maxretry = 5
ignoreip = 127.0.0.1 ::1

[nginx-badbots]
enabled  = true
port     = http,https
filter   = nginx-badbots
logpath  = ${NGINX_LOG_DIR}/*-access.log
maxretry = 3
bantime  = 86400
findtime = 3600
JAIL
    echo "  ✓ jail.local created with nginx-badbots"
  fi
fi

# ── Step 6: Validate nginx ──
echo ""
echo "── Step 6: Validate ──"
if nginx -t 2>&1; then
  echo "  ✓ nginx config valid"
else
  echo "  ✗ nginx config INVALID — NOT reloading"
  echo "  → Rollback: cp ${BACKUP_DIR}/* ${NGINX_DIR}/"
  exit 1
fi

# ── Step 7: Reload ──
echo ""
echo "── Step 7: Reload ──"

# Reload nginx (graceful)
if nginx -s reload 2>&1; then
  echo "  ✓ nginx reload signal sent"
  # Sleep briefly and check if reload actually took effect
  sleep 2
  if tail -5 "${NGINX_LOG_DIR}/error.log" 2>/dev/null | grep -q "still could not bind"; then
    echo "  ⚠ Reload partially failed (port conflicts with old workers)"
    echo "  → Doing full restart to release stale bindings..."
    nginx -s quit 2>/dev/null
    sleep 1
    if command -v systemctl >/dev/null 2>&1; then
      systemctl start nginx 2>/dev/null || nginx 2>&1
    else
      nginx 2>&1
    fi
    echo "  ✓ nginx restarted (new config active)"
  else
    echo "  ✓ nginx reloaded (new config active)"
  fi
else
  echo "  ✗ nginx reload failed"
  exit 1
fi

# Reload fail2ban
if command -v fail2ban-client >/dev/null 2>&1; then
  if fail2ban-client reload nginx-badbots 2>&1; then
    echo "  ✓ fail2ban nginx-badbots reloaded"
  else
    echo "  ⚠ fail2ban reload failed (jail may not be configured yet)"
  fi
fi

echo ""
echo "━━━ Deploy complete — ${TIMESTAMP} ━━━"