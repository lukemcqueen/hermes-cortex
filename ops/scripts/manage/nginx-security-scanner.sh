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
BLOCKED_IPS="${CORTEX_REPO}/ops/install/deploy/nginx/blocked_ips.add"
# Use deploy-blocked-ips.sh for minimal-root deploy
HERMES_HOME="${HERMES_HOME:-${HOME}/.hermes}"
DEPLOY_SCRIPT="${HERMES_HOME}/scripts/deploy-blocked-ips.sh"
if [ ! -x "$DEPLOY_SCRIPT" ]; then
  DEPLOY_SCRIPT="${CORTEX_REPO}/ops/scripts/manage/deploy-blocked-ips.sh"
fi
STATE_FILE="${HOME}/.hermes-cortex/state/nginx-scanner-lastrun"

mkdir -p "$(dirname "$STATE_FILE")"

# ── Allow-list (2026-08-08): read /etc/nginx/allow-ips-manual.conf so the
# scanner NEVER re-adds an allow-listed IP to blocked_ips.add. The manual
# allow file is the one agent-tamper-proof surface (Luke 2026-08-08: only
# blocked_ips.add is agent-writable). Without this check, a legit office IP
# that trips the volume threshold gets re-appended every scan, and the
# deploy-time override keeps having to strip it — a pollution loop.
ALLOW_MANUAL="${ALLOW_MANUAL:-/etc/nginx/allow-ips-manual.conf}"
ALLOWED_IPS=()
if [ -f "$ALLOW_MANUAL" ]; then
  while IFS= read -r line; do
    line="$(echo "$line" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
    [ -z "$line" ] && continue
    case "$line" in
      \#*) continue ;;
      allow*) ALLOWED_IPS+=("$(echo "$line" | sed -E 's/^allow[[:space:]]+//; s/;.*$//')") ;;
    esac
  done < "$ALLOW_MANUAL"
fi

_is_allowed_ip() {
  local ip="$1" entry
  for entry in "${ALLOWED_IPS[@]:-}"; do
    [ -z "$entry" ] && continue
    if [[ "$entry" == */* ]]; then
      if python3 -c "import ipaddress,sys; sys.exit(0 if ipaddress.ip_address('$ip') in ipaddress.ip_network('$entry', strict=False) else 1)" 2>/dev/null; then
        return 0
      fi
    elif [ "$entry" = "$ip" ]; then
      return 0
    fi
  done
  return 1
}

# ── Helpers ──
log()  { echo "[$(date '+%H:%M:%S')] $*"; }
error(){ log "✗ $*"; }

# ── Thresholds ──
# (2026-08-08) Volume threshold REMOVED — fail2ban bans are the sole
# auto-source (see Step 1). Kept as named constants only for clarity.
BAN_TIME="86400"   # fail2ban-style ban time (not used directly)

# ── Step 1: Collect true-abuser IPs ──
# (2026-08-08, Luke directive: "only put true abusers in the banned IPs file")
# The old volume-threshold path (>=10 req/60min per IP) was REMOVED — it had
# zero discrimination and polluted the list with legit users: one dashboard
# SPA refresh fires 15-30 parallel requests, tripping the threshold. A legit
# user browsing normally looked identical to a scanner by volume alone.
# fail2ban bans (below) are the sole auto-source: they require actual attack
# evidence (repeated auth failures, admin-path probes, archive crawls).
NEW_IPS=()

# Check fail2ban logs for confirmed bans
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
  done < <(for f in "$F2B_LOG" "${F2B_LOG}.1" "${F2B_LOG}".*.gz; do
             [ -f "$f" ] || continue
             if [[ "$f" == *.gz ]]; then
               zcat "$f" 2>/dev/null || true
             else
               cat "$f" 2>/dev/null || true
             fi
           done | grep -i "ban.*[0-9]\+[0-9]\+[0-9]\+[0-9]\+" | grep -oP '[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+' | sort -u)
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
  if _is_allowed_ip "$ip"; then
    echo "  ⏭  Skipped (allow-listed): ${ip}"
    continue
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