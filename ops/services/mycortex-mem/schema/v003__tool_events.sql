-- v003__tool_events.sql — HC's own session event log.
--
-- WHY: the pre-commit reflexion gate read ~/.hermes/state.db — a HERMES-owned
-- artifact (hermes_state.py + 21 siblings write it). HC only read it. Two
-- consequences, both bad:
--
--   1. fragile — Hermes owns that schema, so a change to how IT records tool
--      calls silently breaks HC's gate;
--   2. HARNESS-LOCKED — a Pi/aider/CI session has no Hermes and therefore no
--      rows, so the gate is structurally unsatisfiable. Governance-by-reflexion
--      was Hermes-only, which contradicts the interoperability constraint.
--
-- So HC records its own. Same semantics as Hermes's `messages` (tool_name, role,
-- content JSON carrying a `name`), so the gate's question is unchanged while the
-- dependency is not. Any harness writes it through context_tools.
--
-- NO FALLBACK TO HERMES (Luke, 2026-10-02): the gate reads THIS table only. A
-- fallback would keep the incumbent load-bearing, which is the exact coupling
-- being removed — and it would hide a failure of HC's own recording instead of
-- surfacing it.

CREATE TABLE IF NOT EXISTS mycortex_mem.tool_events (
    id           BIGSERIAL PRIMARY KEY,
    -- UUID, matching mycortex_mem.sessions.id — NOT BIGSERIAL's bigint. The
    -- first draft declared BIGINT and the FK was un-implementable:
    --   'Key columns "session_id" and "id" are of incompatible types: bigint and uuid.'
    -- sessions.id is UUID (gen_random_uuid()) in v001; every FK to it must be
    -- UUID. Caught only by APPLYING the migration — no static check sees it,
    -- and both files read fine in isolation.
    session_id   UUID REFERENCES mycortex_mem.sessions(id) ON DELETE CASCADE,
    harness      TEXT,                       -- pi / hermes / claude-code / cron / …
    tool_name    TEXT NOT NULL,              -- e.g. 'skill_view'
    role         TEXT NOT NULL DEFAULT 'tool',
    content      JSONB,                      -- tool payload ({"name": ...} for skill_view)
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Generated column FIRST: the search index below depends on it, and creating an
-- index over a not-yet-existing column fails the whole migration.
ALTER TABLE mycortex_mem.tool_events
    ADD COLUMN IF NOT EXISTS content_text_tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('simple', coalesce(content::text, ''))) STORED;

-- The gate's exact query: "did this session load skill X?" (session + tool).
CREATE INDEX IF NOT EXISTS tool_events_session_tool_idx
    ON mycortex_mem.tool_events (session_id, tool_name, created_at DESC);

-- Look for a name inside the payload without JSONB operators.
CREATE INDEX IF NOT EXISTS tool_events_content_tsv_idx
    ON mycortex_mem.tool_events USING gin (content_text_tsv);

-- ── Grants (same role split as v001/v002) ────────────────────────
-- A new table inherits NOTHING: `GRANT ... ON ALL TABLES` was a one-time
-- statement. Without these the table exists and no role can read it, admin
-- included — verified on v002, where that was exactly the bug.
GRANT SELECT, INSERT ON mycortex_mem.tool_events TO mycortex_mem_writer;
GRANT SELECT ON mycortex_mem.tool_events TO mycortex_mem_reader;
GRANT ALL ON mycortex_mem.tool_events TO mycortex_mem_admin;
GRANT USAGE ON SEQUENCE mycortex_mem.tool_events_id_seq TO mycortex_mem_writer;
GRANT USAGE ON SEQUENCE mycortex_mem.tool_events_id_seq TO mycortex_mem_admin;
