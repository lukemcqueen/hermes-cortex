-- ============================================================================
-- tasks schema v007 — task_upsert partial-update preservation
--
-- BUG (found live 2026-08-10 during TL-v2 S3 e2e): the v005 task_upsert
-- ON CONFLICT DO UPDATE clause reads COALESCE(EXCLUDED.col, existing.col),
-- but EXCLUDED.col is NEVER NULL because the INSERT branch coalesces unset
-- params to defaults (v_source→'manual', v_scope→'personal', v_project→
-- 'hermes-cortex', v_priority→0, v_created_by→current profile). Therefore
-- EVERY status-only update (e.g. `task-db.py update <id> --status
-- in_progress`) silently clobbered:
--     source   inbox  → manual      (breaks S4 bus→task correlation lookup +
--                                    untrusted-inbox pending marking)
--     scope    fleet  → personal    (breaks fleet-task visibility/writes)
--     priority 3      → 0
--     project  client-x → hermes-cortex
--     created_by owner → updater    (ownership theft on cross-role updates)
--
-- FIX: the DO UPDATE branch must coalesce against the FUNCTION PARAMETER
-- (NULL when unset → preserve existing), not against EXCLUDED (defaulted →
-- clobber). "column" is the deliberate exception (v004): it must always
-- reflect the NEW status's derived value.
--
-- The design intent (function header comment: "On status-only updates the
-- caller passes NULL content — fetch the existing row's content...") shows
-- preservation was intended; the EXCLUDED.x form defeated it for every
-- column with a non-NULL default. Content was already preserved via its own
-- subquery; the remaining columns are fixed here.
--
-- Version-gated: fresh DBs apply v001→v007 in order; existing hosts run
-- v007 via migrate.py. CREATE OR REPLACE FUNCTION — safe on re-run.
-- ============================================================================

BEGIN;

CREATE OR REPLACE FUNCTION tasks.task_upsert(
    p_id             UUID DEFAULT NULL,
    p_content        TEXT DEFAULT NULL,
    p_created_by     TEXT DEFAULT NULL,
    p_assignee       TEXT DEFAULT NULL,
    p_project        TEXT DEFAULT 'hermes-cortex',
    p_repo           TEXT DEFAULT NULL,
    p_target         TEXT DEFAULT NULL,
    p_scope          TEXT DEFAULT 'personal',
    p_status         TEXT DEFAULT 'pending',
    p_column         TEXT DEFAULT NULL,   -- NULL → derived from status
    p_position       INT DEFAULT NULL,
    p_priority       INT DEFAULT 0,
    p_due            TIMESTAMPTZ DEFAULT NULL,
    p_tags           TEXT[] DEFAULT NULL,
    p_source         TEXT DEFAULT 'manual',
    p_depends_on     UUID[] DEFAULT NULL,
    p_session_id     TEXT DEFAULT NULL,
    p_parent_id      UUID DEFAULT NULL,   -- NEW (append)
    p_kind           TEXT DEFAULT NULL,   -- NEW
    p_correlation_id TEXT DEFAULT NULL    -- NEW
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
        session_id, parent_id, kind, correlation_id,
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
        p_parent_id, p_kind, p_correlation_id,
        now(), now(), now(),
        CASE WHEN v_status = 'completed' THEN now() ELSE NULL END
    )
    ON CONFLICT (id) DO UPDATE SET
        -- v007: preserve unset columns via the FUNCTION PARAMETER (NULL when
        -- unset) instead of EXCLUDED (defaulted → clobber). Each column keeps
        -- its previous value when the caller did not provide one.
        content          = COALESCE(p_content, tasks.tasks.content),
        created_by       = COALESCE(p_created_by, tasks.tasks.created_by),
        assignee         = COALESCE(p_assignee, tasks.tasks.assignee),
        project          = COALESCE(p_project, tasks.tasks.project),
        repo             = COALESCE(p_repo, tasks.tasks.repo),
        target           = COALESCE(p_target, tasks.tasks.target),
        scope            = COALESCE(p_scope, tasks.tasks.scope),
        status           = COALESCE(p_status, tasks.tasks.status),
        -- v004: column always reflects the NEW state's derived value —
        -- never carry over a stale column (that produced cancelled+todo →
        -- CHECK). For v005 the same holds for paused (derives NULL).
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

COMMIT;
