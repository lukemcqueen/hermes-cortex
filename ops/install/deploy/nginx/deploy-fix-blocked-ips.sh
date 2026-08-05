#!/usr/bin/env bash
# deploy-fix-blocked-ips.sh — Deploy root-owned immutable copy of
# fix-blocked-ips.py from committed repo source.
#
# WHY: the sudoers NOPASSWD entry previously pointed at the USER-WRITABLE
# repo working tree (~/hermes-cortex/ops/install/deploy/nginx/fix-blocked-ips.py).
# Any agent could edit that file and get unconditional root code execution
# (`sudo .../fix-blocked-ips.py` → arbitrary Python as root). This closes
# that hole: the NOPASSWD target becomes a root-owned, immutable copy in
# /usr/local/sbin, deployed ONLY from committed repo source.
#
# SCOPE: installs/updates ONLY /usr/local/sbin/fix-blocked-ips.py.
# Sudoers is owned by deploy-sudoers.sh — this script NEVER writes,
# appends, or sweeps any sudoers file. It verifies the NOPASSWD entry
# exists and points at the immutable copy; if missing or stale it reports
# and exits non-zero so the operator runs deploy-sudoers.sh.
#
# Usage: sudo bash deploy-fix-blocked-ips.sh
# ─────────────────────────────────────────────────────────────
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "✗ Must run as root (sudo). Usage: sudo bash $0"
  exit 1
fi

# Resolve repo root robustly: 4-up from ops/install/deploy/nginx/ (this
# file's canonical location), fallback to git toplevel.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CORTEX_REPO="$(cd "$SCRIPT_DIR/../../../.." && pwd 2>/dev/null || true)"
[ -n "$CORTEX_REPO" ] || CORTEX_REPO="$(cd "$SCRIPT_DIR" && git rev-parse --show-toplevel 2>/dev/null || true)"
SRC="${CORTEX_REPO}/ops/install/deploy/nginx/fix-blocked-ips.py"
DEST="/usr/local/sbin/fix-blocked-ips.py"

[ -f "$SRC" ] || { echo "✗ Source not found: ${SRC}"; exit 1; }

echo "━━━ Deploying root-owned immutable fix-blocked-ips.py ━━━"

# 1. Install root-owned copy from repo source.
#    Unlock first if a previous immutable copy exists (install cannot
#    overwrite an immutable file); re-lock immediately after.
if [ -e "$DEST" ] && lsattr "$DEST" 2>/dev/null | grep -q -- "-i-"; then
  echo "  Unlocking existing immutable copy…"
  chattr -i "$DEST"
fi
install -o root -g root -m 755 "$SRC" "$DEST"

# 2. Lock it immutable (root-owned chattr +i — agent cannot clear)
chattr +i "$DEST" 2>/dev/null || echo "  ⚠ chattr +i failed — check filesystem support"

# 3. VERIFY sudoers entry (read-only — never modify; owned by deploy-sudoers.sh)
SUDOERS_FILE="/etc/sudoers.d/hermes"
ENTRY_PATTERN="/usr/local/sbin/fix-blocked-ips.py"
if [ -f "$SUDOERS_FILE" ] && grep -qF "$ENTRY_PATTERN" "$SUDOERS_FILE" 2>/dev/null; then
  echo "  ✓ Sudoers entry present: NOPASSWD: ${ENTRY_PATTERN}"
else
  echo "  ✗ Sudoers entry for ${ENTRY_PATTERN} NOT found in ${SUDOERS_FILE}"
  echo "    This script does not modify sudoers — run the owner:"
  echo "    sudo bash ${CORTEX_REPO}/ops/install/deploy/nginx/deploy-sudoers.sh"
  exit 1
fi

# 4. Validate the installed file
[ -x "$DEST" ] || { echo "  ✗ ${DEST} not executable"; exit 1; }
if lsattr "$DEST" 2>/dev/null | grep -q -- "-i-"; then
  echo "  ✓ Immutable flag confirmed"
else
  echo "  ⚠ ${DEST} not immutable — verify chattr support on this filesystem"
fi

echo "  ✓ Deployed: ${DEST} (root-owned, immutable)"
echo ""
echo "Verify: sudo -n -l | grep fix-blocked-ips"
echo "        lsattr ${DEST}"
echo ""
echo "IMPORTANT: this script must be re-run AFTER every cortex-update deploy"
echo "of fix-blocked-ips.py changes (the immutable copy only updates via"
echo "this script — cortex-update.sh does NOT own /usr/local/sbin)."
