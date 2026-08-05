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

CORTEX_REPO="$(cd "$(dirname "$0")/../../../.." && pwd)"
CORTEX_DEPLOY_HOME="${CORTEX_DEPLOY_HOME:-${HOME}/.hermes-cortex}"
SOURCE_FILE="${CORTEX_REPO}/ops/install/deploy/nginx/hermes-security"
# Single sudoers file policy (2026-07-31): ALL hermes rules deploy to
# /etc/sudoers.d/hermes. hermes-security was the old split target — kept
# as the repo source name for continuity, but the deploy target is hermes.
TARGET_FILE="/etc/sudoers.d/hermes"

# Remove the obsolete split file if present (one-file policy)
if [ -f /etc/sudoers.d/hermes-security ]; then
  echo "  Removing obsolete /etc/sudoers.d/hermes-security (one-file policy)"
  rm -f /etc/sudoers.d/hermes-security
fi

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

# Resolve the sudo user list (2026-08-05): real account names are PII and
# must NOT live in the public template. Read CORTEX_SUDO_USERS from the
# host's PRIVATE env (~/.hermes-cortex/.env, never committed); fall back
# to the user running this deploy.
SUDO_USERS=""
if [ -f "$CORTEX_DEPLOY_HOME/.env" ]; then
  SUDO_USERS="$(grep '^CORTEX_SUDO_USERS=' "$CORTEX_DEPLOY_HOME/.env" 2>/dev/null | head -1 | cut -d= -f2- || true)"
fi
if [ -z "$SUDO_USERS" ] && [ -f "$HOME/.hermes-cortex/.env" ]; then
  SUDO_USERS="$(grep '^CORTEX_SUDO_USERS=' "$HOME/.hermes-cortex/.env" 2>/dev/null | head -1 | cut -d= -f2- || true)"
fi
if [ -z "$SUDO_USERS" ]; then
  SUDO_USERS="$(id -un)"
  echo "  ⚠ CORTEX_SUDO_USERS not set — granting to deploying user only: ${SUDO_USERS}"
else
  echo "  ✓ Sudo user list: ${SUDO_USERS}"
fi

# Render the template with the placeholder substituted
RENDERED_FILE="${TARGET_FILE}.rendered"
sed "s/__SUDO_USERS__/${SUDO_USERS}/g" "$SOURCE_FILE" > "$RENDERED_FILE"

# Validate the RENDERED content (placeholder substitution could break syntax)
if visudo -c -f "$RENDERED_FILE" 2>&1; then
  echo "  ✓ Rendered sudoers syntax valid"
else
  echo "  ✗ Rendered sudoers has syntax errors — aborting"
  rm -f "$RENDERED_FILE"
  exit 1
fi

# Backup existing sudoers file
if [ -f "$TARGET_FILE" ]; then
  cp "$TARGET_FILE" "${TARGET_FILE}.bak.$(date +%Y%m%d-%H%M%S)"
  echo "  ✓ Backed up existing sudoers file"
fi

# Deploy the complete rules
cp "$RENDERED_FILE" "$TARGET_FILE"
rm -f "$RENDERED_FILE"
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
