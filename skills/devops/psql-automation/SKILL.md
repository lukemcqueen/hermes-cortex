---
name: psql-automation
version: 1.0.0
category: devops
description: "psql from scripts — error propagation, docker wrappers."
author: Hermes Cortex (curator)
license: MIT
platforms: [linux, macos]
---

# psql Automation — Error Propagation & Verification

## Trigger

Use when:
- Writing a script (Python/shell) that calls `psql` against a dockerized Postgres
- A script prints "✅ success" but the DB row never appears — silent write failure
- Debugging why `todo-db.py`-style CLIs report success for queries that error
- A design doc or peer agent claims "schema verified — table exists" and you're about to build on it
- You need to inspect data inside a STOPPED postgres container's volume
- **Security-reviewing a psql call path** (injection, shell embedding, RLS/authz)

## Core pitfall: stdin-mode psql swallows SQL errors (rc=0)

`psql -t -A <<< "SELECT ..."` or `subprocess.run(..., input=query)` (stdin mode)
returns **exit code 0 even when the query fails** — relation not found, function
missing, syntax error, all of them. A script that checks `returncode != 0` then
prints "✅ Todo added" is silently lying: the row never landed.

**Verified 2026-08-06:** `todo-db.py` printed "✅ Todo added" for months while
`bus.todos` never existed on the migrated DB. Every write was a silent no-op.

### The fix: use `-c` mode

```python
# BROKEN — stdin mode, errors swallowed (rc always 0 on SQL failure)
result = subprocess.run(["psql", "-t", "-A", "-F", "||"], input=query, ...)

# FIXED — -c mode propagates the real psql exit code
result = subprocess.run(["psql", "-t", "-A", "-F", "||", "-c", query], ...)
if result.returncode != 0:
    print(result.stderr, file=sys.stderr); sys.exit(1)
```

`-c` mode exits non-zero on query error → the script's `returncode` check
actually fires. Belt-and-suspenders: also scan `stderr` for `ERROR:`.

## Wrapper note: `sg docker -c` is NOT the problem — stdin mode is

Early diagnosis blamed `sg docker -c` for masking the inner rc. Clean
no-pipe tests (2026-08-06) proved otherwise — sg propagates rc correctly
when the query is embedded via `-c`:

| Invocation | rc on SQL error |
|---|---|
| `docker exec ... psql ... -c "<query>"` (direct) | **1** ✓ |
| `sg docker -c "docker exec ... psql ... -c '<query>'"` | **1** ✓ (propagates) |
| `echo "<query>" \| docker exec ... psql` (stdin) | **0** ✗ |
| `echo "<query>" \| sg docker -c "docker exec ... psql"` (stdin) | **0** ✗ |

The single root cause is **stdin-mode psql returning rc=0 on SQL failure**;
the wrapper is irrelevant. The earlier "sg masks rc" observation was a
measurement artifact — the command was piped through `head`, so `$?` was
head's exit code, not sg's/psql's. Always check rc WITHOUT a pipe.

Two safe patterns:

1. **Direct docker exec when the user is in the docker group** (check with
   `docker exec <container> true`; group membership via `id -nG | grep docker`):
   ```python
   ["docker", "exec", "-i", "mycortex-postgres", "psql", "-U", "mycortex", "-d", "mycortex", "-t", "-A", "-F", "||", "-c", query]
   ```
   rc propagates correctly. `-c` is fine HERE because the query is an argv
   element — no shell interprets it.

