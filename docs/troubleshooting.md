# Troubleshooting Guide

> **Version 1.0.0** — Published 2026-06-05
> Common issues and fixes for Hermes Cortex installation and operation.

---

## 🐳 Docker / Langfuse Issues

### 1. Containers crash immediately after startup

**Symptom:** `docker ps` shows containers restarting repeatedly. `docker logs <name>` shows ZodError or missing env var errors.

**Fix:** Langfuse v3 requires several env vars that v2 didn't. Ensure your `deploy/docker-compose.langfuse.yml` includes all of these:

```yaml
# Required by v3 — ClickHouse
CLICKHOUSE_URL: http://clickhouse:8123
CLICKHOUSE_MIGRATION_URL: clickhouse://clickhouse:9000
CLICKHOUSE_CLUSTER_ENABLED: "false"
CLICKHOUSE_USER: default
CLICKHOUSE_PASSWORD: ""

# Required by v3 — Encryption
LANGFUSE_ENCRYPTION_KEY: <32-byte-hex>   # Generate: openssl rand -hex 32

# Required by v3 — S3 (point to local MinIO if not using external S3)
LANGFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID: ${LANGFUSE_MINIO_ACCESS_KEY}
LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY: ${LANGFUSE_MINIO_SECRET_KEY}
LANGFUSE_S3_EVENT_UPLOAD_BUCKET: langfuse
# ... (see deploy/docker-compose.langfuse.yml for full list)
```

### 2. "docker compose restart" doesn't pick up config changes

**Symptom:** You update `.env` or `docker-compose.yml`, run `docker compose restart`, but containers still fail with the same old errors.

**Root cause:** Docker Compose only evaluates env vars when containers are **created**, not when they're restarted. `up -d` is a no-op if the containers already exist.

**Fix — always recreate after config changes:**
```bash
docker compose -f deploy/docker-compose.langfuse.yml down
docker compose -f deploy/docker-compose.langfuse.yml up -d
```

### 3. Port 3000 already in use

**Symptom:** Docker fails with `port is already allocated` or `address already in use`.

**Fix — change the host port:**
```bash
# Run on a different port
LANGFUSE_PORT=3001 docker compose -f deploy/docker-compose.langfuse.yml up -d
```

Then update your nginx config and dashboard `LANGFUSE_HOST` to match.

### 4. ClickHouse won't start (insufficient ulimits)

**Symptom:** ClickHouse container exits with `max file descriptors` error.

**Fix:** Add ulimits to the ClickHouse service in docker-compose:
```yaml
clickhouse:
  ulimits:
    nofile:
      soft: 262144
      hard: 262144
```

(This is already included in the provided deploy/docker-compose.langfuse.yml.)

### 5. MinIO bucket doesn't exist

**Symptom:** Langfuse worker logs show S3 errors like `NoSuchBucket`.

**Fix:** The MinIO entrypoint must create the required buckets on startup:
```yaml
command: -c 'mkdir -p /data/langfuse /data/langfuse-media /data/langfuse-export && minio server /data --console-address ":9001"'
```

If containers were already running, exec in and create them manually:
```bash
docker exec -it langfuse-minio-1 sh
mkdir -p /data/langfuse /data/langfuse-media /data/langfuse-export
exit
docker restart langfuse-minio-1
```

### 5b. MinIO port conflict with ClickHouse (native setup)

**Symptom:** Langfuse logs show `Failed to upload events to blob storage` with `signature mismatch` or `specified bucket does not exist`.

**Root cause:** Both ClickHouse and MinIO default to port **9000**. ClickHouse uses it for native TCP; MinIO uses it for the S3 API. The AWS SDK resolves via IPv4 and hits ClickHouse instead of MinIO.

