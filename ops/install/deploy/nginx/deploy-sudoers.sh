#!/usr/bin/env bash
# deploy-sudoers.sh — Deploy missing NOPASSWD sudo rules for nginx security pipeline
#
# The source file deploy/nginx/hermes-security contains all needed sudoers rules,
# but lines 30-33 (install-nginx-full.sh + blocked_ips.conf cp) were never deployed
# to /etc/sudoers.d/hermes-security. This script deploys them.
#
# Usage: sudo bash deploy-sudoers.sh
# Run this once, then the daily threat-pipeline cron can deploy IPs automatically.

set -euo pipefail

CORTEX_REPO="$(cd "$(dirname "$0")/../.." && pwd)"
SOURCE_FILE="${CORTEX_REPO}/ops/install/deploy/nginx/hermes-security"
TARGET_FILE="/etc/sudoers.d/hermes-security"

if [ ! -f "$SOURCE_FILE" ]; then
  echo "✗ Source file not found at ${SOURCE_FILE}"
  exit 1
fi

if [ "$(id -u)" -ne 0 ]; then
  echo "✗ Must run as root (sudo). Usage: sudo bash $0"
  exit 1
fi

echo "━━━ Deploying NOPASSWD sudo rules ━━━"
echo "  Source: ${SOURCE_FILE}"
echo "  Target: ${TARGET_FILE}"

# Validate source file syntax
if visudo -c -f "$SOURCE_FILE" 2>&1; then
  echo "  ✓ Source file syntax valid"
else
  echo "  ✗ Source file has syntax errors — aborting"
  exit 1
fi

# Backup existing sudoers file
if [ -f "$TARGET_FILE" ]; then
  cp "$TARGET_FILE" "${TARGET_FILE}.bak.$(date +%Y%m%d-%H%M%S)"
  echo "  ✓ Backed up existing sudoers file"
fi

# Deploy the complete rules
cp "$SOURCE_FILE" "$TARGET_FILE"
chmod 0440 "$TARGET_FILE"
chown root:root "$TARGET_FILE"

echo "  ✓ Deployed ${TARGET_FILE}"

# Validate the deployed file
if visudo -c -f "$TARGET_FILE" 2>&1; then
  echo "  ✓ Deployed sudoers syntax valid"
else
  echo "  ✗ Deployed sudoers has syntax errors — restoring backup"
  if ls "${TARGET_FILE}.bak."* 2>/dev/null; then
    cp "$(ls -t "${TARGET_FILE}.bak."* | head -1)" "$TARGET_FILE"
    echo "  ✓ Backup restored"
  fi
  exit 1
fi

echo ""
echo "━━━ Complete ━━━"
echo ""
echo "Now test the pipeline deploy:"
echo "  sudo /usr/local/sbin/install-nginx-full.sh"
echo ""
echo "The daily threat-pipeline cron should now deploy automatically."
