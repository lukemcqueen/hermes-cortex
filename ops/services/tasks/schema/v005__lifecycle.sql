-- ============================================================================
-- tasks schema v005 — Task Lifecycle v2: hierarchy + paused + correlation +
-- task_events (docs/design/task-lifecycle-v2.md §3)
--
-- S1 of the TL-v2 story. Additive ALTERs only, single transaction
-- (BEGIN/COMMIT — SRE R-10: a mid-file failure rolls back, no half-applied
-- state). Version-gated by ops/services/tasks/migrate.py; re-run after a
-- rolled-back attempt is safe (IF NOT EXISTS + DROP-IF-EXISTS guards).
--
-- Adds:
--   3.1 hierarchy     parent_id FK (ON DELETE NO ACTION) + kind CHECK +
--                     coherence CHECK (story has no parent; slice HAS a
--                     parent; legacy flat has neither)
--   3.2 paused        status CHECK extended ('paused'); paused derives
--                     column = NULL (like cancelled, v003/v004 class)
--   3.3 correlation   correlation_id + partial unique index (1 task per
--                     inbox message — Architect R-4 idempotency)
--   3.4 task_events   append-only event trail + task_log_event() (SECURITY
--                     DEFINER) + INSERT-only RLS (SELECT policy for
--                     readers, no direct DML grants — forge-proof audit,
--                     Security R-1)
--   3.5 task_upsert   20-arg (p_parent_id/p_kind/p_correlation_id appended
--                     with trailing defaults — 17-arg legacy callers keep
--                     resolving, QA M-10)
--   triggers          check_transition (BEFORE UPDATE — matrix + story
--                     gate), check_tenant (BEFORE INSERT OR UPDATE —
--                     parent visibility/kind/scope), event_after_insert +
--                     event_after_update (AFTER — event capture with
--                     no-op gate and doctor-probe suppression)
--
-- Backfill (M-6): existing rows get kind = NULL (legacy flat — legal per
-- the coherence CHECK). No data rewrite needed.
--
-- Closes party findings: B-1, B-4, B-5, R-1, R-2, R-7, R-10, R-19, M-1,
-- M-6, M-10, M-11.
--
-- NOTE (S6 deferral): archive-children-first is deferred to v006 (R-3,
-- M-4). In v005, deleting/archiving a story with any slice row is blocked
-- by the FK NO ACTION — the story-gate keeps completed stories free of
-- active slices, but completed/cancelled slices still block archive_old
-- until v006.
-- ============================================================================

BEGIN;

-- ── 3.1 hierarchy ───────────────────────────────────────────────────────
-- parent FK gives story-delete block free (M-1). kind: 'story'/'slice',
-- NULL = legacy flat.
ALTER TABLE tasks.tasks ADD COLUMN IF NOT EXISTS parent_id UUID
    REFERENCES tasks.tasks(id) ON DELETE NO ACTION;
ALTER TABLE tasks.tasks ADD COLUMN IF NOT EXISTS kind TEXT
    CHECK (kind IS NULL OR kind IN ('story','slice'));

ALTER TABLE tasks.tasks DROP CONSTRAINT IF EXISTS tasks_hierarchy_coherence;
ALTER TABLE tasks.tasks ADD CONSTRAINT tasks_hierarchy_coherence CHECK (
    (kind = 'story' AND parent_id IS NULL)
    OR (kind = 'slice' AND parent_id IS NOT NULL)
    OR (kind IS NULL AND parent_id IS NULL)
);

CREATE INDEX IF NOT EXISTS idx_tasks_parent
    ON tasks.tasks (parent_id) WHERE parent_id IS NOT NULL;

-- ── 3.2 paused status (R-7: CHECK + task_upsert CASE + column CHECK) ────
ALTER TABLE tasks.tasks DROP CONSTRAINT IF EXISTS tasks_status_check;
ALTER TABLE tasks.tasks ADD CONSTRAINT tasks_status_check CHECK (
    status IN ('pending','in_progress','paused','completed','cancelled'));