**Fix — move MinIO to a different port:**
```bash
kill $(pgrep -f "minio server") 2>/dev/null
# Edit ~/Library/LaunchAgents/com.hermes.minio.plist
# Change --address :9000 → --address :9002
sed -i '' 's|:9000|:9002|' ~/Library/LaunchAgents/com.hermes.minio.plist
launchctl bootstrap gui/501 ~/Library/LaunchAgents/com.hermes.minio.plist
sed -i '' 's|LANGFUSE_S3_EVENT_UPLOAD_ENDPOINT=.*|LANGFUSE_S3_EVENT_UPLOAD_ENDPOINT=http://localhost:9002|' ~/langfuse/.env
sed -i '' 's|MINIO_ENDPOINT=.*|MINIO_ENDPOINT=localhost:9002|' ~/langfuse/.env
launchctl kickstart -k gui/501/com.hermes.langfuse-web
```

### 5c. S3 signature mismatch (native setup)

**Symptom:** Langfuse logs show `The request signature we calculated does not match the signature you provided`.

**Root cause:** The `LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY` in `.env` doesn't match the actual MinIO root password.

**Fix — sync credentials:**
```bash
PASS=$(plutil -p ~/Library/LaunchAgents/com.hermes.minio.plist | grep MINIO_ROOT_PASSWORD | cut -d'"' -f4 -s)
sed -i '' "s|LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY=***|LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY=$PASS|" ~/langfuse/.env
sed -i '' "s|LANGFUSE_MINIO_SECRET_KEY=***|LANGFUSE_MINIO_SECRET_KEY=$PASS|" ~/langfuse/.env
launchctl kickstart -k gui/501/com.hermes.langfuse-web
```

### 5d. Missing FORCE_PATH_STYLE for MinIO

**Symptom:** Langfuse logs show `The specified bucket does not exist` even though the bucket exists in MinIO.

**Root cause:** AWS SDK defaults to virtual-hosted style URLs, which don't work with localhost MinIO.

**Fix — add to Langfuse .env:**
```
LANGFUSE_S3_EVENT_UPLOAD_FORCE_PATH_STYLE=true
```

---

## 🖥️ Dashboard Issues

### 6. "No module named 'flask'"

**Symptom:** Running `python3 server.py` fails with `ModuleNotFoundError: No module named 'flask'`.

**Fix — create a virtual environment:**
```bash
python3 -m venv ~/.hermes/dashboard/.venv
source ~/.hermes/dashboard/.venv/bin/activate
pip install flask
# Run the dashboard from within the venv:
python3 ~/.hermes/dashboard/server.py
```

Or use the system Python with pip install:
```bash
pip3 install flask
```

### 7. Dashboard links go to wrong URL

**Symptom:** Clicking "Langfuse ↗" or "View All →" on the dashboard opens a broken link.

**Fix:** Edit `src/dashboard/static/index.html` and update the `LANGFUSE_HOST` and `LANGFUSE_EXTERNAL` constants at the top of the `<script>` section:

```javascript
const LANGFUSE_HOST = 'http://localhost:3000';      // Your internal Langfuse URL
const LANGFUSE_EXTERNAL = 'http://localhost:13002';  // Your external/proxy URL
```

---

## 🔧 Installation Issues

### 8. "brew: command not found"

**Symptom:** Install script fails at Homebrew step.

**Fix:** Install Homebrew first:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### 9. "gbrain: command not found"

**Symptom:** After install, `gbrain` isn't found.

**Fix:** Add Bun's bin directory to your PATH:
```bash
export PATH="$HOME/.bun/bin:$PATH"
```

Add it permanently to your shell profile:
```bash
echo 'export PATH="$HOME/.bun/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### 10. "Permission denied" running install.sh

**Fix:**
```bash
chmod +x ${CORTEX_REPO:-$HOME/hermes-cortex}/install.sh
bash ${CORTEX_REPO:-$HOME/hermes-cortex}/install.sh   # Run with bash, not ./
```

### 11. Ollama blocked by macOS Gatekeeper

**Symptom:** Ollama installs but won't start on macOS.

**Fix:**
1. Go to **System Settings → Privacy & Security**
2. Scroll down to the "Security" section
3. Click "Allow" next to Ollama
4. Or run: `spctl --master-disable` (temporarily disable Gatekeeper)

### 12. Install script runs but nothing seems to happen

**Symptom:** The install script completes quickly but services aren't running.

**Fix:** The installer is idempotent — it skips already-installed steps. Check what's actually installed:
```bash
# Check brew packages
brew list | grep -E "ollama|nginx"

