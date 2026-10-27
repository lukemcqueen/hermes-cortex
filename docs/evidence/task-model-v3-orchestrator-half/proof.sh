#!/usr/bin/env bash
# Answers to ADV-13847-1 and ADV-13847-2, measured on host `esther` against the
# LIVE tasks schema. NOTHING IS PERSISTED: every block opens a transaction and
# ends with ROLLBACK. Block A *adds* an overload (never drops anything), so no
# existing caller can be blocked out of the write path.
# Run:  bash docs/evidence/task-model-v3-orchestrator-half/proof.sh
set -u
cd "$(dirname "$0")/../../.." || exit 1
OWNER=(docker exec -i mycortex-postgres psql -U mycortex -d mycortex
       -v ON_ERROR_STOP=1 -t -A -F '||')
READER=(docker exec -i mycortex-postgres psql -U mycortex_reader_esther -d mycortex
        -v ON_ERROR_STOP=1 -t -A -F '||')

blk() { echo "---------------- psql -U $1  (block $2)"; cat; }

echo "host=$(hostname)  captured-at=$(date -Is)  tree=$(git rev-parse --short HEAD)"
echo "every block below ends in ROLLBACK — no schema or row survives it"

echo "=============================================================="
echo "[A] ADV-13847-1: CREATE OR REPLACE alone, with a wider arg list, on the"
echo "    REAL function name (A STUB IS ADDED, NOTHING IS DROPPED)"
blk mycortex A <<'SQL' | "${OWNER[@]}" 2>&1; echo "rc=$?"
BEGIN;
CREATE OR REPLACE FUNCTION tasks.task_upsert(
    p_id UUID, p_content TEXT, p_created_by TEXT, p_assignee TEXT,
    p_project TEXT, p_repo TEXT, p_target TEXT, p_scope TEXT,
    p_status TEXT, p_column TEXT, p_position INT, p_priority INT,
    p_due TIMESTAMPTZ, p_tags TEXT[], p_source TEXT, p_depends_on UUID[],
    p_session_id TEXT, p_parent_id UUID, p_kind TEXT, p_correlation_id TEXT,
    p_plan TEXT DEFAULT NULL)
  RETURNS uuid LANGUAGE sql AS 'SELECT gen_random_uuid()';
SELECT 'task_upsert overloads now: ' || count(*)
  FROM pg_proc WHERE proname='task_upsert' AND pronamespace='tasks'::regnamespace;
SELECT 'the planned verification command would say:';
SELECT pg_get_function_arguments('tasks.task_upsert'::regproc);
ROLLBACK;
SQL

echo "=============================================================="
echo "[B] the v005 house pattern (v005__lifecycle.sql:336 does exactly this):"
echo "    DROP the old signature, then CREATE the wider one — on a PROBE name"
blk mycortex B <<'SQL' | "${OWNER[@]}" 2>&1; echo "rc=$?"
BEGIN;
-- the ORIGINAL plan's shape: bare CREATE OR REPLACE with one more parameter
CREATE FUNCTION tasks.zz_arity_probe(a int) RETURNS int LANGUAGE sql AS 'SELECT a';
CREATE OR REPLACE FUNCTION tasks.zz_arity_probe(a int, b int DEFAULT 0)
  RETURNS int LANGUAGE sql AS 'SELECT a + b';
SELECT 'after bare CREATE OR REPLACE: ' || count(*)
  FROM pg_proc WHERE proname='zz_arity_probe' AND pronamespace='tasks'::regnamespace;
DROP FUNCTION tasks.zz_arity_probe(int);
DROP FUNCTION tasks.zz_arity_probe(int, int);
-- the CORRECTED v016 shape: DROP the old signature, then CREATE the wider one
CREATE FUNCTION tasks.zz_arity_probe(a int) RETURNS int LANGUAGE sql AS 'SELECT a';
DROP FUNCTION tasks.zz_arity_probe(int);
CREATE FUNCTION tasks.zz_arity_probe(a int, b int DEFAULT 0)
  RETURNS int LANGUAGE sql AS 'SELECT a + b';
SELECT 'after DROP + CREATE:        ' || count(*)
  FROM pg_proc WHERE proname='zz_arity_probe' AND pronamespace='tasks'::regnamespace;
SELECT string_agg(pg_get_function_arguments(oid), ' || ')
  FROM pg_proc WHERE proname='zz_arity_probe' AND pronamespace='tasks'::regnamespace;
ROLLBACK;
SQL

echo "=============================================================="
echo "[C] ADV-13847-2: p_status NULL (exactly what task-db.py passes at :849)"
echo "    against an in_progress row"
blk mycortex_reader_esther C <<'SQL' | "${READER[@]}" 2>&1; echo "rc=$?"
BEGIN;
DO $$
DECLARE v_id uuid; v_st text; v_col text;
BEGIN
  SELECT tasks.task_upsert(
      p_content => 'zz-probe: column-derivation trap (rolled back)',
      p_created_by => 'esther', p_scope => 'personal',
      p_status => 'in_progress', p_source => 'doctor-probe') INTO v_id;
  RAISE NOTICE 'scratch row = % (status=in_progress)', v_id;
  BEGIN
    PERFORM tasks.task_upsert(p_id => v_id, p_status => NULL);
    SELECT status, "column" INTO v_st, v_col FROM tasks.tasks WHERE id = v_id;
    RAISE NOTICE 'NO ERROR: status=% column=%', v_st, v_col;
  EXCEPTION WHEN others THEN
    RAISE NOTICE 'RAISED % : %', SQLSTATE, SQLERRM;
  END;
END $$;
ROLLBACK;
SQL

echo "=============================================================="
echo "[D] the EXECUTE grants that a DROP+CREATE must restore (v016 requirement)"
blk mycortex_reader_esther D <<'SQL' | "${READER[@]}" 2>&1; echo "rc=$?"
SELECT r.rolname, has_function_privilege(r.oid, p.oid, 'EXECUTE') AS can_execute
FROM pg_proc p CROSS JOIN pg_roles r
WHERE p.proname = 'task_upsert' AND p.pronamespace = 'tasks'::regnamespace
  AND r.rolname LIKE 'mycortex%'
ORDER BY r.rolname;
SQL

echo "=============================================================="
echo "[E] live arity of the single write path after every block above"
blk mycortex_reader_esther E <<'SQL' | "${READER[@]}" 2>&1; echo "rc=$?"
SELECT count(*) AS task_upsert_functions
  FROM pg_proc WHERE proname='task_upsert' AND pronamespace='tasks'::regnamespace;
SQL
