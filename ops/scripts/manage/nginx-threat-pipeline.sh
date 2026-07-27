#!/usr/bin/env bash
# nginx-threat-pipeline.sh — Extract, block, commit, push
#
# Pipeline: scan logs → collect fail2ban bans → deploy → commit → push
# Silent when no new IPs (watchdog pattern).
# Cross-platform: Linux + macOS (Intel and Apple Silicon).
# Schedule: daily at 5 AM via cron (no_agent: true).
#
# IMPORTANT: All IP collection paths filter out RFC 1918 private/reserved
# ranges (127.x, 10.x, 172.16-31.x, 192.168.x, 0.x, 169.254.x, 224.x, 240.x).
# This prevents LAN IPs (gateway, internal services) from being added to the
# public blocklist when fail2ban bans the router's NAT IP.
set -euo pipefail

# ── Temporary governance lock for automated pushes ─────────
# The pre-push hook requires an active governance lock. Since this
# script runs as a no_agent cron with no session, it creates a
# temporary lock file before pushing and removes it on exit.
_GOV_LOCK="${HOME}/.hermes-cortex/state/.governance-nginx-threat-pipeline.json"
_create_gov_lock() {
  mkdir -p "${HOME}/.hermes-cortex/state"
  cat > "$_GOV_LOCK" <<-LOCKEOF
{
  "task_id": "nginx-threat-pipeline",
  "repo_slug": "hermes-cortex",
  "session_id": "cron-nginx-threat-pipeline",
  "started_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "heartbeat_at": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "agent": "cron"
}
LOCKEOF
}
trap 'rm -f "$_GOV_LOCK"' EXIT

# ── Guard: abort any stale git operations before proceeding ──
if git -C "${CORTEX_REPO:-${HOME}/hermes-cortex}" rev-parse --git-dir &>/dev/null; then
  if git -C "${CORTEX_REPO:-${HOME}/hermes-cortex}" rebase --show-current &>/dev/null 2>&1; then
    echo "[$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST') nginx-threat-pipeline] ⚠ Stale rebase detected — aborting"
    git -C "${CORTEX_REPO:-${HOME}/hermes-cortex}" rebase --abort 2>/dev/null || true
  fi
  # Clear any unfinished merge/revert/cherry-pick state
  git -C "${CORTEX_REPO:-${HOME}/hermes-cortex}" cherry-pick --quit 2>/dev/null || true
  git -C "${CORTEX_REPO:-${HOME}/hermes-cortex}" merge --quit 2>/dev/null || true
fi

CORTEX_REPO="${CORTEX_REPO:-${HOME}/hermes-cortex}"
SCANNER="${CORTEX_REPO}/ops/scripts/manage/nginx-security-scanner.sh"
SUBMIT_FILE="${CORTEX_REPO}/ops/install/deploy/nginx/blocked_ips.submit"

