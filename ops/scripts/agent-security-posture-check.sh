#!/usr/bin/env bash
# agent-security-posture-check.sh — hourly security posture verification.
#
# Silent (exit 0, no output) when everything is healthy.
# Prints a report + exits 1 when ANY check fails — cron delivers it.
#
# State dedup via cron-failure-state.sh: same warning fingerprint is
# suppressed within the cooldown window to prevent hourly floods.
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
#   3. firewall ban set exists (Linux: nftables f2b-table / macOS: pf anchor;
#      fallback to fail2ban.log evidence when chain not probeable)
#   4. SSH is key-only (no PasswordAuthentication yes, no root login)
#   5. nginx jails' logpaths exist (not silently starving)
#   6. recent SSH brute-force volume (last 24h) for situational awareness
set -uo pipefail

# ── State dedup (source first, before any logic) ──
SCRIPT_NAME="security-posture-check"
STATE_DIR="${HOME}/.hermes-cortex/state"
FINGERPRINT_FILE="${STATE_DIR}/${SCRIPT_NAME}-fingerprint.txt"
mkdir -p "$STATE_DIR"

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

# --- 3. firewall ban set + fail2ban log verification ---
if [[ $TIER_MINIMAL -eq 1 ]]; then
  ok "skip firewall ban-set check (minimal tier)"
elif [[ "$OS" == "Darwin" ]]; then
  if command -v pfctl >/dev/null 2>&1 && sudo -n pfctl -s Anchors 2>/dev/null | grep -q 'f2b'; then
    ok "pf f2b anchor present"
  else
    warn "pf f2b anchor not verified (needs root; check: sudo pfctl -s Anchors | grep f2b)"
  fi
else
  # Detection ladder:
  #   1. nft/iptables chain probe succeeds → OK (bans enforced)
  #   2. probes fail → check fail2ban.log for recent bans
  #   3. bans found in log → OK with note (chain not probeable, bans confirmed)
  #   4. no bans in log + no chain → honest lazy-chain warn
  #   5. bans with action errors → FAIL
  CHAIN_OK=0
  if command -v nft >/dev/null 2>&1; then
    if sudo -n nft list set inet f2b-table addr-set f2b-sshd >/dev/null 2>&1; then
      ok "nftables f2b-sshd set present"
      CHAIN_OK=1
    elif nft list set inet f2b-table addr-set f2b-sshd >/dev/null 2>&1; then
      ok "nftables f2b-sshd set present (readable without sudo)"
      CHAIN_OK=1
    fi
  fi
  if [[ $CHAIN_OK -eq 0 ]] && command -v iptables >/dev/null 2>&1; then
    if sudo -n iptables -L f2b-sshd -n >/dev/null 2>&1; then
      ok "iptables f2b-sshd chain present"
      CHAIN_OK=1
    elif iptables -L f2b-sshd -n >/dev/null 2>&1; then
      ok "iptables f2b-sshd chain present"
      CHAIN_OK=1
    fi
  fi

  if [[ $CHAIN_OK -eq 0 ]]; then
    # Chain probes failed — fall back to fail2ban log evidence
    F2B_LOG=""
    for _lp in /var/log/fail2ban.log /var/log/fail2ban.log.1; do
      [[ -r "$_lp" ]] && { F2B_LOG="$_lp"; break; }
    done
    if [[ -n "$F2B_LOG" ]]; then
      RECENT_BANS=$(grep -c 'NOTICE.*Ban' "$F2B_LOG" 2>/dev/null || true)
      RECENT_BANS=${RECENT_BANS:-0}
      ACTION_ERRORS=$(grep -c 'Failed to execute ban' "$F2B_LOG" 2>/dev/null || true)
      ACTION_ERRORS=${ACTION_ERRORS:-0}
      if [[ "$ACTION_ERRORS" -gt 0 ]]; then
        fail "firewall ban set f2b-sshd missing AND fail2ban.log shows $ACTION_ERRORS ban-action error(s) — bans not enforced"
      elif [[ "$RECENT_BANS" -gt 0 ]]; then
        ok "nft/iptables chain not probeable (no sudo), $RECENT_BANS bans in fail2ban.log — bans enforced"
      elif [[ -n "$F2B_JAIL_LIST" ]] && grep -qw sshd <<< "$F2B_JAIL_LIST"; then
        warn "f2b-sshd chain not found in nft/iptables (no sudo) and fail2ban.log shows 0 bans — fail2ban creates ban chains lazily (no bans yet; sshd jail active)"
      else
        fail "firewall ban set f2b-sshd missing (banaction not applied?)"
      fi
    elif [[ -n "$F2B_JAIL_LIST" ]] && grep -qw sshd <<< "$F2B_JAIL_LIST"; then
      warn "f2b-sshd chain not found in nft/iptables (no sudo) and fail2ban.log not readable — cannot verify ban enforcement"
    else
      fail "firewall ban set f2b-sshd missing (banaction not applied?)"
    fi
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

# --- output + state dedup ---
# Compute a fingerprint of the current report to suppress identical
# deliveries within the cooldown window (cron-failure-state.sh pattern).
REPORT_HASH=$(echo -n "$REPORT" | sha256sum | cut -c1-16)
if [[ -f "$FINGERPRINT_FILE" ]]; then
  LAST_HASH=$(cat "$FINGERPRINT_FILE" 2>/dev/null || echo "")
  if [[ "$REPORT_HASH" == "$LAST_HASH" ]]; then
    # Same warning as last run — suppress to prevent hourly flood.
    # The cooldown lasts until the fingerprint file is removed, which
    # happens when REPORT is empty (no warnings) or changes.
    exit 0
  fi
fi
echo -n "$REPORT_HASH" > "$FINGERPRINT_FILE"

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
# Clear fingerprint on clean run (no warnings)
[[ -z "$REPORT" ]] && rm -f "$FINGERPRINT_FILE"
exit 0
