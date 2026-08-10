-- ============================================================================
-- tasks schema v008 — TL-v2 S6 (deferred v006 features, now shipped)
--
-- Docs: docs/design/task-lifecycle-v2.md §3.2/§4/§15 (deferral resolved).
-- Additive ALTERs only, single transaction (BEGIN/COMMIT — SRE R-10).
-- Version-gated by ops/services/tasks/migrate.py; re-run after a rolled-back
-- attempt is safe (IF NOT EXISTS + DROP-IF-EXISTS guards).
--
-- Ships the v006-deferred items (Domain M-7, M-4, R-3):
--   1. blocked/waiting status   status CHECK extended + column derives NULL
--                               (like paused/cancelled) + transition matrix
--   2. task_story_summary()     per-story slice status summary (JSONB)
--   3. archive children-first   task_archive_old deletes slices before their
--                               story (FK NO ACTION would otherwise block)
--   4. story auto-complete      AFTER UPDATE trigger: when the last active
--                               slice reaches completed/cancelled, the story
--                               auto-completes (reason='story_auto_complete',
--                               event_type='story_auto_complete')
--
-- Closes: R-3 (auto-complete polish), M-4 (archive children-first),
-- M-7 (blocked/waiting status).
--
-- ALSO FIXES (found live during S6 e2e): v007's partial-preserve was
-- defeated by non-NULL parameter DEFAULTS. task_upsert declared
-- p_project DEFAULT 'hermes-cortex', p_scope DEFAULT 'personal',
-- p_status DEFAULT 'pending', p_priority DEFAULT 0, p_source DEFAULT
-- 'manual'. A named-arg status-only call (task_upsert(p_id=>…,
-- p_status=>…)) OMITS those args → the DEFAULT fills them → the
-- ON CONFLICT COALESCE(p_x, existing) sees a non-NULL value and clobbers
-- (source doctor-probe → manual, priority 3 → 0, project client-x →
-- hermes-cortex). The DECLARE block's COALESCE already applies the
-- canonical defaults for the INSERT branch, so the signature defaults can
-- be NULL: omitted → NULL → preserve existing (v007's actual intent).
-- ============================================================================

BEGIN;

-- ── 0. task_upsert signature defaults → NULL (v007 completion) ───────────
-- CREATE OR REPLACE cannot change arity but CAN change defaults. All five
-- non-NULL defaults become NULL; the DECLARE block keeps INSERT defaults
-- (v_project/v_scope/v_status/v_priority/v_source coalesce there).
CREATE OR REPLACE FUNCTION tasks.task_upsert(
    p_id             UUID DEFAULT NULL,
    p_content        TEXT DEFAULT NULL,
    p_created_by     TEXT DEFAULT NULL,
    p_assignee       TEXT DEFAULT NULL,
    p_project        TEXT DEFAULT NULL,    -- was 'hermes-cortex' (v007 fix)
    p_repo           TEXT DEFAULT NULL,
    p_target         TEXT DEFAULT NULL,
    p_scope          TEXT DEFAULT NULL,     -- was 'personal'
    p_status         TEXT DEFAULT NULL,     -- was 'pending'
    p_column         TEXT DEFAULT NULL,   -- NULL → derived from status
    p_position       INT DEFAULT NULL,
    p_priority       INT DEFAULT NULL,      -- was 0
    p_due            TIMESTAMPTZ DEFAULT NULL,
    p_tags           TEXT[] DEFAULT NULL,
    p_source         TEXT DEFAULT NULL,     -- was 'manual'
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

-- ── 1. blocked/waiting status (M-7) ─────────────────────────────────────
-- CHECK extended with the two new statuses. blocked = actively stuck on an
-- external dependency; waiting = not yet actionable (dependency not ready).
-- Both derive column = NULL (no kanban column is coherent — same class as
-- paused/cancelled; the leading "column" IS NULL admits it for any status).
ALTER TABLE tasks.tasks DROP CONSTRAINT IF EXISTS tasks_status_check;
ALTER TABLE tasks.tasks ADD CONSTRAINT tasks_status_check CHECK (
    status IN ('pending','in_progress','paused','completed','cancelled',
               'blocked','waiting'));

-- Transition matrix extended (task-lifecycle-v2.md §4):
--   pending     → in_progress, cancelled, blocked, waiting
--   in_progress → paused, completed, cancelled, blocked, waiting
--   paused      → in_progress, completed, cancelled, blocked, waiting
--   blocked     → in_progress, paused, completed, cancelled, waiting
--   waiting     → in_progress, paused, blocked, completed, cancelled
--   completed   → in_progress (reason='reopen' only)
--   cancelled   → terminal
CREATE OR REPLACE FUNCTION tasks.transition_allowed(
    p_from   TEXT,
    p_to     TEXT,
    p_reason TEXT DEFAULT NULL
) RETURNS boolean
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    IF p_from = p_to THEN
        RETURN true;                       -- no-op gate (no transition)
    END IF;
    IF p_from = 'cancelled' THEN
        RETURN false;                      -- terminal
    END IF;
    CASE p_from
        WHEN 'pending' THEN
            RETURN p_to IN ('in_progress', 'cancelled', 'blocked', 'waiting');
        WHEN 'in_progress' THEN
            RETURN p_to IN ('paused', 'completed', 'cancelled',
                            'blocked', 'waiting');
        WHEN 'paused' THEN
            RETURN p_to IN ('in_progress', 'completed', 'cancelled',
                            'blocked', 'waiting');
        WHEN 'blocked' THEN
            RETURN p_to IN ('in_progress', 'paused', 'completed',
                            'cancelled', 'waiting');
        WHEN 'waiting' THEN
            RETURN p_to IN ('in_progress', 'paused', 'blocked',
                            'completed', 'cancelled');
        WHEN 'completed' THEN
            -- COALESCE: NULL reason must NOT satisfy the reopen gate
            -- (three-valued logic — NULL = 'reopen' is NULL, and
            -- NOT NULL would skip the raise).
            RETURN p_to = 'in_progress' AND COALESCE(p_reason, '') = 'reopen';
        ELSE
            RETURN false;
    END CASE;
END;
$$;

-- task_upsert column derivation: blocked/waiting → NULL (v003/v004 class —
-- the CASE's ELSE branch already yields NULL; explicit for readability).
-- (No function body change required: the ELSE NULL covers the new statuses.
--  Documented here so the derivation contract is discoverable in one place.)

-- ── 2. task_story_summary() — per-story slice status summary (M-7 tooling) ─
-- Returns a JSONB summary for a story: story identity + slice counts by
-- status + completion ratio. SECURITY INVOKER — RLS on tasks.tasks applies
-- (a cross-tenant story id simply returns nothing). Null-safe: a story with
-- zero slices reports total_slices=0, done_ratio=0.
CREATE OR REPLACE FUNCTION tasks.task_story_summary(p_story_id UUID)
RETURNS JSONB
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_story RECORD;
    v_result JSONB;
BEGIN
    SELECT id, content, status, priority, scope, created_by
      INTO v_story
      FROM tasks.tasks
     WHERE id = p_story_id AND kind = 'story';
    IF NOT FOUND THEN
        RETURN NULL;                       -- not visible / not a story
    END IF;

    SELECT jsonb_build_object(
        'story_id',       v_story.id,
        'content',        v_story.content,
        'status',         v_story.status,
        'priority',       v_story.priority,
        'scope',          v_story.scope,
        'created_by',     v_story.created_by,
        'total_slices',   count(*),
        'pending',        count(*) FILTER (WHERE status = 'pending'),
        'in_progress',    count(*) FILTER (WHERE status = 'in_progress'),
        'paused',         count(*) FILTER (WHERE status = 'paused'),
        'blocked',        count(*) FILTER (WHERE status = 'blocked'),
        'waiting',        count(*) FILTER (WHERE status = 'waiting'),
        'completed',      count(*) FILTER (WHERE status = 'completed'),
        'cancelled',      count(*) FILTER (WHERE status = 'cancelled'),
        'active',         count(*) FILTER (WHERE status NOT IN
                                           ('completed','cancelled')),
        'done_ratio',     CASE WHEN count(*) = 0 THEN 0
                               ELSE round(100.0 * count(*) FILTER (
                                   WHERE status IN ('completed','cancelled'))
                                   / count(*), 1) END
    ) INTO v_result
      FROM tasks.tasks
     WHERE parent_id = p_story_id;

    RETURN v_result;
END;
$$;
REVOKE ALL ON FUNCTION tasks.task_story_summary(UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tasks.task_story_summary(UUID) TO mycortex_reader;

-- ── 3. Archive children-first (M-4) ──────────────────────────────────────
-- task_archive_old INSERTs completed/cancelled rows into task_archive then
-- DELETEs them from tasks.tasks. With hierarchy, deleting a story whose
-- slices still exist fails on the parent FK (ON DELETE NO ACTION). Delete
-- slices (parent_id NOT NULL) BEFORE their stories. The archive INSERT is
-- unchanged (archive table is flat — no FK on parent_id).
CREATE OR REPLACE FUNCTION tasks.task_archive_old(
    p_created_by TEXT DEFAULT NULL
) RETURNS INT
LANGUAGE plpgsql
AS $$
DECLARE
    v_count INT;
BEGIN
    INSERT INTO tasks.task_archive
    SELECT id, content, created_by, assignee, project, repo, target, scope,
           status, "column", "position", priority, due, tags, source, depends_on,
           session_id, created_at, updated_at, status_changed_at, completed_at,
           now()
    FROM tasks.tasks
    WHERE status IN ('completed', 'cancelled')
      AND (p_created_by IS NULL OR created_by = p_created_by);

    GET DIAGNOSTICS v_count = ROW_COUNT;

    -- Children (slices) first — the parent FK blocks deleting a story while
    -- any of its slices remain (M-4). Flat rows (parent_id NULL) are covered
    -- by the second DELETE.
    DELETE FROM tasks.tasks
    WHERE status IN ('completed', 'cancelled')
      AND parent_id IS NOT NULL
      AND (p_created_by IS NULL OR created_by = p_created_by);

    -- Then the stories themselves (their slices are gone by now) + legacy
    -- flat rows.
    DELETE FROM tasks.tasks
    WHERE status IN ('completed', 'cancelled')
      AND (p_created_by IS NULL OR created_by = p_created_by);

    RETURN v_count;
END;
$$;

-- ── 4. Story auto-complete (R-3 polish) ──────────────────────────────────
-- v005 shipped the GATE (a story may not complete while any non-cancelled
-- slice is active — tasks.check_transition). v008 adds the AUTO-COMPLETE:
-- when a slice transitions to completed/cancelled and NO other slice of its
-- story remains active, the story is completed automatically with
-- reason='story_auto_complete' (event trail records
-- event_type='story_auto_complete').
--
-- The auto-complete UPDATE must pass check_transition: a story in 'pending'
-- (never started) is legal to complete via this path — the trigger only
-- fires when no active slices remain, which satisfies the story gate. We
-- admit the transition by setting the tasks.transition_reason GUC to
-- 'story_auto_complete'; check_transition below special-cases it.
CREATE OR REPLACE FUNCTION tasks.story_auto_complete()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = tasks, pg_temp
AS $$
DECLARE
    v_active INT;
BEGIN
    -- Only slices reaching a terminal state trigger the check.
    IF NEW.kind IS DISTINCT FROM 'slice' OR NEW.parent_id IS NULL THEN
        RETURN NEW;
    END IF;
    IF OLD.status IS NOT DISTINCT FROM NEW.status THEN
        RETURN NEW;                        -- no-op gate
    END IF;
    IF NEW.status NOT IN ('completed', 'cancelled') THEN
        RETURN NEW;                        -- not a terminal transition
    END IF;
    IF NEW.source = 'doctor-probe' THEN
        RETURN NEW;                        -- M-5 suppression at source
    END IF;

    -- Any OTHER slice of this story still active?
    SELECT count(*) INTO v_active
      FROM tasks.tasks
     WHERE parent_id = NEW.parent_id
       AND id <> NEW.id
       AND status NOT IN ('completed', 'cancelled');

    IF v_active > 0 THEN
        RETURN NEW;                        -- story not done yet
    END IF;

    -- Last active slice finished → auto-complete the story. Set column +
    -- completed_at too: the raw UPDATE bypasses task_upsert's derivation,
    -- and a stale 'in_progress' column would violate tasks_column_check
    -- (completed must derive column='done').
    PERFORM set_config('tasks.transition_reason', 'story_auto_complete', true);
    UPDATE tasks.tasks
       SET status = 'completed',
           "column" = 'done',
           completed_at = COALESCE(completed_at, now())
     WHERE id = NEW.parent_id
       AND status IS DISTINCT FROM 'completed';
    -- GUC is transaction-local (is_local=true) — no need to reset for the
    -- surrounding statement; the event trigger reads it during this UPDATE.

    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION tasks.story_auto_complete() FROM PUBLIC;

DROP TRIGGER IF EXISTS tasks_story_auto_complete_trigger ON tasks.tasks;
CREATE TRIGGER tasks_story_auto_complete_trigger
    AFTER UPDATE OF status ON tasks.tasks
    FOR EACH ROW EXECUTE FUNCTION tasks.story_auto_complete();

-- check_transition: admit story → completed when reason='story_auto_complete'
-- (the AFTER trigger above guarantees no active slices — the gate holds).
-- Keep the manual path unchanged: a plain story → completed still requires a
-- legal matrix transition (in_progress → completed, per the L1 battery).
CREATE OR REPLACE FUNCTION tasks.check_transition()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_reason TEXT;
BEGIN
    IF OLD.status IS NOT DISTINCT FROM NEW.status THEN
        RETURN NEW;
    END IF;
    v_reason := NULLIF(current_setting('tasks.transition_reason', true), '');
    -- Auto-complete path: story → completed ONLY via the AFTER trigger's GUC.
    -- The trigger fires only when no active slices remain, so the R-3 story
    -- gate is satisfied by construction.
    IF NEW.kind = 'story' AND NEW.status = 'completed'
       AND v_reason = 'story_auto_complete' THEN
        RETURN NEW;
    END IF;
    -- COALESCE(..., false): transition_allowed must never leak NULL into
    -- the gate (three-valued logic would silently permit the transition).
    IF NOT COALESCE(tasks.transition_allowed(OLD.status, NEW.status, v_reason), false) THEN
        RAISE EXCEPTION 'illegal task transition: % -> % (reason: %)',
            OLD.status, NEW.status, COALESCE(v_reason, 'none');
    END IF;
    IF NEW.kind = 'story' AND NEW.status = 'completed' AND EXISTS (
        SELECT 1 FROM tasks.tasks s
        WHERE s.parent_id = NEW.id
          AND s.status NOT IN ('completed', 'cancelled')
    ) THEN
        RAISE EXCEPTION 'story % has active slices; cannot complete', NEW.id;
    END IF;
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION tasks.check_transition() FROM PUBLIC;

-- event_after_update: record event_type='story_auto_complete' when the
-- transition reason says so (task-lifecycle-v2.md §5 — event trail truth).
CREATE OR REPLACE FUNCTION tasks.event_after_update()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = tasks, pg_temp
AS $$
DECLARE
    v_reason TEXT;
    v_event  TEXT := 'status_changed';
BEGIN
    IF NEW.source = 'doctor-probe' OR OLD.status IS NOT DISTINCT FROM NEW.status THEN
        RETURN NEW;
    END IF;
    v_reason := NULLIF(current_setting('tasks.transition_reason', true), '');
    IF v_reason = 'story_auto_complete' THEN
        v_event := 'story_auto_complete';
    END IF;
    PERFORM tasks.task_log_event(
        NEW.id, v_event, OLD.status, NEW.status, v_reason,
        NULL, NEW.session_id, NEW.correlation_id);
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION tasks.event_after_update() FROM PUBLIC;

COMMIT;