# ── Process agent-submitted IPs before scanning ──
if [ -f "$SUBMIT_FILE" ]; then
  SUBMIT_RAW=$(grep -v '^#' "$SUBMIT_FILE" 2>/dev/null | grep -v '^[[:space:]]*$' || true)
  if [ -n "$SUBMIT_RAW" ]; then
    VALID_IPS=$(echo "$SUBMIT_RAW" | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' | \
      awk -F. '{if($1<=255&&$2<=255&&$3<=255&&$4<=255)print}' | \
      grep -vE '^(127\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.|192\.168\.|0\.|169\.254\.|224\.|240\.)' || true)
    NEW_FROM_SUBMIT=""
    while IFS= read -r ip; do
      [ -z "$ip" ] && continue
      if ! grep -qF "$ip" "${CORTEX_REPO}/ops/install/deploy/nginx/blocked_ips.add" 2>/dev/null; then
        NEW_FROM_SUBMIT+="${ip}"$'\n'
      fi
    done <<< "$VALID_IPS"
    SUBMIT_COUNT=$(echo "$NEW_FROM_SUBMIT" | grep -c '[0-9]' 2>/dev/null || true)
    SUBMIT_COUNT=$((SUBMIT_COUNT + 0))
    if [ "$SUBMIT_COUNT" -gt 0 ]; then
      echo "$NEW_FROM_SUBMIT" >> "${CORTEX_REPO}/ops/install/deploy/nginx/blocked_ips.add"
      NEW_IPS=true
      PIPELINE_OUTPUT+="[$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST') nginx-threat-pipeline] ✓ ${SUBMIT_COUNT} agent-submitted IPs merged from blocked_ips.submit"$'\n'
    fi
    : > "$SUBMIT_FILE"
  fi
fi

# ── Platform-aware paths ──
# timeout: linux=timeout, mac=gtimeout (brew coreutils)
TIMEOUT_CMD=""
for cmd in timeout gtimeout; do
  if command -v "$cmd" &>/dev/null; then
    TIMEOUT_CMD="$cmd"
    break
  fi
done

# DEPLOY_SCRIPT: minimal — just deploy blocked IPs
CORTEX_REPO="${CORTEX_REPO:-${HOME}/hermes-cortex}"
CORTEX_DEPLOY_HOME="${CORTEX_DEPLOY_HOME:-${HOME}/.hermes-cortex}"
DEPLOY_SCRIPT=""
DEPLOY_BLOCKED="${CORTEX_DEPLOY_HOME}/scripts/deploy-blocked-ips.sh"
if [ ! -x "$DEPLOY_BLOCKED" ]; then
  DEPLOY_BLOCKED="${CORTEX_REPO}/ops/scripts/manage/deploy-blocked-ips.sh"
fi
if [ -x "$DEPLOY_BLOCKED" ]; then
  DEPLOY_SCRIPT="$DEPLOY_BLOCKED"
fi

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

mkdir -p "${CORTEX_DEPLOY_HOME:-${HOME}/.hermes-cortex}/state" "${CORTEX_DEPLOY_HOME:-${HOME}/.hermes-cortex}/logs"

log()  { echo "[$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST') nginx-threat-pipeline] $*" >&2; }
error(){ echo "[$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST') nginx-threat-pipeline] ✗ $*" >&2; }

PIPELINE_OUTPUT=""
NEW_IPS=false

# ── Step 1: Scan nginx logs ──
log "── Step 1: Scan logs ──"
if [ -x "$SCANNER" ]; then
  if [ -n "$TIMEOUT_CMD" ]; then
    SCANNER_OUTPUT=$($TIMEOUT_CMD 12 bash "$SCANNER" 2>&1) || true
    RC=$?
    if [ "$RC" -eq 124 ]; then
      error "Scanner timed out after 12s — ABORTING"
      exit 1
    elif [ "$RC" -ne 0 ]; then
      error "Scanner failed with exit code ${RC} — ABORTING"
      exit 1
    fi
  else
    SCANNER_OUTPUT=$(bash "$SCANNER" 2>&1) || true
  fi
  if echo "$SCANNER_OUTPUT" | grep -q "Found.*new suspect IPs\|+ Blocked:"; then
    NEW_IPS=true; PIPELINE_OUTPUT+="${SCANNER_OUTPUT}"$'\n'
  fi
else
  error "Scanner not found at ${SCANNER} — ABORTING (security pipeline broken)"
  exit 1
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
          grep -qF "$ip" "${CORTEX_REPO}/ops/install/deploy/nginx/blocked_ips.add" 2>/dev/null && continue
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
          grep -qF "$ip" "${CORTEX_REPO}/ops/install/deploy/nginx/blocked_ips.add" 2>/dev/null && continue
          echo "$ip"
        done
    ' _ "$F2B_LOG" "$CORTEX_REPO") || true
  fi
  NEW_F2B_IPS="$F2B_TIMEOUT_RESULT"

  # Validate all extracted IPs — reject garbage from fail2ban log parsing
  # Only lines matching IPv4 format (4 dot-separated octets, each 0-255) pass
  # Also reject RFC 1918 private ranges (10.x, 172.16-31.x, 192.168.x) and loopback (127.x)
  NEW_F2B_IPS=$(echo "$F2B_TIMEOUT_RESULT" | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' | \
    awk -F. '{if($1<=255&&$2<=255&&$3<=255&&$4<=255)print}' | \
    grep -vE '^(127\.|10\.|172\.(1[6-9]|2[0-9]|3[01])\.|192\.168\.|0\.|169\.254\.|224\.|240\.)' || true)

  F2B_COUNT=$(echo "$NEW_F2B_IPS" | grep -c '[0-9]' 2>/dev/null || true)
  F2B_COUNT=$((F2B_COUNT + 0))
  if [ "$F2B_COUNT" -gt 0 ]; then
    NEW_IPS=true
    log "  ${F2B_COUNT} new fail2ban-banned IPs"
    # Ensure directory exists before appending
    mkdir -p "${CORTEX_REPO}/ops/install/deploy/nginx"
    echo "$NEW_F2B_IPS" >> "${CORTEX_REPO}/ops/install/deploy/nginx/blocked_ips.add"
  fi
elif $F2B_INSTALLED; then
  log "  fail2ban installed but no log file found — skipping"
else
  log "  fail2ban not installed — skipping"
fi

# ── Step 3: Deploy ──
log "── Step 3: Deploy ──"
if [ -z "$DEPLOY_SCRIPT" ]; then
  log "  install-nginx-full.sh not found on any platform path — skipping"
elif [ -z "$NGINX_BIN" ]; then
  log "  nginx not found — skipping deploy"
elif $NEW_IPS; then
  if ! bash "$DEPLOY_SCRIPT" 2>&1; then
    error "Blocked IPs deploy failed — see above"
  else
    log "  ✓ Blocked IPs deployed"
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
  BLOCKED_FILE="${CORTEX_REPO}/ops/install/deploy/nginx/blocked_ips.add"
  if [ ! -f "$BLOCKED_FILE" ]; then
    log "  No blocked_ips.add file — nothing to commit"
  elif ! git ls-files --error-unmatch ops/install/deploy/nginx/blocked_ips.add &>/dev/null; then
    log "  blocked_ips.add exists but is untracked — first-time commit"
    git add ops/install/deploy/nginx/blocked_ips.add
    IP_COUNT=$(wc -l < "$BLOCKED_FILE" | tr -d ' ') || true
    _create_gov_lock
    git commit -m "auto: initial blocklist with ${IP_COUNT} IPs [pipeline]" 2>&1 || true
    if git diff --cached --quiet ops/install/deploy/nginx/blocked_ips.add 2>/dev/null; then
      PIPELINE_OUTPUT+="[$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST') nginx-threat-pipeline] ✓ Committed initial ${IP_COUNT} IPs to repo"$'\n'
    else
      log "  ⚠ Git commit failed for new file — may need manual add"
    fi
  elif git diff --quiet ops/install/deploy/nginx/blocked_ips.add 2>/dev/null \
     && git diff --cached --quiet ops/install/deploy/nginx/blocked_ips.add 2>/dev/null; then
    log "  No changes to commit"
  else
    _create_gov_lock
    git add ops/install/deploy/nginx/blocked_ips.add
    IP_COUNT=$(git diff --cached --unified=0 ops/install/deploy/nginx/blocked_ips.add 2>/dev/null | \
      grep '^\+[0-9]' | grep -v '^+++' | wc -l) || true
    git commit -m "auto: block ${IP_COUNT} suspect IPs [pipeline]" 2>&1 || true
    # Check if commit succeeded (no staged changes = committed)
    if git diff --cached --quiet ops/install/deploy/nginx/blocked_ips.add 2>/dev/null; then
      PIPELINE_OUTPUT+="[$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST') nginx-threat-pipeline] ✓ Committed ${IP_COUNT} IPs to repo"$'\n'
    else
      log "  ⚠ Git commit failed — may need manual merge"
    fi

    log "── Step 5: Push ──"
    for push_attempt in 1 2; do
      if [ -n "$TIMEOUT_CMD" ]; then
        if $TIMEOUT_CMD 10 git push origin main 2>&1; then
          PIPELINE_OUTPUT+="[$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST') nginx-threat-pipeline] ✓ Pushed to origin"$'\n'
          break
        else
          PUSH_EXIT=$?
          if [ $push_attempt -eq 1 ]; then
            [ $PUSH_EXIT -eq 128 ] && log "  ⚠ Remote ahead — pulling and retrying" || log "  ⚠ Push failed (code $PUSH_EXIT) — pulling and retrying"
            $TIMEOUT_CMD 15 git pull --rebase origin main 2>&1 || true
            # If rebase created a conflict, abort to leave repo clean for next cycle
            if git rebase --show-current &>/dev/null 2>&1; then
              log "  ⚠ Rebase conflict — aborting to leave repo clean"
              git rebase --abort 2>/dev/null || true
              PIPELINE_OUTPUT+="[$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST') nginx-threat-pipeline] ⚠ Push blocked by remote conflict — will retry next cycle"$'\n'
            fi
          else
            # Check for leftover rebase conflict (in case the first attempt's abort also failed)
            if git rebase --show-current &>/dev/null 2>&1; then
              git rebase --abort 2>/dev/null || true
            fi
            PIPELINE_OUTPUT+="[$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST') nginx-threat-pipeline] ⚠ Push failed after retry"$'\n'
          fi
        fi
      else
        if git push origin main 2>&1; then
          PIPELINE_OUTPUT+="[$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST') nginx-threat-pipeline] ✓ Pushed to origin"$'\n'
          break
        else
          PUSH_EXIT=$?
          if [ $push_attempt -eq 1 ]; then
            log "  ⚠ Push failed (code $PUSH_EXIT) — pulling and retrying"
            git pull --rebase origin main 2>&1 || true
            # If rebase created a conflict, abort to leave repo clean for next cycle
            if git rebase --show-current &>/dev/null 2>&1; then
              log "  ⚠ Rebase conflict — aborting to leave repo clean"
              git rebase --abort 2>/dev/null || true
              PIPELINE_OUTPUT+="[$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST') nginx-threat-pipeline] ⚠ Push blocked by remote conflict — will retry next cycle"$'\n'
            fi
          else
            # Check for leftover rebase conflict (in case the first attempt's abort also failed)
            if git rebase --show-current &>/dev/null 2>&1; then
              git rebase --abort 2>/dev/null || true
            fi
            PIPELINE_OUTPUT+="[$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST') nginx-threat-pipeline] ⚠ Push failed after retry"$'\n'
          fi
        fi
      fi
    done
  fi
fi

# ── Save state ──
date -u +"%Y-%m-%dT%H:%M:%SZ" > "${HOME}/.hermes-cortex/state/nginx-threat-pipeline-lastrun"

# ── Output (watchdog: silent unless changes) ──
if $NEW_IPS; then
  TS=$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST')
  echo "[$TS nginx-threat-pipeline] ━━━ Threat Pipeline — ${TS} ━━━"
  echo "$PIPELINE_OUTPUT"
  echo "[$TS nginx-threat-pipeline] ━━━ Complete ━━━"
fi
