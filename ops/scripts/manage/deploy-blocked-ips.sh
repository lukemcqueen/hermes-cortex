#!/usr/bin/env bash
# deploy-blocked-ips.sh — Thin wrapper around fix-blocked-ips.py
#
# Single sudo invocation handles the full lifecycle:
#   generate → atomic rename → nginx -t → nginx -s reload
#
# Usage:
#   bash deploy-blocked-ips.sh           # full deploy via sudo
#   bash deploy-blocked-ips.sh --check   # dry-run (generate + validate only)
#
# Requires NOPASSWD:
#   moses ALL=(root) NOPASSWD: $HOME/hermes-cortex/ops/install/deploy/nginx/fix-blocked-ips.py
# ─────────────────────────────────────────────────────────────
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORTEX_REPO="${CORTEX_REPO:-${HOME}/hermes-cortex}"
if [ ! -d "$CORTEX_REPO" ]; then
  CORTEX_REPO="$(cd "$SCRIPT_DIR/../.." && pwd 2>/dev/null || echo "$HOME/hermes-cortex")"
fi

# Sudoers NOPASSWD matches the old path (deploy/nginx/), not ops/install/deploy/nginx/
FIX_SCRIPT="${CORTEX_REPO}/deploy/nginx/fix-blocked-ips.py"

if [ ! -f "$FIX_SCRIPT" ]; then
  echo "[deploy-blocked-ips] ✗ fix-blocked-ips.py not found at ${FIX_SCRIPT}"
  exit 1
fi

log()   { echo "[$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST') deploy-blocked-ips] $*"; }
error() { echo "[$(TZ=Asia/Seoul date '+%Y-%m-%d %H:%M KST') deploy-blocked-ips] ✗ $*"; }

CHECK_ONLY="${1:-}"

if [ "$CHECK_ONLY" = "--check" ]; then
  log "── Check only ──"
  python3 "$FIX_SCRIPT" 2>&1 || {
    error "Config generation failed"
    exit 1
  }
  log "  ✓ Check complete — not deploying"
  exit 0
fi

# ── Full deploy via single sudo invocation ──
log "── Deploy blocked IPs ──"
if sudo -n "$FIX_SCRIPT" 2>&1; then
  log "  ✓ Deploy complete"
else
  EXIT_CODE=$?
  error "fix-blocked-ips.py failed (exit ${EXIT_CODE})"
  exit $EXIT_CODE
fi
