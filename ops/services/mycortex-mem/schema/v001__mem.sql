-- ============================================================================
-- mycortex_mem schema v001 — persistent memory (Honcho replacement)
-- Backend for the mycortex-mem MemoryProvider plugin.
-- Target: mycortex-postgres, database mycortex, schema mycortex_mem
--
-- Design principles:
--   - Peer model: each workspace has peers (user, ai, etc.)
--   - Sessions: summaries per peer pair, not raw message dumps
--   - Extensible: JSONB for cards/profiles, TSVECTOR for search
--   - Minimal schema: 6 tables, one migration, no premature abstraction
--   - Role split: admin/writer/reader (fail-closed)
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS mycortex_mem;

-- ── Roles (idempotent DO blocks) ──
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mycortex_mem_admin') THEN
    CREATE ROLE mycortex_mem_admin LOGIN;
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mycortex_mem_writer') THEN
    CREATE ROLE mycortex_mem_writer LOGIN;
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mycortex_mem_reader') THEN
    CREATE ROLE mycortex_mem_reader LOGIN;
  END IF;
END $$;

-- ── Peers ──
CREATE TABLE IF NOT EXISTS mycortex_mem.peers (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace      TEXT NOT NULL,
    peer_name      TEXT NOT NULL,
    peer_type      TEXT NOT NULL DEFAULT 'user',
    display_name   TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (workspace, peer_name)
);

-- ── Profiles (peer cards) ──
CREATE TABLE IF NOT EXISTS mycortex_mem.profiles (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    peer_id        UUID NOT NULL REFERENCES mycortex_mem.peers(id) ON DELETE CASCADE,
    card           JSONB NOT NULL DEFAULT '[]'::jsonb,
    representation TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (peer_id)
);

-- ── Sessions ──
CREATE TABLE IF NOT EXISTS mycortex_mem.sessions (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_key    TEXT NOT NULL,
    user_peer_id   UUID REFERENCES mycortex_mem.peers(id),
    ai_peer_id     UUID REFERENCES mycortex_mem.peers(id),
    title          TEXT,
    summary        TEXT,
    message_count  INT NOT NULL DEFAULT 0,
    token_count    INT,
    started_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at       TIMESTAMPTZ,
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (session_key)
);

-- ── Messages (per-turn history) ──
CREATE TABLE IF NOT EXISTS mycortex_mem.messages (
    id             BIGSERIAL PRIMARY KEY,
    session_id     UUID NOT NULL REFERENCES mycortex_mem.sessions(id) ON DELETE CASCADE,
    peer_id        UUID NOT NULL REFERENCES mycortex_mem.peers(id),
    role           TEXT NOT NULL,
    content        TEXT NOT NULL,
    fts            TSVECTOR,
    token_count    INT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_mem_messages_session ON mycortex_mem.messages (session_id);
CREATE INDEX IF NOT EXISTS idx_mem_messages_fts    ON mycortex_mem.messages USING GIN (fts);

-- ── Conclusions (persistent facts about a peer) ──
CREATE TABLE IF NOT EXISTS mycortex_mem.conclusions (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    peer_id        UUID NOT NULL REFERENCES mycortex_mem.peers(id) ON DELETE CASCADE,
    fact           TEXT NOT NULL,
    category       TEXT DEFAULT 'general',
    confidence     TEXT NOT NULL DEFAULT 'high',
    source         TEXT NOT NULL DEFAULT 'agent',
    archived       BOOLEAN NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_mem_conclusions_peer ON mycortex_mem.conclusions (peer_id) WHERE NOT archived;

-- ── Interceptor Log (shared with prompt-guard plugin) ──
CREATE TABLE IF NOT EXISTS mycortex_mem.interceptor_log (
    id                BIGSERIAL PRIMARY KEY,
    stage             TEXT NOT NULL,
    action            TEXT NOT NULL,
    reason            TEXT,
    message_snippet   TEXT,
    model             TEXT,
    provider          TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Schema version ──
CREATE TABLE IF NOT EXISTS mycortex_mem.schema_version (
    version       INT PRIMARY KEY,
    applied_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── Grants (role split) ──
GRANT USAGE ON SCHEMA mycortex_mem TO mycortex_mem_admin, mycortex_mem_writer, mycortex_mem_reader;

GRANT CREATE ON SCHEMA mycortex_mem TO mycortex_mem_admin;
GRANT ALL ON ALL TABLES IN SCHEMA mycortex_mem TO mycortex_mem_admin;
GRANT ALL ON ALL SEQUENCES IN SCHEMA mycortex_mem TO mycortex_mem_admin;

GRANT SELECT, INSERT, UPDATE, DELETE ON mycortex_mem.peers TO mycortex_mem_writer;
GRANT SELECT, INSERT, UPDATE, DELETE ON mycortex_mem.profiles TO mycortex_mem_writer;
GRANT SELECT, INSERT, UPDATE ON mycortex_mem.sessions TO mycortex_mem_writer;
GRANT SELECT, INSERT ON mycortex_mem.messages TO mycortex_mem_writer;
GRANT SELECT, INSERT, UPDATE ON mycortex_mem.conclusions TO mycortex_mem_writer;
GRANT SELECT, INSERT ON mycortex_mem.interceptor_log TO mycortex_mem_writer;
GRANT USAGE ON ALL SEQUENCES IN SCHEMA mycortex_mem TO mycortex_mem_writer;
REVOKE ALL ON mycortex_mem.schema_version FROM mycortex_mem_writer;

GRANT SELECT ON mycortex_mem.peers TO mycortex_mem_reader;
GRANT SELECT ON mycortex_mem.profiles TO mycortex_mem_reader;
GRANT SELECT ON mycortex_mem.sessions TO mycortex_mem_reader;
GRANT SELECT ON mycortex_mem.messages TO mycortex_mem_reader;
GRANT SELECT ON mycortex_mem.conclusions TO mycortex_mem_reader;
