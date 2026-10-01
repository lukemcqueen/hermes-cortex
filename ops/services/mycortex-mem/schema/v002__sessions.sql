-- ─────────────────────────────────────────────────────────────
--  mycortex_mem v002 — session checkpoints (S2c)
--
--  Memory and session are two views of ONE store: `mycortex_mem.sessions`
--  already keys a conversation, and `messages` already holds its history
--  (with an FTS index). What memory lacked was a STRUCTURED statement of
--  where a session is — done / pending / blockers / decisions — cheap enough
--  to restore from in a cold start and precise enough to resume from.
--
--  Design: docs/design/cortex-memory-session-mcp.md
--
--  The session row itself is reused, never duplicated: a checkpoint hangs off
--  `sessions.id`. session_key stays `harness:repo:branch` so identity is
--  explicit and derivable — never "latest" (a caller that cannot name its
--  session must not silently resume someone else's).
-- ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS mycortex_mem.checkpoints (
    id          BIGSERIAL PRIMARY KEY,
    session_id  UUID NOT NULL REFERENCES mycortex_mem.sessions(id) ON DELETE CASCADE,
    -- Denormalised for cheap filtering/listing without a join.
    harness     TEXT,
    repo        TEXT,
    branch      TEXT,
    -- Structured facts, never a transcript: the point of a checkpoint is that
    -- restoring it is cheap and deterministic (no LLM in the loop).
    done        JSONB NOT NULL DEFAULT '[]'::jsonb,
    pending     JSONB NOT NULL DEFAULT '[]'::jsonb,
    blockers    JSONB NOT NULL DEFAULT '[]'::jsonb,
    decisions   JSONB NOT NULL DEFAULT '[]'::jsonb,
    notes       TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Latest-checkpoint lookup is the hot path for session_restore.
CREATE INDEX IF NOT EXISTS idx_mem_checkpoints_session
    ON mycortex_mem.checkpoints (session_id, created_at DESC);

-- "what happened on this repo/branch" without joining sessions.
CREATE INDEX IF NOT EXISTS idx_mem_checkpoints_repo
    ON mycortex_mem.checkpoints (repo, created_at DESC);

-- Keyword search across ALL checkpoint text — the structured arrays included,
-- not just notes. session_search must answer "did we already try X?" where X
-- was recorded as a decision or a blocker, not only in prose.
CREATE INDEX IF NOT EXISTS idx_mem_checkpoints_fts
    ON mycortex_mem.checkpoints USING GIN (
        to_tsvector('english',
            coalesce(notes, '') || ' ' ||
            coalesce(done::text, '') || ' ' ||
            coalesce(pending::text, '') || ' ' ||
            coalesce(blockers::text, '') || ' ' ||
            coalesce(decisions::text, '')));

-- ── Grants (same role split as v001) ─────────────────────────
-- A new table inherits NOTHING from v001's grants: `GRANT ... ON ALL TABLES`
-- was a one-time statement, so without an explicit grant here the table exists
-- but NO role can touch it — including admin (verified: all three failed).
GRANT ALL ON mycortex_mem.checkpoints TO mycortex_mem_admin;
GRANT USAGE ON SEQUENCE mycortex_mem.checkpoints_id_seq TO mycortex_mem_admin;

-- Append-only: the writer inserts and reads back, never updates or deletes
-- (history is corrected by appending, not rewriting).
GRANT SELECT, INSERT ON mycortex_mem.checkpoints TO mycortex_mem_writer;
GRANT USAGE ON SEQUENCE mycortex_mem.checkpoints_id_seq TO mycortex_mem_writer;

GRANT SELECT ON mycortex_mem.checkpoints TO mycortex_mem_reader;

-- NOTE: do NOT insert into schema_version here — migrate.py records the
-- version itself once this file applies cleanly. The table is only
-- (version, applied_at); there is no description column.
