-- ============================================================================
-- tasks schema v001 — enterprise task workflow for the fleet (todo replacement)
-- Source: docs/design/task-workflow.md (party-reviewed 2026-08-06)
-- Applied by: ops/services/tasks/migrate.py (version-gated, NOT cortex-update
--             directly — mirrors ops/services/mycortex/migrate.py)
-- Target: mycortex-postgres, database `mycortex`, schema `tasks`
--
-- DESIGN NOTES (party fixes baked in):
--   B-1  Injection: all DML goes through parameterized task_upsert(); the CLI
--        never string-builds WHERE clauses (allowlists live in task-db.py).
--   B-2  Least privilege: CRUD as mycortex_reader_<profile>; DDL here runs as
--        mycortex_admin; fleet writes require todos_fleet_writer membership.
--        RLS fail-closed: un-granted profile sees zero rows.
--   B-4  status is canonical; column is a dormant display field with a CHECK
--        coherence rule. Single write path task_upsert() derives column.
--   B-5  PII: project is TEXT (client names live in a private app registry,
--        NEVER in a public-repo CHECK). Fleet × client-project blocked.
--   B-9  Version-gated: tasks.schema_version tracks applied versions.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS tasks;

-- ── Version gate (B-9) ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tasks.schema_version (
    version     INT PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    applied_by  TEXT NOT NULL DEFAULT current_user
);

-- ── Roles (cluster-level; idempotent DO-block guards — no CREATE ROLE IF NOT EXISTS) ──
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'todos_fleet_writer') THEN
    CREATE ROLE todos_fleet_writer NOLOGIN;
  END IF;
END $$;

-- ── Helper: profile of the connecting role (mycortex_reader_<profile> → <profile>) ──
CREATE OR REPLACE FUNCTION tasks.profile_of(p_role name DEFAULT current_user)
RETURNS text
LANGUAGE sql
STABLE
AS $$
    SELECT CASE
        WHEN p_role::text LIKE 'mycortex_reader\_%' THEN
            substring(p_role::text FROM 17)  -- strip 'mycortex_reader_'
        ELSE p_role::text
    END;
$$;

-- ── Helper: may this role write scope=fleet rows? ────────────────────
CREATE OR REPLACE FUNCTION tasks.is_fleet_writer(p_role name DEFAULT current_user)
RETURNS boolean
LANGUAGE sql
STABLE
AS $$
    SELECT EXISTS (
        SELECT 1 FROM pg_roles
        WHERE rolname = 'todos_fleet_writer'
          AND pg_has_role(p_role, 'todos_fleet_writer', 'member')
    );
$$;

-- ── Content scrub gate for fleet writes (B-5, PII) ───────────────────
-- Rejects absolute paths, user@host, and IP addresses in fleet content.
CREATE OR REPLACE FUNCTION tasks.content_ok_for_fleet(p_content text)
RETURNS boolean
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT NOT (
        p_content ~ '/[A-Za-z0-9_\-]+/[A-Za-z0-9_\-/.]*'       -- abs path smell
        OR p_content ~ '[A-Za-z0-9._\-]+@[A-Za-z0-9.\-]+'      -- user@host
        OR p_content ~ '\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b' -- IPv4
    );
$$;

