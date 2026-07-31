#!/usr/bin/env bash
# deploy-fix-blocked-ips.sh — Deploy root-owned immutable copy of
# fix-blocked-ips.py and re-point the sudoers entry to it.
#
# WHY: the sudoers NOPASSWD entry previously pointed at the USER-WRITABLE
# repo working tree (~/hermes-cortex/ops/install/deploy/nginx/fix-blocked-ips.py).
# Any agent could edit that file and get unconditional root code execution
# (`sudo .../fix-blocked-ips.py` → arbitrary Python as root). This closes
# that hole: the NOPASSWD target becomes a root-owned, immutable copy in
# /usr/local/sbin, deployed ONLY from committed repo source.
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
SUDOERS_FILE="/etc/sudoers.d/hermes-security"

[ -f "$SRC" ] || { echo "✗ Source not found: ${SRC}"; exit 1; }

echo "━━━ Deploying root-owned immutable fix-blocked-ips.py ━━━"

# 1. Remove the OLD repo-path sudoers entry from EVERY sudoers.d file.
#    The old entry (from /etc/sudoers.d/hermes, deployed 2026-07-27)
#    pointed at the user-writable repo working tree — a root-ACE.
#    Sweep all files; sed on each one that contains the old path.
OLD_PATTERN="/home/moses/hermes-cortex/ops/install/deploy/nginx/fix-blocked-ips.py"
for f in /etc/sudoers.d/*; do
  [ -f "$f" ] || continue
  if grep -qF "$OLD_PATTERN" "$f" 2>/dev/null; then
    echo "  Removing old repo-path entry from $f"
    sed -i "\|${OLD_PATTERN}|d" "$f"
    chmod 0440 "$f" 2>/dev/null || true
  fi
done
# Also sweep /etc/sudoers itself (in case a line landed there)
if [ -f /etc/sudoers ] && grep -qF "$OLD_PATTERN" /etc/sudoers 2>/dev/null; then
  echo "  Removing old repo-path entry from /etc/sudoers"
  sed -i "\|${OLD_PATTERN}|d" /etc/sudoers
fi

# 2. Install root-owned copy from repo source
install -o root -g root -m 755 "$SRC" "$DEST"

# 3. Lock it immutable (root-owned chattr +i — agent cannot clear)
chattr +i "$DEST" 2>/dev/null || echo "  ⚠ chattr +i failed — check filesystem support"

# 4. Re-point sudoers to the immutable copy (append if not present)
if ! grep -q "/usr/local/sbin/fix-blocked-ips.py" "$SUDOERS_FILE" 2>/dev/null; then
  echo "moses ALL=(root) NOPASSWD: /usr/local/sbin/fix-blocked-ips.py" >> "$SUDOERS_FILE"
fi
chmod 0440 "$SUDOERS_FILE" 2>/dev/null || true

# 5. Validate sudoers
if command -v visudo &>/dev/null; then
  visudo -c -f "$SUDOERS_FILE" 2>&1 | tail -2
fi

echo "  ✓ Deployed: ${DEST} (root-owned, immutable)"
echo "  ✓ Sudoers re-pointed to ${DEST}"
echo "  ✓ Old repo-path entry removed (swept all sudoers.d + /etc/sudoers)"
echo ""
echo "Verify: sudo -n -l | grep fix-blocked-ips"
echo "        lsattr ${DEST}"
echo ""
echo "IMPORTANT: this script must be re-run AFTER every cortex-update deploy"
echo "of fix-blocked-ips.py changes (the immutable copy only updates via"
echo "this script — cortex-update.sh does NOT own /usr/local/sbin)."
