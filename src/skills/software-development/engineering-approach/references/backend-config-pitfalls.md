# Backend Configuration Pitfalls

## pydantic-settings v2.14+ — CORS_ORIGINS parsing

**Problem:** pydantic-settings v2.14+ parses env vars from the environment source **before** passing through `@field_validator`. When `CORS_ORIGINS` is defined as `list[str] = ["*"]` and the env var is a comma-separated string (e.g. `http://localhost:15501,http://localhost:3000`), the env source parser rejects the value before the validator ever runs. The result: `SettingsError: error parsing value for field "CORS_ORIGINS"`.

**Fix — use `str` type with a property:**

```python
class Settings(BaseSettings):
    CORS_ORIGINS: str = "*"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def validate_cors(cls, v: str) -> str:
        return v

    @property
    def cors_origins_list(self) -> list[str]:
        return [x.strip() for x in self.CORS_ORIGINS.split(",") if x.strip()]
```

Then use `settings.cors_origins_list` in main.py instead of `settings.CORS_ORIGINS`. The field stays as a raw string; the property does the parsing on access.

**Detection:** API logs show `SettingsError` at startup, not at request time.

## Alembic async env.py — transactional DDL wraps ALL migrations

**Problem:** The async Alembic `env.py` uses `with context.begin_transaction(): context.run_migrations()` (standard from `alembic init -t async`). This wraps **every pending migration** in a single database transaction. When migration N fails, migrations 1 through N-1 are also rolled back, even though they completed without error.

**Output looks like:**
```
Running upgrade  -> c412b77187bd, initial_schema
Running upgrade c412b77187bd -> e4550bd287b6, ...
Running upgrade e4550bd287b6 -> 3b3174c356bd, ...  ← FAILS HERE
```

After the failure, `SELECT * FROM alembic_version;` returns nothing — all migrations were rolled back.

**Fix options:**
- **A: Fix the failing migration before retrying.** All migrations run fresh on retry. This is the simplest approach and works most of the time.
- **B: Set `transaction_per_migration=True`** in `context.configure()`. Each migration gets its own transaction. Failed migrations don't roll back completed ones. More complex to debug when a mid-chain migration fails and you need to selectively fix or stamp.
- **C: Recreate the DB** (drop + create) when migrations are still in early development. Faster than debugging partial state.

**Workflow when a migration fails mid-chain:**
1. Read the error and identify which migration failed and why.
2. Fix the failing migration (e.g. boolean default, duplicate enum, missing column).
3. Drop and recreate the database: `sudo -u postgres psql -c "DROP DATABASE <name>;" && sudo -u postgres psql -c "CREATE DATABASE <name> OWNER <user>;"`
4. Re-run `alembic upgrade head` from scratch.

**Pitfall — `asyncpg` driver:** The error messages from `asyncpg` are less readable than the sync `psycopg2` driver. The chain of exceptions buries the real cause under `sqlalchemy.exc.ProgrammingError < asyncpg.exceptions.DuplicateObjectError`. Always read the bottom-most exception in the traceback, not the top.

## Alembic merge revisions — the future-revision-as-parent cycle

**Problem:** When a merge revision (e.g. `s4_merge_all_heads`) lists a revision that actually comes AFTER it as one of its parent heads, Alembic detects a cycle. The error: `Cycle is detected in revisions (...)`.

**Typical scenario:** A merge revision `M` merges heads A, B, C. Later, revision `D` is created that depends on `M` (down_revision = `M`). If someone manually edits `M`'s down_revision tuple to also include `D`, the graph becomes: `D → some_revision_before_M → M → D → ...` (cycle).

**Root cause:** The merge revision's `down_revision` is a tuple listing the heads at the time of the merge. Adding a future revision to this tuple creates a cycle.

**Fix:** Remove the future revision from the merge's `down_revision` tuple. The correct heads are the ones that existed at the time the merge was created. Never manually edit a merge revision's parent list after it's been applied.

