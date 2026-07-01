#!/usr/bin/env bash
# nginx-threat-pipeline.sh — Extract, block, commit, push
#
# Pipeline: scan logs → collect fail2ban bans → deploy → commit → push
# Silent when no new IPs (watchdog pattern).
# Cross-platform: Linux + macOS (Intel and Apple Silicon).
# Schedule: daily at 5 AM via cron (no_agent: true).
set -euo pipefail

# ── Guard: abort any stale git operations before proceeding ──
if git -C "${CORTEX_REPO:-${HOME}/hermes-cortex}" rev-parse --git-dir &>/dev/null; then
  if git -C "${CORTEX_REPO:-${HOME}/hermes-cortex}" rebase --show-current &>/dev/null 2>&1; then
    echo "[$(date '+%H:%M:%S')] ⚠ Stale rebase detected — aborting"
    git -C "${CORTEX_REPO:-${HOME}/hermes-cortex}" rebase --abort 2>/dev/null || true
  fi
  # Clear any unfinished merge/revert/cherry-pick state
  git -C "${CORTEX_REPO:-${HOME}/hermes-cortex}" cherry-pick --quit 2>/dev/null || true
  git -C "${CORTEX_REPO:-${HOME}/hermes-cortex}" merge --quit 2>/dev/null || true
fi

CORTEX_REPO="${CORTEX_REPO:-${HOME}/hermes-cortex}"
SCANNER="${CORTEX_REPO}/src/scripts/nginx-security-scanner.sh"

# ── Platform-aware paths ──
# timeout: linux=timeout, mac=gtimeout (brew coreutils)
TIMEOUT_CMD=""
for cmd in timeout gtimeout; do
  if command -v "$cmd" &>/dev/null; then
    TIMEOUT_CMD="$cmd"
    break
  fi
done

# DEPLOY_SCRIPT: linux=/usr/local/sbin, mac intel=/usr/local/sbin, mac arm=/opt/homebrew/sbin
CORTEX_REPO="${CORTEX_REPO:-${HOME}/hermes-cortex}"
DEPLOY_SCRIPT=""
for path in "${CORTEX_REPO}/deploy/nginx/hermes-security-apply" /usr/local/sbin/hermes-security-apply /opt/homebrew/sbin/hermes-security-apply; do
  if [ -x "$path" ]; then
    DEPLOY_SCRIPT="$path"
    break
  fi
done

# NGINX binary path (for existence check, not execution)
NGINX_BIN=""
for path in /usr/sbin/nginx /usr/local/bin/nginx /opt/homebrew/bin/nginx; do
  if [ -x "$path" ]; then
    NGINX_BIN="$path"
    break
  fi
done

# fail2ban binary check (is it installed at all?)
F2B_INSTALLED=false
command -v fail2ban-client &>/dev/null && F2B_INSTALLED=true

mkdir -p "${HOME}/.hermes/state" "${HOME}/.hermes/logs"

log()  { echo "[$(date '+%H:%M:%S')] $*"; }
error(){ echo "✗ $*"; }

PIPELINE_OUTPUT=""
NEW_IPS=false

# ── Step 1: Scan nginx logs ──
log "── Step 1: Scan logs ──"
if [ -x "$SCANNER" ]; then
  if [ -n "$TIMEOUT_CMD" ]; then
    SCANNER_OUTPUT=$($TIMEOUT_CMD 12 bash "$SCANNER" 2>&1) || true
    RC=$?
    if [ "$RC" -eq 124 ]; then
      log "  ⚠ Scanner timed out after 12s"
    elif [ "$RC" -ne 0 ]; then
      log "  ⚠ Scanner exited with code ${RC}"
    fi
  else
    SCANNER_OUTPUT=$(bash "$SCANNER" 2>&1) || true
  fi
  if echo "$SCANNER_OUTPUT" | grep -q "Found.*new suspect IPs\|+ Blocked:"; then
    NEW_IPS=true; PIPELINE_OUTPUT+="${SCANNER_OUTPUT}"$'\n'
  fi
else
  error "Scanner not found at ${SCANNER} — skipping"
fi

# ── Step 2: Collect fail2ban bans ──
log "── Step 2: Collect fail2ban bans ──"
F2B_LOG=""
# Only check for logs if fail2ban is actually installed
if $F2B_INSTALLED; then
  [ -f "/var/log/fail2ban.log" ]            && F2B_LOG="/var/log/fail2ban.log"
  [ -f "/opt/homebrew/var/log/fail2ban.log" ] && F2B_LOG="/opt/homebrew/var/log/fail2ban.log"
  [ -f "/usr/local/var/log/fail2ban.log" ]   && F2B_LOG="/usr/local/var/log/fail2ban.log"
fi

