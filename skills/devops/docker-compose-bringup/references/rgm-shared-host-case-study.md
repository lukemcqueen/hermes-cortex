# Example shared-host case study (2026-08-22)

Concrete walkthrough of making an Example-website (FastAPI + Next.js compose stack) actually work on a shared host, which also runs another project's plain `postgres`/`redis`/`worker` containers plus langfuse/mycortex.

## What was broken (5 real findings)

| # | Symptom | Root cause | Fix |
|---|---------|-----------|-----|
| 1 | Every DB call 500: `sqlalchemy.exc.MissingGreenlet` | compose `DATABASE_URL=postgresql+asyncpg://…` but `database.py` uses sync `create_engine` (psycopg2) | set `DATABASE_URL: postgresql://example:example@postgres:5432/example` (sync) |
| 2 | Register 500 — "relation does not exist" | fresh `example-postgres` volume had zero tables; no migration on start | api `CMD` runs `alembic upgrade head` before uvicorn; `migrations/env.py` reads `DATABASE_URL` |
| 3 | Web `/api/v1/evangelist/dashboard` 404 | FastAPI mounts at `/auth`, `/evangelist` (no `/api/v1`); no Next proxy | next.config `rewrites()` `/api/v1/:path*` → FastAPI via `Example_API_INTERNAL_URL` (build-arg) |
| 4 | UI login 500/404 | `AuthForm` POSTed to `/api/auth` (a route nobody serves) | AuthForm → `/api/v1/auth/{login\|register}` through the proxy |
| 5 | `./run status` said web/api "not running" while they were up | `lsof -i :3012`/`:8000` stale after re-port | status checks → 13012/18000 |

Also: `AmenButton` + 3 Next API routes hardcoded `localhost:8000` (broke inside web container) → routed through the proxy / env URL.

## Ports chosen (Example_* in .env, documented in .env.example)

- Example_REDIS_PORT=16379, Example_POSTGRES_PORT=15443, Example_API_PORT=18000, Example_WEB_PORT=13012
- postgres remapped to 15443 because host 5432 is a **native Homebrew Postgres** (not a container) — `lsof -i :5432` showed a host `postgres` PID.
- Internal ports unchanged (redis 6379, postgres 5432, api 8000, web 3000 from the Dockerfile) → `depends_on`/internal URLs untouched.
- `.env` is gitignored; values added via a tiny python script (appends deduped lines; preserved existing `OPENCODE_ZEN_BASE_URL`). `.env.example` documents them for other environments.

## Verification that worked

- `docker compose config -q` (valid), `bash -n run`.
- Stack: `example-api` (18000→8000), `example-postgres` (15443), `example-redis` (16379), `example-web` (13012→3000); api image rebuilt **twice** (first still ran the old CMD — stale-build trap, see 2d).
- HTTP through the deployed web origin (`http://127.0.0.1:13012/api/v1/...`): register → login (cookie) → `/auth/me` 200 → create relationship → set follow-up trigger → dashboard returns the upcoming trigger (`days_overdue: -7`). All 200.
- Real browser (`browser_exec`, after approving Chrome remote-debugging): home → login ("Welcome back, BrowserEv") → dashboard → add relationship → set 7-day reminder ("Reminder set") → dashboard shows "Sarah · Next reminder in 7 days" linking to `/relationships/2`.
- `./run` help/status/up/down/start/stop/restart/logs/build/test:unit(32/32)/api/dev all smoke-verified.

## UX findings surfaced during the browser test (not fixed in this pass)

- Add-relationship form inputs have no `id`/`name`/`placeholder`/label — no accessible name for screen readers.
- Relationship-detail header reads "phase-1No contact logged" — stage chip + date concatenate with no separator.
- The `🐴 Example` title seen in browser was a **false alarm**: server emits `<title>Example</title>` with zero emojis; the horse was injected by the browser automation, not the app.