# Check services
brew services list

# Check Docker
docker ps

# Check gbrain
ls ~/.gbrain/
```

---

## 🔐 nginx / TLS Issues

### 13. Self-signed certificate warnings

**Symptom:** Browser shows "Your connection is not private" warning.

**Fix:** This is expected for self-signed certs. Click "Advanced" → "Proceed" to continue. For production, use Let's Encrypt:
```bash
brew install certbot
sudo certbot certonly --nginx -d your-domain.com
```

### 14. "dh key too small" SSL error

**Symptom:** nginx fails to start with SSL errors about DH key size.

**Fix:** Add or update the SSL config in nginx:
```nginx
ssl_protocols TLSv1.2 TLSv1.3;
ssl_ciphers HIGH:!aNULL:!MD5;
```

### 15. nginx auth popup keeps appearing

**Symptom:** You enter the username/password but the login prompt keeps coming back.

**Fix:** The `.htpasswd` file may need to be regenerated:
```bash
htpasswd -c ${NGINX_HTPASSWD:-/usr/local/etc/nginx/.htpasswd} your-username
# Enter your password when prompted
nginx -s reload
```

---

## 🧠 Memory / Agent Issues

### 16. "Memory tool doesn't work in cron"

**Symptom:** Cron jobs error with `RuntimeError: [Errno 32] Broken pipe` when using the `memory` tool.

**Root cause:** The `memory` tool requires an interactive Hermes session. Cron jobs run without one.

**Fix:** Use file I/O instead. Read/write `~/.hermes/memories/MEMORY.md` directly:
```python
# Instead of memory(action="read")
with open(os.path.expanduser("~/.hermes/memories/MEMORY.md")) as f:
    content = f.read()
```

### 17. MEMORY.md keeps hitting the 2,200 char limit

**Symptom:** `memory(action="add")` fails with "would exceed the limit".

**Fix:** Use the pointer pattern — keep only compact pointers in MEMORY.md and store full detail in a brain directory:
```
docker: 3 GB VM, stable with 6 containers → /brain m docker
```
See `docs/agent-memory-pointer-pattern.md` for the full guide.

---

## 🐧 Linux-Specific Issues

The installer is optimized for macOS (uses launchd, Homebrew). On Linux:

- **launchd services are skipped** — use systemd instead
- **Homebrew is not available** — use your distro's package manager (apt, yum, etc.)
- **Ollama** — install manually from [ollama.ai](https://ollama.ai)
- **gbrain** — works the same (Bun runs on Linux)

---

### 18. Ollama listening on all network interfaces (0.0.0.0)

**Symptom:** Running `lsof -i -P | grep LISTEN` shows `ollama *:11434` — it's accessible from any device on your network.

**Root cause:** Ollama defaults to binding on all interfaces. This means anyone on your WiFi can run models on your machine without authentication.

**Fix:** The installer now fixes this automatically. To fix a running installation:

**macOS:**
```bash
# Stop Ollama
launchctl bootout gui/$(id -u)/com.ollama.serve 2>/dev/null

# Update the plist
sed -i '' 's|0.0.0.0|127.0.0.1|' ~/Library/LaunchAgents/com.ollama.serve.plist

# Start Ollama (now on localhost only)
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.ollama.serve.plist

