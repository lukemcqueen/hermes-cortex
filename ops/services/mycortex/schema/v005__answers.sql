-- ============================================================================
-- mycortex schema v005 — agent answer cache (S-017)
-- Source: docs/design/mycortex-answers-DESIGN.md
-- Applied by: ops/services/mycortex/migrate.py (NOT by cortex-update.sh directly)
-- Target: mycortex-postgres, database `mycortex`, schema `mycortex`
--
-- Adds an `answers` table storing cached LLM responses keyed by query + source
-- scope. Separates Q&A from bug-fix/skill lessons (which live in the `lessons`
-- brain source). Each entry stores the original query, answer, hash for
-- dedup, and quality metadata. RLS isolates per profile.
--
-- RLS note: answers table gets its own RLS/FORCE with its own policies and
-- source_grants-like access control. Agents see answers iff their reader role
-- has a grant for the answer's source scope.
-- ============================================================================

CREATE TABLE IF NOT EXISTS mycortex.answers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_scope    TEXT NOT NULL DEFAULT 'federated', -- 'federated' (visible to all) or source name (isolated to that source's readers)
    query_hash      TEXT NOT NULL,                   -- sha256(normalized query) for dedup
    query           TEXT NOT NULL,                   -- original query text
    normalized_query TEXT NOT NULL,                   -- lowercased, stripped for matching
    answer          TEXT NOT NULL,                   -- the LLM's answer
    answer_hash     TEXT NOT NULL,                   -- sha256(answer) for content dedup
    confidence      TEXT NOT NULL DEFAULT 'medium',   -- 'high' | 'medium' | 'low'
    quality_gate    TEXT NOT NULL DEFAULT 'passed',   -- 'passed' | 'refused' | 'pii_rejected' | 'time_sensitive'
    token_count     INT,                             -- token count for cost tracking
    model           TEXT,                            -- model that produced the answer
    agent_name      TEXT,                            -- agent that stored the answer
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    accessed_at     TIMESTAMPTZ,                     -- last access time for LRU-style pruning
    access_count    INT NOT NULL DEFAULT 0,          -- usage counter
    archived        BOOLEAN NOT NULL DEFAULT FALSE
);

-- Fast lookup by hash for dedup
CREATE UNIQUE INDEX IF NOT EXISTS uq_answers_query_hash
    ON mycortex.answers (query_hash)
    WHERE NOT archived;

-- Search by normalized query text
CREATE INDEX IF NOT EXISTS idx_answers_query_gin
    ON mycortex.answers USING GIN (to_tsvector('simple', normalized_query))
    WHERE NOT archived;

-- Sorted by recency for listing
CREATE INDEX IF NOT EXISTS idx_answers_created_at
    ON mycortex.answers (created_at DESC)
    WHERE NOT archived;

-- Usage-based pruning index
CREATE INDEX IF NOT EXISTS idx_answers_access_count
    ON mycortex.answers (access_count)
    WHERE NOT archived AND access_count > 0;

-- Similarity search via trigram on query
CREATE INDEX IF NOT EXISTS idx_answers_query_trgm
    ON mycortex.answers USING GIN (query gin_trgm_ops)
    WHERE NOT archived;

-- Trigram index on normalized_query for semantic dedup/search
CREATE INDEX IF NOT EXISTS idx_answers_normalized_query_trgm
    ON mycortex.answers USING GIN (normalized_query gin_trgm_ops)
    WHERE NOT archived;

-- ── RLS (fail-closed, same pattern as pages/content_chunks) ──
ALTER TABLE mycortex.answers ENABLE ROW LEVEL SECURITY;
ALTER TABLE mycortex.answers FORCE ROW LEVEL SECURITY;

-- Visibility helper: can this reader role see this answer?
-- Federated answers are visible to all. Source-scoped answers require
-- an explicit grant to the reader's role for that source name.
CREATE OR REPLACE FUNCTION mycortex.is_answer_visible(p_answer_id UUID, p_role TEXT)
RETURNS boolean
LANGUAGE sql
SECURITY DEFINER
SET search_path = mycortex
AS $$
    SELECT EXISTS (
        SELECT 1 FROM mycortex.answers a
        WHERE a.id = p_answer_id
          AND NOT a.archived
          AND (
            a.source_scope = 'federated'
            OR EXISTS (
                SELECT 1 FROM mycortex.sources s
                JOIN mycortex.source_grants g ON g.source_id = s.id
                WHERE s.name = a.source_scope
                  AND g.role_name = p_role
            )
          )
    );
$$;
REVOKE ALL ON FUNCTION mycortex.is_answer_visible(UUID, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mycortex.is_answer_visible(UUID, TEXT) TO mycortex_reader;

-- Reader SELECT policy
CREATE POLICY mycortex_answers_select ON mycortex.answers
    FOR SELECT TO mycortex_reader
    USING (mycortex.is_answer_visible(answers.id, current_user));

-- Ingest DML policy (same as pages: answer cache writes via ingest or agent operations)
CREATE POLICY mycortex_answers_ingest ON mycortex.answers
    FOR ALL TO mycortex_ingest
    USING (true) WITH CHECK (true);

-- Admin SELECT policy (orchestrators can see all answers for audit)
CREATE POLICY mycortex_answers_admin ON mycortex.answers
    FOR SELECT TO mycortex_admin
    USING (true);

-- Admin can also INSERT/UPDATE answers (quality gate resolution, manual curation)
CREATE POLICY mycortex_answers_admin_write ON mycortex.answers
    FOR INSERT TO mycortex_admin
    WITH CHECK (true);
CREATE POLICY mycortex_answers_admin_update ON mycortex.answers
    FOR UPDATE TO mycortex_admin
    USING (true) WITH CHECK (true);

-- ── Grants ────────────────────────────────────────────────────
-- mycortex_admin gets full control
GRANT ALL ON mycortex.answers TO mycortex_admin;
-- mycortex_ingest can read/write (for answer cache operations)
GRANT SELECT, INSERT, UPDATE ON mycortex.answers TO mycortex_ingest;
-- mycortex_reader can SELECT (RLS-filtered)
GRANT SELECT ON mycortex.answers TO mycortex_reader;
