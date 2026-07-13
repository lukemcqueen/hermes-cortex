# gbrain Postgres Migration — PGLite → Postgres + pgvector

## Why

**PGLite (embedded WASM) is unreliable under Bun.** The WASM runtime consistently fails to initialize on several Linux configurations with `Aborted() — Build with -sASSERTIONS for more info.` This is a known PGLite + Bun incompatibility (the error message misleadingly references "the macOS 26.3 WASM bug," but it occurs on Linux too).

**Switching to Postgres + pgvector solves this permanently** — no WASM, no embedded runtime, just a standard Postgres connection.

## Architecture

```
┌──────────────┐     ┌─────────────────┐     ┌──────────────────┐
│  gbrain CLI  │────→│   gbrain sync    │────→│  Postgres (pgvec) │
│  (bun run)   │     │  daemon (systemd)│     │  Docker container│
└──────────────┘     └─────────────────┘     │  :15432 → :5432  │
                                             └──────────────────┘
                                                    │
                                            ┌───────┴───────┐
                                            │   pgvector    │
                                            │  extension   │
                                            │ (vector cols) │
                                            └───────────────┘
```

## Setup

### 1. Add to docker-compose

Add this service to your existing docker-compose (e.g. `~/langfuse/docker-compose.yml`):

```yaml
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
```

Add the volume:

```yaml
volumes:
  gbrain-postgres-data:
```

Add to `.env`:

```env
GBRAIN_PG_PASSWORD=<your-password-here>
```

### 2. Deploy

```bash
sg docker -c "docker compose -f ~/langfuse/docker-compose.yml up -d"
```

### 3. Enable pgvector

```bash
sg docker -c "docker exec gbrain-postgres psql -U gbrain -d gbrain -c 'CREATE EXTENSION vector;'"
```

### 4. Re-initialize gbrain

```bash
# Stop the sync daemon first
systemctl --user stop gbrain-sync.service

# Re-init with the database URL
DATABASE_URL="postgresql://gbrain:<password>@127.0.0.1:15432/gbrain"
gbrain init --url "$DATABASE_URL" --embedding-model ollama:nomic-embed-text:v1.5 --yes

# Add your brain source
gbrain sources add hermes-cortex --path ~/hermes-cortex
gbrain sources default hermes-cortex

# Restart the daemon
systemctl --user start gbrain-sync.service
```

### 5. Import existing data

```bash
# Stop daemon to free DB locks
systemctl --user stop gbrain-sync.service

# Force a fresh import (--force ignores old PGLite checkpoint)
cd ~/hermes-cortex && gbrain import . --yes --force

# Restart daemon
systemctl --user start gbrain-sync.service
```

> **Note:** The import runs embeddings via ollama (`nomic-embed-text:v1.5`). At ~1-3s per file, importing 800 files takes roughly 15-40 minutes. The sync daemon handles this incrementally.

## Can this serve as a RAG database?

**Yes.** This Postgres instance has pgvector installed, which provides:

| Feature | How |
|---------|-----|
| **Vector similarity search** | `SELECT * FROM chunks ORDER BY embedding <=> $query_vector LIMIT 10` |
| **Hybrid search** | gbrain combines pgvector (cosine distance) + Postgres tsvector (keyword) via RRF |
| **Indexes** | IVFFlat (default), HNSW also available for faster ANN search |
| **Any pgvector client** | LangChain, LlamaIndex, custom Python/Node — anything that speaks Postgres + pgvector |

Agents on the same machine can connect via `127.0.0.1:15432` with user `gbrain`. The database contains:
- `pages` — knowledge pages with slugs, content, metadata
- `content_chunks` — chunked page content with embedding vectors
- `links` — inter-page relationships
- `facts` — structured fact extraction

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `PGLite failed to initialize its WASM runtime` | Already switched to Postgres — this error shouldn't appear. If it does, check `~/.gbrain/config.json` has `"engine": "postgres"` |
| `Connection refused` on port 15432 | Container not started. Run `docker ps \| grep gbrain-postgres` and `docker compose up -d` |
| `No pgvector extension` | Run `docker exec gbrain-postgres psql -U gbrain -d gbrain -c 'CREATE EXTENSION vector;'` |
| `gbrain query` hangs | Sync daemon holds the DB lock. Stop it first: `systemctl --user stop gbrain-sync.service` |
| Migration v0.32.2 fails | Known gbrain issue — apply with `gbrain apply-migrations --yes --force` or skip with `--schema-pack gbrain-base-v2` |
| Docker permission denied | Use `sg docker -c "..."` or add user to docker group: `sudo usermod -aG docker $USER` |
