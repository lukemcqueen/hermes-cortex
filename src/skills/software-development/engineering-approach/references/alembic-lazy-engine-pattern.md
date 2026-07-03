# Alembic Lazy Engine Pattern for Async FastAPI

## Problem

Alembic's `env.py` imports `from app.models import Base` to get `target_metadata`. In an async FastAPI project, this import chain triggers `app/database.py` which creates `create_async_engine(...)` at module load time. When Alembic connects with the sync `psycopg2` driver, it crashes:

```
sqlalchemy.exc.InvalidRequestError: The asyncio extension requires an async driver
```

Or, after stripping `+asyncpg`, it connects but fails because the async engine was already created with the wrong URL.

## Root Cause

Engine objects are created at **module import time** in `database.py`:

```python
# BAD — engines created on import
async_engine = create_async_engine(...)
sync_engine = create_engine(...)
```

Alembic's `env.py` does `from app.models import Base` → `app/models/__init__.py` → `from app.database import Base` → entire module runs → engines created → crash.

## Fix: Lazy Engine Initialization

Replace module-level engine creation with `@lru_cache`-decorated factory functions:

```python
from functools import lru_cache

@lru_cache(maxsize=1)
def _get_async_engine():
    return create_async_engine(
        str(settings.database_url),
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
    )

@lru_cache(maxsize=1)
def _get_sync_engine():
    return create_engine(
        settings.database_url_sync,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
    )

def get_async_engine():
    return _get_async_engine()

def get_sync_engine():
    return _get_sync_engine()
```

Make the session factory lazy too:

```python
async_session_factory: async_sessionmaker[AsyncSession] = None  # type: ignore

def _init_session_factory():
    global async_session_factory
    if async_session_factory is None:
        async_session_factory = async_sessionmaker(
            get_async_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )

async def get_db() -> AsyncSession:
    _init_session_factory()
    async with async_session_factory() as session:
        ...
```

## Migration

If the table was already created manually (via `docker compose exec postgres psql ...`), the alembic_version table may have two rows (m4 and m5 as sibling branches). Fix:

```bash
# Remove the manual entry
docker compose exec -T postgres psql -U user -d dbname \
  -c "DELETE FROM alembic_version WHERE version_num = 'm5_add_society_splits';"

# Stamp alembic so it knows m5 was already applied
DATABASE_URL="postgresql://user:pass@host:port/dbname" alembic stamp m5_add_society_splits
```

## Verification

```bash
# Check that import no longer crashes
DATABASE_URL="postgresql://user:pass@host:port/dbname" python3 -c "from app.database import Base; print('OK')"

# Run migration check
DATABASE_URL="postgresql://user:pass@host:port/dbname" alembic check
```

## Update all references

After renaming `async_engine` → `get_async_engine()`, update every import site:

```bash
# Find all references
grep -r "from app.database import.*async_engine" app/ --include="*.py"
```

Change `async_engine.connect()` to `get_async_engine().connect()`.
