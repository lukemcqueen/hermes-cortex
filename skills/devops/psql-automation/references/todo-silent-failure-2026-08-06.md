# Todo Silent-Failure — 2026-08-06 Session Trace

## What happened

`todo-db.py add` printed "✅ Todo added" for months while `bus.todos` never
existed on the migrated DB. Every write was a silent no-op. The dream→todo
bridge design doc (kustos) claimed "Existing plumbing (verified 2026-08-06)"
for this table — the verification was wrong because the CLI always reported
success.

## Root-cause chain (two compounding bugs)

1. **stdin-mode psql swallows errors.** `subprocess.run([...psql...], input=query)`
   feeds the query via stdin; psql in stdin mode returns rc=0 even when the
   query fails. The `if result.returncode != 0` guard never fired.

2. **`sg docker -c` masks the inner rc.** Even with the query reaching psql,
   `sg` wraps docker and returns its own rc (0) regardless of the inner
   failure. Verified with `sg docker -c "docker exec ... -c 'SELECT * FROM
   bus.nonexistent;'"` → psql ERROR on stderr, sg rc=0.

Both had to be fixed for errors to surface.

## Diagnosis evidence trail

- `pg_restore -l ~/.hermes-cortex/backups/mycortex-migration-20260805.dump | grep -i todo` → 0 hits (table never in old DB dump)
- Temp container on old volume (`langfuse_legacy Postgres-data`, image `pgvector/pgvector:0.8.0-pg17`): bus schema = archives, audit_log, messages, messages_archive, permissions, queues, tokens — **no todos, no functions**
- Current DB (`mycortex-postgres`): same — no todos, no `todo_upsert`
- Conclusion: `bus.todos` never existed anywhere; the whole todo system was a silent no-op since introduction

## The fix (committed + deployed)

1. Applied `core/cortex_bus/schema/todos.sql` (idempotent) → `bus.todos` +
   `bus.todo_archive` + `todo_upsert`/`todo_list`/`todo_archive_old`
2. `todo-db.py` psql(): switched to `-c` mode; `_get_db_query()` tries direct
   `docker exec` (rc propagates) with `sg` fallback that embeds the query in
   the command string (`_build_query_cmd`)
3. Added `todo-db.py --apply-schema` (platform-aware: Linux docker exec,
   macOS direct psql via mycortex.conf) wired into `cortex-update.sh` so all
   hosts converge on update
4. New `dream-todo-bridge.py` (registered in cortex-update.sh): enforces
   caps (4 gaps / 2 insights per run) + dedup + tenant-scoping in code, so
   the LLM only judges actionability
5. `install-dream-crons.sh`: all three dream prompts gained bridge steps
   (monthly: Option A gaps→learn todos + Option B; nightly/weekly: Option B)

## Verification after fix

- `todo-db.py add` → row visible in `list` + `pending` (real UUID)
- `todo-db.py update <id> --status completed` → status changes
- `todo-db.py save-end` → archived
- genuine SQL error → `ERROR: ...` + exit 1 (no more false ✅)
- bridge: add-gap lands, dedup SKIPs on repeat, tenant isolation holds
  (Joseph sees zero Esther todos)

## Related findings (same session)

- `ops/offline/lessons.py` still hardcoded `HOME/brain/kustos/lessons` —
  Moses fixed `session_mine.py` (9426e4c4) but missed the sibling module the
  index/search imports. Offline lesson stats read 241 stale files vs 631 live.
  Fixed: LESSONS_DIR → `~/brain/lessons/`. Lesson: when a path-hardcoding fix
  lands, `git log -S '<bad-string>'` to catch sibling files.
- Bash escaping in `create_cron` prompt strings: `\"` (single backslash)
  terminates the double-quoted bash string early, exposing `<verb>` to shell
  redirection → `bash -n` syntax error. Correct: `\\\"`. Use python repr to
  read exact bytes; copy the good segment verbatim.