if [ -n "$F2B_LOG" ]; then
  if [ -n "$TIMEOUT_CMD" ]; then
    F2B_TIMEOUT_RESULT=$($TIMEOUT_CMD 20 bash -c '
      F2B_LOG="$1"; CORTEX_REPO="$2"
      grep -i "Ban" "$F2B_LOG" 2>/dev/null | \
        grep -oP '\'"'"'[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+'\'"'"' | sort -u | \
        while IFS= read -r ip; do
          [ -z "$ip" ] && continue
          grep -qF "$ip" "${CORTEX_REPO}/deploy/nginx/blocked_ips.add" 2>/dev/null && continue
          echo "$ip"
        done
    ' _ "$F2B_LOG" "$CORTEX_REPO") || true
  else
    # no timeout available, run without it
    F2B_TIMEOUT_RESULT=$(bash -c '
      F2B_LOG="$1"; CORTEX_REPO="$2"
      grep -i "Ban" "$F2B_LOG" 2>/dev/null | \
        grep -oP '\'"'"'[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+'\'"'"' | sort -u | \
        while IFS= read -r ip; do
          [ -z "$ip" ] && continue
          grep -qF "$ip" "${CORTEX_REPO}/deploy/nginx/blocked_ips.add" 2>/dev/null && continue
          echo "$ip"
        done
    ' _ "$F2B_LOG" "$CORTEX_REPO") || true
  fi
  NEW_F2B_IPS="$F2B_TIMEOUT_RESULT"

  # Validate all extracted IPs — reject garbage from fail2ban log parsing
  # Only lines matching IPv4 format (4 dot-separated octets, each 0-255) pass
  NEW_F2B_IPS=$(echo "$F2B_TIMEOUT_RESULT" | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' | \
    awk -F. '{if($1<=255&&$2<=255&&$3<=255&&$4<=255)print}' || true)

  F2B_COUNT=$(echo "$NEW_F2B_IPS" | grep -c '[0-9]' 2>/dev/null || true)
  F2B_COUNT=$((F2B_COUNT + 0))
  if [ "$F2B_COUNT" -gt 0 ]; then
    NEW_IPS=true
    log "  ${F2B_COUNT} new fail2ban-banned IPs"
    # Ensure directory exists before appending
    mkdir -p "${CORTEX_REPO}/deploy/nginx"
    echo "$NEW_F2B_IPS" >> "${CORTEX_REPO}/deploy/nginx/blocked_ips.add"
  fi
elif $F2B_INSTALLED; then
  log "  fail2ban installed but no log file found — skipping"
else
  log "  fail2ban not installed — skipping"
fi

# ── Step 3: Deploy ──
log "── Step 3: Deploy ──"
if [ -z "$DEPLOY_SCRIPT" ]; then
  log "  hermes-security-apply not found on any platform path — skipping"
elif [ -z "$NGINX_BIN" ]; then
  log "  nginx not found — skipping deploy"
elif $NEW_IPS; then
  if sudo -n "$DEPLOY_SCRIPT" 2>&1; then
    log "  ✓ Deployed"
  else
    error "Deploy failed"
  fi
else
  log "  No new IPs — skipping"
fi

# ── Step 4: Commit & push ──
log "── Step 4: Commit ──"
if [ ! -d "$CORTEX_REPO" ]; then
  error "Cortex repo not found at ${CORTEX_REPO} — skipping commit"
else
  cd "$CORTEX_REPO"
  if git diff --quiet deploy/nginx/blocked_ips.add 2>/dev/null \
     && git diff --cached --quiet deploy/nginx/blocked_ips.add 2>/dev/null; then
    log "  No changes to commit"
  else
    git add deploy/nginx/blocked_ips.add
    IP_COUNT=$(git diff --cached --unified=0 deploy/nginx/blocked_ips.add 2>/dev/null | \
      grep '^\+[0-9]' | grep -v '^+++' | wc -l) || true
    git commit -m "auto: block ${IP_COUNT} suspect IPs [pipeline]"
    PIPELINE_OUTPUT+="  ✓ Committed ${IP_COUNT} IPs to repo"$'\n'

    log "── Step 5: Push ──"
    for push_attempt in 1 2; do
      if [ -n "$TIMEOUT_CMD" ]; then
        if $TIMEOUT_CMD 10 git push origin main 2>&1; then
          PIPELINE_OUTPUT+="  ✓ Pushed to origin"$'\n'
          break
        else
          PUSH_EXIT=$?
          if [ $push_attempt -eq 1 ] && [ $PUSH_EXIT -eq 128 ]; then
            log "  ⚠ Remote ahead — pulling and retrying"
            $TIMEOUT_CMD 15 git pull --rebase origin main 2>&1 || true
          elif [ $push_attempt -eq 1 ]; then
            log "  ⚠ Push failed (code $PUSH_EXIT) — pulling and retrying"
            $TIMEOUT_CMD 15 git pull --rebase origin main 2>&1 || true
          else
            PIPELINE_OUTPUT+="  ⚠ Push failed after retry"$'\n'
          fi
        fi
      else
        if git push origin main 2>&1; then
          PIPELINE_OUTPUT+="  ✓ Pushed to origin"$'\n'
          break
        else
          PUSH_EXIT=$?
          if [ $push_attempt -eq 1 ]; then
            log "  ⚠ Push failed (code $PUSH_EXIT) — pulling and retrying"
            git pull --rebase origin main 2>&1 || true
          else
            PIPELINE_OUTPUT+="  ⚠ Push failed after retry"$'\n'
          fi
        fi
      fi
    done
  fi
fi

# ── Save state ──
date -u +"%Y-%m-%dT%H:%M:%SZ" > "${HOME}/.hermes/state/nginx-threat-pipeline-lastrun"

# ── Output (watchdog: silent unless changes) ──
if $NEW_IPS; then
  echo ""
  echo "━━━ Threat Pipeline — $(date '+%Y-%m-%d %H:%M:%S') ━━━"
  echo "$PIPELINE_OUTPUT"
  echo "━━━ Complete ━━━"
fi
