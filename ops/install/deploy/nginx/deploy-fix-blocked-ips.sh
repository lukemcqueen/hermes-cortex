#!/usr/bin/env bash
# deploy-fix-blocked-ips.sh — Deploy root-owned immutable copy of
# fix-blocked-ips.py from committed repo source.
#
# WHY: the sudoers NOPASSWD entry previously pointed at the USER-WRITABLE
# repo working tree (~/hermes-cortex/ops/install/deploy/nginx/fix-blocked-ips.py).
# Any agent could edit that file and get unconditional root code execution
# (`sudo .../fix-blocked-ips.py` → arbitrary Python as root). This closes
# that hole: the NOPASSWD target becomes a root-owned, immutable copy in
# /usr/local/sbin (Linux) or /usr/local/bin (macOS), deployed ONLY from
# committed repo source.
#
# SCOPE: installs/updates ONLY the root-owned fix-blocked-ips.py copy.
# Sudoers is owned by deploy-sudoers.sh — this script NEVER writes,
# appends, or sweeps any sudoers file. It verifies the NOPASSWD entry
# exists and points at the immutable copy; if missing or stale it reports
# and exits non-zero so the operator runs deploy-sudoers.sh.
#
# macOS portability (2026-08-05, Titus): Linux uses /usr/local/sbin +
# chattr/lsattr + group root; macOS uses /usr/local/bin + chflags/nouchg +
# group wheel (no root group). The doctor check (checks.py) is already
# platform-aware — this script now matches it.
#
# Usage: sudo bash deploy-fix-blocked-ips.sh
# ─────────────────────────────────────────────────────────────
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "✗ Must run as root (sudo). Usage: sudo bash $0"
  exit 1
fi

# Platform detection (macOS vs Linux)
IS_MACOS=0
[ "$(uname -s)" = "Darwin" ] && IS_MACOS=1

# Resolve repo root robustly: 4-up from ops/install/deploy/nginx/ (this
# file's canonical location), fallback to git toplevel.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CORTEX_REPO="$(cd "$SCRIPT_DIR/../../../.." && pwd 2>/dev/null || true)"
[ -n "$CORTEX_REPO" ] || CORTEX_REPO="$(cd "$SCRIPT_DIR" && git rev-parse --show-toplevel 2>/dev/null || true)"
SRC="${CORTEX_REPO}/ops/install/deploy/nginx/fix-blocked-ips.py"
if [ "$IS_MACOS" -eq 1 ]; then
  DEST="/usr/local/bin/fix-blocked-ips.py"
  DEST_GROUP="wheel"
else
  DEST="/usr/local/sbin/fix-blocked-ips.py"
  DEST_GROUP="root"
fi

[ -f "$SRC" ] || { echo "✗ Source not found: ${SRC}"; exit 1; }

echo "━━━ Deploying root-owned immutable fix-blocked-ips.py ━━━"
echo "  Platform: $([ "$IS_MACOS" -eq 1 ] && echo macOS || echo Linux)"
echo "  Dest:     ${DEST}"

# ── Immutability helpers (platform-aware) ────────────────────
# Linux: chattr +i / lsattr (e2fs). macOS: chflags uchg / nouchg.
# chattr/lsattr are ABSENT on macOS (Titus 2026-08-05) — chflags is the
# macOS equivalent. Guarded so a missing tool never fails the deploy.
unlock_file() {
  if [ "$IS_MACOS" -eq 1 ]; then
    chflags nouchg "$1" 2>/dev/null || true
  else
    if command -v chattr >/dev/null 2>&1; then
      chattr -i "$1" 2>/dev/null || true
    fi
  fi
}

lock_file() {
  if [ "$IS_MACOS" -eq 1 ]; then
    chflags uchg "$1" 2>/dev/null || echo "  ⚠ chflags uchg failed — check filesystem support"
  else
    if command -v chattr >/dev/null 2>&1; then
      chattr +i "$1" 2>/dev/null || echo "  ⚠ chattr +i failed — check filesystem support"
    else
      echo "  ⚠ chattr not available — immutability not enforced (Linux)"
    fi
  fi
}

is_locked() {
  if [ "$IS_MACOS" -eq 1 ]; then
    # chflags uchg shows as "uchg" in `ls -lO` flags column
    ls -lO "$1" 2>/dev/null | grep -q "uchg"
  else
    command -v lsattr >/dev/null 2>&1 && lsattr "$1" 2>/dev/null | grep -q -- "-i-"
  fi
}

# 1. Install root-owned copy from repo source.
#    Unlock first if a previous immutable copy exists (install cannot
#    overwrite an immutable file); re-lock immediately after.
if [ -e "$DEST" ] && is_locked "$DEST"; then
  echo "  Unlocking existing immutable copy…"
  unlock_file "$DEST"
fi
install -o root -g "$DEST_GROUP" -m 755 "$SRC" "$DEST"

# 2. Lock it immutable (root-owned — agent cannot clear)
lock_file "$DEST"

# 3. VERIFY sudoers entry (read-only — never modify; owned by deploy-sudoers.sh)
SUDOERS_FILE="/etc/sudoers.d/hermes"
# Platform-appropriate path; the sudoers template carries BOTH entries
# (dead entry on the other platform — sudoers ignores non-matching paths).
ENTRY_PATTERN="$DEST"
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
if is_locked "$DEST"; then
  echo "  ✓ Immutable flag confirmed"
else
  echo "  ⚠ ${DEST} not immutable — verify $( [ "$IS_MACOS" -eq 1 ] && echo 'chflags' || echo 'chattr' ) support on this filesystem"
fi

echo "  ✓ Deployed: ${DEST} (root-owned, immutable)"
echo ""
echo "Verify: sudo -n -l | grep fix-blocked-ips"
echo "        $([ "$IS_MACOS" -eq 1 ] && echo 'ls -lO' || echo 'lsattr') ${DEST}"
echo ""
echo "IMPORTANT: this script must be re-run AFTER every cortex-update deploy"
echo "of fix-blocked-ips.py changes (the immutable copy only updates via"
echo "this script — cortex-update.sh does NOT own /usr/local/sbin|bin)."
