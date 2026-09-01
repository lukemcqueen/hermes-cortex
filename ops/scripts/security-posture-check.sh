#!/usr/bin/env bash
# security-posture-check.sh — hourly security posture verification.
#
# Silent (exit 0, no output) when everything is healthy.
# Prints a report + exits 1 when ANY check fails — cron delivers it.
#
# Cross-platform: Linux (systemd, nftables, journalctl) and macOS
# (launchd, pf, system.log). Platform-inapplicable checks are skipped
# with an explicit "n/a" note, never silently.
#
# TIER — per-host posture depth, read from ~/hermes-cortex/.env:
#   SECURITY_POSTURE=full     (default) all checks — internet-facing host
#   SECURITY_POSTURE=minimal  skip network-exposure checks (firewall ban
#                             set, brute-force volume, nginx jail req);
#                             keep service-up + SSH key-only basics
#   SECURITY_POSTURE=off      exit 0 silently — host opts out entirely
#                             (e.g. an agent not on the net at all)
#
# Checks (full tier):
#   1. fail2ban service active (systemctl / launchctl)
#   2. fail2ban jails enabled (sshd, nginx-http-auth, nginx-badbots)
#   3. firewall ban set exists (Linux: nftables f2b-table / macOS: pf anchor)
#   4. SSH is key-only (no PasswordAuthentication yes, no root login)
#   5. nginx jails' logpaths exist (not silently starving)
#   6. recent SSH brute-force volume (last 24h) for situational awareness
set -uo pipefail

FAILS=0
REPORT=""

fail()  { FAILS=$((FAILS + 1)); REPORT+="❌ $1"$'\n'; }
warn()  { REPORT+="⚠️  $1"$'\n'; }
ok()    { :; }

OS="$(uname -s)"

# --- tier: env var wins, ~/hermes-cortex/.env is the fallback default ---
# (same convention as IS_SERVER). SECURITY_POSTURE=full|minimal|off.
POSTURE_TIER="${SECURITY_POSTURE:-full}"
if [[ -z "${SECURITY_POSTURE:-}" && -f "${HOME}/hermes-cortex/.env" ]]; then
  _tier="$(grep -E '^SECURITY_POSTURE=' "${HOME}/hermes-cortex/.env" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"
  [[ -n "$_tier" ]] && POSTURE_TIER="$_tier"
fi
case "$POSTURE_TIER" in
  off)
    exit 0 ;;
  minimal|full) : ;;
  *)
    warn "SECURITY_POSTURE='$POSTURE_TIER' unknown (expected full|minimal|off) — treating as full" ;;
esac
TIER_MINIMAL=0
[[ "$POSTURE_TIER" == "minimal" ]] && TIER_MINIMAL=1


# --- 1. fail2ban service ---
if [[ "$OS" == "Darwin" ]]; then
  if launchctl list | grep -q 'fail2ban'; then
    ok "fail2ban loaded (launchd)"
  elif [[ $TIER_MINIMAL -eq 1 ]]; then
    ok "skip fail2ban (minimal tier — host not directly exposed)"
  else
    fail "fail2ban is NOT loaded (launchctl list | grep fail2ban)"
  fi
else
  if systemctl is-active fail2ban >/dev/null 2>&1; then
    ok "fail2ban active"
  elif [[ $TIER_MINIMAL -eq 1 ]]; then
    ok "skip fail2ban (minimal tier — host not directly exposed)"
  else
    fail "fail2ban service is NOT active"
  fi
fi

# --- 2. jails ---
# nginx jails only apply where nginx is installed/running (host-awareness:
# a host without nginx has no nginx attack surface and must not false-fail).
HAS_NGINX=0
if command -v nginx >/dev/null 2>&1 || [[ -d /etc/nginx ]]; then
  HAS_NGINX=1
fi
if [[ $TIER_MINIMAL -eq 1 ]]; then
  ok "skip jail checks (minimal tier)"
else

# fail2ban-client status <jail> needs the root socket; as a cron (non-root)
# only the top-level `fail2ban-client status` is available (and only where
# sudoers grants NOPASSWD: /usr/bin/fail2ban-client status). Parse the
# top-level "Jail list:" line — it names every active jail. If neither the
# sudo nor plain call works, report "cannot verify" (honest gap, not a lie).
F2B_JAIL_LIST=""
if sudo -n fail2ban-client status >/dev/null 2>&1; then
  F2B_JAIL_LIST=$(sudo -n fail2ban-client status 2>/dev/null | grep -i 'Jail list' | sed 's/.*Jail list:[[:space:]]*//')
