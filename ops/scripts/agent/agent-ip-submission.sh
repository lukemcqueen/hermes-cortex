#!/usr/bin/env bash
# agent-ip-submission.sh — Process agent-submitted IPs into blocked_ips.add
#
# Agents (Gisu, Moses, Titus) write IPs to ops/install/deploy/nginx/blocked_ips.submit.
# This script validates, deduplicates, and merges them into blocked_ips.add,
# then clears the submit file. Silent when no submissions (watchdog pattern).
#
# Schedule: every 30 minutes via cron (no_agent: true).
set -euo pipefail

CORTEX_REPO="${CORTEX_REPO:-${HOME}/hermes-cortex}"
SUBMIT_FILE="${CORTEX_REPO}/ops/install/ops/install/deploy/nginx/blocked_ips.submit"
ADD_FILE="${CORTEX_REPO}/ops/install/ops/install/deploy/nginx/blocked_ips.add"
NEW_IPS=false
PIPELINE_OUTPUT=""

log()  { echo "[$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST')] agent-ip-submission: $*"; }
error(){ echo "[$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST')] agent-ip-submission: ✗ $*"; }

# ── Guard: no submit file or empty ──
if [ ! -f "$SUBMIT_FILE" ]; then
  exit 0
fi

SUBMIT_RAW=$(grep -v '^#' "$SUBMIT_FILE" 2>/dev/null | grep -v '^[[:space:]]*$' || true)
if [ -z "$SUBMIT_RAW" ]; then
  exit 0
fi

# ── Validate IPv4 ──
VALID_IPS=$(echo "$SUBMIT_RAW" | grep -E '^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$' | \
  awk -F. '{if($1<=255&&$2<=255&&$3<=255&&$4<=255)print}' || true)

SUBMIT_COUNT=$(echo "$VALID_IPS" | grep -c '[0-9]' 2>/dev/null || true)
SUBMIT_COUNT=$((SUBMIT_COUNT + 0))

if [ "$SUBMIT_COUNT" -eq 0 ]; then
  # Silent no-op: nothing valid to process
  : > "$SUBMIT_FILE"
  exit 0
fi

log "── Agent IP Submission Processor ──"

# ── Deduplicate against blocked_ips.add ──
NEW_ENTRIES=""
while IFS= read -r ip; do
  [ -z "$ip" ] && continue
  if ! grep -qF "$ip" "$ADD_FILE" 2>/dev/null; then
    NEW_ENTRIES+="${ip}"$'\n'
  fi
done <<< "$VALID_IPS"

NEW_COUNT=$(echo "$NEW_ENTRIES" | grep -c '[0-9]' 2>/dev/null || true)
NEW_COUNT=$((NEW_COUNT + 0))

if [ "$NEW_COUNT" -eq 0 ]; then
  # Silent no-op: all already blocked
  : > "$SUBMIT_FILE"
  exit 0
fi

# ── Append new IPs to blocked_ips.add ──
echo "$NEW_ENTRIES" >> "$ADD_FILE"
NEW_IPS=true
PIPELINE_OUTPUT+="  ✓ Added ${NEW_COUNT} agent-submitted IPs to blocked_ips.add"$'\n'

# ── Clear submit file ──
: > "$SUBMIT_FILE"
PIPELINE_OUTPUT+="  ✓ Cleared blocked_ips.submit"$'\n'

# ── Commit and push ──
cd "$CORTEX_REPO"
if git diff --quiet ops/install/deploy/nginx/blocked_ips.add 2>/dev/null; then
  log "  No git changes (unexpected) — skipping commit"
else
  git add ops/install/deploy/nginx/blocked_ips.add ops/install/deploy/nginx/blocked_ips.submit 2>/dev/null || git add ops/install/deploy/nginx/blocked_ips.add
  SKIP_SCORE=1 git commit -m "auto: block ${NEW_COUNT} agent-submitted IPs [pipeline]" 2>&1 || true

  # Push with retry
  for push_attempt in 1 2; do
    if SKIP_PRE_PUSH=1 git push origin main 2>&1; then
      PIPELINE_OUTPUT+="  ✓ Pushed to origin"$'\n'
      break
    else
      PUSH_EXIT=$?
      if [ $push_attempt -eq 1 ]; then
        log "  ⚠ Push failed (code ${PUSH_EXIT}) — pulling and retrying"
        git pull --rebase origin main 2>&1 || true
      else
        PIPELINE_OUTPUT+="  ⚠ Push failed after retry"$'\n'
      fi
    fi
  done
fi

# ── Deploy live if deploy-blocked-ips is available ──
DEPLOY_BLOCKED="${CORTEX_DEPLOY_HOME:-${HOME}/.hermes-cortex}/scripts/deploy-blocked-ips.sh"
if [ ! -x "$DEPLOY_BLOCKED" ]; then
  DEPLOY_BLOCKED="${CORTEX_REPO}/ops/scripts/manage/deploy-blocked-ips.sh"
fi
if [ -x "$DEPLOY_BLOCKED" ]; then
  if bash "$DEPLOY_BLOCKED" 2>&1; then
    PIPELINE_OUTPUT+="  ✓ Deployed live via deploy-blocked-ips"$'\n'
  else
    log "  ⚠ Deploy failed — will be picked up by daily pipeline"
  fi
else
  log "  deploy-blocked-ips.sh not found — IPs will be deployed by daily threat-pipeline"
fi

# ── Output ──
echo ""
echo "━━━ Agent IP Submission — $(date '+%Y-%m-%d %H:%M:%S') ━━━"
echo "$PIPELINE_OUTPUT"
echo "━━━ Complete ━━━"