# Verify
lsof -i -P | grep ollama | grep LISTEN
# Should show: ollama ... localhost:11434 (LISTEN)
```

**Linux (systemd):**
```bash
sudo systemctl stop ollama
sudo sed -i 's|0.0.0.0|127.0.0.1|' /etc/systemd/system/ollama.service
sudo systemctl daemon-reload && sudo systemctl start ollama
```

**Verify:** Run `lsof -i -P | grep ollama` — it should show `localhost:11434`, not `*:11434`.

**Prevention:** The installer now hardens this automatically. Re-run `install.sh` or see the [Security Guide](SECURITY.md) for more details.

---

### 19. Can't log in — no admin user created on first startup

**Symptom:** You navigate to `localhost:3000` (or your nginx URL) and see the login page, but there's no "Sign Up" / "Create Account" link, and no admin user was created.

**Root cause:** Langfuse v3 can auto-create the first admin account at startup if you provide `LANGFUSE_INIT_USER_EMAIL`, `LANGFUSE_INIT_USER_NAME`, and `LANGFUSE_INIT_USER_PASSWORD` in your `.env` file. If these are missing, the web container starts but no admin user is provisioned.

**Fix:** Add these to your `.env` before the **first** startup (they only apply on initial deploy):

```bash
# ~/langfuse/.env  (or wherever your docker-compose reads env vars)
LANGFUSE_INIT_USER_EMAIL=admin@langfuse.local
LANGFUSE_INIT_USER_NAME=admin
LANGFUSE_INIT_USER_PASSWORD=<choose a strong password>
```

Then recreate containers:
```bash
docker compose down
docker compose up -d
```

If containers were already started without these vars, the init routine has already run and won't re-run — you'll need to either:
- **Navigate to the login page** and use the "Sign up" link if available (the default Langfuse login page includes one), or
- **Manually create a user** in the Postgres database, or
- **Reset** by wiping the Postgres volume (`docker compose down -v` — ⚠️ destroys all data)

If no `LANGFUSE_INIT_USER_*` vars are set, the login page's "Sign up" link should still be visible. Use it to register the first admin account normally.

---

### 20. Worker logs show "Queue job errored: socketTimeout" every 30s

**Symptom:** `docker logs langfuse-langfuse-worker-1` shows ~2 errors per minute:
```
Queue job X errored: socketTimeout: 30000
```
Usually for queues like `trace-delete`, `evaluation-execution`, `dataset-delete`.

**Root cause:** Langfuse configures a 30-second ioredis socket timeout. When no LLM traces are flowing, the worker's Bull queues have nothing to do. Every 30s the idle Redis connection times out, Bull logs an error, then reconnects automatically. The worker process stays alive and healthy.

**Assessment:** This is **normal idle behavior**. The errors stop once LLM trace data flows. No action needed.

---

## 📋 Quick Reference: Common Commands

```bash
# Langfuse management
docker compose -f deploy/docker-compose.langfuse.yml logs -f langfuse-web
docker compose -f deploy/docker-compose.langfuse.yml logs -f langfuse-worker
docker compose -f deploy/docker-compose.langfuse.yml down && docker compose -f deploy/docker-compose.langfuse.yml up -d

# Dashboard
cd ~/.hermes/dashboard && source .venv/bin/activate && python3 server.py

# nginx
nginx -t              # Test config
nginx -s reload       # Reload config
nginx -s stop         # Stop

# gbrain
gbrain doctor --fast  # Health check
gbrain sync --all     # Resync all sources
gbrain dream          # Knowledge consolidation

# Cron jobs
hermes cron list      # List all cron jobs
hermes cron run <id>  # Test a job immediately
```

---

## 📊 Langfuse Data Issues

### 21. Dashboard shows "Unexpected Error"

**Symptom:** Dashboard loads but shows errors instead of traces.

**Root cause:** Langfuse v3.178+ requires `fromTimestamp` on trace API queries. The dashboard's `_lf()` function must auto-append it.

**Fix — ensure `_lf()` in `~/.hermes/dashboard/server.py` appends `fromTimestamp={iso_7days_ago}` when missing from the path. Then restart: `launchctl kickstart gui/$(id -u)/com.hermes.cortex-dashboard`

**Alternative:** Add `LANGFUSE_API_TRACES_REJECT_NO_DATE_RANGE=false` to `~/langfuse/.env` and recreate Docker containers (less secure).

---

### 22. Dashboard shows no traces or wrong data

**Symptom:** Dashboard loads but shows "0 traces" or stale data.

**Check in order:**
1. **Wrong port** — Dashboard defaults to `localhost:3000`. Verify Langfuse port: `docker ps --format '{{.Names}} {{.Ports}}' | grep langfuse-web`
2. **Invalid API keys** — Dashboard reads `LANGFUSE_INIT_PROJECT_PUBLIC_KEY` / `HERMES_LANGFUSE_PUBLIC_KEY` from `~/langfuse/.env` or `~/.hermes/.env`
3. **Cache stale** — Dashboard caches for 60 seconds. Wait or restart.

**Verify:**
```bash
curl -s http://localhost:{PORT}/api/public/health
curl -u "pk:sk" http://localhost:{PORT}/api/public/traces?limit=1
```

Then set `LANGFUSE_HOST=http://localhost:{PORT}` and restart dashboard.

