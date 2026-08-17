---
name: postgres-schema-design
description: "Postgres schemas with RLS, roles, or migrations."
version: 1.0.0
author: Hermes Cortex
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [postgres, rls, schema, migration, roles, security, sql]
    related_skills: [postgres-docker, todo-persistence, shell-scripting, test-driven-development]
---

# Postgres Schema Design — Fail-Closed Multi-Role Schemas

## When to Use

- Creating a new schema with row-level security (RLS), roles, or a PII gate
- Adding tables to a shared fleet DB (e.g. `mycortex-postgres`) that other schemas (bus) must not be disturbed by
- Writing a schema-versioned migration runner or a psql-based test battery
- Any "can the reader role see only what it should?" isolation design

## Core Principles (non-negotiable)

1. **Fail-closed from day one** — RLS enabled + FORCE + policies in the SAME migration file. No "v001b after first ingest" fail-open window.
2. **Role split, not shared superuser** — separate `admin` / `ingest` / `reader` roles. Admin owns registration + grants; ingest does DML on content tables ONLY; reader gets SELECT filtered by RLS.
3. **PII gate as a DB CHECK constraint** — `CHECK (is_federated = FALSE OR pii_scan_at IS NOT NULL)`. Federation is impossible without a recorded scan, enforced at the DB, not by convention.
4. **Ownership by superuser** — tables owned by `postgres`/`gbrain` (superuser), never runtime roles. Runtime roles get GRANTs, not ownership.
5. **Migrate via a runner, never inline DDL in a deploy script** — `cortex-update.sh`-style file copiers have no DDL path. A `schema_version`-gated `migrate.py` invoked AFTER file sync is the DDL path.

## ⚠️ RLS Policy Evaluation Semantics (the #1 gotcha)

**Policy subqueries evaluate with the CALLER's privileges — NOT the table owner's.**

A `USING` expression like `EXISTS (SELECT 1 FROM source_grants g WHERE ...)` fails with
`ERROR: permission denied for table source_grants` when the querying role lacks
SELECT on `source_grants` — even though the policy was created by the superuser.

**Fix pattern — SECURITY DEFINER visibility helper:**

```sql
-- Runs as owner (superuser); caller never needs SELECT on sources/source_grants.
CREATE OR REPLACE FUNCTION mycortex.is_source_visible(p_source_id UUID, p_role TEXT)
RETURNS boolean LANGUAGE sql SECURITY DEFINER SET search_path = mycortex AS $$
    SELECT EXISTS (
        SELECT 1 FROM mycortex.sources s
        WHERE s.id = p_source_id
          AND (s.is_federated OR EXISTS (
                SELECT 1 FROM mycortex.source_grants g
                WHERE g.source_id = p_source_id AND g.role_name = p_role))
    );
$$;
REVOKE ALL ON FUNCTION mycortex.is_source_visible(UUID, TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION mycortex.is_source_visible(UUID, TEXT) TO mycortex_reader;

CREATE POLICY mycortex_pages_select ON mycortex.pages
    FOR SELECT TO mycortex_reader
    USING (mycortex.is_source_visible(pages.source_id, current_user));
```

