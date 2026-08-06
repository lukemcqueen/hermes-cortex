-- ============================================================================
-- tasks schema v004 — fix ON CONFLICT column preservation (cancelled update)
--
-- BUG (found by L1 test test-tasks-schema.sh + live CLI probe, 2026-08-06):
--   v003 fixed the INSERT derivation (cancelled → column NULL), but the
--   ON CONFLICT DO UPDATE branch still used
--       "column" = COALESCE(EXCLUDED."column", tasks.tasks."column")
--   so updating an EXISTING row to 'cancelled' kept the stale column
--   ('todo'/'in_progress'), producing status='cancelled', column='todo'
--   → CHECK violation. Live probe:
--       task-db.py update <id> --status cancelled
--       ERROR: new row for relation "tasks" violates check constraint
--       "tasks_check" (…, cancelled, todo, …)
--
-- FIX: ON CONFLICT DO UPDATE SET "column" = EXCLUDED."column" — the column
--   is ALWAYS the derived (or explicitly passed) value for the NEW row
--   state, never a stale carry-over. The CLI passes p_column=NULL with a
--   full status on every update (task-db.py cmd_update), so the derived
--   value is exactly what the new status requires.
--
-- Pure CREATE OR REPLACE FUNCTION — additive, re-runnable, safe.
-- ============================================================================

CREATE OR REPLACE FUNCTION tasks.task_upsert(
    p_id            UUID DEFAULT NULL,
    p_content       TEXT DEFAULT NULL,
    p_created_by    TEXT DEFAULT NULL,
    p_assignee      TEXT DEFAULT NULL,
    p_project       TEXT DEFAULT 'hermes-cortex',
    p_repo          TEXT DEFAULT NULL,
    p_target        TEXT DEFAULT NULL,
    p_scope         TEXT DEFAULT 'personal',
    p_status        TEXT DEFAULT 'pending',
    p_column        TEXT DEFAULT NULL,   -- NULL → derived from status
    p_position      INT DEFAULT NULL,
    p_priority      INT DEFAULT 0,
    p_due           TIMESTAMPTZ DEFAULT NULL,
    p_tags          TEXT[] DEFAULT NULL,
    p_source        TEXT DEFAULT 'manual',
    p_depends_on    UUID[] DEFAULT NULL,
    p_session_id    TEXT DEFAULT NULL
) RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    v_id UUID;
    v_column TEXT;
    v_created_by TEXT := COALESCE(p_created_by, tasks.profile_of(current_user));
    -- Resolve the target id ONCE (used by the INSERT, the lookup subquery,
    -- and the RETURNING clause).
    v_target_id UUID := COALESCE(p_id, gen_random_uuid());
    -- Non-nullable columns: coalesce defaults so a partial update (status-only)
    -- still proposes a valid row that passes RLS WITH CHECK and NOT NULL.
    v_project TEXT := COALESCE(p_project, 'hermes-cortex');
    v_scope   TEXT := COALESCE(p_scope, 'personal');
    v_status  TEXT := COALESCE(p_status, 'pending');
    v_priority INT := COALESCE(p_priority, 0);
    v_source  TEXT := COALESCE(p_source, 'manual');
BEGIN
    -- Derive column from status when not explicitly provided (B-4).
    -- cancelled → NULL (no kanban column is coherent; CHECK forbids 'done').
    v_column := COALESCE(p_column, CASE v_status
        WHEN 'pending'     THEN 'todo'
        WHEN 'in_progress' THEN 'in_progress'
        WHEN 'completed'   THEN 'done'
        ELSE NULL
    END);

    INSERT INTO tasks.tasks (
        id, content, created_by, assignee, project, repo, target, scope,
        status, "column", "position", priority, due, tags, source, depends_on,
        session_id, created_at, updated_at, status_changed_at, completed_at
    ) VALUES (
        v_target_id,
        -- On status-only updates the caller passes NULL content — fetch the
        -- existing row's content so the proposed INSERT row satisfies NOT NULL
        -- before ON CONFLICT resolution kicks in.
        COALESCE(p_content, (SELECT t.content FROM tasks.tasks t
                             WHERE t.id = v_target_id)),
        v_created_by, p_assignee,
        v_project, p_repo, p_target, v_scope, v_status, v_column, p_position,
        v_priority, p_due, p_tags, v_source, p_depends_on, p_session_id,
        now(), now(), now(),
        CASE WHEN v_status = 'completed' THEN now() ELSE NULL END
    )
    ON CONFLICT (id) DO UPDATE SET
        content          = COALESCE(EXCLUDED.content, tasks.tasks.content),
        assignee         = COALESCE(EXCLUDED.assignee, tasks.tasks.assignee),
        project          = COALESCE(EXCLUDED.project, tasks.tasks.project),
        repo             = COALESCE(EXCLUDED.repo, tasks.tasks.repo),
        target           = COALESCE(EXCLUDED.target, tasks.tasks.target),
        scope            = COALESCE(EXCLUDED.scope, tasks.tasks.scope),
        status           = COALESCE(EXCLUDED.status, tasks.tasks.status),
        -- v004: column always reflects the NEW state's derived value — never
        -- carry over a stale column (that produced cancelled+todo → CHECK).
        "column"         = EXCLUDED."column",
        "position"       = COALESCE(EXCLUDED."position", tasks.tasks."position"),
        priority         = COALESCE(EXCLUDED.priority, tasks.tasks.priority),
        due              = COALESCE(EXCLUDED.due, tasks.tasks.due),
        tags             = COALESCE(EXCLUDED.tags, tasks.tasks.tags),
        source           = COALESCE(EXCLUDED.source, tasks.tasks.source),
        depends_on       = COALESCE(EXCLUDED.depends_on, tasks.tasks.depends_on),
        session_id       = COALESCE(EXCLUDED.session_id, tasks.tasks.session_id),
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