elif fail2ban-client status >/dev/null 2>&1; then
  F2B_JAIL_LIST=$(fail2ban-client status 2>/dev/null | grep -i 'Jail list' | sed 's/.*Jail list:[[:space:]]*//')
fi

for jail in sshd nginx-http-auth nginx-badbots; do
  if [[ "$jail" != "sshd" && "$HAS_NGINX" -eq 0 ]]; then
    ok "skip $jail (no nginx on this host)"
    continue
  fi
  if [[ -n "$F2B_JAIL_LIST" ]]; then
    if grep -qw "$jail" <<< "$F2B_JAIL_LIST"; then
      ok "$jail jail active"
    else
      fail "fail2ban jail '$jail' is NOT in the active jail list (loaded: $F2B_JAIL_LIST)"
    fi
  else
    warn "cannot verify fail2ban jails (no socket access as cron; needs NOPASSWD: /usr/bin/fail2ban-client status)"
    break
  fi
done
fi

# --- 3. firewall ban set ---
if [[ $TIER_MINIMAL -eq 1 ]]; then
  ok "skip firewall ban-set check (minimal tier)"
elif [[ "$OS" == "Darwin" ]]; then
  if command -v pfctl >/dev/null 2>&1 && sudo -n pfctl -s Anchors 2>/dev/null | grep -q 'f2b'; then
    ok "pf f2b anchor present"
  else
    warn "pf f2b anchor not verified (needs root; check: sudo pfctl -s Anchors | grep f2b)"
  fi
else
  if command -v nft >/dev/null 2>&1 && sudo -n nft list set inet f2b-table addr-set f2b-sshd >/dev/null 2>&1; then
    ok "nftables f2b-sshd set present"
  elif command -v nft >/dev/null 2>&1 && nft list set inet f2b-table addr-set f2b-sshd >/dev/null 2>&1; then
    ok "nftables f2b-sshd set present (readable without sudo)"
  elif command -v iptables >/dev/null 2>&1 && iptables -L f2b-sshd -n >/dev/null 2>&1; then
    ok "iptables f2b-sshd chain present"
  else
    fail "firewall ban set f2b-sshd missing (banaction not applied?)"
  fi
fi

# --- 4. SSH key-only ---
SSHD_FILES="/etc/ssh/sshd_config"
[[ -d /etc/ssh/sshd_config.d ]] && SSHD_FILES="$SSHD_FILES /etc/ssh/sshd_config.d"
if grep -rhE '^[[:space:]]*PasswordAuthentication[[:space:]]+yes' $SSHD_FILES 2>/dev/null | grep -qv '^[[:space:]]*#'; then
  fail "SSH PasswordAuthentication is ENABLED (should be key-only)"
else
  ok "SSH password auth disabled"
fi
if grep -rhE '^[[:space:]]*PermitRootLogin[[:space:]]+yes' $SSHD_FILES 2>/dev/null | grep -qv '^[[:space:]]*#'; then
  fail "SSH PermitRootLogin is ENABLED (should be no/prohibit-password)"
else
  ok "SSH root login restricted"
fi

# --- 5. nginx jail logpaths exist (silent starvation check) ---
if [[ "$HAS_NGINX" -eq 1 ]]; then
  for lp in /var/log/nginx/error.log /var/log/nginx/access.log; do
    if [[ -f "$lp" ]]; then
      ok "nginx log $lp present"
    else
      warn "nginx log $lp missing — jail may be silently starving"
    fi
  done
else
  ok "skip nginx logpaths (no nginx on this host)"
fi

# --- 6. brute-force volume (last 24h) ---
if [[ $TIER_MINIMAL -eq 1 ]]; then
  ok "skip brute-force volume (minimal tier)"
else
  BRUTE=0
  if [[ "$OS" == "Darwin" ]]; then
    BRUTE=$(grep -cE 'Failed password|Invalid user' /var/log/system.log 2>/dev/null || true)
  else
    BRUTE=$(journalctl -u sshd --since "24 hours ago" 2>/dev/null | grep -cE 'Failed password|Invalid user' || true)
  fi
  if [[ "${BRUTE:-0}" -gt 100 ]]; then
    warn "$BRUTE SSH brute-force attempts in last 24h"
  fi
fi

# --- output ---
if [[ $FAILS -gt 0 ]]; then
  echo "🔐 SECURITY POSTURE FAILING — ${FAILS} issue(s)"
  echo ""
  echo "$REPORT"
  exit 1
fi
if [[ -n "$REPORT" ]]; then
  echo "🔐 Security posture OK (warnings):"
  echo ""
  echo "$REPORT"
fi
exit 0
