---
name: arq-worker-startup-pitfalls
description: >-
  Use when an arq worker crash-loops or runs no jobs.
version: 1.0.0
category: devops
platforms: [linux, macos]
---

# arq Worker Startup Pitfalls

Three independent failures that all look like "the worker container won't
stay up". Check them in order.

## 1. `TypeError: 'type' object is not iterable` at `map(func, functions)`

**Cause:** arq 0.28's `Worker.__init__` takes `functions` as its FIRST
positional argument. Calling `Worker(WorkerSettings)` passes the settings
class itself as the functions sequence:

```python
# ❌ BAD — passes the class, not its functions
asyncio.run(Worker(WorkerSettings).run())
# TypeError: 'type' object is not iterable
```

**Fix:** use the exported `run_worker()` helper, which expands the settings
class via `get_kwargs()` and blocks running the loop (`Worker.run()` is
synchronous):

```python
from arq import run_worker

class WorkerSettings:
    functions = JOB_FUNCTIONS          # list of async funcs
    redis_settings = _arq_settings()   # arq.connections.RedisSettings
    ...

run_worker(WorkerSettings)             # blocks, runs the worker loop
```

Note: `create_worker` exists in `arq.worker` but is NOT exported from
`arq/__init__.py` in 0.28 — `from arq import create_worker` raises
ImportError. Use `run_worker`.

## 2. Worker runs uvicorn (or nothing) instead of its job script

**Cause A — entrypoint ignores CMD:** the image ENTRYPOINT ends with
`exec uvicorn ...` unconditionally, so compose `command: python3
arq_worker.py` is discarded. Fix: exec the supplied command when present,
fall back to the API server:

```bash
if [ "$#" -gt 0 ]; then
    exec "$@"
fi
exec .venv/bin/uvicorn app.main:app ...
```

**Cause B — job script missing from image:** the Dockerfile never
`COPY`s the worker entrypoint (`arq_worker.py`). Add it:

```dockerfile
COPY arq_worker.py ./
```

## 3. Worker connects to the wrong Redis port

**Cause:** `.env` carries the HOST-side published port (e.g.
`REDIS_PORT=13212`) and it leaks into containers via `env_file: .env`.
Inside the compose network Redis listens on 6379, so the worker logs
`redis=redis:13212` and can't connect.

**Fix:** pin the internal port explicitly in the compose service
environment (overrides env_file):

```yaml
    environment:
      REDIS_HOST: redis
      REDIS_PASSWORD: ${REDIS_PASSWORD:-your-redis-password}
      REDIS_PORT: 6379
```

## Verification

```bash
docker ps --format '{{.Names}}\t{{.Status}}' | grep worker   # Up, not Restarting
docker logs worker | tail -10
# expect: Starting worker for N functions: ...
#         redis_version=... clients_connected=1
```

## Pitfalls

- Images with baked `/app` need a rebuild (`./run build worker`) for
  `arq_worker.py` / entrypoint changes; `docker cp` is only a temporary
  dev-loop test.
- Check the pinned arq version in `uv.lock` before using API helpers —
  0.28 exports `run_worker`, not `create_worker`.
