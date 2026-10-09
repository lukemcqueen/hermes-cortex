#!/usr/bin/env bash
# Re-runnable evidence: evening orchestrator verification pass (task model v3).
set -uo pipefail
TD="$HOME/.hermes-cortex/scripts/task-db.py"
echo "=== evening verification pass $(date -Is) ==="
echo "--- board ---"
python3 "$TD" list --board
echo "--- review queue ---"
python3 "$TD" list --status review
echo "--- review rows + explicit stale >24h check (tasks schema) ---"
TASK_DB="$TD" python3 "$(dirname "$0")/evening-verify-2026-10-09.helper.txt"
echo "=== end ==="