2. **Universal safe pattern — SQL via STDIN + `-v ON_ERROR_STOP=1` (works on
   BOTH paths, kills the rc=0 lie AND the shell-embedding risk):**
   ```python
   # Query flows through stdin — the command string contains ONLY fixed
   # names/flags, never user data → not shell-injectable.
   cmd = ["sg", "docker", "-c",
          "docker exec -i mycortex-postgres psql -U mycortex -d mycortex "
          "-v ON_ERROR_STOP=1 -t -A -F '||'"]
   proc = subprocess.run(cmd, input=sql, capture_output=True, text=True, timeout=30)
   if proc.returncode != 0 or "ERROR:" in proc.stderr:
       sys.exit(1)
   ```
   With `ON_ERROR_STOP=1`, psql exits **rc=3 on SQL error even in stdin mode**
   — the rc=0-swallows-errors failure is structurally impossible, and no user
   input ever reaches a shell. This is the pattern used by
   `ops/services/tasks/migrate.py` and the rewritten `task-db.py` (2026-08-06).

   ⚠️ Shell-quote the `-F` separator inside an sg string: `-F '||'` (unquoted
   `-F ||` becomes shell OR → "Syntax error: end of file unexpected").

   ❌ **NEVER** embed `-c {query!r}` into an sg/shell command string. Python's
   `repr()` quoting is NOT POSIX shell quoting: a `'` inside the value closes
   the shell string and appends arbitrary commands. SQL injection escalates to
   **arbitrary shell command execution as the agent user** on any host where
   the script falls back to the sg path. Verified exploitable in todo-db.py
   (2026-08-06 party, Security role, finding B-1).

## Verify "verified" schema claims before building on them

A design doc or peer's "Existing plumbing (verified YYYY-MM-DD)" is a claim,
not proof. Five-minute check:

```bash
# current DB
docker exec -i mycortex-postgres psql -U mycortex -d mycortex -t -A \
  -c "SELECT schemaname||'.'||tablename FROM pg_tables WHERE tablename LIKE '%todo%';"
# functions too
docker exec -i mycortex-postgres psql -U mycortex -d mycortex -t -A \
  -c "SELECT proname FROM pg_proc WHERE proname LIKE '%todo%';"
# migration dump (if one exists) — pg_restore -l lists objects; grep for the table
pg_restore -l ~/.hermes-cortex/backups/*.dump | grep -i todo
```

If the table/function is missing from BOTH the current DB and the migration
dump, it never existed — the CLI's "✅" was the rc=0 lie. Fix the schema
(idempotent `CREATE TABLE IF NOT EXISTS` + `CREATE OR REPLACE FUNCTION`), then
fix the CLI's psql invocation, then re-test with a real add/list.

### ⚠️ Verify against EVERY agent type, not just your host (2026-08-06)

A schema that exists on the ORCHESTRATOR host may not exist on WORKERS. The
`bus` schema is created by `setup-cortex-bus.sh` — a `register_orch`
(orchestrator-only) script. Workers (Gisu, Joseph, Kustos, Titus) run
`mycortex-postgres` (the doctor checks the container on every host) but
**never get the `bus` schema**. Building a "fleet-wide" feature on `bus.*`
silently locks out every worker — the 2026-08-06 todo-system flaw:
`bus.todos` never existed on workers, and even the orchestrator's CLI
printed ✅ while rows vanished.

**Check the role matrix, not just your DB:** `docs/bus-architecture.md`
lists what each agent type RUNS (workers: HTTP client only — never the bus
Postgres/schema). Before designing around a schema, verify it will exist on
the hosts that must use it.

**Rule (Luke directive 2026-08-06):** features ALL agents should have must
not depend on bus infrastructure or bus nomenclature. Give them a dedicated
schema (`todos.*`, not `bus.*`) applied on every host's mycortex-postgres
via cortex-update.sh, with a platform-aware apply path — docker exec on
Linux, direct psql via mycortex.conf/config.json on macOS.

## Inspect a stopped container's data volume

The old container is `Exited (0)` (not removed) — its volume is intact. Query
it WITHOUT port conflicts by running a temp container on the same volume:

```bash
docker run --rm -d --name inspect \
  -v <old-volume>:/var/lib/postgresql/data <same-image>   # no -p publish = no host port conflict
sleep 7   # wait for "database system is ready to accept connections" in docker logs
docker exec -i inspect psql -U <user> -d <db> -t -A -c "<query>"
docker rm -f inspect
```

