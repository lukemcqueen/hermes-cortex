-- ============================================================================
-- mycortex schema v001 — knowledge index for the fleet (gbrain replacement)
-- Source: docs/design/mycortex-DESIGN.md §2 (v2)
-- Applied by: ops/services/mycortex/migrate.py (NOT by cortex-update.sh directly)
-- Target: shared gbrain-postgres, database `gbrain`, schema `mycortex`
--
-- v001 ships FAIL-CLOSED: RLS enabled + FORCE on pages/content_chunks, policies
-- created in this same file (no fail-open window), PII gate as a CHECK constraint,
-- and a strict role split (admin / ingest / reader).
--
-- DEVIATIONS FROM DESIGN DOC §2 (deliberate, tested):
--   1. `sources.host` DEFAULT 'localhost' — the design's
--      `current_setting('hostname', true)` returns NULL (no such GUC), violating
--      NOT NULL. The sync CLI always passes the real host explicitly.
--   2. chunks RLS policy does NOT rely on "page-level RLS cascades" — policy
--      expressions evaluate as the table owner (gbrain, a superuser), which
--      BYPASSES RLS, so a cascade check would leak chunks of isolated pages.
--      The chunks policy independently applies the same federated/grant
--      predicate via a join to pages+sources. (Isolation-leak test covers this.)
--   3. mycortex_reader gets SELECT (id, name, is_federated) on sources — the
--      CLI needs id to resolve --source filters. local_path + query_log stay
--      protected.
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS pg_texample;

CREATE SCHEMA IF NOT EXISTS mycortex;

-- ── Roles (cluster-level; idempotent guards — PG has no CREATE ROLE IF NOT EXISTS) ──
-- mycortex_admin   — orchestrators: source registration, PII gate, grants
-- mycortex_ingest  — sync cron: DML on pages/content_chunks/ingest_log ONLY
-- mycortex_reader  — fleet agents: SELECT (RLS-filtered), no query_log
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mycortex_admin') THEN
    CREATE ROLE mycortex_admin LOGIN;
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mycortex_ingest') THEN
    CREATE ROLE mycortex_ingest LOGIN;
  END IF;
END $$;
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'mycortex_reader') THEN
    CREATE ROLE mycortex_reader LOGIN;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS mycortex.sources (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT NOT NULL UNIQUE,          -- 'hermes-cortex', 'moses', 'shared', 'lessons'
    local_path    TEXT,                           -- absolute path (scrubbed from logs)
    host          TEXT NOT NULL DEFAULT 'localhost', -- owning host; sync/CLI always sets it
    sync_mode     TEXT NOT NULL DEFAULT 'git',    -- 'git' | 'local'
    is_federated  BOOLEAN NOT NULL DEFAULT FALSE, -- FALSE = isolated (RLS: reader needs source grant)
    pii_scan_at   TIMESTAMPTZ,                    -- PII scan gate: federation requires a recorded scan
    search_config TEXT NOT NULL DEFAULT 'simple', -- per-source FTS config. Language-agnostic: the DB stores mixed-language content (English is the DEFAULT language for sessions/agent communication, not a storage constraint). 'simple' (no stemming, no stop-words) keeps all languages findable.
    builtin       BOOLEAN NOT NULL DEFAULT FALSE, -- 'default' source is unremovable
    last_sync_at  TIMESTAMPTZ,
    last_commit   TEXT,                           -- git HEAD at last sync (git sources)
    archived      BOOLEAN NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (is_federated = FALSE OR pii_scan_at IS NOT NULL)  -- no federation without PII scan
);

