---
name: alembic-enum-double-create
description: >-
  Use when alembic fails DuplicateObject enum on fresh DB.
version: 1.0.0
category: software-development
platforms: [linux, macos]
---

# Alembic Enum Double-Create — Fresh DB Migration Crash

## Symptom

`alembic upgrade head` fails on a fresh/empty database (e.g. after Docker
volumes were deleted):

```
psycopg2.errors.DuplicateObject: type "notification_type" already exists
[SQL: CREATE TYPE notification_type AS ENUM (...)]
```

The api container crash-loops (`health: starting` forever), `alembic_version`
is stuck at an older revision, and web never starts (`depends_on: api
service_healthy`). The same failure replays on every restart because
transactional DDL rolls the whole chain back.

## Root cause

The migration does BOTH:

1. Explicitly creates the enum: `sa.Enum(..., name="notification_type").create(op.get_bind())`
2. Declares table columns with `sa.Enum(..., name="notification_type", create_constraint=True)`

`create_constraint=True` makes SQLAlchemy emit CREATE TYPE again during
`op.create_table` (via `Enum._on_table_create`). Within one transaction the
type gets created twice → `DuplicateObject`. This only shows on a fresh DB;
an existing DB that already ran the migration never re-executes it, which is
why the bug can sit unnoticed.

## Fix

Remove the explicit `.create()` calls. The column definitions create each
type exactly once during `op.create_table`:

```python
def upgrade() -> None:
    # Do NOT call sa.Enum(...).create() here — the column definitions below
    # (create_constraint=True) emit CREATE TYPE during op.create_table.
    # Double creation fails with DuplicateObject on a fresh DB.
    op.create_table(
        "notifications",
        sa.Column("type", sa.Enum(..., name="notification_type", create_constraint=True), nullable=False),
        ...
    )
```

Keep the downgrade dropping the types.

## Verification

1. Restart the api container (or rebuild + `docker compose up -d`).
2. `docker logs api | grep -E "Running upgrade|✓|✗"` → all migrations run
   through head, then `✓ Migrations up to date`, uvicorn starts.
3. `alembic current` reports the head revision.
4. `\dT+` shows the enum types exist exactly once.

## Pitfalls

- **`docker cp` mode 600**: copying a migration into a running container
  lands with `-rw-------` owned by the host uid — the container user can't
  read it → `PermissionError` on next start. Fix: `docker exec -u root api
  chmod 644 /app/alembic/versions/<file>.py`.
- **Baked `/app`**: if the Dockerfile `COPY`s the app (no volume mount for
  code), `docker cp` is only a fast dev-loop test — rebuild the image so the
  fix survives `docker compose up` / `./run up`.
- **Stuck version is normal**: after the failed run, `alembic_version` shows
  the revision where the batch started (e.g. m10), not the failing one —
  the whole batch rolled back.
