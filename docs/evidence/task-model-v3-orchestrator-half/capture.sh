#!/usr/bin/env bash
# Raw capture for backlog row 9fb2ddb6 — the task-model-v3 orchestrator write
# surface. Every command is run bare; the line above each block is its own
# exit code. Read-only: no schema or row is modified by this script.
# Run:  bash docs/evidence/task-model-v3-orchestrator-half/capture.sh
set -u
cd "$(dirname "$0")/../../.." || exit 1   # repo root
PSQL=(docker exec -i mycortex-postgres psql -U mycortex_reader_esther -d mycortex
      -v ON_ERROR_STOP=1 -t -A -F '||')

run() {
  echo "=============================================================="
  echo "\$ $*"
  "$@"; rc=$?
  echo "rc=$rc"
  return 0
}

echo "host=$(hostname)  captured-at=$(date -Is)  tree=$(git rev-parse --short HEAD)"

# 1. live signature of the single write path
run "${PSQL[@]}" -c "SELECT pg_get_function_arguments('tasks.task_upsert'::regproc);"

# 2. does ANY code in the repo know about p_plan? (rc=1 expected = no matches)
run grep -rn "p_plan" ops/services/tasks/schema ops/scripts/manage/task-db.py mcp-servers

# 3. the documented CLI surface of add / update
run grep -n "task-db.py add\|task-db.py update" ops/scripts/manage/task-db.py

# 4. the no-op honesty gate that a metadata-only update must get past
run sed -n '796,816p' ops/scripts/manage/task-db.py

# 5. live census of open rows (columns the write surface cannot set)
run "${PSQL[@]}" -c "SELECT count(*) AS open_rows, \
  count(*) FILTER (WHERE plan IS NULL) AS plan_null, \
  count(*) FILTER (WHERE assignee IS NULL) AS unassigned, \
  count(*) FILTER (WHERE correlation_id IS NULL) AS no_correlation, \
  count(*) FILTER (WHERE depends_on IS NULL) AS no_depends_on \
  FROM tasks.tasks WHERE status NOT IN ('completed','cancelled');"

# 6. the latest committed definition of the single write path
run grep -n "p_correlation_id\|p_plan\|CREATE OR REPLACE FUNCTION tasks.task_upsert" \
  ops/services/tasks/schema/v008__v006-deferred.sql

# 7. the write path is called POSITIONALLY (so an appended param is safe)
run grep -n "task_upsert(?::uuid" ops/scripts/manage/task-db.py
