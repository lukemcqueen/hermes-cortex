-- ============================================================================
-- tasks schema v016 — task_upsert writes `plan` (21-arg), the single write path
--
-- WHY
--   The orchestrator half of Task Model v3 is unimplemented: there is no write
--   surface for a slice's `plan`. Measured before this migration on host esther
--   (docs/evidence/task-model-v3-orchestrator-half/cur-surface.txt):
--     * the live tasks.task_upsert took 20 parameters and `p_plan` was NOT one
--       of them; `p_assignee`, `p_depends_on` and `p_correlation_id` already were;
--     * the token `p_plan` appeared nowhere in the schema, the CLI or the MCP
--       servers (`grep -rn p_plan` → rc=1);
--     * 31 of 38 open rows on this host had `plan IS NULL`.
--   Row 9fb2ddb6. Design: docs/design/task-model-v3-orchestrator-half.md rev 2.
--
-- WHY A DROP + CREATE AND NOT `CREATE OR REPLACE`
--   Measured, not assumed (adversarial review ADV-13847-1, host esther,
--   findings-proof.txt block A): `CREATE OR REPLACE` cannot change a function's
--   argument list. Given one more parameter it ADDS A SECOND OVERLOAD and
--   leaves the 20-arg function live, after which the obvious verification
--   command dies with `ERROR: more than one function named "tasks.task_upsert"`.
--   This is the repo's own house pattern — v005__lifecycle.sql:332 says exactly
--   this for the 17-arg -> 20-arg step and drops first at :336.
--
-- THE ACL, MEASURED (this is why the re-grant below is shaped the way it is)
--   `SELECT proacl FROM pg_proc WHERE proname='task_upsert'` on host esther
--   returned NULL — the DEFAULT acl, i.e. EXECUTE to the owner and to PUBLIC.
--   The ten non-predefined roles that hold EXECUTE today (mycortex,
--   mycortex_admin, mycortex_ingest, mycortex_mem_admin, mycortex_mem_reader,
--   mycortex_mem_writer, mycortex_reader, mycortex_reader_esther,
--   mycortex_reader_probe, todos_fleet_writer) therefore hold it THROUGH PUBLIC,
--   and a freshly created function gets the same default ACL back.
--   So the re-grant is defence-in-depth, not a repair: it re-asserts the
--   measured holder set explicitly, so a later migration that revokes PUBLIC on
--   this function cannot silently lock the writers out. It is written with the
--   guarded `IF EXISTS (SELECT 1 FROM pg_roles ...)` loop that
--   v009__task-model-v3.sql:87-97 established, because an unguarded grant to a
--   role that a non-orchestrator host does not have kills the whole migration.
--
-- SCOPE
--   One column on the write path. It does NOT touch transition_allowed,
--   check_transition, claim_slice or any RLS policy.
--   Additive and re-runnable; wrapped in one transaction.
--
-- AUTHORITATIVE CONTRACT
--   tests/test-tasks-schema.sh (arity + single-overload assertions) — this file
--   states the contract, the test is the enforcement.
-- ============================================================================

BEGIN;

-- ── task_upsert 21-arg (append p_plan LAST — the positional signature that all
--    six call sites in ops/scripts/manage/task-db.py depend on is unchanged) ──
DROP FUNCTION IF EXISTS tasks.task_upsert(UUID, TEXT, TEXT, TEXT, TEXT, TEXT,
    TEXT, TEXT, TEXT, TEXT, INT, INT, TIMESTAMPTZ, TEXT[], TEXT, UUID[], TEXT,
    UUID, TEXT, TEXT);
CREATE FUNCTION tasks.task_upsert(
    p_id             UUID DEFAULT NULL,
    p_content        TEXT DEFAULT NULL,
    p_created_by     TEXT DEFAULT NULL,
    p_assignee       TEXT DEFAULT NULL,
    p_project        TEXT DEFAULT NULL,
    p_repo           TEXT DEFAULT NULL,
    p_target         TEXT DEFAULT NULL,
    p_scope          TEXT DEFAULT NULL,
    p_status         TEXT DEFAULT NULL,
    p_column         TEXT DEFAULT NULL,   -- NULL → derived from status
    p_position       INT DEFAULT NULL,
    p_priority       INT DEFAULT NULL,
    p_due            TIMESTAMPTZ DEFAULT NULL,
    p_tags           TEXT[] DEFAULT NULL,
    p_source         TEXT DEFAULT NULL,
    p_depends_on     UUID[] DEFAULT NULL,
    p_session_id     TEXT DEFAULT NULL,
    p_parent_id      UUID DEFAULT NULL,
    p_kind           TEXT DEFAULT NULL,
    p_correlation_id TEXT DEFAULT NULL,
    p_plan           TEXT DEFAULT NULL    -- NEW (v016, append)
) RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    v_id UUID;
    v_column TEXT;
    v_old_status TEXT;
    v_created_by TEXT := COALESCE(p_created_by, tasks.profile_of(current_user));
    -- Resolve the target id ONCE (used by the INSERT, the lookup subquery,
    -- and the RETURNING clause).
    v_target_id UUID := COALESCE(p_id, gen_random_uuid());
    -- Non-nullable columns: coalesce defaults so a partial update
    -- (status-only) still proposes a valid row that passes RLS WITH CHECK
    -- and NOT NULL.
    v_project TEXT := COALESCE(p_project, 'hermes-cortex');
    v_scope   TEXT := COALESCE(p_scope, 'personal');
    v_status  TEXT := COALESCE(p_status, 'pending');
    v_priority INT := COALESCE(p_priority, 0);
    v_source  TEXT := COALESCE(p_source, 'manual');