-- ── Tasks table ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tasks.tasks (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content            TEXT NOT NULL,
    created_by         TEXT NOT NULL,                -- provenance + de-facto tenant
    assignee           TEXT,                         -- metadata-only until transport
    project            TEXT NOT NULL DEFAULT 'hermes-cortex',  -- TEXT, app-layer registry
    repo               TEXT,                         -- label only, resolved once at creation
    target             TEXT,                         -- host/service name; validated in CLI
    scope              TEXT NOT NULL DEFAULT 'personal'
                       CHECK (scope IN ('personal','fleet')),
    status             TEXT NOT NULL DEFAULT 'pending'
                       CHECK (status IN ('pending','in_progress','completed','cancelled')),
    "column"           TEXT,                         -- dormant display field (B-4)
                       -- ⚠️ RESERVED WORD — must be quoted ("column") in every query
                       CHECK ("column" IS NULL OR (
                           ("column" IN ('backlog','todo') AND status = 'pending')
                           OR ("column" = 'in_progress' AND status = 'in_progress')
                           OR ("column" = 'done' AND status = 'completed')
                           OR ("column" = 'review' AND status IN ('pending','in_progress'))
                       )),
    "position"         INT,                          -- NULL = unpositioned; nulls-last
                       -- ⚠️ RESERVED WORD — must be quoted ("position") in every query
    priority           INT NOT NULL DEFAULT 0
                       CHECK (priority BETWEEN 0 AND 3),
    due                TIMESTAMPTZ,
    tags               TEXT[],
    source             TEXT NOT NULL DEFAULT 'manual'
                       CHECK (source IN ('dream','session','manual','bridge','governance','inbox')),
    depends_on         UUID[],                       -- no FK — deliberate at this scale
    session_id         TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    status_changed_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at       TIMESTAMPTZ
);

-- ── RLS: fail-closed (B-2) ───────────────────────────────────────────
-- Visible: fleet rows (everyone) OR personal rows of the connecting profile.
-- Writable: personal rows for own profile; fleet rows only for fleet writers.
ALTER TABLE tasks.tasks ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tasks_personal ON tasks.tasks;
CREATE POLICY tasks_personal ON tasks.tasks
    USING (scope = 'fleet' OR created_by = tasks.profile_of(current_user))
    WITH CHECK (
        (scope = 'personal' AND created_by = tasks.profile_of(current_user))
        OR (scope = 'fleet'
            AND tasks.is_fleet_writer(current_user)
            AND NOT (project LIKE 'client-%')           -- B-5: fleet × client banned
            AND tasks.content_ok_for_fleet(content))    -- B-5: scrub gate
    );

-- Indexes
CREATE INDEX IF NOT EXISTS idx_tasks_agent_status ON tasks.tasks (created_by, status);
CREATE INDEX IF NOT EXISTS idx_tasks_scope ON tasks.tasks (scope) WHERE scope = 'fleet';
CREATE INDEX IF NOT EXISTS idx_tasks_repo ON tasks.tasks (repo) WHERE repo IS NOT NULL;

