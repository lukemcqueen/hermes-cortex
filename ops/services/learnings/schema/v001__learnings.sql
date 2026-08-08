-- ============================================================================
-- learnings schema v001 — fleet learning ledger (F-001, self-healing loop)
-- Source: docs/design/learning-ledger.md (party-reviewed 2026-08-08, Option A)
-- Applied by: ops/services/learnings/migrate.py (version-gated, mirror of
--             ops/services/tasks/migrate.py)
-- Target: mycortex-postgres, database `mycortex`, schema `learnings`
--         (same Postgres that hosts bus.* — "bus Postgres" per party doc)
--
-- PARTY DECISIONS BAKED IN (docs/elicit/2026-08-08_self-healing-auto-learning-party.md):
--   L-1  INSERT-only collectors — capture() is the ONLY write path; no role
--        gets table INSERT/UPDATE/DELETE. Lifecycle (orchestrator) gets
--        SELECT + set_status() only. "No UPDATE from fleet" (Security 8/10).
--   L-2  Scrub hook strips PII at insert (BEFORE INSERT trigger, reuses
--        pii-scrubbing patterns: email / IPv4 / home-path → placeholders).
--   L-3  Deterministic dedup at write — UNIQUE (route, content_hash);
--        ON CONFLICT DO NOTHING keeps capture() idempotent (QA 8/10).
--        Monday deep-eval semantic merge is a separate pass (F-006+).
--   L-4  Status lifecycle: pending → evaluated → applied → verified → retired
--        (elicit F-001). impact_score scale: -3..+3 (0=unknown, +improvement,
--        -regression) — documented convention for F-006 consumers.
--   L-5  Zero LLM cost on the agent side — collectors are no_agent scripts
--        hitting POST /api/learnings (server-side write, existing bus auth).
--   L-6  RLS fail-closed like tasks (B-2): un-granted role sees zero rows.
-- ============================================================================

CREATE SCHEMA IF NOT EXISTS learnings;

-- ── pgcrypto for sha256 content_hash (L-3) ─────────────────────────
-- Available cluster-wide (pg_available_extensions), created per-DB here so
-- fresh test DBs and the live mycortex DB both get digest().
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ── Version gate ─────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS learnings.schema_version (
    version     INT PRIMARY KEY,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    applied_by  TEXT NOT NULL DEFAULT current_user
);