BEGIN
    -- Fast-fail transition check on the update path (the BEFORE UPDATE
    -- trigger is the authoritative gate; this gives callers a clear error
    -- before the write). Reopen requires the tasks.transition_reason GUC.
    IF p_id IS NOT NULL THEN
        SELECT status INTO v_old_status FROM tasks.tasks WHERE id = p_id;
        IF FOUND AND NOT COALESCE(tasks.transition_allowed(
                v_old_status, v_status,
                NULLIF(current_setting('tasks.transition_reason', true), '')), false) THEN
            RAISE EXCEPTION 'illegal task transition: % -> %',
                v_old_status, v_status;
        END IF;
    END IF;

    -- Derive column from status when not explicitly provided (B-4).
    -- paused/cancelled → NULL (no kanban column is coherent; the column
    -- CHECK admits NULL for any status).
    v_column := COALESCE(p_column, CASE v_status
        WHEN 'pending'     THEN 'todo'
        WHEN 'in_progress' THEN 'in_progress'
        WHEN 'completed'   THEN 'done'
        ELSE NULL
    END);

    INSERT INTO tasks.tasks (
        id, content, created_by, assignee, project, repo, target, scope,
        status, "column", "position", priority, due, tags, source, depends_on,
        session_id, parent_id, kind, correlation_id, plan,
        created_at, updated_at, status_changed_at, completed_at
    ) VALUES (
        v_target_id,
        -- On status-only updates the caller passes NULL content — fetch the
        -- existing row's content so the proposed INSERT row satisfies NOT
        -- NULL before ON CONFLICT resolution kicks in.
        COALESCE(p_content, (SELECT t.content FROM tasks.tasks t
                             WHERE t.id = v_target_id)),
        v_created_by, p_assignee,
        v_project, p_repo, p_target, v_scope, v_status, v_column, p_position,
        v_priority, p_due, p_tags, v_source, p_depends_on, p_session_id,
        p_parent_id, p_kind, p_correlation_id, p_plan,
        now(), now(), now(),
        CASE WHEN v_status = 'completed' THEN now() ELSE NULL END
    )
    ON CONFLICT (id) DO UPDATE SET
        -- v007: preserve unset columns via the FUNCTION PARAMETER (NULL when
        -- unset → preserve existing). v008: the signature defaults are now
        -- NULL so "unset" really is NULL — the named-arg omission no longer
        -- fills the default and clobbers. "column" is the deliberate
        -- exception (v004): always reflects the NEW status's derived value.
        content          = COALESCE(p_content, tasks.tasks.content),
        created_by       = COALESCE(p_created_by, tasks.tasks.created_by),
        assignee         = COALESCE(p_assignee, tasks.tasks.assignee),
        project          = COALESCE(p_project, tasks.tasks.project),
        repo             = COALESCE(p_repo, tasks.tasks.repo),
        target           = COALESCE(p_target, tasks.tasks.target),
        scope            = COALESCE(p_scope, tasks.tasks.scope),
        status           = COALESCE(p_status, tasks.tasks.status),
        "column"         = EXCLUDED."column",
        "position"       = COALESCE(p_position, tasks.tasks."position"),
        priority         = COALESCE(p_priority, tasks.tasks.priority),
        due              = COALESCE(p_due, tasks.tasks.due),
        tags             = COALESCE(p_tags, tasks.tasks.tags),
        source           = COALESCE(p_source, tasks.tasks.source),
        depends_on       = COALESCE(p_depends_on, tasks.tasks.depends_on),
        session_id       = COALESCE(p_session_id, tasks.tasks.session_id),
        parent_id        = COALESCE(p_parent_id, tasks.tasks.parent_id),
        kind             = COALESCE(p_kind, tasks.tasks.kind),
        correlation_id   = COALESCE(p_correlation_id, tasks.tasks.correlation_id),
        plan             = COALESCE(p_plan, tasks.tasks.plan),   -- NEW (v016)
        updated_at       = now(),
        status_changed_at = CASE WHEN tasks.tasks.status IS DISTINCT FROM EXCLUDED.status
                                 THEN now() ELSE tasks.tasks.status_changed_at END,
        completed_at      = CASE WHEN COALESCE(EXCLUDED.status, tasks.tasks.status) = 'completed'
                                 THEN COALESCE(tasks.tasks.completed_at, now())
                                 ELSE NULL END
    RETURNING id INTO v_id;

    RETURN v_id;
END;
$$;

-- Re-assert the measured holder set (see THE ACL, MEASURED above). PUBLIC keeps
-- its default EXECUTE, so this is additive; `IF EXISTS` keeps it safe on hosts
-- that lack a given agent's read role.
DO $$
DECLARE
  r text;
BEGIN
  FOREACH r IN ARRAY ARRAY[
      'mycortex','mycortex_admin','mycortex_ingest','mycortex_mem_admin',
      'mycortex_mem_reader','mycortex_mem_writer','mycortex_reader',
      'mycortex_reader_esther','mycortex_reader_probe','todos_fleet_writer']
  LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format(
        'GRANT EXECUTE ON FUNCTION tasks.task_upsert(UUID, TEXT, TEXT, TEXT, '
        'TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, INT, INT, TIMESTAMPTZ, TEXT[], '
        'TEXT, UUID[], TEXT, UUID, TEXT, TEXT, TEXT) TO %I', r);
    END IF;
  END LOOP;
END $$;

COMMIT;
