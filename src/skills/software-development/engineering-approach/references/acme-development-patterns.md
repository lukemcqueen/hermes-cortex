# ACME Development Patterns

## Rust Batch Processor Integration

When adding a new Rust batch processor service:
1. **Project structure**:
   ```
   apps/batch/
   ├── Cargo.toml
   ├── src/
   │   ├── main.rs (CLI with clap subcommands)
   │   ├── db.rs (sqlx connection pool)
   │   ├── export.rs (CWR export logic)
   │   └── validate.rs (share validation logic)
   ├── Dockerfile
   └── .gitignore
   ```

2. **Cargo.toml dependencies**:
   ```toml
   [dependencies]
   clap = { version = "4.5", features = ["derive"] }
   sqlx = { version = "0.8", features = ["postgres", "runtime-tokio", "tls-rustls", "uuid", "chrono"] }
   anyhow = "1.0"
   tracing = "0.1"
   tracing-subscriber = { version = "0.3", features = ["fmt"] }
   uuid = { version = "1.0", features = ["v4"] }
   ```

3. **Dockerfile pattern**:
   ```dockerfile
   FROM rust:slim-bookworm AS builder
   WORKDIR /app
   COPY . .
   RUN cargo install --locked --path . --root /usr/local

   FROM debian:bookworm-slim
   RUN apt-get update && apt-get install -y ca-certificates && rm -rf /var/lib/apt/lists/*
   COPY --from=builder /usr/local/bin/batch /usr/local/bin/batch
   ENTRYPOINT ["/usr/local/bin/batch"]
   ```

4. **docker-compose.yml integration**:
   ```yaml
   batch:
     build:
       context: ./apps/batch
       dockerfile: Dockerfile
     container_name: batch
     profiles: [batch]  # Don't run with main stack
     environment:
       DATABASE_URL: postgresql://${POSTGRES_USER:-acme}:${POSTGRES_PASSWORD:-acme_dev}@postgres:5432/${POSTGRES_DB:-acme_works}
       EXPECTED_ALEMBIC_VERSION: ${EXPECTED_ALEMBIC_VERSION:-HEAD}
     depends_on:
       postgres:
         condition: service_healthy
   ```

5. **./run script integration**:
   Add to command routing:
   ```bash
   cmd_batch() {
       echo "=== Building batch image ==="
       docker compose build batch
       echo ""
       echo "=== Running batch processor ==="
       docker compose run --rm batch "$@"
   }
   ```
   And add to case statement:
   ```bash
   batch)           shift; cmd_batch "$@" ;;
   ```

6. **Running batch with `check-schema`**:
   - The `EXPECTED_ALEMBIC_VERSION` env var defaults to `HEAD`, but `HEAD` is NOT a valid Alembic revision number. Pass the actual revision (e.g. `002`):
     ```bash
     docker compose run --rm -e EXPECTED_ALEMBIC_VERSION=002 batch check-schema
     ```
   - The Rust query must use `SELECT version_num FROM alembic_version` (SQLAlchemy's column name), not `SELECT version`.
   - Build first, then run — changes to `apps/batch/src/` require `docker compose build batch` first.

## Model Mixin Rules

ACME uses SQLAlchemy mixins for timestamp fields:
- **CreatedAtMixin**: Provides only `created_at` column (TIMESTAMP with timezone, server_default=func.now())
- **TimestampMixin**: Provides both `created_at` and `updated_at` columns
- **SoftDeleteMixin**: Adds `deleted_at` column for soft deletes

**Usage rules**:
1. Models that are **append-only** (never updated after creation) use `CreatedAtMixin`:
   - WorkIdentifier, WorkTitle, WorkRecording (identifiers/titles/recordings don't change)
   - ContractTerritory (territory assignments are immutable)
   - AuditLog entries (immutable by nature)

2. Models that support **updates** use `TimestampMixin`:
   - Work, Contract, Creator, Member, Publisher
   - WorksContractShare (share percentages can be adjusted)

3. Never mix both mixins on the same model

**Debugging model mismatches**:
- If you see `column work_identifiers_1.updated_at does not exist`:
  1. Check the model definition - it likely incorrectly uses `TimestampMixin`
  2. Change to `CreatedAtMixin`
  3. Rebuild and restart API container
  4. If table already has wrong column, you may need a migration to drop it

## Auth Protection Patterns

Endpoints that modify data or expose sensitive information **must** require authentication:

**Required dependency**:
```python
from app.auth.deps import require_active_user
```

**Endpoint pattern**:
```python
@router.get("/endpoint", response_model=SomeResponse)
async def endpoint(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_active_user),  # ← This line is required
) -> SomeResponse:
    # implementation
```

**Commonly missed endpoints** that need protection:
- List endpoints (GET /creators, /members, /publishers)
- Dashboard/summary endpoints
- Template/list endpoints
- Any endpoint returning PII or business data

**Testing auth protection**:
```bash
# Should return 401/403 without auth
curl -i http://localhost:13202/api/endpoint

# Should work with service key or proper auth
curl -i -H "X-API-Key: dev-service-key-change-in-prod" http://localhost:13202/api/endpoint
```

## Docker Service Debugging Workflow

When a service fails to start or connect:

1. **Check container status**:
   ```bash
   docker compose ps SERVICE_NAME
   ```

2. **View logs**:
   ```bash
   docker compose logs SERVICE_NAME --tail 50
   ```

3. **Test connectivity**:
   ```bash
   # From host to service
   curl http://localhost:EXPOSED_PORT/endpoint
   
   # From another container (if debug image available)
   docker compose run --rm SERVICE_NAME curl http://dependent_service:internal_port/endpoint
   ```

4. **Check environment variables**:
   ```bash
   docker compose config | grep -A5 -B5 SERVICE_NAME
   ```

5. **Verify depends_on conditions**:
   Ensure PostgreSQL/Redis show `healthy` status before dependent services start

## Migration Safety

When changing model definitions:
1. Never change column types without a migration
2. Adding columns: Make them nullable first, then backfill, then add NOT NULL
3. Removing columns: Remove API usage first, then add migration to drop column
4. Always test migrations against a copy of production data
5. Use `alembic revision --autogenerate` to detect changes, but always review generated SQL

## Verification Checklist for New Features

Before considering a feature complete:
- [ ] Code builds without warnings
- [ ] Docker image builds successfully
- [ ] Service starts and health checks pass
- [ ] API endpoints return expected status codes (200/401/404/422/500)
- [ ] Auth-protected endpoints require authentication
- [ ] Error handling covers edge cases (empty results, malformed input)
- [ ] Logs show appropriate startup/shutdown sequences
- [ ] No permission issues with generated files (fix 600 permissions if needed)