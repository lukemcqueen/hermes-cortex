---
name: alembic-postgres-migrations
description: Use when debugging Alembic Postgres migration failures.
version: 1.1.0
category: devops
author: Hermes Cortex
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [alembic, sqlalchemy, postgres, migrations, schema, enums, ddl]
    category: devops
    related_skills: [dockerized-stack-recovery, root-cause-debugging]
    aliases: [alembic-enum-double-create]
---

# Alembic Postgres Migrations

Author, review, and debug Alembic migrations for SQLAlchemy + PostgreSQL backends.

## When to Use

- Writing or reviewing an Alembic migration (any schema change)
- A migration fails on a fresh/empty database: `DuplicateObject`, `type "X" already exists`, `relation "X" already exists`
- A containerized API crash-loops in its entrypoint's `alembic upgrade head` step
- Schema drift — DB state doesn't match migration history

## Core Rules

1. **One enum creation path per migration.** A PostgreSQL enum type can be created two ways in SQLAlchemy:
   - Explicit: `sa.Enum("a","b", name="my_enum").create(op.get_bind())`
   - Implicit: a column typed `sa.Enum(..., name="my_enum", create_constraint=True)` — the `create_constraint=True` flag ALSO emits `CREATE TYPE` during `op.create_table` (via the table's `_on_table_create` → `CreateEnumType` event).
   Doing BOTH in one migration fails on a fresh DB with `psycopg2.errors.DuplicateObject: type "my_enum" already exists` — the explicit create succeeds, then the table creation tries to create the type a second time. **Pick one path.** Prefer the column definitions (drop the explicit `.create()` calls). If you keep explicit creates, the columns must not re-create the type.

2. **Fresh-DB failures roll back the WHOLE chain.** Alembic assumes transactional DDL on Postgres: if migration m15 fails, the DDL from m10–m14 in that run is UNDONE and `alembic_version` stays at the last committed revision (e.g. m10). Never trust partial "Running upgrade …" log lines as progress — the whole batch rolled back. Tables and enums created earlier in the same failed run will NOT exist afterward.

3. **Verify DB state with psql before theorizing.** The api's own error message can mislead (it re-runs the chain every restart, so logs interleave multiple attempts):
   - `SELECT version_num FROM alembic_version;` — where the chain actually stopped
   - `SELECT typname FROM pg_type WHERE typname LIKE '<prefix>%';` — whether enum types exist (absent after rollback)
   - `\dt` — which tables exist
   Get the container name right first (`docker ps` — compose names aren't `project-service-1` if `container_name:` is set).

4. **Fix the migration file, never hand-stamp the DB.** `INSERT INTO alembic_version` or dropping types manually only defers the failure to the next fresh checkout/volume/CI run. The migration must be idempotent enough to run clean on an empty database — that's the contract.

5. **Test through the real entrypoint.** `alembic upgrade` from the repo isn't the shipping path; the container entrypoint that runs `alembic upgrade head` on every start is. Restart that container and watch its logs. For speed on a baked image, hot-fix via `docker cp` (see `dockerized-stack-recovery`); for durability, rebuild the image.

6. **Enums named in column types must match the model.** The migration's column Enum (`name="notification_type"`) and the ORM model's `Enum(NotificationType, name="notification_type")` must agree on values — drift surfaces as opaque failures at query time, not at migration time.

## Pitfalls

### Column Name Shadowing SQLAlchemy Utility Functions

A column named `text` on any model shadows `sqlalchemy.sql.text()` — the
aliased `from sqlalchemy.sql import text` in the module is inaccessible because
the column binding wins. This surfaces as a `TypeError: 'Column' object is not
callable` at import time (since SQLAlchemy eagerly evaluates class bodies).

**Pattern:**
```python
from sqlalchemy import Column, Text
from sqlalchemy.sql import func, text      # ← text() is available here

class Translation(Base):
    text = Column(Text, nullable=False)     # ← shadows text() above
    canonical = Column(Boolean, server_default=text("false"))  # TypeError!
```

**Fix:** import with an alias that won't collide:
```python
from sqlalchemy.sql import func, text as sql_text

canonical = Column(Boolean, server_default=sql_text("false"))
```

**Scope:** Any column name that matches a commonly-imported sqlalchemy.sql
function — `func`, `text`, `literal`, `case`, `cast`, `type_`, `select` —
could shadow the utility. The `text` collision is the most frequent because
`text` (data) and `text()` (SQL expression) are both ubiquitous.

**Detection:** The API container crash-loops on startup with `TypeError:
'Column' object is not callable` pointed at the model line. The migration
`env.py` won't even import. Check the model file for column names matching
SQLAlchemy function imports.

### Migration DAG Fork Resolution

When two migrations share the same `down_revision`, alembic detects multiple
heads and `alembic upgrade head` refuses to proceed. To find the actual DB
head and relinearize:

1. List every migration's revision and down_revision:
   ```bash
   for f in migrations/versions/*.py; do
     r=$(grep -E '^revision' "$f" | head -1 | sed -E 's/.*"([^"]+)".*/\1/')
     d=$(grep -E '^down_revision' "$f" | head -1 | sed -E 's/.*"([^"]+)".*/\1/')
     echo "$r  <- $d   ($(basename $f))"
   done
   ```
2. Compare against the DB's actual head (`alembic current` from the running
   container — note the database may be behind the repo).
3. The corrective migration's `down_revision` must point to the DB's actual
   current revision, not the repo's newest head. This creates a single linear
   chain.
4. Verify: `alembic heads` returns exactly one revision, and `alembic upgrade
   head` from a fresh DB applies all migrations.

## Review Checklist (for other people's migrations)

- [ ] Would this migration run clean on an EMPTY database? (fresh volume, CI, new checkout)
- [ ] Any explicit `sa.Enum(...).create()` that duplicates a column-level enum with `create_constraint=True`?
- [ ] Does `downgrade()` drop every enum/table the upgrade creates (and in dependency-safe order)?
- [ ] Single head — `alembic heads` returns exactly one revision; two devs branching = merge revision needed
- [ ] Build-time guards: `check-heads.py`-style gate in CI/Dockerfile catches fork-merge issues before runtime

## References

- `references/fresh-db-migration-recovery.md` — worked example: the notification_type DuplicateObject crash-loop, full diagnosis sequence, and the fix pattern
