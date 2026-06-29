# Install.sh Update — Langfuse, Cortex Dashboard, nginx

**Commit:** 650fc94 (2026-06-04)
**Issue:** Public installer claimed to install Langfuse, Cortex Dashboard, and nginx but had zero code to actually install them. These were excised when Clawmetry was removed from public repo.

**Fix:** Added 3 new installation steps (now 13 total):

## Step 9 — Langfuse (Docker Compose)

```bash
LANGFUSE_DIR="${CORTEX_HOME}/langfuse"
LANGFUSE_COMPOSE="${LANGFUSE_DIR}/docker-compose.yml"

# Copy docker-compose.langfuse.yml from repo
# Auto-generate secrets in .env (openssl rand -hex)
# Start with: docker compose up -d
```

**Components:**
- `langfuse-worker` — Background job processor
- `langfuse-web` — Web UI (port 3000)
- `postgres:16-alpine` — Database
- `redis:7-alpine` — Cache/queue
- `minio/minio` — Object storage for traces

**Secrets auto-generated:**
- `LANGFUSE_SALT`
- `LANGFUSE_SECRET_KEY`
- `LANGFUSE_NEXTAUTH_SECRET`
- `LANGFUSE_REDIS_AUTH`
- `LANGFUSE_MINIO_ACCESS_KEY` / `MINIO_SECRET_KEY`
- `LANGFUSE_INIT_PROJECT_PUBLIC_KEY` / `SECRET_KEY`

**Note:** The original v2 compose (commit 650fc94) used port 3000, no ClickHouse, no S3 upload vars. **Upgraded to v3 in commit a51c3a0** — see `references/langfuse-v3-migration.md` for the full delta.

**Components (v2 original):**

## Step 10 — Cortex Dashboard (Flask)

```bash
DASHBOARD_DEST="${HERMES_HOME}/dashboard"

# Copy dashboard/ from repo (server.py, static/index.html)
# Install Flask if needed: pip3 install flask
# Create launchd plist: com.hermes.cortex-dashboard.plist
# Load service: launchctl load
```

**Features:**
- System health monitoring (Ollama, gbrain, Hermes gateway)
- Langfuse integration (displays traces, scores)
- Cron job status
- Memory sync freshness checks

**Access:** `http://localhost:8901` (or `:11003` via nginx)

## Step 11 — nginx (Reverse Proxy)

```bash
NGINX_CONF="/usr/local/etc/nginx/servers/hermes-services.conf"

# Install via Homebrew if missing
# Copy config from repo nginx/hermes-services.conf
# OR create local-only config (no SSL) if SSL certs missing
# Start: brew services start nginx
```

**Configuration modes:**

1. **With SSL certs** (from private repo):
   - Copies `nginx/hermes-services.conf` with TLS + basic auth
   - Requires certs at `/usr/local/etc/nginx/ssl/fleet-operator.com/`
   - External access: `https://your-domain.com:11002` (Langfuse), `:11003` (Dashboard)

2. **Local-only** (fallback):
   - Creates basic config without SSL
   - No authentication
   - Access: `http://localhost:11002`, `http://localhost:11003`

**Upstreams:**
- `langfuse_backend` → `127.0.0.1:3000`
- `cortex_dashboard_backend` → `127.0.0.1:8901`

## Summary Section Updates

Updated installer summary to reflect new components:

```
✅ System components installed
  • Ollama           — LLM server (embedding: nomic-embed-text)
  • Bun              — JS runtime
  • gbrain           — Knowledge brain (PGLite)
  • Langfuse         — LLM observability (Docker, port 3000)
  • Cortex Dashboard — Flask companion app (port 8901)
  • nginx            — Reverse proxy (ports 11002, 11003)
  • Brain sources    → ~/brain/{default,...}
  • gbrain plugin    → /brain slash command
  • heartbeat.py     → system health watchdog
  • memory-to-brain-sync.py → memory sync to gbrain
  Launchd services:
    com.ollama.serve
    com.gbrain.sync-watch
    com.hermes.cortex-dashboard
    homebrew.mxcl.nginx
```

## Files Changed

| File | Lines Changed |
|------|---------------|
| `install.sh` | +312, -16 (13 steps now) |
| `docker-compose.langfuse.yml` | +95 (new file) |

**Note:** Initial commit used `fleet-operator.com` as placeholder domain. This was later replaced with `example.com` via git history rewrite (see `references/public-repo-privacy.md`).

## Testing Performed

- Bash syntax validation: `bash -n install.sh` ✓
- Git commit: `650fc94` ✓
- Push to GitHub: success ✓
- GitHub UI shows commit: verified ✓

## Migration Notes

For existing installations:
```bash
cd ~/hermes-cortex
git pull
bash install.sh  # idempotent — only runs new steps
```

Langfuse secrets are auto-generated on first run only (subsequent runs skip).

## Domain Privacy Cleanup (Post-Install)

If you installed before commit 7b7a8f2 and used your personal domain:

```bash
# Check for personal domain in config
grep -rn "your-domain\.com" ~/langfuse/ ~/.hermes/dashboard/ /usr/local/etc/nginx/servers/

# Replace with example.com for public repo safety
# See references/public-repo-privacy.md for full workflow
```

**Recommended:** Use `example.com` in all public-facing configs. Put your real domain in private repo only.
