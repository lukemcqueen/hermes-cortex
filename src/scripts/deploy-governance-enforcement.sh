#!/bin/bash
# =============================================================================
# deploy-governance-enforcement.sh — Install governance enforcement hook
# =============================================================================
# Installs the guard-governance.sh pre_tool_call hook and registers it in
# ~/.hermes/config.yaml so it fires on every tool call.
#
# Usage:
#   bash deploy-governance-enforcement.sh
#
# This hook blocks write tools (write_file, patch, terminal, execute_code,
# skill_manage, cronjob) unless a governance lock is active via
# mcp_loop_governance_begin_change().
#
# To verify the hook is installed:
#   hermes hooks list
#   hermes hooks doctor
# =============================================================================

set -euo pipefail

REPO_DIR="${CORTEX_REPO:-$HOME/hermes-cortex}"
HOOK_SOURCE="$REPO_DIR/src/hooks/guard-governance.sh"
HOOK_TARGET="$HOME/.hermes/hooks/guard-governance.sh"
CONFIG="$HOME/.hermes/config.yaml"
HOOKS_CONFIG_BLOCK="hooks:
  pre_tool_call:
    - command: $HOOK_TARGET
      timeout: 3"

echo "🔧 Deploying governance enforcement hook..."

# Step 1: Copy hook script
mkdir -p "$HOME/.hermes/hooks"
cp "$HOOK_SOURCE" "$HOOK_TARGET"
chmod 755 "$HOOK_TARGET"
echo "  ✅ Hook script installed: $HOOK_TARGET"

# Step 2: Register in config.yaml (if not already there)
if grep -q "guard-governance.sh" "$CONFIG" 2>/dev/null; then
  echo "  ✅ Hook already registered in config.yaml"
else
  # Add before mcp_servers section
  if grep -q "^mcp_servers:" "$CONFIG"; then
    # Use sed to insert before mcp_servers
    sed -i "/^mcp_servers:/i $HOOKS_CONFIG_BLOCK" "$CONFIG"
    echo "  ✅ Hook registered in config.yaml"
  else
    # Append at end
    echo "" >> "$CONFIG"
    echo "$HOOKS_CONFIG_BLOCK" >> "$CONFIG"
    echo "  ✅ Hook appended to config.yaml"
  fi
fi

# Step 3: Verify hook is properly registered
echo ""
echo "🔧 Verification:"
echo "  Run: hermes hooks list"
echo "  Run: hermes hooks doctor"
echo ""
echo "⚠️  NOTE: The hook takes effect on next Hermes session."
echo "  If you're in an active session, start a new one with --accept-hooks"
echo "  to activate the governance enforcement."
echo ""
echo "✅ Deployment complete."