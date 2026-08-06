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

## Wrapper pitfall: `sg docker -c` masks the inner rc

`sg docker -c "docker exec -i <container> psql ..."` returns sg's own rc (0)
even when the inner docker/psql failed. Verified: `sg ... -c 'SELECT * FROM
bus.nonexistent;'` → psql errors on stderr, sg returns **rc=0**.

Two safe patterns:

1. **Direct docker exec when the user is in the docker group** (check with
   `docker exec <container> true`; group membership via `id -nG | grep docker`):
   ```python
   ["docker", "exec", "-i", "mycortex-postgres", "psql", "-U", "mycortex", "-d", "mycortex", "-t", "-A", "-F", "||", "-c", query]
   ```
   rc propagates correctly.

2. **sg fallback (no docker group):** embed the `-c query` INSIDE the sg
   command string — sg's `-c` flag takes one string:
   ```python
   ["sg", "docker", "-c", f"docker exec -i {c} psql ... -c {query!r}"]
   ```
   Appending `-c query` as separate argv elements passes it to sg itself, not
   to psql.

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

- **`--source`-style filters never grant access** — RLS is the enforcement; a filter is just a filter.
- **Idempotent schema files are your friend** — `IF NOT EXISTS` + `CREATE OR REPLACE` means you can apply on every deploy/update; wire it into the update script so Linux (docker exec) and macOS (direct psql via config URL) both converge.
- **When a path-hardcoding bug is fixed in ONE of two sibling files, grep for the sibling.** 2026-08-06: `session_mine.py` was fixed to write `~/brain/lessons/`, but `lessons.py` (the module the index/search imports) still hardcoded `~/brain/kustos/lessons/` — offline search read a stale 241-file dir while 631 live lessons sat elsewhere. `git log -S '<bad-string>'` finds every file that ever contained it.
- **Check `psql` via the `-t -A` flags when parsing** — column headers break naive parsers on macOS without `-t -A`.

## References

- `references/todo-silent-failure-2026-08-06.md` — full session trace: the
  todo-db.py rc=0 bug, sg masking, old-container inspection, dream→todo bridge
  build, and the bus.todos-never-existed diagnosis.
