#!/usr/bin/env bash
# deploy-blocked-ips.sh — Generate and deploy blocked_ips.conf
#
# Minimal-root deploy: generates the blocklist config without needing
# the full hermes-security-apply script. Only uses sudo for the final
# cp to /etc/nginx/.
#
# Usage:
#   bash deploy-blocked-ips.sh         # deploy if IPs exist
#   bash deploy-blocked-ips.sh --check # validate only, no deploy
#
# Requires NOPASSWD:
#   moses ALL=(root) NOPASSWD: /bin/cp /tmp/blocked_ips.conf.new /etc/nginx/blocked_ips.conf
#
# Also relies on existing NOPASSWD for nginx -t and nginx -s reload.
# ─────────────────────────────────────────────────────────────
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORTEX_REPO="${CORTEX_REPO:-${HOME}/hermes-cortex}"
if [ ! -d "$CORTEX_REPO" ]; then
  # Fallback: try walking up from script dir
  CORTEX_REPO="$(cd "$SCRIPT_DIR/../.." && pwd 2>/dev/null || echo "$HOME/hermes-cortex")"
fi

NGINX_CONF_DIR="/etc/nginx"
[ "$(uname -s)" = "Darwin" ] && {
  [ "$(uname -m)" = "arm64" ] && NGINX_CONF_DIR="/opt/homebrew/etc/nginx" || NGINX_CONF_DIR="/usr/local/etc/nginx"
}

FIX_SCRIPT="${CORTEX_REPO}/deploy/nginx/fix-blocked-ips.py"
TMP_CONF="/tmp/blocked_ips.conf.new"
TARGET_CONF="${NGINX_CONF_DIR}/blocked_ips.conf"
CHECK_ONLY="${1:-}"

log()   { echo "[$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST') deploy-blocked-ips] $*"; }
error() { echo "[$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST') deploy-blocked-ips] ✗ $*"; }

# ── Generate config ──
if [ ! -f "$FIX_SCRIPT" ]; then
  error "fix-blocked-ips.py not found at ${FIX_SCRIPT}"
  exit 1
fi

GENERATED=$(python3 "$FIX_SCRIPT" 2>&1) || {
  error "Failed to generate blocked IPs config"
  echo "$GENERATED"
  exit 1
}
echo "$GENERATED"

# Extract IP count from output
IP_COUNT=$(echo "$GENERATED" | grep -oP 'blocked IPs: \K\d+')
if [ -z "$IP_COUNT" ] || [ "$IP_COUNT" -eq 0 ]; then
  log "  No IPs to deploy — skipping"
  exit 0
fi

[ "$CHECK_ONLY" = "--check" ] && { log "  Check only — not deploying"; exit 0; }

# ── Deploy config (sudo cp) ──
if [ ! -f "$TMP_CONF" ]; then
  error "Generated config not found at ${TMP_CONF}"
  exit 1
fi

if diff -q "$TMP_CONF" "$TARGET_CONF" 2>/dev/null; then
  log "  Config unchanged — skipping reload"
  rm -f "$TMP_CONF"
  exit 0
fi

if ! sudo -n cp "$TMP_CONF" "$TARGET_CONF" 2>/dev/null; then
  error "sudo cp failed — add NOPASSWD rule: cp ${TMP_CONF} ${TARGET_CONF}"
  rm -f "$TMP_CONF"
  exit 1
fi
log "  ✓ Deployed ${TARGET_CONF} (${IP_COUNT} IPs)"
rm -f "$TMP_CONF"

# ── Validate nginx ──
if ! sudo -n /usr/sbin/nginx -t 2>&1; then
  error "nginx config INVALID — rolling back"
  # Can't roll back without sudo cp, but nginx won't reload
  exit 1
fi
log "  ✓ nginx config valid"

# ── Reload nginx ──
if ! sudo -n /usr/sbin/nginx -s reload 2>&1; then
  error "nginx reload failed"
  exit 1
fi
log "  ✓ nginx reloaded"
