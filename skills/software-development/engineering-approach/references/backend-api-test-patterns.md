# Backend API Test Patterns — FastAPI + asyncpg + httpx

## Conftest Architecture

```
tests/
  conftest.py      — fixtures: engine, session, client, tokens, seed data
  pytest.ini       — asyncio_mode = auto
  test_*.py        — one file per domain module
```

Key pattern: session-scoped engine + per-test session. No transaction nesting, no SQLite hacks.

## Fixture Chain

```
event_loop (session)
  → db_engine (session)  — creates test PG DB + metadata.create_all + drop_all
    → db_session (function) — fresh AsyncSession per test, rollback on exit
      → client (function) — httpx.AsyncClient with get_db override
        → admin_token / viewer_token (function) — creates real User row + JWT
          → admin_headers / viewer_headers (function) — dict for Authorization header
```

## Test Database URL

```python
import os

TEST_DB_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://acme:acme@localhost:5432/acme_test",
)
```

Auto-creates `acme_test` by connecting to the default `postgres` DB first (never assume a project-specific DB exists):

```python
maint_engine = create_async_engine(
    TEST_DB_URL.rsplit("/", 1)[0] + "/postgres",  # use 'postgres' DB, not a project DB
    isolation_level="AUTOCOMMIT",
)
# CREATE DATABASE acme_test
```

## Dependency Override Pattern

```python
@pytest_asyncio.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()
```

## Auth Token Fixtures

Create a real User row in the test DB (so FK constraints pass), then generate a JWT:

```python
@pytest_asyncio.fixture
async def admin_token(db_session):
    user = User(id=uuid.uuid4(), email="admin@test.acme",
                role="superadmin", status="active", display_name="Test Admin")
    db_session.add(user)
    await db_session.commit()
    return create_access_token(user_id=str(user.id), role="superadmin")
```

## Multi-Role Fixtures

Test RBAC by creating tokens for different roles:

```python
@pytest_asyncio.fixture
async def admin_token(db_session):
    user = User(id=uuid.uuid4(), email="admin@test.acme",
                role="superadmin", status="active")
    db_session.add(user)
    await db_session.commit()
    return create_access_token(user_id=str(user.id), role="superadmin")

@pytest_asyncio.fixture
async def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}

@pytest_asyncio.fixture
async def viewer_token(db_session):
    user = User(id=uuid.uuid4(), email="viewer@test.acme",
                role="viewer", status="active")
    db_session.add(user)
    await db_session.commit()
    return create_access_token(user_id=str(user.id), role="viewer")

@pytest_asyncio.fixture
async def viewer_headers(viewer_token):
    return {"Authorization": f"Bearer {viewer_token}"}
```

Use in tests:
```python
async def test_viewer_cannot_create(client, viewer_headers):
    resp = await client.post("/api/works", headers=viewer_headers, json={...})
    assert resp.status_code == 403
```

## Entity Seed Data

Each domain entity gets its own seed fixture returning its ID. Tests compose the seeds they need:

```python
@pytest_asyncio.fixture
async def seed_member(db_session):
    member = Member(
        id=uuid.uuid4(),
        code="M001",
        name="Test Member",
        ipi_name="00000000000",
        ipi_base_number="I-000000000-0",
    )
    db_session.add(member)
    await db_session.commit()
    return member.id

@pytest_asyncio.fixture
async def seed_publisher(db_session):
    pub = Publisher(
        id=uuid.uuid4(),
        code="P001",
        name="Test Publisher",
        ipi_name="11111111111",
    )
    db_session.add(pub)
    await db_session.commit()
    return pub.id

@pytest_asyncio.fixture
async def seed_creator(db_session):
    creator = Creator(
        id=uuid.uuid4(),
        name="Test Creator",
        code="PE00000001",
        ipi_name="22222222222",
        ipi_base_number="I-222222222-2",
    )
    db_session.add(creator)
    await db_session.commit()
    return creator.id

@pytest_asyncio.fixture
async def seed_work(db_session):
    work = Work(
        id=uuid.uuid4(),
        title="Test Work",
        iswc="T-345.678.901-2",
        work_type="pop",
        language="en",
        status="active",
    )
    db_session.add(work)
    await db_session.commit()
    return work.id

@pytest_asyncio.fixture
async def seed_territories(db_session):
    territories = [
        Territory(id=uuid.uuid4(), code="+82", name="South Korea", tis_code="KR"),
        Territory(id=uuid.uuid4(), code="+81", name="Japan", tis_code="JP"),
        Territory(id=uuid.uuid4(), code="+0100", name="Worldwide", tis_code="WW"),
        Territory(id=uuid.uuid4(), code="+1", name="United States", tis_code="US"),
    ]
    for t in territories:
        db_session.add(t)
    await db_session.commit()
```

