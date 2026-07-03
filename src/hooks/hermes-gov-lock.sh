#!/bin/bash
# =============================================================================
# hermes-gov-lock — Root-owned governance lock helper
# =============================================================================
# This script is installed as root:root at /usr/local/sbin/hermes-gov-lock
# and invoked via sudo NOPASSWD by the loop-governance MCP server.
#
# Usage:
#   hermes-gov-lock on <task_id> [description]
#   hermes-gov-lock off <task_id>
#   hermes-gov-lock status
#
# The lock file is root-owned, so no agent can modify or delete it.
# Repo permissions are toggled between 555 (read-only) and 755 (writable).
# =============================================================================

set -euo pipefail

LOCK_DIR="/var/lib/hermes-gov"
LOCK_FILE="$LOCK_DIR/lock.json"
# Hardcoded — sudo resets HOME to /root
REPO_BASE="${REPO_BASE:-/home/moses/hermes-cortex}"
PROTECTED_DIRS=(
    "$REPO_BASE/src"
)

# ── Helpers ────────────────────────────────────────────────────────────────

die() { echo "ERROR: $*" >&2; exit 1; }
info() { echo "$*"; }

require_root() {
    if [ "$(id -u)" -ne 0 ]; then
        die "This script must be run as root (via sudo)."
    fi
}

get_config() {
    local key="$1"
    if [ -f "$LOCK_FILE" ]; then
        python3 -c "import json,sys; print(json.load(open('$LOCK_FILE')).get('$key',''))" 2>/dev/null || echo ""
    fi
}

lock_active() {
    [ -f "$LOCK_FILE" ]
}

# ── Commands ───────────────────────────────────────────────────────────────

cmd_on() {
    local task_id="${1:-}"
    local description="${2:-}"
    [ -z "$task_id" ] && die "task_id is required"

    # Check double-lock
    if lock_active; then
        local existing_task
        existing_task=$(get_config "task_id")
        die "Already locked by: $existing_task. Call 'hermes-gov-lock off $existing_task' first."
    fi

    # Create lock directory
    mkdir -p "$LOCK_DIR"
    chmod 700 "$LOCK_DIR"

    # Write lock file
    cat > "$LOCK_FILE" << EOF
{
  "task_id": "$task_id",
  "description": "$description",
  "started_at": "$(date -Iseconds)",
  "pid": $$,
  "protected_dirs": [$(printf '"%s"' "${PROTECTED_DIRS[0]}")]
}
EOF
    chmod 600 "$LOCK_FILE"

    # Make protected directories writable
    for dir in "${PROTECTED_DIRS[@]}"; do
        if [ -d "$dir" ]; then
            chmod -R 755 "$dir" 2>/dev/null || true
        fi
    done

    info "LOCK ACTIVE: task_id=$task_id"
    info "Repo writable: ${PROTECTED_DIRS[*]}"
}

cmd_off() {
    local task_id="${1:-}"
    [ -z "$task_id" ] && die "task_id is required"

    if ! lock_active; then
        die "No active lock."
    fi

    local stored_task
    stored_task=$(get_config "task_id")
    if [ "$stored_task" != "$task_id" ]; then
        die "Lock belongs to task '$stored_task', not '$task_id'."
    fi

    # Make protected directories recursively read-only
    # Files get 444 (read-only), dirs get 555 (read+execute)
    for dir in "${PROTECTED_DIRS[@]}"; do
        if [ -d "$dir" ]; then
            find "$dir" -type f -exec chmod 444 {} \; 2>/dev/null || true
            chmod -R u-w "$dir" 2>/dev/null || true
            find "$dir" -type d -exec chmod u+x {} \; 2>/dev/null || true
        fi
    done

    # Remove lock
    rm -f "$LOCK_FILE"

    info "LOCK RELEASED: task_id=$task_id"
    info "Repo read-only: ${PROTECTED_DIRS[*]}"
}

cmd_status() {
    if ! lock_active; then
        echo '{"active": false}'
        exit 0
    fi

    cat "$LOCK_FILE"
    echo ""
    echo "Lock file owners: $(ls -la "$LOCK_FILE" 2>/dev/null | awk '{print $3,$4}')"
}

cmd_emergency_off() {
    # Emergency release — NO task_id check. Only for manual use when stuck.
    echo "⚠️  EMERGENCY RELEASE — bypasses all checks!" >&2
    for dir in "${PROTECTED_DIRS[@]}"; do
        if [ -d "$dir" ]; then
            chmod -R 755 "$dir" 2>/dev/null || true
        fi
    done
    rm -f "$LOCK_FILE"
    echo "LOCK FORCE-RELEASED. Repo set to writable." >&2
}

# ── Main ───────────────────────────────────────────────────────────────────

require_root

ACTION="${1:-}"
case "$ACTION" in
    on)
        shift
        cmd_on "$@"
        ;;
    off)
        shift
        cmd_off "$@"
        ;;
    status)
        cmd_status
        ;;
    emergency-off)
        cmd_emergency_off
        ;;
    *)
        echo "Usage: $0 {on|off|status} [args...]"
        echo ""
        echo "  on <task_id> [description]    Create governance lock, make repo writable"
        echo "  off <task_id>                 Release lock, make repo read-only"
        echo "  status                        Show lock state"
        echo "  emergency-off                 Force release (manual use only)"
        exit 1
        ;;
esac