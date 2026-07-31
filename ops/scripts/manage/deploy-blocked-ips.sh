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
# Requires NOPASSWD (deployed root-owned immutable copy — NOT the repo copy,
# which is user-writable and would be an arbitrary-root-code-execution hole):
#   moses ALL=(root) NOPASSWD: /usr/local/sbin/fix-blocked-ips.py
# Deploy the root copy with:
#   sudo bash ~/hermes-cortex/ops/install/deploy/nginx/deploy-fix-blocked-ips.sh
# ─────────────────────────────────────────────────────────────
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CORTEX_REPO="${CORTEX_REPO:-${HOME}/hermes-cortex}"
if [ ! -d "$CORTEX_REPO" ]; then
  CORTEX_REPO="$(cd "$SCRIPT_DIR/../.." && pwd 2>/dev/null || echo "$HOME/hermes-cortex")"
fi

# P1-A hardening (2026-07-31): prefer the root-owned immutable deployed copy
# at /usr/local/sbin. Fall back to the repo copy ONLY for --check (read-only).
FIX_SCRIPT="/usr/local/sbin/fix-blocked-ips.py"
if [ ! -f "$FIX_SCRIPT" ]; then
  FIX_SCRIPT="${CORTEX_REPO}/ops/install/deploy/nginx/fix-blocked-ips.py"
  echo "[deploy-blocked-ips] ⚠ using repo copy — deploy the root-owned copy:" >&2
  echo "[deploy-blocked-ips]   sudo bash ~/hermes-cortex/ops/install/deploy/nginx/deploy-fix-blocked-ips.sh" >&2
fi

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