**Key patterns:**
- Each fixture commits independently so other fixtures can reference the row
- IDs are explicitly generated (not left to DB default) so they can be returned
- Fixtures return the UUID for use in endpoint tests
- Tests that need multiple entities compose fixtures: `def test_x(client, seed_work, seed_creator, seed_member):`

### pytest.ini

Required for async tests:

```ini
[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "function"
testpaths = ["tests"]
python_files = ["test_*.py"]
```

- **`asyncio_mode = auto`** — pytest-asyncio detects async test functions automatically. Without this, every async test needs a `@pytest.mark.asyncio` decorator.
- **`asyncio_default_fixture_loop_scope = "function"`** — REQUIRED when mixing fixture scopes (e.g. session-scoped engine + function-scoped tests). Without this, session-scoped async fixtures create their engine on one event loop while function-scoped tests try to use it on a different loop, producing: `RuntimeError: Task <...> got Future <...> attached to a different loop`. Set to `"function"` so all fixtures and tests share the same loop.

## Infrastructure Dependencies

### greenlet

SQLAlchemy async mode with asyncpg **requires** the `greenlet` library on all Python versions, including Python 3.14. Without it, every async test fails with:

```
ValueError: the greenlet library is required to use this function...
```

It must be declared as an explicit dependency, even though it's a transitive dependency of SQLAlchemy — on Python 3.14 the wheel may not be pulled automatically:

```
"greenlet>=3.0.0"
```

Greenlet 3.5.1+ has wheels for CPython 3.14 (macOS universal2, Linux x86_64/aarch64).

### asyncpg

For PostgreSQL testing, use asyncpg (async) + psycopg2-binary (sync for Alembic). Both must be in `pyproject.toml`.

## Pitfalls

### Env var quoting with `set -a; source .env`

Bash's `set -a; source .env` strips inner double-quotes from JSON values. Given `.env`:

```
CORS_ORIGINS=["http://localhost:13201"]
```

After `set -a; source .env`, the env var becomes `CORS_ORIGINS=[http://localhost:13201]` — the inner quotes around the URL are consumed by bash's quote removal.

**Impact:** pydantic-settings tries to `json.loads()` this malformed string on complex fields (`list[str]`, `dict`), producing `JSONDecodeError`. The error message says `Expecting value: line 1 column 2 (char 1)`.

**Fix options (pick the right one for your context):**

1. **Unset the problematic var after sourcing** — let pydantic-settings read the .env file directly (it parses the file without bash quoting):
   ```bash
   set -a; source .env; set +a
   unset CORS_ORIGINS
   ```

2. **Wrap in single quotes in .env** — bash single quotes protect the value from quote removal:
   ```
   CORS_ORIGINS='["http://localhost:13201"]'
   ```

3. **Don't source .env at all in scripts that invoke Python** — if pydantic-settings already reads the .env file directly via `SettingsConfigDict(env_file=...)`, there's no need to also export the vars.

### pydantic-settings `decode_complex_value` runs before field validators

When an env var value is a JSON-like string (starts with `[` or `{`), pydantic-settings' `EnvSettingsSource.decode_complex_value` tries `json.loads()` on it **before** any Pydantic `field_validator(mode="before")` runs. If the JSON parse fails, the error is raised as `SettingsError` before the validator gets a chance.

This means:
- You **cannot** rescue malformed JSON from env vars with a field_validator
- The fix must be at the env-var level (fix the quoting, unset the bad var, or use a `Union` type that sets `allow_parse_failure = True`)

### `Base.metadata.create_all` doesn't create schemas

If a model uses `__table_args__ = {"schema": "audit"}`, the schema must be created manually before `create_all`:

```python
async with engine.begin() as conn:
    await conn.execute(text("CREATE SCHEMA IF NOT EXISTS audit"))
    await conn.run_sync(Base.metadata.create_all)
```

Without this, tests fail with `InvalidSchemaNameError: schema "audit" does not exist`.

### Maintenance DB URL assumes a DB exists

The conftest creates the test database by connecting to a maintenance DB first. The maintenance DB must exist and be accepting connections. Use `postgres` (the default system database that always exists) rather than a project-specific DB name:

```python
# WRONG — assumes 'acme' or 'acme_works' exists
base_url = TEST_DB_URL.replace("/acme_test", "/acme")

# RIGHT — uses 'postgres' which always exists
base_url = TEST_DB_URL.rsplit("/", 1)[0] + "/postgres"
```

