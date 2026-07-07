#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
#  nginx-security-scanner.sh — Daily nginx security auto-scan
#
#  Scans nginx access logs for suspect IPs, appends new ones
#  to blocked_ips.add, and auto-deploys if changes found.
#
#  Also scans fail2ban logs — both paths filter out RFC 1918
#  private/reserved ranges (127.x, 10.x, 172.16-31.x, 192.168.x,
#  0.x, 169.254.x, 224.x, 240.x) to prevent LAN IP contamination.
#
#  Silent when clean (watchdog pattern). Only outputs on changes.
#
#  Schedule: daily at 6 AM (cron)
#  no_agent: true
#  deliver: local
#
#  PREREQUISITES:
#  - nginx installed and running (access logs exist)
#  - fail2ban installed (optional — log scanning skipped if absent)
#  - deploy-blocked-ips.sh installed (generates + deploys blocked IPs)
#
#  AGENTS WITHOUT NGINX: Skip this cron entirely. The scanner silently
#  exits with no output when nginx logs aren't found (watchdog pattern),
#  but it's cleaner to not schedule it at all on non-nginx hosts.
# ─────────────────────────────────────────────────────────────
set -euo pipefail

CORTEX_REPO="${CORTEX_REPO:-${HOME}/hermes-cortex}"
BLOCKED_IPS="${CORTEX_REPO}/deploy/nginx/blocked_ips.add"
# Use deploy-blocked-ips.sh for minimal-root deploy
HERMES_HOME="${HERMES_HOME:-${HOME}/.hermes}"
DEPLOY_SCRIPT="${HERMES_HOME}/scripts/deploy-blocked-ips.sh"
if [ ! -x "$DEPLOY_SCRIPT" ]; then
  DEPLOY_SCRIPT="${CORTEX_REPO}/src/scripts/manage/deploy-blocked-ips.sh"
fi
# Linux: /var/log/nginx, macOS x86_64: /usr/local/var/log/nginx, macOS arm64: /opt/homebrew/var/log/nginx
if [ -d "/var/log/nginx" ]; then
  LOG_DIR="/var/log/nginx"
elif [ -d "/opt/homebrew/var/log/nginx" ]; then
  LOG_DIR="/opt/homebrew/var/log/nginx"
else
  LOG_DIR="/usr/local/var/log/nginx"
fi
STATE_FILE="${HOME}/.hermes/state/nginx-scanner-lastrun"

mkdir -p "$(dirname "$STATE_FILE")"

# ── Helpers ──
log()  { echo "[$(date '+%H:%M:%S')] $*"; }
error(){ log "✗ $*"; }

# ── Thresholds ──
MIN_HITS=10        # Min requests from same IP in the window
WINDOW_MINS=60     # Time window to scan
BAN_TIME="86400"   # fail2ban-style ban time (not used directly)

# ── Step 1: Scan access logs for suspect IPs ──
NEW_IPS=()
RECENT_SECONDS=$((WINDOW_MINS * 60))

if [ -d "$LOG_DIR" ]; then
  for logfile in "$LOG_DIR"/*-access.log; do
    [ -f "$logfile" ] || continue
    # Find IPs with high request counts in the recent window
    # Uses awk to count requests per IP, then filters by threshold
    cutoff="$(date -v-${WINDOW_MINS}M +%d/%b/%Y:%H:%M:%S 2>/dev/null || date -d "-${WINDOW_MINS} min" "+%d/%b/%Y:%H:%M:%S")"
    while IFS= read -r ip; do
      [ -z "$ip" ] && continue
      # Skip IPs already blocked
      if [ -f "$BLOCKED_IPS" ] && grep -qF "$ip" "$BLOCKED_IPS" 2>/dev/null; then
        continue
      fi
      # Skip private/local IPs
      if [[ "$ip" =~ ^(127\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.|192\.168\.) ]]; then
        continue
      fi
      NEW_IPS+=("$ip")
    done < <(timeout 10 awk -v cutoff="$cutoff" -v MIN_HITS=$MIN_HITS '
            {
              if (match($0, /\[[^]]+\]/)) {
                ts = substr($0, RSTART+1, RLENGTH-2)
                if (ts >= cutoff) { ip = $1; count[ip]++ }
              }
            }
            END { for (ip in count) if (count[ip] >= MIN_HITS) print ip }
          ' "$logfile")
  done
fi

# Also check fail2ban logs for emerging patterns
# Linux: /var/log/fail2ban.log, macOS: /usr/local/var/log/fail2ban.log
if [ -f "/var/log/fail2ban.log" ]; then
  F2B_LOG="/var/log/fail2ban.log"
elif [ -f "/opt/homebrew/var/log/fail2ban.log" ]; then
  F2B_LOG="/opt/homebrew/var/log/fail2ban.log"
else
  F2B_LOG="/usr/local/var/log/fail2ban.log"
fi
if [ -f "$F2B_LOG" ]; then
  while IFS= read -r ip; do
    [ -z "$ip" ] && continue
    # Skip private/local IPs (RFC 1918, loopback, link-local, multicast)
    if [[ "$ip" =~ ^(127\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.|192\.168\.|0\.|169\.254\.|224\.|240\.) ]]; then
      continue
    fi
    if [ -f "$BLOCKED_IPS" ] && grep -qF "$ip" "$BLOCKED_IPS" 2>/dev/null; then
      continue
    fi
    # Deduplicate against already-found IPs
    already=false
    for existing in "${NEW_IPS[@]:-}"; do
      [ "$existing" = "$ip" ] && already=true && break
    done
    $already && continue
    NEW_IPS+=("$ip")
  done < <(grep -i "ban.*[0-9]\+[0-9]\+[0-9]\+[0-9]\+" "$F2B_LOG" 2>/dev/null | grep -oP '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' | sort -u)
fi

# ── Step 2: Append new IPs ──
TOTAL_NEW=${#NEW_IPS[@]}
if [ "$TOTAL_NEW" -eq 0 ]; then
  # Silent exit — no news is good news
  exit 0
fi

# Deduplicate NEW_IPS
UNIQUE_IPS=()
for ip in "${NEW_IPS[@]}"; do
  already=false
  for existing in "${UNIQUE_IPS[@]:-}"; do
    [ "$existing" = "$ip" ] && already=true && break
  done
  $already && continue
  UNIQUE_IPS+=("$ip")
done

echo "━━━ Nginx Security Scan — $(date '+%Y-%m-%d %H:%M:%S') ━━━"
echo "  Found ${#UNIQUE_IPS[@]} new suspect IPs"
echo ""

# Append to blocked_ips.add
ADDED=0
for ip in "${UNIQUE_IPS[@]}"; do
  if grep -qF "$ip" "$BLOCKED_IPS" 2>/dev/null; then
    continue  # Already in list (race condition safe)
  fi
  echo "$ip" >> "$BLOCKED_IPS"
  echo "  + Blocked: ${ip}"
  ADDED=$((ADDED + 1))
done

echo ""
echo "  ${ADDED} IPs appended to blocked_ips.add"

# ── Step 3: Auto-deploy if IPs were added ──
if [ "$ADDED" -gt 0 ] && [ -x "$DEPLOY_SCRIPT" ]; then
  echo ""
  echo "── Deploying... ──"
  if bash "$DEPLOY_SCRIPT" 2>&1; then
    echo ""
    echo "✓ Security update deployed successfully"
  else
    error "Deploy script failed — manual intervention required"
    exit 1
  fi
fi

# Save state
date -u +"%Y-%m-%dT%H:%M:%SZ" > "$STATE_FILE"