-- Column coherence unchanged except explicitly named; paused derives
-- column = NULL and the leading "column" IS NULL admits it for any status.
ALTER TABLE tasks.tasks DROP CONSTRAINT IF EXISTS tasks_check;
ALTER TABLE tasks.tasks ADD CONSTRAINT tasks_column_check CHECK (
    "column" IS NULL OR (
        ("column" IN ('backlog','todo') AND status = 'pending')
        OR ("column" = 'in_progress' AND status = 'in_progress')
        OR ("column" = 'done' AND status = 'completed')
        OR ("column" = 'review' AND status IN ('pending','in_progress'))
    ));

-- ── 3.3 correlation_id for bus traceability (R-19) ──────────────────────
-- session_id stays provenance; correlation_id links bus message → task.
-- Partial unique index → 1 task per bus message even across handler
-- restart/state-file loss (Architect R-4 idempotency).
ALTER TABLE tasks.tasks ADD COLUMN IF NOT EXISTS correlation_id TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_inbox_correlation
    ON tasks.tasks (correlation_id)
    WHERE source = 'inbox' AND correlation_id IS NOT NULL;

-- ── 3.4 task_events — the notify source of truth (B-5, R-1, M-11) ───────
CREATE TABLE IF NOT EXISTS tasks.task_events (
    id             BIGSERIAL PRIMARY KEY,
    task_id        UUID NOT NULL REFERENCES tasks.tasks(id) ON DELETE CASCADE,
    event_type     TEXT NOT NULL CHECK (event_type IN
                     ('created','status_changed','story_auto_complete')),
    from_status    TEXT,               -- NULL for 'created'
    to_status      TEXT,
    reason         TEXT,               -- 'switch','stale','story_auto_complete','reopen',…
    by             TEXT NOT NULL,      -- profile (resolved from session_user)
    session_id     TEXT,
    correlation_id TEXT,
    at             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_task_events_task_at
    ON tasks.task_events (task_id, at);

-- INSERT-only for app roles: readers SELECT via policy; writes ONLY via
-- task_log_event() (SECURITY DEFINER owned by mycortex) — no direct
-- UPDATE/DELETE grants (Security R-1 forge-proof audit). Retention: events
-- CASCADE with task delete (SRE R-9/R-19).
ALTER TABLE tasks.task_events ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS task_events_select ON tasks.task_events;
CREATE POLICY task_events_select ON tasks.task_events FOR SELECT USING (
    EXISTS (SELECT 1 FROM tasks.tasks t WHERE t.id = task_id
            AND (t.scope = 'fleet' OR t.created_by = tasks.profile_of(current_user))));

GRANT SELECT ON tasks.task_events TO mycortex_reader;

-- Event write path — SECURITY DEFINER (owner mycortex): app roles have no
-- direct DML on task_events; the AFTER triggers call this. 'by' resolves
-- from session_user (the authenticated role) — SECURITY DEFINER would
-- otherwise see the definer as current_user (postgres-schema-design #1
-- gotcha).
CREATE OR REPLACE FUNCTION tasks.task_log_event(
    p_task_id        UUID,
    p_event_type     TEXT,
    p_from_status    TEXT DEFAULT NULL,
    p_to_status      TEXT DEFAULT NULL,
    p_reason         TEXT DEFAULT NULL,
    p_by             TEXT DEFAULT NULL,
    p_session_id     TEXT DEFAULT NULL,
    p_correlation_id TEXT DEFAULT NULL
) RETURNS BIGINT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = tasks, pg_temp
AS $$
DECLARE
    v_by TEXT := COALESCE(p_by, tasks.profile_of(session_user));
    v_id BIGINT;
BEGIN
    IF v_by IS NULL OR v_by = '' THEN
        RAISE EXCEPTION 'task_log_event: cannot resolve caller profile (session_user=%)',
            session_user;
    END IF;
    INSERT INTO tasks.task_events
        (task_id, event_type, from_status, to_status, reason, by,
         session_id, correlation_id)
    VALUES
        (p_task_id, p_event_type, p_from_status, p_to_status, p_reason, v_by,
         p_session_id, p_correlation_id)
    RETURNING id INTO v_id;
    RETURN v_id;
END;
$$;
REVOKE ALL ON FUNCTION tasks.task_log_event(UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT) FROM PUBLIC;

-- ── 3.5 transition matrix helper ────────────────────────────────────────
-- B-4 enforced in the DB write path; see docs/design/task-lifecycle-v2.md
-- §4. Reopen (completed → in_progress) requires reason='reopen'.
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
            RETURN p_to IN ('in_progress', 'cancelled');
        WHEN 'in_progress' THEN
            RETURN p_to IN ('paused', 'completed', 'cancelled');
        WHEN 'paused' THEN
            RETURN p_to IN ('in_progress', 'completed', 'cancelled');
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
REVOKE ALL ON FUNCTION tasks.transition_allowed(TEXT, TEXT, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tasks.transition_allowed(TEXT, TEXT, TEXT) TO mycortex_reader;

-- ── Transition trigger (BEFORE UPDATE, INVOKER) ─────────────────────────
-- Authoritative gate for direct SQL AND task_upsert (ON CONFLICT DO UPDATE
-- fires UPDATE triggers). Reopen requires the tasks.transition_reason
-- session GUC set to 'reopen' by the caller immediately before the upsert
-- (fail-closed: no GUC → no reopen). Story gate (Domain R-3): a story may
-- not be completed while any non-cancelled slice is active; auto-complete
-- itself is v006 — v005 ships the gate.
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

DROP TRIGGER IF EXISTS tasks_transition_trigger ON tasks.tasks;
CREATE TRIGGER tasks_transition_trigger
    BEFORE UPDATE ON tasks.tasks
    FOR EACH ROW EXECUTE FUNCTION tasks.check_transition();

-- ── Tenant coherence trigger (BEFORE INSERT OR UPDATE, INVOKER) ─────────
-- R-2: slice.parent must be visible to the caller — enforced by RLS on the
-- lookup (INVOKER security: a cross-tenant parent is invisible → NOT FOUND
-- → raise; a SECURITY DEFINER lookup would bypass RLS and defeat the check).
-- Parent must be a story; slice.scope ≤ parent.scope (fleet slice under a
-- personal story forbidden).
CREATE OR REPLACE FUNCTION tasks.check_tenant()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_parent_scope TEXT;
    v_parent_kind  TEXT;
BEGIN
    IF NEW.parent_id IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT scope, kind INTO v_parent_scope, v_parent_kind
    FROM tasks.tasks
    WHERE id = NEW.parent_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'parent task % not found or not visible', NEW.parent_id;
    END IF;
    IF v_parent_kind IS DISTINCT FROM 'story' THEN
        RAISE EXCEPTION 'parent task % is not a story (kind=%)',
            NEW.parent_id, COALESCE(v_parent_kind, 'flat');
    END IF;
    IF NEW.scope = 'fleet' AND v_parent_scope = 'personal' THEN
        RAISE EXCEPTION 'slice scope (fleet) exceeds parent scope (personal)';
    END IF;
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION tasks.check_tenant() FROM PUBLIC;

DROP TRIGGER IF EXISTS tasks_tenant_trigger ON tasks.tasks;
CREATE TRIGGER tasks_tenant_trigger
    BEFORE INSERT OR UPDATE ON tasks.tasks
    FOR EACH ROW EXECUTE FUNCTION tasks.check_tenant();

-- ── Event capture triggers (AFTER, SECURITY DEFINER) ────────────────────
-- B-5/R-1/M-11: one enforcement point covers CLI, MCP, handler, restore,
-- bridge — future callers can't forget. No-op gate (QA B-5): status
-- unchanged → no event. Suppression at source (M-5): doctor-probe rows
-- emit NO events (and thus no notify).
CREATE OR REPLACE FUNCTION tasks.event_after_insert()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = tasks, pg_temp
AS $$
BEGIN
    IF NEW.source = 'doctor-probe' THEN
        RETURN NEW;
    END IF;
    PERFORM tasks.task_log_event(
        NEW.id, 'created', NULL, NEW.status, NULL,
        NULL, NEW.session_id, NEW.correlation_id);
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION tasks.event_after_insert() FROM PUBLIC;

CREATE OR REPLACE FUNCTION tasks.event_after_update()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = tasks, pg_temp
AS $$
DECLARE
    v_reason TEXT;
BEGIN
    IF NEW.source = 'doctor-probe' OR OLD.status IS NOT DISTINCT FROM NEW.status THEN
        RETURN NEW;
    END IF;
    v_reason := NULLIF(current_setting('tasks.transition_reason', true), '');
    PERFORM tasks.task_log_event(
        NEW.id, 'status_changed', OLD.status, NEW.status, v_reason,
        NULL, NEW.session_id, NEW.correlation_id);
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION tasks.event_after_update() FROM PUBLIC;

DROP TRIGGER IF EXISTS tasks_event_insert_trigger ON tasks.tasks;
CREATE TRIGGER tasks_event_insert_trigger
    AFTER INSERT ON tasks.tasks
    FOR EACH ROW EXECUTE FUNCTION tasks.event_after_insert();

DROP TRIGGER IF EXISTS tasks_event_update_trigger ON tasks.tasks;
CREATE TRIGGER tasks_event_update_trigger
    AFTER UPDATE OF status ON tasks.tasks
    FOR EACH ROW EXECUTE FUNCTION tasks.event_after_update();

-- ── task_upsert 20-arg (QA M-10: APPEND with defaults) ──────────────────
-- CREATE OR REPLACE cannot change arity — the 17-arg function must be
-- dropped first (same transaction: a failure rolls both back). 17-arg
-- legacy callers (dream-bridge, restore, MCP wrappers, positional SQL
-- strings) then resolve to the 20-arg function via trailing defaults.
DROP FUNCTION IF EXISTS tasks.task_upsert(UUID, TEXT, TEXT, TEXT, TEXT, TEXT,
    TEXT, TEXT, TEXT, TEXT, INT, INT, TIMESTAMPTZ, TEXT[], TEXT, UUID[], TEXT);
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
        content          = COALESCE(EXCLUDED.content, tasks.tasks.content),
        assignee         = COALESCE(EXCLUDED.assignee, tasks.tasks.assignee),
        project          = COALESCE(EXCLUDED.project, tasks.tasks.project),
        repo             = COALESCE(EXCLUDED.repo, tasks.tasks.repo),
        target           = COALESCE(EXCLUDED.target, tasks.tasks.target),
        scope            = COALESCE(EXCLUDED.scope, tasks.tasks.scope),
        status           = COALESCE(EXCLUDED.status, tasks.tasks.status),
        -- v004: column always reflects the NEW state's derived value —
        -- never carry over a stale column (that produced cancelled+todo →
        -- CHECK). For v005 the same holds for paused (derives NULL).
        "column"         = EXCLUDED."column",
        "position"       = COALESCE(EXCLUDED."position", tasks.tasks."position"),
        priority         = COALESCE(EXCLUDED.priority, tasks.tasks.priority),
        due              = COALESCE(EXCLUDED.due, tasks.tasks.due),
        tags             = COALESCE(EXCLUDED.tags, tasks.tasks.tags),
        source           = COALESCE(EXCLUDED.source, tasks.tasks.source),
        depends_on       = COALESCE(EXCLUDED.depends_on, tasks.tasks.depends_on),
        session_id       = COALESCE(EXCLUDED.session_id, tasks.tasks.session_id),
        parent_id        = COALESCE(EXCLUDED.parent_id, tasks.tasks.parent_id),
        kind             = COALESCE(EXCLUDED.kind, tasks.tasks.kind),
        correlation_id   = COALESCE(EXCLUDED.correlation_id, tasks.tasks.correlation_id),
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