### Broken FK to non-existent table

When `Base.metadata.create_all` encounters a `ForeignKey()` referencing a table that doesn't exist in the metadata registry, it raises `NoReferencedTableError`. Common causes:
- A model references a table that was never created as a SQLAlchemy model
- The referenced model isn't imported in `models/__init__.py`
- The FK target was renamed but the FK wasn't updated

**Diagnosis:** inspect the FK target directly:
```python
# error says: "column 'membership_applications.reviewer_id' could not find table 'admins'"
search_files("ForeignKey.*admins\\.id")  # find the broken reference
```

**Fix:** change the FK to an existing table's PK column, matching the column type (UUID → UUID, Integer → Integer).

### Shared test DB: unique constraint collisions across test runs

When tests share a persistent test database (no transaction-per-test rollback, no per-test DB teardown), `make_*_payload()` helper functions that produce hardcoded slugs, emails, or IPI numbers will collide on the second run:

```
httpx.IntegrityError: duplicate key value violates unique constraint "uq_categories_slug"
```

**Fix pattern — add `_uid()` helper and use it in all payload factories:**

```python
from uuid import uuid4

def _uid() -> str:
    return uuid4().hex[:8]

def make_category_payload(**overrides: dict) -> dict:
    uid = _uid()
    payload = {
        "slug": f"test-cat-{uid}",
        "name_en": f"Test Category {uid}",
        ...
    }
    payload.update(overrides)
    return payload
```

Apply to every unique-constrained field: `slug`, `email`, `ipi_name`, `code`, `reference_number`.

**Caveat:** tests that assert on the exact slug value must switch to extracting it from the generated payload instead of hardcoding:

```python
# BEFORE (collides on second run):
payload = make_category_payload()
resp = await client.post("/api/admin/categories", json=payload, headers=admin_headers)
data = resp.json()
assert data["slug"] == "test-category"  # hardcoded — fails after uuid change

# AFTER (resilient):
payload = make_category_payload()
resp = await client.post("/api/admin/categories", json=payload, headers=admin_headers)
data = resp.json()
assert data["slug"] == payload["slug"]  # matches generated value
```

## When to Use

Always use these patterns when writing or debugging backend API tests for FastAPI + asyncpg projects. Refer to this reference when setting up a new conftest, debugging test infrastructure failures, or adding a new test file.

## Integration Test Segregation

When some tests need a real PostgreSQL database (seed data, full endpoint integration) and others are pure unit tests (schema validation, mock-based logic), use pytest markers to separate them.

### Pattern — marker + auto-skip

1. **Mark integration tests** with `@pytest.mark.integration`:
```python
@pytest.mark.integration
async def test_create_venue_via_api(db_session, admin_headers):
    """Requires a running PostgreSQL database."""
    ...
```

2. **Register the marker** in `pyproject.toml`:
```ini
[tool.pytest.ini_options]
asyncio_default_fixture_loop_scope = "session"
testpaths = ["tests"]
markers = [
    "integration: marks tests that require a running PostgreSQL database",
]
addopts = "-m 'not integration'"
```

3. **Running tests:**
```bash
pytest                          # skips integration tests by default
pytest -m integration           # runs only integration tests
pytest -m "not integration"     # explicit skip (same as default)
pytest                          # full suite with addopts filtering
```

### What goes where

| Tag | Requires | What to test | Example |
|-----|----------|-------------|---------|
| (none — unit) | Nothing | Schema validation, math, pure logic | `test_create_venue_empty_name` — no DB needed |
| `@pytest.mark.integration` | Real PostgreSQL | End-to-end API calls, DB reads/writes, status transitions | `test_create_venue_via_api` — needs `db_session` + `admin_headers` |

### Fixture-level alternative

For projects where conftest already provides a `db_session` fixture that auto-creates a test DB, the unit tests simply don't use it:

```python
# Unit test — no db_session parameter → no DB overhead
async def test_venue_type_validation(client):
    resp = await client.post("/api/venues", json={"name": "Test", "type": "INVALID"})
    assert resp.status_code == 422

# Integration test — takes db_session → full DB setup
async def test_create_venue_via_api(db_session, admin_headers, client):
    ...
```

This works without markers because pytest only sets up fixtures that are actually used by the test. The marker pattern above adds explicit opt-in for projects where DB setup is too expensive to run unconditionally.

## Related

- `python-test-env-pitfalls.md` — .env leakage into assertions
- `backend-api-feature-workflow.md` — model → migration → router → tests workflow
- `docker-password-alignment.md` — .env DATABASE_URL vs POSTGRES_PASSWORD mismatch
