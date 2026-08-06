# mycortex v001 Case — First Fail-Closed Schema (2026-08-01)

Concrete failure transcripts + fixes from building the mycortex knowledge-brain
schema on the shared gbrain-postgres (PG 17.6, `docker exec` trust auth). These
are the exact bugs the SKILL.md patterns prevent.

## Failure 1: "permission denied for table source_grants"

**Design intent:** reader sees a page iff its source is federated OR the reader
holds a grant in `source_grants`. The design doc wrote the policy inline:

```sql
CREATE POLICY mycortex_pages_select ON mycortex.pages
    FOR SELECT TO mycortex_reader
    USING (EXISTS (SELECT 1 FROM mycortex.sources s
            WHERE s.id = pages.source_id
              AND (s.is_federated OR EXISTS (
                    SELECT 1 FROM mycortex.source_grants g
                    WHERE g.source_id = pages.source_id
                      AND g.role_name = current_user))));
```

**Symptom (ran as reader, not superuser):**
```
ERROR:  permission denied for table source_grants
```

**Root cause:** policy subqueries evaluate with the CALLER's privileges, not the
table owner's. `mycortex_reader` had no SELECT on `source_grants` (by design!),
so the policy's own subquery blew up.

**Fix:** SECURITY DEFINER helper `mycortex.is_source_visible(p_source_id, p_role)`
(see SKILL.md) — reader only needs EXECUTE on the function. The isolation-leak
test that caught this runs AS `mycortex_reader` via `docker exec
gbrain-postgres psql -U mycortex_reader -d <test>`.

## Failure 2: FORCE RLS "cascade" leaks isolated chunks

**Design intent:** chunks policy only checks page existence, assuming page-level
RLS cascades to chunks:
```sql
CREATE POLICY mycortex_chunks_select ON mycortex.content_chunks
    FOR SELECT TO mycortex_reader
    USING (EXISTS (SELECT 1 FROM mycortex.pages p WHERE p.id = content_chunks.page_id));
```

**Why it's wrong:** policy expressions evaluate as the table owner (gbrain, a
SUPERUSER), and superusers bypass RLS entirely. The subquery sees ALL pages, so
chunks of isolated pages become visible whenever a reader can reference the
page_id. Never rely on cascade — apply the SAME predicate explicitly:
```sql
USING (EXISTS (SELECT 1 FROM mycortex.pages p
        WHERE p.id = content_chunks.page_id
          AND mycortex.is_source_visible(p.source_id, current_user)));
```

## Failure 3: ingest role's DML blocked by RLS

**Symptom:**
```
ERROR:  new row violates row-level security policy for table "pages"
```
**Root cause:** ENABLE RLS default-denies DML for non-owner roles. The ingest
role had GRANTs but no policy. Reader-only SELECT policies don't cover DML.
**Fix:** explicit `FOR ALL TO mycortex_ingest USING (true) WITH CHECK (true)`
policies on pages + content_chunks.

## Failure 4: `sources.host` NOT NULL violated

Design default was `current_setting('hostname', true)` — there is no `hostname`
GUC, so missing_ok returns NULL → NOT NULL violation on INSERT. Fixed with
`DEFAULT 'localhost'`; the CLI passes the real host explicitly.

## Failure 5: psql `-t -A` command-tag pollution

```bash
FED_ID=$($PSQL -c "INSERT INTO mycortex.sources (...) RETURNING id;")
```
With `-t -A`, psql prints BOTH the returned UUID **and** the `INSERT 0 1`
command tag on a second line. `$FED_ID` becomes two lines; the next INSERT
using it fails with a syntax error under `set -e` (silent in the trace).
**Fix:** pipe through `head -1`.

## Test battery shape that caught all of these

`tests/test-mycortex-schema.sh` — 15 checks:
1. Fresh DB → migrate.py applies v001; re-run reports no-op (schema_version gate)
2. RLS FORCE present on pages + content_chunks; policies exist
3. **Reader sees exactly the federated page (count=1), isolated page invisible**
4. **Isolated chunks invisible** (the cascade leak test)
5. Grant row in source_grants → reader now sees isolated source
6. PII gate CHECK rejects `is_federated=true` without `pii_scan_at`
7. ingest UPDATE on sources → permission denied (role split)
8. ingest CAN insert pages (DML scope intact)
9. reader cannot SELECT query_log
10. `log_query()` SECURITY DEFINER: reader can call it (appends), but direct
    INSERT into query_log denied; `application_name` comes from pg_stat_activity

Hermeticity: refuses `TEST_DB == "gbrain"`, scratch DB created/dropped via
`docker exec`, `trap cleanup EXIT`.

## Deploy-path lesson

cortex-update.sh is a pure file-copier — it CANNOT run DDL. The migrate.py
runner is registered as a file AND invoked after file sync; a failure there
fails the whole update loudly (`error` + `exit 1`), because a missing schema
silently breaks every consumer. Deploying it was the first time the schema
reached the REAL gbrain DB: `mycortex schema at version 1 — done`, bus (13
tables) untouched.

## Hosting note (transient, 2026-08-01)

Postgres PANICKED once with `could not fdatasync file ... Input/output error`
during a `CREATE DATABASE` on the VM's overlay2 storage; WAL redo recovered it
cleanly and the bus was verified intact. Environment-specific — not a schema
design issue, but worth watching on the host.
