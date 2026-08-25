---
name: docker-test-isolation-harness
description: "Isolated throwaway containers for Docker test runs."
category: devops
version: 1.0.0
platforms: [linux, macos]
---

# Docker Test Isolation Harness

Run a Docker-based project's integration test suite WITHOUT bringing up its full compose stack
on a shared host where that stack would collide with other running services. Uses isolated
throwaway containers with unique names/ports, then tears them down.

## When to Use

Trigger when the project's stack can't come up safely on the host, yet the suite needs a real
Postgres/Redis:
- The compose uses generic `container_name: postgres` / `redis` that collide with another
  project's already-running containers of the same name — running yours would attach to or
  disturb the wrong project's DB.
- You must not touch running services (a sibling project's production DB sharing the host).

## Prerequisites
- Docker CLI on the host (`docker ps`).
- The project's own Python `.venv` with pytest + alembic installed (or the equivalent runner).

## Diagnose ownership first (never assume)

```bash
# Which project owns the running 'postgres'? Read the compose-project label.
docker inspect postgres --format \
  'project={{index .Config.Labels "com.docker.compose.project"}} \
  workdir={{index .Config.Labels "com.docker.compose.project.working_dir"}}'
docker ps --format '{{.Names}}\t{{.Status}}\t{{.Ports}}'  # non-default port maps reveal a sibling
```

A postgres on `13211->5432` is *not* your project's default `5432` — it belongs to someone else.

## Procedure

```bash
# 1. Throwaway Postgres + Redis with UNIQUE names and free ports.
docker run -d --name <proj>-test-pg -e POSTGRES_USER=<user> -e POSTGRES_PASSWORD=<pw> \
  -e POSTGRES_DB=<db> -p 127.0.0.1:<p1>:5432 postgres:16-alpine
docker run -d --name <proj>-test-redis -p 127.0.0.1:<p2>:6379 redis:7-alpine
# wait for readiness: for i in $(seq 1 30); do \
#   docker exec <proj>-test-pg pg_isready -U <user> >/dev/null 2>&1 && break; sleep 1; done

# 2. Point the app/tests at them via env. Env overrides .env in pydantic-settings.
export DATABASE_URL="postgresql://<user>:<pw>@127.0.0.1:<p1>/<db>"
export REDIS_URL="redis://127.0.0.1:<p2>/0"

# 3. Alembic reads sqlalchemy.url from alembic.ini, NOT env -> throwaway ini via -c.
#    env.py's sys.path insert is anchored to env.py location, so -c from /tmp still imports the project.
#    [alembic] script_location = <abs>/.../migrations ; sqlalchemy.url = postgresql://<user>:<pw>@127.0.0.1:<p1>/<db>
.venv/bin/python -m alembic -c /tmp/<proj>-test-alembic.ini upgrade head

# 4. Run the suite. The test harness spawns its own server subprocess -> inherits the env.
DATABASE_URL=... REDIS_URL=... .venv/bin/python -m pytest tests/ -q

# 5. Teardown AND confirm the sibling project is still up.
docker rm -f <proj>-test-pg <proj>-test-redis && rm -f /tmp/<proj>-test-alembic.ini
docker ps --format '{{.Names}}' | grep -E '^(postgres|redis|worker)$'   # sibling set present
```

## Pitfalls
- **Endpoint dialect must match the app**: a sync SQLAlchemy `create_engine` wants `postgresql://`
  (psycopg2), NOT `postgresql+asyncpg`. Match the project's database.py / config default.
- **Route env directly, not through `./run`**: the suite's spawned subprocess inherits YOUR
  exported env; a `./run` wrapper may source `.env` and clobber the override.
- **Check ports free first**: `nc -z 127.0.0.1 <port>` before `docker run -p`.
- **Teardown is mandatory** — leftover `-test-` containers clutter the host and can be mistaken
  for the real stack.

## Related
- The underlying collision (generic `container_name: postgres`/`redis` across projects) and its
  permanent fix (unique container names per project) is covered in the `engineering-approach` skill.
- A sibling source-control hazard — an unanchored `api/` gitignore silently dropping an app dir
  from git — is in `git-forensics` / `git-pull-local-changes`.

## Verification
- Full suite green against throwaway infra; count matches baseline after any fixture fixes.
- Sibling containers reported by the teardown ownership check are unchanged.
