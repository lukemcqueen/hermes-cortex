# gbrain Postgres Migration — PGLite → Postgres + pgvector

> **Status:** Recommended — PGLite (embedded WASM) is deprecated for new installs.
> **Engine:** Postgres 17 with pgvector 0.8.0
> **Docker image:** `pgvector/pgvector:0.8.0-pg17`

---

## Why Migrate

| Factor | PGLite (WASM) | Postgres + pgvector |
|--------|--------------|---------------------|
| **Engine** | PostgreSQL compiled to WASM, runs inside Bun | Native PostgreSQL process, runs in Docker |
| **Reliability** | WASM runtime crashes under Bun (`Aborted()`) on many Linux configs | Native process — zero WASM dependency |
| **Concurrency** | **Single-connection** — only one process at a time | **Multi-connection** — sync daemon + CLI queries simultaneously |
| **Lock contention** | Every CLI command (`gbrain query`, `gbrain doctor`) hangs if daemon is running | CLI commands work without stopping the daemon |
| **Data persistence** | Writes lost if `postmaster.pid` goes stale (in-memory fallback) | ACID transactions on disk, standard Postgres recovery |
| **Disk I/O sensitivity** | WASM file (8.7MB) on a bad block = total failure | Standard Postgres resilience |
| **Backup** | File-copy of PGLite directory (unsafe if daemon is running) | `pg_dump` / `pg_basebackup` — standard tooling |
| **Observability** | Minimal | `pg_stat_activity`, `pg_stat_statements`, standard Postgres monitoring |
| **RAG access** | PGLite only, no external clients | Any pgvector client (LangChain, LlamaIndex, Python, Node) on `:15432` |
| **Port** | N/A (embedded) | `127.0.0.1:15432` |

---

## Architecture

```
┌──────────────────┐     ┌─────────────────┐     ┌──────────────────────┐
│  gbrain CLI      │────→│  gbrain sync     │────→│  Postgres 17         │
│  (bun, local)    │     │  daemon (systemd)│     │  + pgvector 0.8.0    │
└──────────────────┘     └─────────────────┘     │  Docker container    │
       │                                          │  :15432 → :5432      │
       │  (no lock contention)                    └──────────────────────┘
       ▼                                                    │
┌──────────────┐                                    ┌───────┴───────┐
│ gbrain query │                                    │   Tables      │
│   (works!)   │                                    │  • pages      │
└──────────────┘                                    │  • content_chunks  │
                                                    │  • links      │
                                       pgvector ───│  • facts      │
                                       tsvector ───│  (full-text)  │
                                                    └───────────────┘
```

**Key difference from PGLite:** With Postgres, you can query gbrain while the sync daemon is running. No more `systemctl --user stop gbrain-sync.service` before every `gbrain query`.

---

## Prerequisites

- Docker (with `sg docker` group access or `sudo`)
- gbrain ≥ 0.42.59.0 (earlier versions may lack full Postgres support)
- ollama 0.31.2+ with `nomic-embed-text:v1.5` pulled

---

## Migration Steps

### Step 1 — Add to docker-compose

Add the `gbrain-postgres` service to your existing compose file (`~/langfuse/docker-compose.yml`):

```yaml
services:
  # ... existing services (langfuse, clickhouse, postgres, redis, minio) ...

  gbrain-postgres:
    image: pgvector/pgvector:0.8.0-pg17
    restart: unless-stopped
    container_name: gbrain-postgres
    mem_limit: 512m
    memswap_limit: 512m
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U gbrain -d gbrain"]
      interval: 5s
      timeout: 5s
      retries: 5
      start_period: 15s
    ports:
      - "127.0.0.1:15432:5432"
    volumes:
      - gbrain-postgres-data:/var/lib/postgresql/data
    environment:
      POSTGRES_USER: gbrain
      POSTGRES_PASSWORD: ${GBRAIN_PG_PASSWORD}
      POSTGRES_DB: gbrain

volumes:
  gbrain-postgres-data:
```

### Step 2 — Add env var

Add to `~/langfuse/.env`:

```env
GBRAIN_PG_PASSWORD=<your-random-password>
```

### Step 3 — Deploy

```bash
sg docker -c "docker compose -f ~/langfuse/docker-compose.yml up -d"

# Wait for healthy, then enable pgvector
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -c 'CREATE EXTENSION vector;'"

# Verify
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -c 'SELECT extname, extversion FROM pg_extension;'"
# Expected:
#  extname | extversion
# ---------+------------
#  plpgsql | 1.0
#  vector  | 0.8.0
```

### Step 4 — Stop old daemon and backup PGLite data

```bash
systemctl --user stop gbrain-sync.service

# Backup PGLite brain (in case you need to roll back)
cp -r ~/.gbrain ~/.gbrain.pglite-backup.$(date +%s)

# Verify the old config
cat ~/.gbrain/config.json
# Should show "engine": "pglite"
```

### Step 5 — Re-initialize gbrain with Postgres

```bash
DATABASE_URL="postgresql://gbrain:<password-from-step-2>@127.0.0.1:15432/gbrain"
gbrain init --url "$DATABASE_URL" --embedding-model ollama:nomic-embed-text:v1.5 --yes
```

**What happens:**
1. gbrain connects to Postgres via the URL
2. Runs all schema migrations (v1 → v122+)
3. Saves config to `~/.gbrain/config.json` with `"engine": "postgres"`
4. The PGLite data in `~/.gbrain/brain.pglite/` is left intact but unused

**Verify the config:**