---

### 23. Langfuse costs show $0.00

**Symptom:** Traces appear but costs are always $0.00.

**Three causes:**

**A) Missing model pricing** — The model name reported by the provider isn't in Langfuse's `public.models` table. Langfuse ships with 160+ built-in model entries but custom/open-router models aren't included.

```sql
-- Check current models for your project (NULL project_id = global, available to all):
docker exec langfuse-postgres-1 psql -U postgres -d postgres \
  -c "SELECT model_name, input_price, output_price, unit FROM public.models WHERE project_id IS NULL ORDER BY model_name;"

-- Check project-specific models (like custom additions):
docker exec langfuse-postgres-1 psql -U postgres -d postgres \
  -c "SELECT model_name, input_price, output_price FROM public.models WHERE project_id IS NOT NULL ORDER BY model_name;"

-- Insert a global model pricing entry (NULL project_id — applies to all projects):
INSERT INTO public."models" (id, model_name, match_pattern, input_price, output_price, unit, tokenizer_config)
VALUES (
  gen_random_uuid()::text,
  'deepseek-v4-flash-free',
  '(?i)deepseek-v4-flash-free',
  0.00000014,   -- $0.14/M input tokens
  0.00000028,   -- $0.28/M output tokens
  'TOKENS',
  NULL
);

-- To insert project-specific (scoped to one project):
INSERT INTO public."models" (id, project_id, model_name, match_pattern, input_price, output_price, unit, tokenizer_config)
VALUES (
  gen_random_uuid()::text,
  (SELECT id FROM public.projects WHERE name = 'Hermes Agent' LIMIT 1),
  'deepseek-v4-flash-free',
  '(?i)deepseek-v4-flash-free',
  0.00000014,
  0.00000028,
  'TOKENS',
  NULL
);
```

**B) opencode-zen / opencode-go provider** — When using the `opencode-zen` or `opencode-go` provider in Hermes (i.e. `model.provider: opencode-go`, `base_url: https://opencode.ai/zen/go/v1`), the model name reported to Langfuse is whatever `model.default` is set to (e.g. `deepseek-v4-flash` or `deepseek-v4-flash-free`).

| Model name in Langfuse | Default pricing (DeepSeek direct) | Tokens/M |
|---|---|---|
| `deepseek-v4-flash` | $0.14 input / $0.28 output | Already in table (project: Hermes Agent) |
| `deepseek-v4-flash-free` | $0.14 input / $0.28 output | **Not in table — insert required** |

The `deepseek-v4-flash-free` model routes through the same DeepSeek API underneath (OpenCode adds a free daily quota on top). Use the standard DeepSeek pricing as the base rate. Adjust if your OpenCode plan has different rates.

Insert the missing entry:
```sql
INSERT INTO public."models" (id, model_name, match_pattern, input_price, output_price, unit)
VALUES (
  gen_random_uuid()::text,
  'deepseek-v4-flash-free',
  '(?i)deepseek-v4-flash-free',
  0.00000014,
  0.00000028,
  'TOKENS'
);
```

**C) Provider doesn't report tokens** — Check if `inputTokens` / `outputTokens` are null in Langfuse observations. If null, the provider's Langfuse instrumentation isn't capturing usage (provider-specific, can't fix in Langfuse/dashboard alone). The dashboard falls back to `state.db` token counts for calculated costs.

To verify tokens are flowing:
```sql
docker exec langfuse-postgres-1 psql -U postgres -d postgres \
  -c "SELECT id, model, input_tokens, output_tokens FROM observations WHERE input_tokens IS NULL LIMIT 5;"
```

