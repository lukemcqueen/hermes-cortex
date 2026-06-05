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

**ClickHouse migration URL** must use Go driver TCP protocol: `clickhouse://clickhouse:9000` (not HTTP port 8123).

**Startup failure diagnosis:** Check `docker logs langfuse-langfuse-web-1` for ZodError — it means missing env var. Full recreate required on config changes (`down` + `up -d`, not just `restart`).
