---
title: Background Job Queue
name: background-job-queue
version: 1.0.0
description: Add durable background job processing to a FastAPI/asyncpg app using arq. Covers project layout, job function contract, DB session management, worker entrypoint, Docker Compose service, run-script command, and testing strategy.
trigger:
  - User says "add job queue", "arq", "background job", "worker", "durable task"
  - Task involves long-running async work (exports, reconciliation, batch processing)
  - Adding a new job type to an existing arq worker
role: developer-agent
---

# Background Job Queue (arq)

## Prerequisites

- FastAPI app with async SQLAlchemy + asyncpg
- Redis already in the stack
- `arq>=0.26` in `pyproject.toml`

## Structure

```
apps/api/
├── app/
│   └── jobs/
│       ├── __init__.py       # JobQueue helper, pool factory, JOB_FUNCTIONS registry
│       ├── export_jobs.py    # Job functions per concern
│       └── reconciliation_jobs.py
├── arq_worker.py              # Worker entrypoint (settings + run_worker)
├── Dockerfile.worker          # or reuse the API image with a different command
├── docker-compose.yml         # adds worker service (depends_on redis + db)
└── run                        # adds `./run worker` command
```

## Job Function Contract

Every arq job is an async function whose first argument is `ctx`:

```python
# app/jobs/export_jobs.py
from arq import cron

async def export_report(ctx, report_id: int) -> str:
    """Generate a report; return a human-readable summary (stored in arq)."""
    db = ctx["db"]   # session from the worker's startup
    rows = await db.execute(...)
    path = await write_csv(rows)
    return f"exported {len(rows)} rows to {path}"

async def daily_cleanup(ctx):
    """Example cron-style job."""
    ...
```

**Contract rules:**
- `ctx` is always first — it carries settings, db, redis
- Return a `str` summary (arq records it as the job result)
- Raise to mark failure; arq retries per `max_tries`/`retry_jobs`

## DB Session Management

Create the session in the worker's `on_startup`, expose via `ctx`:

```python
# arq_worker.py
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

engine = create_async_engine(DATABASE_URL)
Session = async_sessionmaker(engine, expire_on_commit=False)

async def startup(ctx):
    ctx["db"] = Session()

async def shutdown(ctx):
    await ctx["db"].close()
    await engine.dispose()

async def run_worker():
    from arq import create_pool
    redis = await create_pool(REDIS_URL)
    worker = Worker(
        functions=[export_report, daily_cleanup],
        on_startup=startup,
        on_shutdown=shutdown,
        redis_settings=RedisSettings.from_dsn(REDIS_URL),
        max_jobs=10,
        job_timeout=3600,
    )
    await worker.async_run()
```

## Enqueueing from the API

```python
# app/jobs/__init__.py
from arq import create_pool

class JobQueue:
    def __init__(self, redis_url: str):
        self._redis_url = redis_url
        self._pool = None

    async def _pool_or_create(self):
        if self._pool is None:
            self._pool = await create_pool(self._redis_url)
        return self._pool

    async def enqueue(self, func_name: str, *args):
        pool = await self._pool_or_create()
        return await pool.enqueue_job(func_name, *args)

    async def close(self):
        if self._pool:
            await self._pool.close()
```

Wire into FastAPI via dependency:

```python
# app/main.py
from app.jobs import JobQueue

queue = JobQueue(settings.redis_url)

@app.post("/reports")
async def create_report(report_id: int):
    job = await queue.enqueue("export_report", report_id)
    return {"job_id": job.job_id, "status": "queued"}
```

> **Lifespan cleanup:** close the pool in FastAPI's lifespan shutdown so tests
> don't leak connections.

## Worker Entrypoint

```python
# arq_worker.py — runnable directly
if __name__ == "__main__":
    import asyncio
    asyncio.run(run_worker())
```

```bash
# Run locally
python -m arq_worker
```

## Docker Compose Service

```yaml
  worker:
    build: { context: ., dockerfile: Dockerfile.worker }
    command: python -m arq_worker
    environment:
      - DATABASE_URL=postgresql+asyncpg://postgres:postgres@db:5432/app
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      - db
      - redis
    restart: unless-stopped
```

> **Worker must NOT be `depends_on: [api]` with health-gating** — it needs
> db+redis only. Keep the worker's restart policy independent of API health.

## Run-Script Command

Add to the `./run` CLI (see `unified-cli-script` / `env-aware-compose-wrapper`):

```bash
worker() {
  _compose up -d worker && _compose logs -f worker
}
```

```bash
# Usage
./run worker
```

## Testing Strategy

### Unit-test the job function with a fake ctx

```python
import pytest

async def test_export_report(tmp_path, db_session):
    ctx = {"db": db_session}
    result = await export_report(ctx, report_id=1)
    assert result.startswith("exported")
    assert (tmp_path / "report.csv").exists()
```

### Integration-test enqueueing against real Redis

```python
@pytest.mark.asyncio
async def test_enqueue(redis_pool):
    queue = JobQueue(redis_url=REDIS_URL)
    job = await queue.enqueue("export_report", 1)
    assert job.job_id is not None
    await queue.close()
```

### Avoid testing the worker loop itself

Don't spin up the full Worker in unit tests — test the functions with fake
ctx and test enqueueing separately. The arq loop is arq's own concern.

## Pitfalls

- ❌ **Job functions that need request context** — jobs are process-local; pass IDs, not objects
- ❌ **Sync DB calls in async jobs** — blocks the worker event loop; use async SQLAlchemy
- ❌ **No `job_timeout`** — a hung job pins a worker slot forever
- ❌ **Multiple workers + cron jobs** — arq runs each cron once globally; duplicate workers cause double-fires. Use `cron` decorators with a single worker.
- ❌ **Worker in the API container** — separate process (or at least separate command) so API deploys don't restart jobs mid-flight
- ❌ **`insert_all!` skipped callbacks** — N/A for arq, but the same "audit before bypassing ORM" rule applies to bulk DB writes inside jobs

## Verification

```bash
# Start Redis + db + worker
./run worker &

# Enqueue a job and watch it execute
curl -s -X POST http://localhost:8000/reports -d '{"report_id": 1}'
./run worker logs   # should show the job running + result

# Inspect job result in arq
python -c "import asyncio, arq; ..."
```

## Related
- `arq-worker-startup-pitfalls` — crash-loop diagnosis for arq workers
- `batch-job-optimization` — making the job fast once it runs
- `postgres-docker` — DB container config
- `unified-cli-script` — the `./run` pattern
- `test-seed-uniqueness` — seed data rules for job tests
