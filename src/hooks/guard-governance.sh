#!/bin/bash
# =============================================================================
# guard-governance.sh — Hermes pre_tool_call enforcement hook
# =============================================================================
# Blocks write tools (write_file, patch, terminal, execute_code, skill_manage,
# cronjob) unless a governance lock is active via mcp_loop_governance_begin_change.
#
# The lock file is created by the loop-governance MCP server at:
#   ~/.hermes-cortex/state/.governance-active.json
#
# This hook fires on every tool call. If the tool is a write tool and no lock
# exists, the call is blocked with a clear message telling the agent to call
# begin_change first.
#
# For the canonical list of allowed (read-only) tools, see the READ_ONLY_PREFIXES
# and READ_ONLY_TOOLS arrays below.
# =============================================================================

set -euo pipefail

# Parse stdin: JSON payload from Hermes with {tool_name, args, session_id, ...}
INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | python3 -c "
import sys, json
try:
    print(json.load(sys.stdin).get('tool_name', ''))
except:
    print('')
" 2>/dev/null || echo "")

# If parsing failed, allow (safety: don't break everything)
if [ -z "$TOOL_NAME" ]; then
  echo '{"action": "allow"}'
  exit 0
fi

# ── Phase 1: Always-allow tools ──────────────────────────────────────────

# Governance tools — these are how you START a governance session
case "$TOOL_NAME" in
  mcp_loop_governance_begin_change|mcp_loop_governance_end_change|mcp_loop_governance_check_lock|mcp_loop_governance_cycle_query|mcp_loop_governance_cycle_stats|mcp_loop_governance_feedback_accept|mcp_loop_governance_feedback_override|mcp_loop_governance_cache_search|mcp_loop_governance_config_show|mcp_loop_governance_config_set)
    echo '{"action": "allow"}'
    exit 0
    ;;
esac

# Read-only tools — these never write to the filesystem or system state
case "$TOOL_NAME" in
  read_file|search_files|web_search|web_extract|session_search|clarify|todo|delegate_task|vision_analyze|image_generate|text_to_speech)
    echo '{"action": "allow"}'
    exit 0
    ;;
  mcp_agent_inbox_inbox_read|mcp_agent_inbox_inbox_watch)
    echo '{"action": "allow"}'
    exit 0
    ;;
  skill_view|skills_list)
    echo '{"action": "allow"}'
    exit 0
    ;;
esac

# Memory is a special case — it's read AND write, but blocking it would
# prevent the agent from saving important info. Always allow.
case "$TOOL_NAME" in
  memory)
    echo '{"action": "allow"}'
    exit 0
    ;;
esac

# ── Phase 2: Check governance lock ───────────────────────────────────────

LOCK_FILE="$HOME/.hermes-cortex/state/.governance-active.json"
if [ -f "$LOCK_FILE" ]; then
  # Lock exists — allow the write tool
  exit 0
fi

# ── Phase 3: No lock — block ─────────────────────────────────────────────

# This is a write tool without a governance lock. Block it.
cat << 'BLOCK_JSON'
{
  "action": "block",
  "message": "⛔ No governance lock active. You must call mcp_loop_governance_begin_change(task_id=\"...\", description=\"...\") before making any changes. This ensures every change is tracked and scored. After completing the change, call mcp_loop_governance_end_change() to release the lock."
}
BLOCK_JSON
exit 0