# Fresh-DB Migration Recovery — worked example

From a real incident (2026-07): an API container crash-looped after its Postgres volumes were
deleted and recreated. This is the exact diagnosis and fix sequence.

## Symptom

`docker ps` showed `api Up 13 seconds (health: starting)` — restarting every few seconds.
`docker logs api | tail` showed:

```
INFO  [alembic.runtime.migration] Running upgrade m16_user_token_version -> n01_notifications, ...
psycopg2.errors.DuplicateObject: type "notification_type" already exists
[SQL: CREATE TYPE notification_type AS ENUM ('system_alert', ...)]
  ✗ Alembic migration failed (exit 1).
```

A dependent service (web) with `depends_on: api: condition: service_healthy` stayed in
`Created` — it never starts until the api passes health. That's a second clue, not a second bug.

## Diagnosis (in order)

1. `SELECT version_num FROM alembic_version;` → `m10_creator_society_work_intl`
   The chain had stopped at m10 even though logs showed m10→m11→m12 running.
2. `SELECT typname FROM pg_type WHERE typname LIKE 'notification%';` → `(0 rows)`
   No notification enums existed — yet the error claimed `notification_type already exists`.
   Contradiction resolved by transactional DDL: the whole batch m10→…→n01 runs in ONE
   transaction; the enum created by the explicit `.create()` at the top of n01 was rolled back
   when the table creation later failed on the SAME type name.
3. Read the migration (not the model) — the bug was entirely in the migration file:
   - `sa.Enum(..., name="notification_type").create(op.get_bind())` at the top of `upgrade()`
   - AND columns `sa.Enum(..., name="notification_type", create_constraint=True)` in
     `op.create_table(...)` — `create_constraint=True` makes SQLAlchemy emit `CREATE TYPE`
     again during table creation (traceback path: `op.create_table` → `table.dispatch.before_create`
     → `_on_table_create` → `CreateEnumType`).

## Fix

Remove the explicit `.create()` calls; let the column definitions create each enum exactly
once during `op.create_table`. Keep the comment explaining why, so nobody re-adds them.

```python
def upgrade() -> None:
    # Enum types are created by the column definitions below (create_constraint=True
    # emits CREATE TYPE during op.create_table). Do NOT call sa.Enum(...).create()
    # here as well — that double-creates the type and fails with
    # DuplicateObject: type "notification_type" already exists on a fresh DB.
    op.create_table("inbox_threads", ...)
    op.create_table("notifications", sa.Column("type", sa.Enum(..., name="notification_type", create_constraint=True), ...), ...)
```

## Verification

- Restart the container that runs `alembic upgrade head` (the real entrypoint, not repo-side).
- Confirm the log now shows the full chain including revisions AFTER the fixed one:
  `Running upgrade n01_notifications -> m17_cwr_export_tracking` then `✓ Migrations up to date`.
- Confirm `alembic_version` = head and the previously-missing tables/enums exist.
- Note: once migrations pass, a SECOND crash cause can surface (in this case uvicorn rejecting
  `--max-request-body-size`) — keep watching the logs past the migration step.

## Why this bites

The migration had never run on an empty database — it was only ever applied to a DB that
already had the enum (created by a prior partial run or by `create_all`). Any fresh
checkout, CI database, or deleted-volume recovery hits it. Rule: every migration must run
clean on an empty DB; the container entrypoint re-runs the full chain from scratch whenever
the DB is fresh, so this class of bug always manifests as a crash-loop.
