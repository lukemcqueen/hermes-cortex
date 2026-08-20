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

# Timezone-aware timestamp: honors HERMES_TIMEZONE (IANA), else system TZ.
ts() {
  if [[ -n "${HERMES_TIMEZONE:-}" ]]; then
    TZ="${HERMES_TIMEZONE}" date '+%Y-%m-%d %H:%M %Z'
  else
    date '+%Y-%m-%d %H:%M %Z'
  fi
}
# Requires NOPASSWD (deployed root-owned immutable copy — NOT the repo copy,
# which is user-writable and would be an arbitrary-root-code-execution hole):
#   moses ALL=(root) NOPASSWD: /usr/local/sbin/fix-blocked-ips.py
# Deploy the root copy with:
#   sudo bash ~/hermes-cortex/ops/install/deploy/nginx/deploy-fix-blocked-ips.sh
# ─────────────────────────────────────────────────────────────
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Resolve repo root robustly: env → git toplevel → 3-up (repo layout) →
# canonical $HOME/hermes-cortex. Each candidate is VALIDATED against the
# actual fix-blocked-ips.py path, so the script works identically from the
# repo location (ops/scripts/manage/) and the DEPLOYED location
# (~/.hermes-cortex/scripts/), where git rev-parse fails and ../../.. lands
# on /home (regression 2026-08-05: pipeline deploy step failed with
# "fix-blocked-ips.py not found at /home/ops/...").
CORTEX_REPO="${CORTEX_REPO:-}"
if [ -z "$CORTEX_REPO" ] || [ ! -f "$CORTEX_REPO/ops/install/deploy/nginx/fix-blocked-ips.py" ]; then
  CORTEX_REPO="$(cd "$SCRIPT_DIR" && git rev-parse --show-toplevel 2>/dev/null || true)"
fi
if [ -z "$CORTEX_REPO" ] || [ ! -f "$CORTEX_REPO/ops/install/deploy/nginx/fix-blocked-ips.py" ]; then
  CORTEX_REPO="$(cd "$SCRIPT_DIR/../../.." && pwd 2>/dev/null || true)"
fi
if [ -z "$CORTEX_REPO" ] || [ ! -f "$CORTEX_REPO/ops/install/deploy/nginx/fix-blocked-ips.py" ]; then
  CORTEX_REPO="${HOME}/hermes-cortex"
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

log()   { echo "[$(ts) deploy-blocked-ips] $*"; }
error() { echo "[$(ts) deploy-blocked-ips] ✗ $*"; }

CHECK_ONLY="${1:-}"

# --repo <path>: pass the resolved repo root explicitly. REQUIRED when the
# target script runs under sudo — sudo's env_reset sets HOME=/root and
# blocks HOME/CORTEX_REPO env overrides, so the Python repo_dir() $HOME
# fallback silently misses on Linux. argv is the only channel sudo allows.
REPO_ARG="--repo ${CORTEX_REPO}"

if [ "$CHECK_ONLY" = "--check" ]; then
  log "── Check only ──"
  python3 "$FIX_SCRIPT" $REPO_ARG 2>&1 || {
    error "Config generation failed"
    exit 1
  }
  log "  ✓ Check complete — not deploying"
  exit 0
fi

# ── Full deploy via single sudo invocation ──
log "── Deploy blocked IPs ──"
if sudo -n "$FIX_SCRIPT" $REPO_ARG 2>&1; then
  log "  ✓ Deploy complete"
else
  EXIT_CODE=$?
  error "fix-blocked-ips.py failed (exit ${EXIT_CODE})"
  exit $EXIT_CODE
fi
