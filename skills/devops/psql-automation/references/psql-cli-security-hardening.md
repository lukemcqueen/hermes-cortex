# psql-backed CLI Security Hardening — task-db.py rewrite (2026-08-06)

Full worked example of taking a psql-backed CLI from "silently no-op + injectable"
to "fail-loud + least-privilege + injection-proof". Source of truth for the
pitfalls summarized in SKILL.md. Design: `docs/design/task-workflow.md` (party B-1/B-2).

## The starting state (what the party found — all verified live)

The old `todo-db.py` (now `task-db.py`) had three distinct security flaws:

1. **Raw f-string SQL** in `cmd_list`/`cmd_pending`/`cmd_save_end`:
   ```python
   conditions.append(f"t.agent_name = '{agent}'")   # --agent "x' OR 1=1--" → reads ALL tenants
   ```
   `status` was NOT validated on the `list` path (only on `update`); `AGENT_NAME`
   is env/hostname-influenced. On a superuser connection this escalates to
   full-DB read/write.

2. **`sg docker -c` shell-embedding = RCE**: the fallback built
   `[sg, docker, -c, inner + " -c " + repr(full_query)]`. Python `repr()` quoting
   is NOT POSIX shell quoting: a value containing `'` yields `\'` inside the
   shell's single-quoted string, which does NOT escape in sh → the shell string
   closes and arbitrary commands execute as the agent user. This fired on any
   host where the agent lacks docker-group membership.

3. **Superuser connection**: `-U mycortex` (the compose `POSTGRES_USER` = PG
   superuser) bypasses RLS entirely. The multi-tenancy RLS policies cover
   `mycortex.*` only, not `bus.todos` — so tenant isolation was theater.

## The fixed architecture (what shipped)

```
Agent/cron → task-mcp.py (MCP) → task-db.py (CLI engine) → tasks.tasks
                                  (mycortex_reader_<profile>, NOT superuser)
DDL → ops/services/tasks/migrate.py (as DB owner mycortex, version-gated)
```

### Connection model (least privilege)
- CRUD connects as `mycortex_reader_<profile>` (resolution order:
  `HERMES_PROFILE` → `AGENT_NAME` → hostname — same as
  `install-profile-reader-role.sh`; NEVER scan `~/.hermes/profiles/*/`).
- DDL/schema apply runs as the DB owner (house precedent: mycortex
  migrate.py). A dedicated admin role does NOT work for role-creation
  migrations — only the owner has CREATEROLE (verified: `mycortex_admin`
  fails "permission denied to create role" until granted CREATEROLE, and
  granting that is cluster-wide surface, so owner-run DDL wins).
- Grants: base `mycortex_reader` gets `USAGE ON SCHEMA tasks` +
  `SELECT/INSERT/UPDATE/DELETE ON tasks.tasks` + DML on the archive table
  (the archive function INSERTs into it — forgetting this grant fails
  save-end with "permission denied for table task_archive").

### RLS WITH CHECK — the fleet-write gate
```sql
ALTER TABLE tasks.tasks ENABLE ROW LEVEL SECURITY;
CREATE POLICY tasks_personal ON tasks.tasks
    USING (scope = 'fleet' OR created_by = tasks.profile_of(current_user))
    WITH CHECK (
        (scope = 'personal' AND created_by = tasks.profile_of(current_user))
        OR (scope = 'fleet'
            AND tasks.is_fleet_writer(current_user)
            AND NOT (project LIKE 'client-%')           -- fleet × client banned
            AND tasks.content_ok_for_fleet(content))    -- no paths/user@host/IPs
    );
```
- `profile_of(current_user)` parses `mycortex_reader_<profile>` → `<profile>`.
- `is_fleet_writer` = membership in a `todos_fleet_writer` role granted ONLY
  to orchestrator profile roles (conditional DO-block grant — granting to a
  nonexistent role on worker hosts FAILS the migration).
- Verified behavior: worker profile inserting `scope=fleet` → "new row
  violates row-level security policy"; orchestrator CAN write fleet;
  cross-profile read of another's personal row → 0 rows.

### Verification transcript (what to re-run after any schema/CLI change)
```bash
# schema + idempotency
python3 ops/services/tasks/migrate.py --verbose   # apply
python3 ops/services/tasks/migrate.py             # "up to date (version 1) — no-op"
# RLS behavior as profile role
docker exec -i mycortex-postgres psql -U mycortex_reader_esther -d mycortex \
  -c "SELECT tasks.task_upsert(p_content := 't', p_created_by := 'esther', p_scope := 'fleet');"
# injection resistance (must be validation errors, not rows)
task-db.py list --agent "x' OR 1=1--"
task-db.py list --status "completed' OR '1'='1"
# shell injection via content (must store literal, NOT execute)
task-db.py add "test \$(whoami) ; touch /tmp/pwned"   # /tmp/pwned must NOT exist
```

## Guarded migration pattern (bus.todos → tasks.tasks)

The migration is the riskiest destructive op in the fleet — guardrails that
survived review (party B-5, SRE SS-2):

1. Pre-flight `pg_dump -t <table>` to a dated host-local file (the rollback).
2. Record parity: `COUNT(*)` + `md5(string_agg(t::text, '' ORDER BY t.id))`.
3. Copy in ONE transaction with an explicit column-mapping SELECT.
4. Verify count parity (hard gate) + checksum + spot-check rows.
5. **Table-scoped** drop: `DROP TABLE IF EXISTS bus.todos` + specific
   functions — NEVER `DROP SCHEMA bus CASCADE` (PGMQ `bus.messages`/DLQ live
   in the same schema on orchestrators).
6. Idempotency guard: no source table → no-op, exit 0.
7. Write a marker file the doctor checks, so verification outlives the run.
8. Scope honestly: only hosts that HAVE the table (workers never did — F-08),
   and document the cleanup for orchestrator hosts explicitly (Luke: "don't
   forget to document cleanup for orchestrators too!").
