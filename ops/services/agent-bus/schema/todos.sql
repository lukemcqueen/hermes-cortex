-- ─────────────────────────────────────────────────────────────
-- Hermes Cortex Agent Bus — Cross-Session Todo Persistence
--
-- Durable per-agent todo items that survive session boundaries.
-- All agents share the same Postgres — fleet-visible by default.
--
-- Tables:
--   bus.todos         — todo items with agent ownership + status
--   bus.todo_archive  — completed/cancelled items (optional audit)
--
-- Functions:
--   bus.todo_save()   — upsert a todo item
--   bus.todo_list()   — list todos for an agent by status
--   bus.todo_clear()  — archive all completed/cancelled items
-- ─────────────────────────────────────────────────────────────

-- ── Todo Items ──────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS bus.todos (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_name      TEXT NOT NULL,
    content         TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending',
        CHECK (status IN ('pending', 'in_progress', 'completed', 'cancelled')),
    session_id      TEXT,
    priority        INT DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_todos_agent_status
    ON bus.todos (agent_name, status);

CREATE INDEX IF NOT EXISTS idx_todos_agent_session
    ON bus.todos (agent_name, session_id);

-- ── Todo Archive ────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS bus.todo_archive (
    id              UUID PRIMARY KEY,
    agent_name      TEXT NOT NULL,
    content         TEXT NOT NULL,
    status          TEXT NOT NULL,
    session_id      TEXT,
    priority        INT DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL,
    updated_at      TIMESTAMPTZ NOT NULL,
    archived_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_todo_archive_agent
    ON bus.todo_archive (agent_name, archived_at);

-- ── Helper: upsert a todo (insert or update by id) ──────────

CREATE OR REPLACE FUNCTION bus.todo_upsert(
    p_id            UUID,
    p_agent_name    TEXT,
    p_content       TEXT,
    p_status        TEXT DEFAULT 'pending',
    p_session_id    TEXT DEFAULT NULL,
    p_priority      INT DEFAULT 0
) RETURNS UUID
LANGUAGE plpgsql
AS $$
DECLARE
    v_id UUID;
BEGIN
    INSERT INTO bus.todos (id, agent_name, content, status, session_id, priority)
    VALUES (COALESCE(p_id, gen_random_uuid()), p_agent_name, p_content, p_status, p_session_id, p_priority)
    ON CONFLICT (id) DO UPDATE SET
        content    = EXCLUDED.content,
        status     = EXCLUDED.status,
        session_id = EXCLUDED.session_id,
        priority   = EXCLUDED.priority,
        updated_at = now()
    RETURNING id INTO v_id;

    RETURN v_id;
END;
$$;

-- ── Helper: list todos for an agent ─────────────────────────

CREATE OR REPLACE FUNCTION bus.todo_list(
    p_agent_name TEXT DEFAULT NULL,
    p_status TEXT DEFAULT NULL
) RETURNS TABLE(
    id          UUID,
    agent_name  TEXT,
    content     TEXT,
    status      TEXT,
    session_id  TEXT,
    priority    INT,
    created_at  TIMESTAMPTZ,
    updated_at  TIMESTAMPTZ
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT t.id, t.agent_name, t.content, t.status, t.session_id,
           t.priority, t.created_at, t.updated_at
    FROM bus.todos t
    WHERE (p_agent_name IS NULL OR t.agent_name = p_agent_name)
      AND (p_status IS NULL OR t.status = p_status)
    ORDER BY t.priority DESC, t.created_at ASC;
END;
$$;

-- ── Helper: archive completed/cancelled items ───────────────

CREATE OR REPLACE FUNCTION bus.todo_archive_old(
    p_agent_name TEXT DEFAULT NULL
) RETURNS INT
LANGUAGE plpgsql
AS $$
DECLARE
    v_count INT;
BEGIN
    INSERT INTO bus.todo_archive
    SELECT id, agent_name, content, status, session_id, priority,
           created_at, updated_at, now()
    FROM bus.todos
    WHERE status IN ('completed', 'cancelled')
      AND (p_agent_name IS NULL OR agent_name = p_agent_name);

    GET DIAGNOSTICS v_count = ROW_COUNT;

    DELETE FROM bus.todos
    WHERE status IN ('completed', 'cancelled')
      AND (p_agent_name IS NULL OR agent_name = p_agent_name);

    RETURN v_count;
END;
$$;
