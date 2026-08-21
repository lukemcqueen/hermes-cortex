-- v003: mycortex_admin SELECT on schema_version (2026-08-02)
--
-- Background: `mycortex doctor` reads mycortex.schema_version to report the
-- applied schema version. The v001 grants give schema_version only to the
-- `mycortex` superuser; mycortex_admin (the role doctor now runs as) had no
-- grant → `permission denied for table schema_version`.
-- Fix: grant SELECT on schema_version to mycortex_admin (idempotent).
-- Also hardens v001 for fresh installs (v001 grants section updated too).

GRANT SELECT ON mycortex.schema_version TO mycortex_admin;

-- Version bump (migrate.py runs this file only when version < 3)
INSERT INTO mycortex.schema_version (version) VALUES (3)
ON CONFLICT (version) DO NOTHING;