Pitfalls: don't pass `-c port=NNNN` to postgres — that changes the listening
port while psql inside still tries the 5432 socket; and don't pipe the query
through `head` when checking rc (head's rc masks psql's).

## Pitfalls

- **Injection defense for psql-backed CLIs** (2026-08-06, task-db.py rewrite):
  - **Allowlist every identifier-ish value** (`agent`, `project`, `repo`,
    `target`, `assignee`, `scope`, `status`, `source`, `column`) against
    `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$` + enum allowlists (`personal|fleet`,
    `pending|in_progress|completed|cancelled`, …) BEFORE it touches SQL.
  - **Never string-build WHERE clauses.** Route all DML through a parameterized
    function (`tasks.task_upsert(...)`) with positional params.
  - Free text (content, tags) is quote-doubled (`'` → `''`) into string
    literals only — safe under `standard_conforming_strings=on` (PG default).
  - Extract `build_query(sql, params) -> sql` as a **pure function** — that's
    the unit-test seam for injection regressions (`--agent "x' OR 1=1--"` must
    return a validation error, not rows).
- **`column` and `position` are PostgreSQL RESERVED words** — must be quoted as
  `"column"`/`"position"` in EVERY query. Unquoted `column` fails with
  "syntax error at or near \"column\"". Cost two migration re-runs (2026-08-06).
- **`INSERT ... ON CONFLICT DO UPDATE` evaluates NOT NULL and RLS WITH CHECK on
  the PROPOSED insert row BEFORE conflict resolution** — a status-only update
  passing NULL content fails with "null value in column". Fix inside the upsert
  function: COALESCE defaults for non-nullable columns (`scope`/`status`/
  `project`/`source`) so partial updates propose a valid row, and
  `COALESCE(p_content, (SELECT content FROM t WHERE id = p_id))` to fetch the
  existing content. `ON CONFLICT DO UPDATE SET x = COALESCE(EXCLUDED.x, t.x)`
  so NULL params don't clobber existing values.
- **Role creation in migrations needs CREATEROLE** — only the DB owner has it.
  Run DDL as the owner (house precedent: mycortex migrate.py connects as
  `mycortex`), not a dedicated admin role, or the migration fails with
  "permission denied to create role". Granting CREATEROLE to a non-owner role
  is cluster-wide surface — prefer owner-run DDL.
- **`--source`-style filters never grant access** — RLS is the enforcement; a filter is just a filter.
- **Idempotent schema files are your friend** — `IF NOT EXISTS` + `CREATE OR REPLACE` means you can apply on every deploy/update; wire it into the update script so Linux (docker exec) and macOS (direct psql via config URL) both converge.
- **When a path-hardcoding bug is fixed in ONE of two sibling files, grep for the sibling.** 2026-08-06: `session_mine.py` was fixed to write `~/brain/lessons/`, but `lessons.py` (the module the index/search imports) still hardcoded `~/brain/kustos/lessons/` — offline search read a stale 241-file dir while 631 live lessons sat elsewhere. `git log -S '<bad-string>'` finds every file that ever contained it.
- **Check `psql` via the `-t -A` flags when parsing** — column headers break naive parsers on macOS without `-t -A`.

## References

- `references/todo-silent-failure-2026-08-06.md` — full session trace: the
  todo-db.py rc=0 bug, sg masking, old-container inspection, dream→todo bridge
  build, and the bus.todos-never-existed diagnosis.
- `references/psql-cli-security-hardening.md` — injection-proof psql CLI
  rewrite: allowlists, stdin+ON_ERROR_STOP pattern, profile-role CRUD + RLS
  WITH CHECK, guarded table-scoped migration, verification transcript
  (2026-08-06 task-db.py / tasks schema).
