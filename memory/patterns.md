# Patterns

## Langfuse Docker Stack

A self-contained LLM observability stack. Deploy pattern:

```
docker compose -f docker-compose.langfuse.yml up -d
```

**Stack:** postgres + redis + clickhouse + minio + langfuse-web + langfuse-worker

**Mandatory env vars** (in `~/langfuse/.env`):
- `LANGFUSE_SALT`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_NEXTAUTH_SECRET`
- `LANGFUSE_ENCRYPTION_KEY` (64 hex chars)
- `CLICKHOUSE_USER`, `CLICKHOUSE_PASSWORD`
- `LANGFUSE_REDIS_AUTH`
- `LANGFUSE_MINIO_ACCESS_KEY`, `LANGFUSE_MINIO_SECRET_KEY`
- `LANGFUSE_INIT_PROJECT_PUBLIC_KEY`, `LANGFUSE_INIT_PROJECT_SECRET_KEY`

**First-time admin access:** Set these in `.env` before first deploy to auto-create an admin user:
- `LANGFUSE_INIT_USER_EMAIL` (e.g. `admin@langfuse.local`)
- `LANGFUSE_INIT_USER_NAME` (e.g. `admin`)
- `LANGFUSE_INIT_USER_PASSWORD`
If omitted, use the **Sign up** link on the login page (`localhost:3001`) to create the first admin account.

**ClickHouse migration URL** must use Go driver TCP protocol: `clickhouse://clickhouse:9000` (not HTTP port 8123).

**Startup failure diagnosis:** Check `docker logs langfuse-langfuse-web-1` for ZodError — it means missing env var. Full recreate required on config changes (`down` + `up -d`, not just `restart`).

**Worker idle Redis timeout:** When no LLM traces are flowing, the worker logs ~2 `"Queue job X errored: socketTimeout: 30000"` errors per minute. These come from ioredis on idle Bull queue connections (trace-delete, evaluation-execution, etc.). Web container stays at 0 errors. The worker stays alive and reconnects automatically. This is expected idle behavior — errors stop when real trace data flows.