-- ── Single write path (B-4): task_upsert ─────────────────────────────
-- All lifecycle mutations funnel through this function so column/status
-- coherence is centralized. Params are positional — never string-built SQL.
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
    -- Derive column from status when not explicitly provided (B-4)
    v_column := COALESCE(p_column, CASE v_status
        WHEN 'pending'     THEN 'todo'
        WHEN 'in_progress' THEN 'in_progress'
        WHEN 'completed'   THEN 'done'
        WHEN 'cancelled'   THEN 'done'
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
        "column"         = COALESCE(EXCLUDED."column", tasks.tasks."column"),
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

-- ── List (union: personal + locally-present fleet rows) ──────────────
CREATE OR REPLACE FUNCTION tasks.task_list(
    p_created_by TEXT DEFAULT NULL,
    p_status     TEXT DEFAULT NULL,
    p_scope      TEXT DEFAULT NULL,
    p_project    TEXT DEFAULT NULL,
    p_repo       TEXT DEFAULT NULL,
    p_assignee   TEXT DEFAULT NULL,
    p_tag        TEXT DEFAULT NULL,
    p_limit      INT DEFAULT 200
) RETURNS TABLE(
    id UUID, content TEXT, created_by TEXT, assignee TEXT, project TEXT,
    repo TEXT, target TEXT, scope TEXT, status TEXT, "column" TEXT,
    "position" INT, priority INT, due TIMESTAMPTZ, tags TEXT[], source TEXT,
    depends_on UUID[], session_id TEXT, created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ, status_changed_at TIMESTAMPTZ, completed_at TIMESTAMPTZ
)
LANGUAGE sql
STABLE
AS $$
    SELECT t.id, t.content, t.created_by, t.assignee, t.project, t.repo,
           t.target, t.scope, t.status, t."column", t."position", t.priority,
           t.due, t.tags, t.source, t.depends_on, t.session_id,
           t.created_at, t.updated_at, t.status_changed_at, t.completed_at
    FROM tasks.tasks t
    WHERE (p_created_by IS NULL OR t.created_by = p_created_by)
      AND (p_status IS NULL OR t.status = p_status)
      AND (p_scope IS NULL OR t.scope = p_scope)
      AND (p_project IS NULL OR t.project = p_project)
      AND (p_repo IS NULL OR t.repo = p_repo)
      AND (p_assignee IS NULL OR t.assignee = p_assignee)
      AND (p_tag IS NULL OR p_tag = ANY(t.tags))
    ORDER BY t.priority DESC, t.created_at ASC
    LIMIT p_limit;
$$;

-- ── Archive: move completed/cancelled to archive table ───────────────
CREATE TABLE IF NOT EXISTS tasks.task_archive (
    id UUID PRIMARY KEY,
    content TEXT NOT NULL,
    created_by TEXT NOT NULL,
    assignee TEXT,
    project TEXT NOT NULL,
    repo TEXT,
    target TEXT,
    scope TEXT NOT NULL,
    status TEXT NOT NULL,
    "column" TEXT,
    "position" INT,
    priority INT NOT NULL DEFAULT 0,
    due TIMESTAMPTZ,
    tags TEXT[],
    source TEXT NOT NULL DEFAULT 'manual',
    depends_on UUID[],
    session_id TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    status_changed_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    archived_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_task_archive_agent
    ON tasks.task_archive (created_by, archived_at);

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

    DELETE FROM tasks.tasks
    WHERE status IN ('completed', 'cancelled')
      AND (p_created_by IS NULL OR created_by = p_created_by);

    RETURN v_count;
END;
$$;

-- ── Prune: delete ONLY archived rows older than N (B-5 retention) ─────
-- Deletes archived rows only — active rows are never touched. Transactional,
-- logs the deleted count. Conservative defaults enforced by the caller.
CREATE OR REPLACE FUNCTION tasks.task_prune(
    p_older_than interval,
    p_created_by TEXT DEFAULT NULL
) RETURNS INT
LANGUAGE plpgsql
AS $$
DECLARE
    v_count INT;
BEGIN
    DELETE FROM tasks.task_archive
    WHERE archived_at < now() - p_older_than
      AND (p_created_by IS NULL OR created_by = p_created_by);

    GET DIAGNOSTICS v_count = ROW_COUNT;
    RETURN v_count;
END;
$$;

-- ── Grants (B-2 least privilege) ─────────────────────────────────────
-- Base capability: every profile role inherits mycortex_reader → schema access.
GRANT USAGE ON SCHEMA tasks TO mycortex_reader;
GRANT SELECT, INSERT, UPDATE, DELETE ON tasks.tasks TO mycortex_reader;
-- task_archive_old() INSERTs into task_archive + DELETEs from it on prune —
-- the reader role needs DML on the archive table too.
GRANT SELECT, INSERT, DELETE ON tasks.task_archive TO mycortex_reader;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA tasks TO mycortex_reader;

-- Fleet writers: orchestrator profile roles only. Conditional DO-block —
-- worker hosts don't have mycortex_reader_moses/esther, and granting to a
-- nonexistent role FAILS the migration. Orchestrator profile roles get
-- membership here; workers stay read-only on fleet rows (RLS WITH CHECK).
DO $$ BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'mycortex_reader_esther') THEN
    GRANT todos_fleet_writer TO mycortex_reader_esther;
  END IF;
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'mycortex_reader_moses') THEN
    GRANT todos_fleet_writer TO mycortex_reader_moses;
  END IF;
END $$;

-- DDL/schema apply runs as mycortex_admin (migrate.py); CRUD never touches
-- superuser (task-db.py connects as mycortex_reader_<profile>).
