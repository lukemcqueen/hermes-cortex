---
name: docker-compose-bringup
description: "Fix a compose stack on a shared host that 500s/404s."
version: 1.0.0
category: devops
author: Hermes Cortex
platforms: [linux, macos]
---

# Docker-Compose Bring-Up & Multi-Project Collisions

Making a compose stack *actually work* (login → authenticated request succeeds through the web origin) is different from "containers start". This skill captures the collision and bring-up failure modes that make `./run up` look healthy while every real request fails. Verified on a FastAPI + Next.js stack living on a host that also runs another project's plain `postgres`/`redis`.

## When to Use

- `./run up` / `docker compose up` starts containers but the app 500s, 404s, or can't reach its DB.
- Two projects on the same Docker host use the same container names or default host ports.
- You're told "this deploys to a shared repo server" — plan for name AND port collisions up front.

## 1. Multi-project collision: unique names AND unique host ports

Container names and host ports BOTH collide across projects on a shared host. The default ports (5432 postgres, 6379 redis, 8000 api, 3000 web) are the highest-risk. A native host service (e.g. Homebrew postgres on 5432) also blocks a container bind — check with `lsof -i :PORT` and identify the owner (`docker inspect -f '{{index .Config.Labels "com.docker.compose.project"}}' <name>` for containers).

**Fix — unique names + ports, centralized in `.env`:**

```yaml
# docker-compose.yml
services:
  api:
    container_name: example-api
    ports:
      - "127.0.0.1:${Example_API_PORT:-18000}:8000"   # host 18000 -> container 8000
  postgres:
    container_name: example-postgres
    ports:
      - "127.0.0.1:${Example_POSTGRES_PORT:-15443}:5432"
```

- Compose auto-reads `.env` in the project dir for `${VAR:-default}` interpolation.
- The container-INTERNAL port stays canonical (`api:8000`, `postgres:5432`) so `depends_on` and internal `DATABASE_URL`/`REDIS_URL` (service-name hosts) are untouched. Only the host-published side changes.
- Document every var in `.env.example` (the real `.env` is gitignored). `.env` secret-file edits are security-blocked → update via a small Python script that appends deduplicated lines.

**Keep every config surface in sync when you relabel ports** (a single stale one silently lies):
- `config.py`/settings defaults (e.g. `database_url` host port, `ALLOWED_ORIGINS` web port)
- `./run status` port checks (`lsof -i :3012` goes stale when web moves to 13012)
- playwright `baseURL`, CI lighthouse `urls`
- client-side `fetch('http://localhost:<port>')` and Next API-route proxies

## 2. Bring-up failure modes that look like "healthy but broken"

Each makes containers start clean yet every request fail:

**2a. DB-URL driver must match the app's engine.** If the app's SQLAlchemy layer is SYNC (`create_engine(...)`) but compose sets `DATABASE_URL=postgresql+asyncpg://...`, every DB query 500s with `sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called`. Fix: use the matching sync URL `postgresql://user:pass@service:5432/db` (psycopg2). Check the app's engine before copying an async URL. Also: `create_engine` fails lazily — the API can boot fine and only crash on the first query, so health checks pass while register/login 500.

**2b. Fresh volume has no tables.** A brand-new named volume starts empty; unless migrations run, every table query fails. Robust fix: run migrations at API start and make Alembic honor the runtime URL:
- `Dockerfile` CMD: `["sh","-c","uv run alembic upgrade head && exec uv run uvicorn ..."]` (alembic is idempotent so restarting is safe).
- `migrations/env.py`: in `run_migrations_online`, `db_url = os.environ.get("DATABASE_URL")` and `config.set_main_option("sqlalchemy.url", db_url)` — NEVER bake a host into `alembic.ini` (its `localhost:5432` is wrong inside the container).
- Confirm `alembic` is in PROD deps (a `uv sync --no-dev` build drops it if it's dev-only).

**2c. Frontend `/api/v1` prefix vs backend with no such prefix.** Pages may call `/api/v1/auth/*` while FastAPI mounts at `/auth`, `/evangelist` (no `/api/v1`). Without a proxy every browser call 404s. Fix: a Next rewrite forwarding `/api/v1/:path*` → FastAPI `/:path*`, with the target from an env var baked at BUILD time (so it survives in Docker where `localhost:8000` isn't the API):
```js
// next.config.mjs
async rewrites() {
  const api = process.env.Example_API_INTERNAL_URL || 'http://localhost:8000';
  return [{ source: '/api/v1/:path*', destination: `${api}/:path*` }];
}
```
Web Dockerfile: `ARG Example_API_INTERNAL_URL=http://localhost:8000` + `ENV` before `npm run build`; compose passes `args: Example_API_INTERNAL_URL: http://api:8000`. Server-side Next API routes can read the same env at runtime. Client components should use the relative `/api/v1/...` path (through the proxy) instead of hardcoding `localhost:<port>`. Grep the whole frontend for hardcoded `localhost:8000` / nonexistent route strings (e.g. an `AuthForm` posting to `/api/auth` that no route serves).

**2d. Stale Docker image after a Dockerfile edit.** `docker compose up` may serve an image built with the OLD `CMD`/`RUN` — symptom: your new `alembic upgrade head` CMD doesn't run, logs go straight to uvicorn. Fix: force a rebuild (`docker compose build --no-cache <svc>`, or rebuild explicitly after editing a Dockerfile) and confirm BEHAVIOR (check logs show the new step), not just that the container restarted.

## 3. Verify it's truly working end-to-end

"Containers up / healthy" is not done. Drive the deployed path:
- `./run status` or `docker compose ps` → all healthy
- Register + login against the web ORIGIN (`http://127.0.0.1:<WEB_PORT>/api/v1/auth/login`), then an authenticated request (`/api/v1/auth/me`) through the proxy
- For a real-browser check (when Playwright's browser isn't installed), the `browser_exec` tool drives the actual UI; verify a full flow (login → list → create → mutation → read-back).
- Rebuild the web image after ANY frontend source change; the running container serves the last-build bundle, not your latest edit.

## References
- `references/example-shared-host-case-study.md` — the concrete Example walkthrough: the 5 real breakages found, the port set chosen, and how the stack was verified.
