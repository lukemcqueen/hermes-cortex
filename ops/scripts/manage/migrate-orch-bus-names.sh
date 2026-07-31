#!/usr/bin/env bash
# migrate-orch-bus-names.sh — Clean up orphaned bus/* sources and stale deployed bus-* scripts
#
# WHAT: After the ops/scripts/orch-bus/ rename (bus-* → orch-bus-*), these
# orphan files remain:
#   ops/scripts/bus/bus-forwarder.py           → superseded by orch-bus/orch-bus-forwarder.py
#   ops/scripts/bus/bus-message-tracker.py     → superseded by orch-bus/orch-bus-confirmation-poller.py
#   ops/scripts/bus/bus-message-tracker-alert.sh → superseded by orch-bus/orch-bus-confirmation-alert.sh
#
# These were never registered in cortex-update.sh and are not deployed
# anywhere. This script:
#   1. Removes the orphan source files from ops/scripts/bus/
#   2. Removes any stale bus-* deployed copies from ~/.hermes-cortex/scripts/
#      and ~/.hermes/scripts/
#   3. Verifies the orch-bus-* counterparts exist
#
# Safe to re-run. Only removes files that have verified orch-bus-* counterparts.

set -euo pipefail

REPO="${CORTEX_REPO:-$HOME/hermes-cortex}"
CORTEX_HOME="${CORTEX_DEPLOY_HOME:-$HOME/.hermes-cortex}"
HERMES_SCRIPTS="$HOME/.hermes/scripts"

# Files to clean up: old source path → new source path (for verification)
declare -A ORPHANS
ORPHANS["ops/scripts/bus/bus-forwarder.py"]="ops/scripts/orch-bus/orch-bus-forwarder.py"
ORPHANS["ops/scripts/bus/bus-message-tracker.py"]="ops/scripts/orch-bus/orch-bus-confirmation-poller.py"

# Old deploy names that might exist as stale copies (only the 3 orphans
# that were never registered — bus/bus-* had no register lines in cortex-update.sh)
STALE_NAMES=(
    "bus-forwarder.py"
    "bus-message-tracker.py"
    "bus-message-tracker-alert.sh"
)

# Files that were ALSO renamed (their register source paths changed to orch-bus-*,
# but the old deploy destination might still have stale copies)
# Only clean these AFTER verifying the new orch-bus-* deploy exists
REGISTER_RENAMED=(
    "bus-audit-watchdog.py"        # now deploys as orch-bus-audit-watchdog.py
    "bus-recover-timeouts.sh"      # now deploys as orch-bus-recover-timeouts.sh
    "bus-depth-watchdog.sh"        # now deploys as orch-bus-depth-watchdog.sh
    "bus-generate-wrappers.py"     # now deploys as orch-bus-generate-wrappers.py
    "bus-git-auth-check.py"        # now deploys as orch-bus-git-auth-check.py
    "bus-health-check.py"          # now deploys as orch-bus-health-check.py
    "bus-mcp.py"                   # now deploys as orch-bus-mcp.py
    "bus-readiness-check.py"       # now deploys as orch-bus-readiness-check.py
    "test-bus.py"                  # now deploys as orch-bus-test.py
)

cleaned_source=0
cleaned_deploy=0
errors=0

echo "🔍 Verifying orch-bus-* counterparts exist..."
for replacement in "${ORPHANS[@]}"; do
    if [ -f "$REPO/$replacement" ]; then
        echo "  ✅ $replacement"
    else
        echo "  ❌ MISSING: $replacement — aborting"
        exit 1
    fi
done

echo ""
echo "🧹 Removing orphan source files from ops/scripts/bus/..."
for orphan in "${!ORPHANS[@]}"; do
    if [ -f "$REPO/$orphan" ]; then
        echo "  Removing $orphan..."
        rm -f "$REPO/$orphan"
        ((cleaned_source++))
    else
        echo "  Already gone: $orphan"
    fi
done

echo ""
echo "🧹 Removing stale deployed copies (orphans)..."
for name in "${STALE_NAMES[@]}"; do
    for dir in "$CORTEX_HOME/scripts" "$HERMES_SCRIPTS"; do
        path="$dir/$name"
        if [ -f "$path" ]; then
            echo "  Removing $path..."
            rm -f "$path"
            ((cleaned_deploy++))
        fi
    done
done

echo ""
echo "🧹 Removing stale register-renamed deploy copies (old bus-* → now orch-bus-*)..."
for name in "${REGISTER_RENAMED[@]}"; do
    orch_name="${name/#bus-/orch-bus-}"
    for dir in "$CORTEX_HOME/scripts" "$HERMES_SCRIPTS"; do
        old_path="$dir/$name"
        new_path="$dir/$orch_name"
        if [ -f "$old_path" ] && [ -f "$new_path" ]; then
            echo "  Removing $old_path (replaced by $new_path)..."
            rm -f "$old_path"
            ((cleaned_deploy++))
        elif [ -f "$old_path" ] && [ ! -f "$new_path" ]; then
            echo "  ⚠️  Keeping $old_path — no $new_path found (run cortex-update.sh first)"
        fi
    done
done

echo ""
echo "━━━ Summary ━━━"
echo "  Source orphans removed: $cleaned_source"
echo "  Stale deploys removed:  $cleaned_deploy"
echo "  Errors:                 $errors"

if [ "$errors" -gt 0 ]; then
    echo "⚠️  Completed with errors"
    exit 1
fi

echo "✅ Migration complete — all bus-* orphans cleaned"
echo ""
echo "Next steps:"
echo "  1. Verify: python3 $REPO/ops/scripts/manage/cortex-doctor.py --quiet"
echo "  2. Commit: cd $REPO && git add -A && git commit -m 'clean: remove orphaned bus/* sources superseded by orch-bus/*'"