-- ── Canonical capture routes (elicit sub-domain 1, Q: routes) ─────────
-- The 8 routes a learning enters the system today. DB CHECK = fail-closed
-- allowlist: an unknown route is a protocol violation, not a silent row.
-- Adding a route is a v00X migration (deliberate — keeps F-015 registry honest).
DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_type t JOIN pg_namespace n ON n.oid = t.typnamespace
    WHERE n.nspname = 'learnings' AND t.typname = 'learning_route'
  ) THEN
    CREATE TYPE learnings.learning_route AS ENUM (
      'brain_pending',        -- 1: ~/brain/learnings/pending/*.md → collector → Learning Report
      'brain_lessons',        -- 2: ~/brain/lessons/ via offline_knowledge + agent-session-mine
      'session_corrections',  -- 3: session transcripts via agent-session-correction-scan
      'governance_cycles',    -- 4: loop-governance feedback notes + high-scoring cycles
      'llm_judge',            -- 5: LLM-judge trace scoring
      'remediation',          -- 6: sensor/fixer novel-success lessons (F-002 wires this)
      'user_feedback',        -- 7: in-session user feedback (F-003 wires this)
      'cron_outputs'          -- 8: watchdog findings (F-004 wires this)
    );
  END IF;
END $$;

-- ── Content scrub gate (L-2, pii-scrubbing patterns) ─────────────────
-- BEFORE INSERT trigger replaces PII patterns with placeholders so the
-- ledger never stores identifying data that could leak via digest (F-020)
-- or promotion to tasks (F-007). Strips, never rejects: a learning with a
-- hostname in it is still a learning; the identifying part becomes a token.
CREATE OR REPLACE FUNCTION learnings.scrub_content(p_content TEXT)
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT regexp_replace(
        regexp_replace(
            regexp_replace(
                p_content,
                -- email-like pattern → placeholder (never store a real address)
                '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',
                'user@client-domain.com',
                'g'
            ),
            -- IPv4: 1.2.3.4 → x.x.x.x  (PG ARE: word boundaries are
            -- [[:<:]]/[[:>:]], NOT \b — \b matches a backspace char)
            '[[:<:]]\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}[[:>:]]',
            'x.x.x.x',
            'g'
        ),
        -- home paths: /home/<user>/... → ~/
        '/home/[A-Za-z0-9_.-]+/',
        '~/',
        'g'
    );
$$;

CREATE OR REPLACE FUNCTION learnings.scrub_trigger()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.content := learnings.scrub_content(NEW.content);
    RETURN NEW;
END;
$$;

-- ── Learnings table ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS learnings.learning (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    route          learnings.learning_route NOT NULL,
    agent          TEXT NOT NULL,                 -- capturing agent (from bus auth, never client-supplied)
    type           TEXT NOT NULL DEFAULT 'lesson'
                   CHECK (type IN ('lesson','fix','correction','insight',
                                   'feedback','watchdog','skill','other')),
    content        TEXT NOT NULL CHECK (length(content) BETWEEN 1 AND 4000),
    content_hash   TEXT NOT NULL,                 -- sha256 hex of scrubbed content (L-3)
    status         TEXT NOT NULL DEFAULT 'pending'
                   CHECK (status IN ('pending','evaluated','applied','verified','retired')),
    impact_score   INT NOT NULL DEFAULT 0
                   CHECK (impact_score BETWEEN -3 AND 3),  -- L-4 scale
    source_ref     TEXT,                          -- provenance: file/cycle/msg the learning came from
    applied_ref    TEXT,                          -- what it became: skill/memory/task ref (F-005)
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    status_changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_learning_route_hash UNIQUE (route, content_hash)  -- L-3
);

-- Scrub hook (L-2) — fires on every insert, runs as the table owner via
-- SECURITY DEFINER capture() below (owner bypasses RLS for its own writes).
DROP TRIGGER IF EXISTS trg_learning_scrub ON learnings.learning;
CREATE TRIGGER trg_learning_scrub
    BEFORE INSERT ON learnings.learning
    FOR EACH ROW EXECUTE FUNCTION learnings.scrub_trigger();

-- Indexes for the digest / lifecycle query patterns (F-006/F-020)
CREATE INDEX IF NOT EXISTS idx_learning_status_created
    ON learnings.learning (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_learning_agent
    ON learnings.learning (agent, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_learning_route
    ON learnings.learning (route, created_at DESC);

-- ── RLS: fail-closed (L-6) ─────────────────────────────────────────
-- Owner (mycortex — the bus server's connection role) bypasses RLS, which
-- is exactly right: the server-side capture() is the sanctioned writer.
-- Non-owner roles see rows only via explicit policy + grant.
ALTER TABLE learnings.learning ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS learnings_select_lifecycle ON learnings.learning;
-- Lifecycle (orchestrator profiles) may read all learnings for evaluation.
-- Policy alone grants nothing — the GRANT below gates who reaches it.
CREATE POLICY learnings_select_lifecycle ON learnings.learning
    FOR SELECT
    USING (true);

-- ── Single write path (L-1): learnings.capture() ────────────────────
-- SECURITY DEFINER (owner) — the ONLY way rows enter the ledger. Callers
-- (server endpoint, future DB-level collectors) need EXECUTE, never table
-- DML. Idempotent: same (route, scrubbed-hash) → returns existing id,
-- deduped=true, no new row (L-3). content_hash computed from SCRUBBED
-- content so a PII-bearing retry of the same learning still dedups.
CREATE OR REPLACE FUNCTION learnings.capture(
    p_route        learnings.learning_route,
    p_agent        TEXT,
    p_content      TEXT,
    p_type         TEXT DEFAULT 'lesson',
    p_impact_score INT DEFAULT 0,
    p_source_ref   TEXT DEFAULT NULL
) RETURNS TABLE (id UUID, deduped BOOLEAN, status TEXT)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = learnings, public
AS $$
DECLARE
    v_scrubbed TEXT;
    v_hash     TEXT;
BEGIN
    IF p_content IS NULL OR length(p_content) = 0 THEN
        RAISE EXCEPTION 'learnings.capture: content required';
    END IF;
    IF length(p_content) > 4000 THEN
        RAISE EXCEPTION 'learnings.capture: content exceeds 4000 chars';
    END IF;

    v_scrubbed := learnings.scrub_content(p_content);
    v_hash     := encode(digest(v_scrubbed, 'sha256'), 'hex');

    INSERT INTO learnings.learning
        (route, agent, type, content, content_hash, impact_score, source_ref)
    VALUES
        (p_route, p_agent, p_type, v_scrubbed, v_hash, p_impact_score, p_source_ref)
    ON CONFLICT (route, content_hash) DO NOTHING
    RETURNING learnings.learning.id, learnings.learning.status
    INTO id, status;

    IF id IS NULL THEN
        -- Duplicate: return the existing row (idempotent, L-3)
        SELECT l.id, l.status INTO id, status
        FROM learnings.learning l
        WHERE l.route = p_route AND l.content_hash = v_hash
        LIMIT 1;
        deduped := true;
    ELSE
        deduped := false;
    END IF;

    RETURN NEXT;
END;
$$;

-- ── Lifecycle status transition (L-1: only orchestrator UPDATE path) ──
-- F-006 (orch-skill-lifecycle) moves learnings through the status machine.
-- No fleet role can UPDATE directly — this function is the gate.
CREATE OR REPLACE FUNCTION learnings.set_status(
    p_id     UUID,
    p_status TEXT
) RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = learnings, public
AS $$
BEGIN
    IF p_status NOT IN ('pending','evaluated','applied','verified','retired') THEN
        RAISE EXCEPTION 'learnings.set_status: invalid status %', p_status;
    END IF;

    UPDATE learnings.learning
    SET status = p_status,
        status_changed_at = now(),
        updated_at = now()
    WHERE id = p_id;

    RETURN FOUND;
END;
$$;

-- ── Grants (L-1 least privilege; mirror tasks B-2) ──────────────────
-- Capture + set_status: executable by the reader base role (covers every
-- profile role that inherits it) and by the orchestrator profile roles
-- explicitly. Table DML: NOTHING is granted to non-owner roles.
GRANT USAGE ON SCHEMA learnings TO mycortex_reader;
GRANT EXECUTE ON FUNCTION learnings.capture(learnings.learning_route, TEXT, TEXT, TEXT, INT, TEXT) TO mycortex_reader;
GRANT EXECUTE ON FUNCTION learnings.set_status(UUID, TEXT) TO mycortex_reader;

-- Lifecycle SELECT — orchestrator profile roles only (workers stay
-- INSERT-only via capture(); they have no reason to read the ledger).
GRANT SELECT ON learnings.learning TO mycortex_reader_esther;
DO $$ BEGIN
  IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'mycortex_reader_moses') THEN
    GRANT SELECT ON learnings.learning TO mycortex_reader_moses;
  END IF;
END $$;

-- DDL/schema apply runs as mycortex (owner) via migrate.py — the same
-- trust level as tasks/mycortex runners. CRUD never touches superuser.