Key detail: pass `current_user` as an **argument** (evaluated in the caller's context),
and compare against `g.role_name = p_role` inside the definer-owned function. Do NOT
read `current_user` inside the function body — SECURITY DEFINER runs as the owner, so
it would see the owner's name, not the caller's.

**FORCE RLS does NOT create cascades.** A chunks policy that only checks
`EXISTS (SELECT 1 FROM pages p WHERE p.id = chunk.page_id)` LEAKS isolated chunks:
the subquery evaluates with owner (superuser) privileges, which bypass RLS entirely.
Each dependent-table policy must apply the SAME predicate explicitly (join through
the parent to its source and call the visibility helper). Never rely on "page-level
RLS cascades".

## RLS + DML: writer roles need their own policies

`ENABLE ROW LEVEL SECURITY` **default-denies DML for non-owner roles**. A
reader-only SELECT policy is not enough for the ingest role — its INSERT/UPDATE/
DELETE/SELECT is blocked until it gets an explicit policy:

```sql
CREATE POLICY mycortex_pages_ingest ON mycortex.pages
    FOR ALL TO mycortex_ingest USING (true) WITH CHECK (true);
CREATE POLICY mycortex_chunks_ingest ON mycortex.content_chunks
    FOR ALL TO mycortex_ingest USING (true) WITH CHECK (true);
```

The role-split boundary lives in the GRANTs (REVOKE ALL on sources from ingest),
not in page-level RLS.

## NOT NULL DEFAULT gotcha

`DEFAULT current_setting('hostname', true)` returns **NULL** (no such GUC exists),
violating NOT NULL on INSERT. Use a literal default (`DEFAULT 'localhost'`) and have
the app pass the real value explicitly. Same trap applies to any
`current_setting('<nonexistent-guc>', true)`.

## Role-split grant matrix (tested pattern)

| Role | Grants | Denied |
|------|--------|--------|
| `*_admin` | ALL on sources + source_grants, CREATE on schema, SELECT on content tables | — (orchestrator-only) |
| `*_ingest` | SELECT/INSERT/UPDATE/DELETE on pages/content_chunks/ingest_log + sequence USAGE | sources, source_grants, query_log, schema_version (REVOKE ALL) |
| `*_reader` | SELECT on pages/content_chunks (RLS-filtered), SELECT (id,name,is_federated) on sources, EXECUTE on log function | query_log (REVOKE SELECT), local_path column |

Reader needs column-level `GRANT SELECT (id, name, is_federated)` on sources —
the CLI resolves `--source` filters by id, but `local_path` stays protected.

## Migration runner pattern

- `schema_version(version INT PK, applied_at)` table; runner reads `MAX(version)`, applies pending, records — re-run is a **no-op**.
- Role creation: `DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='x') THEN CREATE ROLE x LOGIN; END IF; END $$;` — PG has no `CREATE ROLE IF NOT EXISTS`. Roles are cluster-level; guard idempotently.
- `--db-name` override so tests target a scratch DB, never prod.
- Pinned `search_path`, `ON_ERROR_STOP=1`, explicit target DB.
- Append-only audit: SECURITY DEFINER `log_query()` that reads `application_name` from `pg_stat_activity` (not self-reported) + `REVOKE SELECT` from readers.

## psql test battery pattern (AC verification)

Mirror `tests/test-bus-schema.sh` style:
- **Hermeticity guard:** refuse to run against the prod DB name (fail fast: `if [[ "$TEST_DB" == "gbrain" ]]; then exit 1; fi`).
- **Scratch DB lifecycle:** `DROP DATABASE IF EXISTS <test>` + `CREATE DATABASE <test>` + `trap cleanup EXIT`.
- **Test as the actual role:** `docker exec mycortex-postgres psql -U mycortex_reader -d <test>` — the isolation-leak test MUST run as the reader, never superuser.
- ⚠️ **psql `-t -A` prints command tags:** `$ID=$(psql ... -c "INSERT ... RETURNING id")` captures BOTH the id AND the `INSERT 0 1` tag (two lines). Pipe through `head -1` or the multi-line value breaks the next query.
- Idempotency check: run migrate.py twice, assert second run reports no-op.
- Bus-untouched: assert `bus` schema table count unchanged after schema apply.

## Verification checklist

- [ ] Isolation-leak test runs AS the reader role and returns zero rows for isolated sources
- [ ] Chunks policy applies the same predicate explicitly (no cascade reliance)
- [ ] Ingest role's DML works (has its own ALL policies)
- [ ] PII CHECK rejects federated-without-scan
- [ ] Migrate re-run is a no-op
- [ ] query_log: reader can EXECUTE the log function but not SELECT/INSERT the table
- [ ] Bus schema untouched after apply

## Related

- `references/mycortex-v001-case.md` — concrete failure transcripts + fixes from the first fail-closed schema (mycortex v001)
- `postgres-docker` — tuning/config the shared container
- `todo-persistence` — the `sg docker` psql wrapper pattern (reuse it)
