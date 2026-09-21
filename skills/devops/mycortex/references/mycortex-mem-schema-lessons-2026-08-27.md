# mycortex-mem schema + connection lessons (2026-08-27)

Titus handoff built on Esther: mycortex-mem (Honcho replacement) + prompt-guard.
Three real bugs caught by live testing — all schema/connection-class lessons.

## 1. sessions needs `updated_at`

The plugin's `sync_turn` runs
`UPDATE sessions SET message_count = message_count + 2, updated_at = now()`.
v001 shipped WITHOUT `updated_at`, so every sync_turn UPDATE failed and the
exception was swallowed by `logger.debug` → messages never inserted, search
returned "No relevant messages found" with ZERO errors surfaced.

**Lesson:** when a plugin writes to your schema, grep the plugin's SQL for
every column it touches BEFORE writing the migration. The schema author must
cross-check the consumer's DML, not just the DDL.

**Fix:** add `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()` to sessions.
Because v001 was applied minutes earlier with nothing depending on it, the
schema was dropped (`DROP SCHEMA mycortex_mem CASCADE`) and re-applied — a
v002 would be the right path if anything already depended on the table.

## 2. Linux `sg docker -c` psql flags must be INSIDE the quoted string

Broken pattern:

```python
def _cmd(self, role):
    return ["sg", "docker", "-c",
            f"docker exec -i {CONTAINER} psql -U {role} -d {db} -v ON_ERROR_STOP=1"], {}

def query(self, sql, role):
    full_cmd = cmd + ["-t", "-A"]   # BUG: appended AFTER the sg wrapper
    r = subprocess.run(full_cmd, ...)
```

`sg` treats everything after `-c` as ONE argument (the shell command string),
so `["-t", "-A"]` became sg ARGS, not psql args → psql ran WITH headers →
`_resolve_peer_id` returned the column header `"id                  "` →
`invalid input syntax for type uuid`.

**Correct pattern** (matches mycortex migrate.py `_psql_base`): embed `-t -A`
inside the quoted docker-exec string:

```python
f"docker exec -i {CONTAINER} psql -U {role} -d {db} -v ON_ERROR_STOP=1 -t -A"
```

**Rule:** never append argv flags after a `sg ... -c "<cmd>"` wrapper — the
wrapper consumes exactly one argument; everything after is sg's, not psql's.
macOS direct-psql paths (no sg wrapper) can append normally — but keep both
platforms symmetric by embedding the flags.

## 3. `is_available()` must `.init()` the connection seam

`_PgConnection` is constructor-less (a `init(db_name)` method sets state).
`is_available()` created `_PgConnection()` then called `.scalar(...)` →
AttributeError on `_is_macos` → caught → `is_available` always False (silently
"unavailable"). Same bug in `initialize()` — `self._pg = _PgConnection()`
without `.init()`.

**Fix:** call `.init()` at EVERY entry point (is_available AND initialize).
Class-level lesson: for constructor-less seam objects, either give them a real
`__init__` or audit every instantiation site.

## Verification evidence

- `bash tests/test-mycortex-mem-schema.sh` → 17/17 PASS (fresh scratch DB)
- Full plugin lifecycle via real loader (`plugins.memory.load_memory_provider`):
  initialize OK, 5 mem_* tools exposed, conclude/list/search/context all
  returned live data, memory-write mirroring works.
- prompt-guard middleware: flag/block/benign/trivial all correct, DB logging
  rows landed in interceptor_log.