CREATE TABLE IF NOT EXISTS mycortex.pages (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id     UUID NOT NULL REFERENCES mycortex.sources(id) ON DELETE CASCADE,
    relpath       TEXT NOT NULL,                  -- NFC-normalized, case-insensitive-unique per source
    title         TEXT,
    author        TEXT,                           -- owning agent (frontmatter, else source-level default)
    content_hash  TEXT NOT NULL,                  -- sha256 of file content (change detector)
    fts           TSVECTOR,                       -- MAINTAINED BY INGEST (chunk upsert → page rebuild, same txn)
    archived      BOOLEAN NOT NULL DEFAULT FALSE, -- soft-delete; hard purge only on sources remove
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Partial unique index: soft-deleted rows don't block re-ingest within the 7-day window
CREATE UNIQUE INDEX IF NOT EXISTS uq_pages_active ON mycortex.pages (source_id, relpath) WHERE NOT archived;
CREATE INDEX IF NOT EXISTS idx_pages_source   ON mycortex.pages (source_id) WHERE NOT archived;
CREATE INDEX IF NOT EXISTS idx_pages_fts      ON mycortex.pages USING GIN (fts);
CREATE INDEX IF NOT EXISTS idx_pages_title_texample ON mycortex.pages USING GIN (title gin_texample_ops);
CREATE INDEX IF NOT EXISTS idx_pages_content_texample ON mycortex.pages USING GIN (relpath gin_texample_ops);

CREATE TABLE IF NOT EXISTS mycortex.content_chunks (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    page_id       UUID NOT NULL REFERENCES mycortex.pages(id) ON DELETE CASCADE,
    chunk_index   INT  NOT NULL,
    content       TEXT NOT NULL,
    chunk_size    INT,                            -- params recorded per chunk for re-embed
    overlap       INT,
    -- v1.1 semantic slice (added by migration v004 — NOT in v001):
    -- embedding    vector(768),
    -- embedding_model TEXT,
    -- embedding_dim  INT,
    UNIQUE (page_id, chunk_index)
);

-- v1.2: links deferred (no extractor in v1 — no entity-graph in v1, per anti-architecture)
-- CREATE TABLE mycortex.links (...);   -- created by migration v005

CREATE TABLE IF NOT EXISTS mycortex.source_grants (
    role_name     TEXT NOT NULL,
    source_id     UUID NOT NULL REFERENCES mycortex.sources(id) ON DELETE CASCADE,
    granted_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (role_name, source_id)
);

CREATE TABLE IF NOT EXISTS mycortex.ingest_log (
    id            BIGSERIAL PRIMARY KEY,
    source_id     UUID REFERENCES mycortex.sources(id) ON DELETE SET NULL,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ,
    pages_seen    INT,
    pages_upserted INT,
    pages_archived INT,
    pages_skipped  INT,                          -- binary/oversize/non-UTF8 (counted, not silent)
    status        TEXT NOT NULL DEFAULT 'running',   -- 'running' | 'ok' | 'error'
    error         TEXT
);

CREATE TABLE IF NOT EXISTS mycortex.query_log (
    id            BIGSERIAL PRIMARY KEY,
    application_name TEXT,                       -- from pg_stat_activity (not self-reported)
    source_filter TEXT,                          -- NULL = federated
    query         TEXT,
    result_relpaths TEXT[],                      -- top-K result relpaths (exfil detection)
    latency_ms    INT,
    at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- query_log is append-only via SECURITY DEFINER log_query(); REVOKE SELECT from readers
REVOKE SELECT ON mycortex.query_log FROM mycortex_reader;
REVOKE ALL ON mycortex.query_log FROM mycortex_ingest;

-- Append-only query logging: runs as owner (superuser) so callers never need
-- INSERT on query_log; application_name is read from pg_stat_activity, so the
-- agent can't self-report a fake identity.
CREATE OR REPLACE FUNCTION mycortex.log_query(
    p_source_filter TEXT,
    p_query TEXT,
    p_result_relpaths TEXT[],
    p_latency_ms INT
) RETURNS void
LANGUAGE sql
SECURITY DEFINER
SET search_path = mycortex
AS $$
  INSERT INTO mycortex.query_log (application_name, source_filter, query, result_relpaths, latency_ms)
  SELECT application_name, p_source_filter, p_query, p_result_relpaths, p_latency_ms
  FROM pg_stat_activity WHERE pid = pg_backend_pid();
$$;
REVOKE ALL ON FUNCTION mycortex.log_query(TEXT, TEXT, TEXT[], INT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mycortex.log_query(TEXT, TEXT, TEXT[], INT) TO mycortex_reader;

CREATE TABLE IF NOT EXISTS mycortex.schema_version (
    version       INT PRIMARY KEY,
    applied_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ── RLS (fail-closed from v001, same file) ──────────────────────────────
ALTER TABLE mycortex.pages ENABLE ROW LEVEL SECURITY;
ALTER TABLE mycortex.content_chunks ENABLE ROW LEVEL SECURITY;
ALTER TABLE mycortex.pages FORCE ROW LEVEL SECURITY;
ALTER TABLE mycortex.content_chunks FORCE ROW LEVEL SECURITY;

-- Visibility helper: is this source visible to the given role?
-- SECURITY DEFINER (runs as owner/superuser) so the reader role never needs
-- SELECT on sources/source_grants. Policy subqueries evaluate with the CALLER's
-- privileges (observed: "permission denied for table source_grants"), so the
-- grant check MUST live inside a definer-owned function. The role is passed as
-- an argument (current_user is evaluated in the caller's context), keeping the
-- check bound to the actual querying role.
CREATE OR REPLACE FUNCTION mycortex.is_source_visible(p_source_id UUID, p_role TEXT)
RETURNS boolean
LANGUAGE sql
SECURITY DEFINER
SET search_path = mycortex
AS $$
    SELECT EXISTS (
        SELECT 1 FROM mycortex.sources s
        WHERE s.id = p_source_id
          AND (s.is_federated OR EXISTS (
                SELECT 1 FROM mycortex.source_grants g
                WHERE g.source_id = p_source_id
                  AND g.role_name = p_role))
    );
$$;
REVOKE ALL ON FUNCTION mycortex.is_source_visible(UUID, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mycortex.is_source_visible(UUID, TEXT) TO mycortex_reader;

-- Default-deny: reader sees a page iff its source is visible to the reader
-- role (federated OR grant). Policy runs as owner; the helper does the check
-- with owner privileges but binds to the passed-in caller role.
CREATE POLICY mycortex_pages_select ON mycortex.pages
    FOR SELECT TO mycortex_reader
    USING (mycortex.is_source_visible(pages.source_id, current_user));

-- Chunks: SAME predicate applied directly (join through pages → sources).
-- Do NOT rely on "page RLS cascades" — policy expressions evaluate as the
-- caller, and FORCE RLS makes cascade behavior fragile. Explicit is safer.
CREATE POLICY mycortex_chunks_select ON mycortex.content_chunks
    FOR SELECT TO mycortex_reader
    USING (
        EXISTS (
            SELECT 1 FROM mycortex.pages p
            WHERE p.id = content_chunks.page_id
              AND mycortex.is_source_visible(p.source_id, current_user)
        )
    );

-- Ingest DML policies: the sync engine writes/reads pages and chunks it owns.
-- RLS applies to non-owner roles even without FORCE, so mycortex_ingest needs
-- explicit ALL policies — otherwise its INSERT/UPDATE/SELECT is default-deny.
-- The role split boundary is that ingest CANNOT touch sources/source_grants/
-- query_log (REVOKEd below); page-level access is unrestricted by design.
CREATE POLICY mycortex_pages_ingest ON mycortex.pages
    FOR ALL TO mycortex_ingest
    USING (true) WITH CHECK (true);
CREATE POLICY mycortex_chunks_ingest ON mycortex.content_chunks
    FOR ALL TO mycortex_ingest
    USING (true) WITH CHECK (true);

-- Admin = audit role: orchestrators must see ALL pages/chunks (incl. isolated)
-- to manage PII gates, grants, and query audit. FORCE RLS otherwise default-denies
-- admin (no policy applies) — the GRANT SELECT in the grants section would be useless.
CREATE POLICY mycortex_pages_admin ON mycortex.pages
    FOR SELECT TO mycortex_admin
    USING (true);
CREATE POLICY mycortex_chunks_admin ON mycortex.content_chunks
    FOR SELECT TO mycortex_admin
    USING (true);

-- ── Grants (role split) ────────────────────────────────────────────────
GRANT USAGE ON SCHEMA mycortex TO mycortex_admin, mycortex_ingest, mycortex_reader;

-- mycortex_admin — orchestrator-only: source registration, PII gate, grants, DDL
GRANT CREATE ON SCHEMA mycortex TO mycortex_admin;
GRANT ALL ON mycortex.sources, mycortex.source_grants TO mycortex_admin;
GRANT SELECT ON mycortex.pages, mycortex.content_chunks, mycortex.ingest_log, mycortex.schema_version TO mycortex_admin;

-- mycortex_ingest — DML on pages/content_chunks/ingest_log ONLY; NO sources access
GRANT SELECT, INSERT, UPDATE, DELETE ON mycortex.pages, mycortex.content_chunks, mycortex.ingest_log TO mycortex_ingest;
GRANT USAGE ON SEQUENCE mycortex.ingest_log_id_seq TO mycortex_ingest;
REVOKE ALL ON mycortex.sources, mycortex.source_grants, mycortex.query_log, mycortex.schema_version FROM mycortex_ingest;

-- mycortex_reader — SELECT on pages/chunks (RLS-filtered), sources (id,name,is_federated,search_config only)
GRANT SELECT ON mycortex.pages, mycortex.content_chunks TO mycortex_reader;
GRANT SELECT (id, name, is_federated, search_config) ON mycortex.sources TO mycortex_reader;
