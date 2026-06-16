#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  nginx-security-scanner.sh — Daily IP Ban & Filter Scanner
#
#  Scans nginx access logs for suspicious activity, appends
#  new IPs to blocked_ips.add, updates fail2ban patterns,
#  and re-deploys via hermes-security-apply.
#
#  Designed to run as a daily cron job.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

NGINX_LOG="/var/log/nginx"
BLOCKED_ADD="${HOME}/hermes-cortex/deploy/nginx/blocked_ips.add"
FILTER_CONF="${HOME}/hermes-cortex/deploy/nginx/nginx-badbots.conf"
DEPLOY_SCRIPT="/usr/local/sbin/hermes-security-apply"

# Ensure blocked_ips.add exists
mkdir -p "$(dirname "$BLOCKED_ADD")"
touch "$BLOCKED_ADD"

CHANGED=false

# ── Phase 1: Find /storage/ scanners from today's access logs ──
if [ -f "${NGINX_LOG}/agent-inbox-access.log" ]; then
  # Extract IPs hitting /storage/ with 404 in the last 24h
  SUSPECT_IPS=$(grep "$(date +%d/%b/%Y)" "${NGINX_LOG}/agent-inbox-access.log" 2>/dev/null \
    | grep '"GET /storage/' \
    | grep ' 404 ' \
    | awk '{print $1}' \
    | sort -u) || true

  if [ -n "$SUSPECT_IPS" ]; then
    for ip in $SUSPECT_IPS; do
      if ! grep -qxF "$ip" "$BLOCKED_ADD" 2>/dev/null; then
        echo "$ip" >> "$BLOCKED_ADD"
        echo "➕ Blocked new /storage/ scanner: $ip"
        CHANGED=true
      fi
    done
  fi
fi

# ── Phase 2: Find archive file scanners ──
for logfile in "${NGINX_LOG}"/*-access.log; do
  [ -f "$logfile" ] || continue
  ARCHIVE_IPS=$(grep "$(date +%d/%b/%Y)" "$logfile" 2>/dev/null \
    | grep -E 'GET\s/\S+\.(zip|rar|tar\.gz|tar\.bz2|tar\.xz|7z|zst|sql\.gz|sql\.bz2)\s' \
    | grep ' 404 ' \
    | awk '{print $1}' \
    | sort -u) || true

  if [ -n "$ARCHIVE_IPS" ]; then
    for ip in $ARCHIVE_IPS; do
      if ! grep -qxF "$ip" "$BLOCKED_ADD" 2>/dev/null; then
        echo "$ip" >> "$BLOCKED_ADD"
        echo "➕ Blocked new archive scanner: $ip"
        CHANGED=true
      fi
    done
  fi
done

# ── Phase 3: Check fail2ban for emerging patterns ──
# If fail2ban is logging new ban types, flag them for human review
FAIL2BAN_LOG="/var/log/fail2ban.log"
if [ -f "$FAIL2BAN_LOG" ]; then
  NEW_PATTERNS=$(grep "$(date +%Y-%m-%d)" "$FAIL2BAN_LOG" 2>/dev/null \
    | grep -i "ban\|find" \
    | grep -oP ']\s+\S+\s+\[.*\]' \
    | sort -u) || true
  if [ -n "$NEW_PATTERNS" ]; then
    echo "📊 New fail2ban patterns today:"
    echo "$NEW_PATTERNS"
    # (filters require human review — just report)
  fi
fi

# ── Phase 4: Deploy if anything changed ──
if [ "$CHANGED" = true ]; then
  echo ""
  echo "🚀 Deploying updated configs..."
  if sudo "$DEPLOY_SCRIPT"; then
    echo "✅ Deployment successful"
  else
    echo "❌ Deployment failed — check hermes-security-apply output" >&2
    exit 1
  fi
else
  echo "✅ No new threats found today"
fi
