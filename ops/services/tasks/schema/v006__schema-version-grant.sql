-- ============================================================================
-- tasks schema v006 — reader SELECT on tasks.schema_version
--
-- TL-v2 S3/S7 dependency: task-db.py's schema probe (schema_version()) and the
-- doctor's `schema_version >= 5` check read tasks.schema_version AS
-- mycortex_reader_<profile>. v001 only granted DML on tasks.tasks /
-- task_archive — the version table was owner-only, so the probe returned
-- "permission denied" and every v2 feature (paused, switch, --parent/--kind,
-- --by-correlation) failed with "requires v5+ (found v0)" even on a healthy
-- v005 host.
--
-- GRANT is idempotent — safe to apply on already-migrated hosts via the
-- version-gated runner; fresh DBs get it in order after v001.
--
-- No security impact: schema_version is metadata (version/applied_at/by),
-- already readable by the fleet via the doctor's other checks; SELECT-only.
-- ============================================================================

BEGIN;

GRANT SELECT ON tasks.schema_version TO mycortex_reader;

COMMIT;