```json
{
  "engine": "postgres",
  "database_url": "postgresql://gbrain:***@127.0.0.1:15432/gbrain",
  "embedding_model": "ollama:nomic-embed-text:v1.5",
  "embedding_dimensions": 768
}
```

### Step 6 — Add your brain source

```bash
# Add the source directory
gbrain sources add hermes-cortex --path ~/hermes-cortex

# Make it the default (searched implicitly)
gbrain sources default hermes-cortex

# Verify
gbrain sources list
# Expected output shows hermes-cortex as active source
```

### Step 7 — Import existing content

```bash
# Import from your content directory
cd ~/hermes-cortex && gbrain import . --yes --force

# OR let the sync daemon handle it (slower but incremental)
systemctl --user start gbrain-sync.service
```

> **Embedding speed:** Each file takes ~1-3s to embed via ollama (`nomic-embed-text:v1.5`).
> For 800 files, expect 15-40 minutes. The sync daemon shows progress in journald:
> `journalctl --user -u gbrain-sync.service -f`

### Step 8 — Verify

```bash
# Check daemon is running
systemctl --user is-active gbrain-sync.service

# Check gbrain health
gbrain doctor --json --fast

# Query the brain
gbrain query "your test query"

# Check Postgres is receiving data
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -c 'SELECT count(*) FROM pages;'"
```

---

## Testing Queries Directly on Postgres

The gbrain Postgres doubles as a general-purpose RAG database. Any agent with a pgvector client can connect:

```bash
# Connect directly
sg docker -c "docker exec -it gbrain-postgres psql -U gbrain -d gbrain"

# Count pages
SELECT count(*) FROM pages;

# Vector similarity search (768-dim embeddings)
SELECT p.slug, p.title,
       1 - (c.embedding <=> '[0.01, 0.02, ... 768 floats ...]'::vector) AS similarity
FROM content_chunks c
JOIN pages p ON p.id = c.page_id
ORDER BY c.embedding <=> '[0.01, 0.02, ...]'::vector
LIMIT 10;

# Full-text search
SELECT slug, title, ts_rank(search_text, plainto_tsquery('english', 'your query')) AS rank
FROM pages
WHERE search_text @@ plainto_tsquery('english', 'your query')
ORDER BY rank DESC
LIMIT 10;
```

**Connection details for other agents:**

| Field | Value |
|-------|-------|
| Host | `127.0.0.1` |
| Port | `15432` |
| Database | `gbrain` |
| User | `gbrain` |
| Password | From `GBRAIN_PG_PASSWORD` in `.env` |
| Extension | `vector` (pgvector) |

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `PGLite failed to initialize its WASM runtime` | Still running old PGLite or config says `"engine": "pglite"` | Check `~/.gbrain/config.json` — should say `"engine": "postgres"`. Re-run `gbrain init --url ...` |
| `Connection refused` on port 15432 | Container not started | `sg docker -c "docker ps \| grep gbrain-postgres"` then `docker compose -f ~/langfuse/docker-compose.yml up -d` |
| `No pgvector extension` | Extension not created | `sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -c 'CREATE EXTENSION vector;'"` |
| `gbrain query` returns no results | Import hasn't finished yet | Check `journalctl --user -u gbrain-sync.service -f` for progress |
| `Permission denied` for Docker | User not in docker group | `sg docker -c "..."` or `sudo usermod -aG docker $USER` then re-login |
| `gbrain doctor` shows minions migration failed | Known gbrain issue (v0.32.2 facts migration) | `gbrain apply-migrations --yes --force` to skip the specific migration |
| Sync daemon says `git pull failed` | Rebasing/history rewrite | Normal after `git pull --rebase`. Run a full import with `gbrain import . --force` |
| High memory usage on gbrain-postgres | Shared_buffers default (128MB) | Tune via `docker exec gbrain-postgres psql -U gbrain -c 'ALTER SYSTEM SET shared_buffers = "256MB";'` then restart container |

---

## Rollback to PGLite

If you need to revert:

```bash
# Stop Postgres-backed daemon
systemctl --user stop gbrain-sync.service

# Restore PGLite config
cp ~/.gbrain/config.json ~/.gbrain/config.json.postgres-backup
# Edit ~/.gbrain/config.json to set "engine": "pglite" and remove "database_url"

# Restore PGLite brain from backup
rm -rf ~/.gbrain/brain.pglite
cp -r ~/.gbrain.pglite-backup.<date>/ ~/.gbrain/brain.pglite

# Restart daemon
systemctl --user start gbrain-sync.service
```

---

## Connecting to External RAG Pipelines

Any agent in the fleet can use this Postgres as a RAG database:

```python
import psycopg2
import numpy as np

conn = psycopg2.connect(
    host="127.0.0.1",
    port=15432,
    dbname="gbrain",
    user="gbrain",
    password="<password>"
)

# Search by vector similarity
def search(query_vector: list[float], limit: int = 5):
    vec = np.array(query_vector)
    with conn.cursor() as cur:
        cur.execute("""
            SELECT p.slug, p.title, c.content,
                   1 - (c.embedding <=> %s::vector) AS score
            FROM content_chunks c
            JOIN pages p ON p.id = c.page_id
            ORDER BY score DESC
            LIMIT %s
        """, (vec.tolist(), limit))
        return cur.fetchall()
```

---

## See Also

- [`docs/gbrain-pglite-recovery.md`](gbrain-pglite-recovery.md) — **DEPRECATED** (PGLite-specific recovery guide, kept for rollback reference)
- [`docs/architecture.md`](architecture.md) — System architecture overview
- [`docs/seeding-brain-content.md`](seeding-brain-content.md) — Seeding your brain with initial content