**Verification:** After fixing, `alembic check` should pass with no cycle errors. The `alembic upgrade head` should show a single linear chain.

## alembic check detects schema drift, not just graph issues

**Problem:** `alembic check` is often added to entrypoints as a safety guard, but it detects TWO things:
1. Migration graph issues (cycles, duplicate revisions) — these should block startup
2. Schema drift (models define columns/tables that don't match DB state) — this is a development concern, not a startup blocker

Schema drift happens when SQLAlchemy models are updated but no migration is generated to match them. This is normal during development. `alembic check` will report `New upgrade operations detected` and exit with code 1.

**Fix:** Do NOT put `alembic check` in the container entrypoint. It's a CI/development tool. Use it in CI (`./run check:migrations`) to catch drift before deployment. The container entrypoint should only run `alembic upgrade head` — if there are no pending migrations, it does nothing. If there are, it applies them.

**For CI:** `docker compose exec api bash -c "PYTHONPATH=. alembic check"` — this will fail if there's drift, which is the correct behavior for CI.

## PostgreSQL 18 — strict boolean defaults

**Problem:** PostgreSQL 18 rejects `ALTER TABLE ... ADD COLUMN is_new BOOLEAN DEFAULT 1 NOT NULL` with:
```
asyncpg.exceptions.DatatypeMismatchError: column "is_new" is of type boolean
but default expression is of type integer
```

PG18 no longer coerces integer (`1`, `0`) to boolean in column defaults. Older PG versions silently accepted `DEFAULT 1` as `DEFAULT true`.

**Fix — use proper boolean literals:**
```python
# WRONG — PG18 rejects this
sa.Column("is_new", sa.Boolean(), nullable=False, server_default=sa.text("1"))

# RIGHT — use 'true'/'false' strings
sa.Column("is_new", sa.Boolean(), nullable=False, server_default=sa.text("true"))
```

**Detection:** The error only surfaces when Alembic runs the migration against PG18. SQLite (used in tests) accepts `1` as a boolean default without complaint, so this passes CI but fails in production.

**Scope:** Affects any `Alembic` `add_column` operation that adds a `BOOLEAN` column with a server default. Includes `batch_alter_table` contexts.

## Postgres ENUM types — double-creation in Alembic

**Problem:** When an Alembic migration creates a `sa.Enum()` type explicitly via `part_of_speech_enum.create(op.get_bind(), checkfirst=True)` AND then uses the same enum in a column definition inside `op.create_table()`, the table creation triggers `_on_table_create` which tries to create the enum a **second time** — and `checkfirst` is `False` in that path, causing `DuplicateObjectError`.

**Fix — remove the explicit `create()` call:**
```python
# Define the enum (creates CHECK constraint, not the PG type itself)
part_of_speech_enum = sa.Enum(
    "NOUN", "VERB", ..., name="part_of_speech_enum",
    create_constraint=True,
)

# DO NOT call create() manually — table creation handles it

# The column reference in create_table auto-creates the enum type
op.create_table(
    "lexicon_items",
    sa.Column("part_of_speech", part_of_speech_enum, ...),
    ...
)
```

Let SQLAlchemy's `_on_table_create` callback handle the type creation. The callback works correctly on a fresh database where the type doesn't exist yet.

## db:reset must run migrations inside Docker, not from host

**Problem:** The `./run db:reset` command drops and recreates the database via `docker compose exec postgres`, then runs `alembic upgrade head` from the **host** Python venv. The host venv connects to `localhost:<port>` with host-environment credentials, which may differ from the Docker Postgres credentials. The error: `psycopg2.OperationalError: password authentication failed for user "acme"`.

**Fix:** Run `alembic upgrade head` inside the API container, not from the host:

```bash
docker compose exec -T api bash -c "export PATH=/app/.venv/bin:\$PATH && cd /app && PYTHONPATH=. alembic upgrade head"
```

The API container has its own venv and connects to `postgres:5432` via Docker networking with the correct credentials.