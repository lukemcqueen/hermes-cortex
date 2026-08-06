-- ============================================================================
-- mycortex schema v004 — v1.1 semantic slice (S-014): pgvector embeddings
-- Source: docs/design/mycortex-DESIGN.md §1.2 "Embedding metadata (v1.1)"
--         docs/elicit/2026-08-01_mycortex-stories.md S-014
-- Applied by: ops/services/mycortex/migrate.py (NOT by cortex-update.sh directly)
-- Target: mycortex-postgres, database `mycortex`, schema `mycortex`
--
-- Adds three columns to content_chunks:
--   embedding        vector(768)   — nomic-embed-text:v1.5 (768-dim, float4)
--   embedding_model  TEXT          — model tag that produced the embedding
--   embedding_dim    INT           — model dim (sanity + future model switch)
--
-- The UNIQUE partial index on (id, embedding_model, embedding_dim) allows a
-- chunk to hold embeddings from MULTIPLE models side by side (non-destructive
-- model change): re-embedding with a new model inserts a new row key instead
-- of clobbering the old one; queries filter by embedding_model.
--
-- RLS note: content_chunks RLS/FORCE already exists from v001; the new
-- columns inherit the table's grants (mycortex_reader SELECT is table-wide),
-- so reader visibility of embeddings is enforced by the SAME policy.
-- ============================================================================

-- pgvector extension (cluster-level; idempotent). migrate.py runs as the
-- `mycortex` superuser role in-container, so CREATE EXTENSION is permitted.
-- ⚠️ SCHEMA IS MANDATORY: the superuser's search_path is "$user", public and
-- "$user" resolves to the EXISTING mycortex schema — a bare CREATE EXTENSION
-- installs the type into mycortex, invisible to roles whose default
-- search_path is "$user", public (observed 2026-08-06: ingest UPDATE failed
-- `type "vector" does not exist`). CREATE in public + relocate any prior
-- install → deterministic placement for every host.
CREATE EXTENSION IF NOT EXISTS vector SCHEMA public;
ALTER EXTENSION vector SET SCHEMA public;

ALTER TABLE mycortex.content_chunks
    ADD COLUMN IF NOT EXISTS embedding       vector(768),
    ADD COLUMN IF NOT EXISTS embedding_model TEXT,
    ADD COLUMN IF NOT EXISTS embedding_dim   INT;

-- one embedding per (chunk, model, dim); partial so NULLs (un-embedded) never collide
CREATE UNIQUE INDEX IF NOT EXISTS uq_chunk_embedding
    ON mycortex.content_chunks (id, embedding_model, embedding_dim)
    WHERE embedding IS NOT NULL;

-- HNSW index for fast approximate nearest-neighbor on the LIVE model only
-- (partial on the default model keeps the index focused; other models stay
-- queryable via exact scan). vector_cosine_ops = cosine distance (<=>).
CREATE INDEX IF NOT EXISTS idx_chunk_embedding_hnsw
    ON mycortex.content_chunks
    USING hnsw (embedding vector_cosine_ops)
    WHERE embedding IS NOT NULL AND embedding_model = 'nomic-embed-text:v1.5';
