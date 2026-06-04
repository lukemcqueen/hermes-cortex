#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
PROJECT_ROOT="$(pwd)"
echo "Repo root: $REPO_ROOT"
cd "$PROJECT_ROOT"
echo "Project root: $PROJECT_ROOT"
echo

TASK="${*:-}"
if [ -z "$TASK" ]; then
  echo "Usage: .agentkore/scripts/agentkore-task.sh \"task description\""
  exit 1
fi
mkdir -p .agentkore/runtime
cat > .agentkore/runtime/current_task.md <<EOF
# Current Task

$TASK

## Started
$(date -u +"%Y-%m-%dT%H:%M:%SZ")
EOF
echo "AgentKore task set: $TASK"
