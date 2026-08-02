-- v002: RLS admin-visibility + reader search_config grant (2026-08-02)
--
-- Background: hosts that applied v001 before 2026-08-02 are missing two fixes
-- that live only in the v001 file (schema_version=1 blocks re-apply):
--   1. FORCE RLS default-denies mycortex_admin — no admin policy means
--      stats/audit/sources-list queries silently return 0 rows.
--   2. mycortex_reader lacks the search_config column grant on sources —
--      the search query joins sources for per-source FTS config and fails
--      `permission denied for table sources`.
-- This migration brings existing hosts to parity with fresh v001 installs.
-- Idempotent: CREATE POLICY / GRANT are safe to re-run (policies are keyed
-- by name, grants are additive).

-- 1. Admin visibility policies (audit role must see everything)
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_policies
                 WHERE schemaname='mycortex' AND tablename='pages'
                   AND policyname='mycortex_pages_admin') THEN
    CREATE POLICY mycortex_pages_admin ON mycortex.pages
      FOR SELECT TO mycortex_admin USING (true);
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_policies
                 WHERE schemaname='mycortex' AND tablename='content_chunks'
                   AND policyname='mycortex_chunks_admin') THEN
    CREATE POLICY mycortex_chunks_admin ON mycortex.content_chunks
      FOR SELECT TO mycortex_admin USING (true);
  END IF;
END $$;

-- 2. Reader column grant (search_config used by search JOIN)
GRANT SELECT (id, name, is_federated, search_config) ON mycortex.sources TO mycortex_reader;

-- 3. Version bump (migrate.py runs this file only when version < 2)
INSERT INTO mycortex.schema_version (version) VALUES (2)
ON CONFLICT (version) DO NOTHING;