---

## 🇱 Linux Mint / Ubuntu Migration

### 7. Ollama install fails — "sudo: a terminal is required"

**Symptom:** The Ollama install script (`curl ... | sh`) uses sudo non-interactively during `install.sh`.

**Fix:** Download the tarball directly and install locally before running install.sh:
```bash
curl -fsSL -o /tmp/ollama.tar.zst https://ollama.com/download/ollama-linux-amd64.tar.zst
tar -xf /tmp/ollama.tar.zst -C /tmp/ollama-extract
mkdir -p ~/.local/bin ~/.local/lib/ollama
cp /tmp/ollama-extract/bin/ollama ~/.local/bin/
cp -r /tmp/ollama-extract/lib/ollama/* ~/.local/lib/ollama/
```

### 8. Disk I/O errors on Docker pulls

**Symptom:** `failed commit on ref "layer-sha256:...": failed to perform sync: sync .../data: input/output error`

**Fix:** Bad disk sectors. Run `sudo tune2fs -c 1 /dev/mapper/vgmint-root && sudo reboot`, then `docker system prune -af` and pull images fresh.

### 9. gbrain WASM error

**Symptom:** `[unhandledRejection] WebAssembly.Module doesn't parse at byte N`

**Fix:** The PGLite WASM file landed on a bad block:
```bash
bun remove -g gbrain
rm -rf ~/.bun/install/global/node_modules/@electric-sql
bun install -g github:garrytan/gbrain
```

### 10. dpkg post-install failures

**Symptom:** `sync: error syncing '/boot/initrd.img-...': Input/output error`

**Fix:** Remove the bad initramfs and retry:
```bash
sudo mv /boot/initrd.img-$(uname -r) /tmp/initrd-backup
sudo dpkg --configure -a
```

---

### 24. Docker build fails — "Alembic migration failed"

**Symptom:** `docker compose build` succeeds, but `./run up` reports "Alembic migration failed" and the API container exits immediately. Or `./run build` reports multiple heads.

**Root cause:** Multiple Alembic migration heads from parallel work creating migrations from the same parent without merging.

**Prevention (agents, follow this protocol):**

- **Before creating any migration**, run `./run check:alembic`. If >1 head, stop and merge first:
  ```bash
  cd apps/api && .venv/bin/alembic merge heads -m "merge_<descriptions>"
  ```

- **Always use `./run migration:new`** instead of bare `alembic revision`. It checks single head BEFORE and AFTER creation.

- **Docker build has two guards:** `./run build` pre-checks locally, the Dockerfile also checks at docker build time. Either will catch a fork before deploy.

**If you find a fork:**
```bash
cd apps/api && .venv/bin/alembic heads          # see the heads
.venv/bin/alembic merge heads -m "merge_<a>_<b>"  # create merge
./run build                                       # rebuild
```

**Diagnostics:** `./run check:alembic` (static, no DB needed), `./run check:migrations` (requires DB), `alembic history` (full lineage).

---

## Changelog

| Version | Date | Changes |
|---|---|---|
| 1.5.0 | 2026-06-22 | Added #24 (Alembic migration fork troubleshooting, prevention protocol, diagnostics) |
| 1.4.0 | 2026-06-10 | Rewrote #23 (Langfuse costs) — fixed schema from `langfuse.models` to `public.models`, corrected INSERT SQL for v3 schema, added opencode-zen/opencode-go provider subsection with deepseek-v4-flash-free pricing SQL |
| 1.2.0 | 2026-06-06 | Added #21 (Langfuse fromTimestamp), #22 (dashboard no-traces), #23 (costs $0.00), #24 (pf firewall), #25 (fail2ban), updated port ranges |
| 1.1.0 | 2026-06-06 | Added entry #18 (Ollama 0.0.0.0 fix), #19 (first-time admin access), #20 (Redis timeout) |
| 1.0.0 | 2026-06-05 | Initial release — 17 entries covering Docker, Dashboard, install, nginx, memory, and Linux |
