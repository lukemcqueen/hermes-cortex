# Troubleshooting Guide

> **Version 1.0.0** — Published 2026-06-05
> Common issues and fixes for Hermes Cortex installation and operation.

---

## ⚠️ TWO HARD RULES — Every Agent Must Follow

> **RULE 1: USE LOOP GOVERNANCE ALWAYS**
> Every code/config/cron change REQUIRES: `begin_change` → work → `cycle_query` → `feedback_accept/override` → `end_change`. No exceptions. If `end_change` rejects, confess and force-clear — never silently skip the loop. The MCP server blocks write tools without an active lock — this is enforced at the tool level, not optional.
>
> **RULE 2: SHARE IMPROVEMENTS TO THE PUBLIC REPO**
> Every improvement you make that benefits other agents MUST go into the `hermes-cortex` repo — template files, skills, scripts, docs, config patterns. Not just your local profile. The repo is how every agent benefits from each other's work. If you built something useful, upstream it.

---

## 🐳 Docker / Langfuse Issues

### 1. Containers crash immediately after startup

**Symptom:** `docker ps` shows containers restarting repeatedly. `docker logs <name>` shows ZodError or missing env var errors.

**Fix:** Langfuse v3 requires several env vars that v2 didn't. Ensure your `ops/install/deploy/docker-compose.langfuse.yml` includes all of these:

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
# ... (see ops/install/deploy/docker-compose.langfuse.yml for full list)
```

### 2. "docker compose restart" doesn't pick up config changes

**Symptom:** You update `.env` or `docker-compose.yml`, run `docker compose restart`, but containers still fail with the same old errors.

**Root cause:** Docker Compose only evaluates env vars when containers are **created**, not when they're restarted. `up -d` is a no-op if the containers already exist.

**Fix — always recreate after config changes:**
```bash
docker compose -f ops/install/deploy/docker-compose.langfuse.yml down
docker compose -f ops/install/deploy/docker-compose.langfuse.yml up -d
```

### 3. Port 3000 already in use

**Symptom:** Docker fails with `port is already allocated` or `address already in use`.

**Fix — change the host port:**
```bash
# Run on a different port
LANGFUSE_PORT=3001 docker compose -f ops/install/deploy/docker-compose.langfuse.yml up -d
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

(This is already included in the provided ops/install/deploy/docker-compose.langfuse.yml.)

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
python3 -m venv ~/.hermes-cortex/dashboard/.venv
source ~/.hermes-cortex/dashboard/.venv/bin/activate
pip install flask
# Run the dashboard from within the venv:
python3 ~/.hermes-cortex/dashboard/server.py
```

Or use the system Python with pip install:
```bash
pip3 install flask
```

### 7. Dashboard links go to wrong URL

**Symptom:** Clicking "Langfuse ↗" or "View All →" on the dashboard opens a broken link.

**Fix:** Edit `ops/services/dashboard/static/index.html` and update the `LANGFUSE_HOST` and `LANGFUSE_EXTERNAL` constants at the top of the `<script>` section:

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

### 13. TLS certificate warnings

**Symptom:** Browser shows "Your connection is not private" warning.

**Fix:** Ensure certificates are valid. All servers use Let's Encrypt certs provisioned by certbot:
```bash
brew install certbot
sudo certbot certonly --nginx -d your-domain.com
```
For Moses/Esther, certs are pulled from Joseph's server — do not generate local certs. Titus uses mkcert for local dev.

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
# Linux: /etc/nginx/.hermes-htpasswd
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

### 18. Memory got wiped after a cortex update / "Checksum: MEMORY.seed.md" FAIL

**Symptom (2026-08-05):** `MEMORY.md`/`USER.md` lost all custom notes after
every deploy (7 clobbers in one day). The doctor showed `❌ Checksum:
MEMORY.seed.md — MD5 mismatch — deployed copy differs from repo source` and
recommended "Run: cortex-update.sh to resync" — which was exactly the
destructive action.

**Root cause:** Memory files were registered as deploy targets in
`cortex-update.sh` (seed templates → deployed copy). The live file is
personalized, so its hash always differed from the blank template, and the
generic `needs_update()` hash path overwrote it on every run. The doctor's
checksum sweep then FAILed on the healthy personalized state (inverted
check).

**Resolution:** Memory is Hermes-owned — `~/.hermes/memories/MEMORY.md` is
read directly by Hermes and created on first memory write. Cortex no longer
seeds, registers, or checksums memory files at all (removed 2026-08-05):
- `cortex-update.sh` has no register entry for memory files — and now
  **fails CLOSED** on any register target under `/memories/` or `~/.hermes/`
  (physical guard in `_assert_register_dest_safe()`), so a re-add aborts the
  deploy with a clear error instead of silently overwriting user data.
- `install.sh` step 9 no longer seeds a cortex-side memory copy.
- The doctor never content-compares memory files.

**If your memory was wiped:** restore from
`~/.hermes-cortex/state/deploy-backups/MEMORY.md.<ts>.bak` (deploy backups
the file before overwriting). After the fix deploys, no further backups of
that path will be created because the file is no longer touched.

**Legacy leftover:** an inert copy may exist at
`~/.hermes-cortex/memories/MEMORY.md` from before the fix. Leave it in
place — it is not loaded by Hermes and deleting it risks destroying data on
a host where it was once live.

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

**Linux (systemd — user-level):**
```bash
# Ollama should run as a user-level service (not system-level).
# This ensures no port conflicts with other services.
systemctl --user stop ollama
sed -i 's|0.0.0.0|127.0.0.1|' ~/.config/systemd/user/ollama.service
systemctl --user daemon-reload && systemctl --user start ollama
```

> ⚠️ If you have a stale system-level ollama.service in `/etc/systemd/system/`, remove it:
> `sudo systemctl disable --now ollama && sudo rm /etc/systemd/system/ollama.service`
> See [`docs/linux-service-layer.md`](linux-service-layer.md) for details.

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

## 🔥 Thermal / CPU Throttling Issues

### 1. Ollama causes CPU throttling / system halting (MacBook Intel)

**Symptom:** System becomes unresponsive or freezes under load. CPU temperature hits 90°C+. `dmesg` shows `intel_powerclamp: Start idle injection`. Linux Pressure Stall Information (`/proc/pressure/cpu`) shows `some avg10 > 20%`.

**Root cause:** The default Ollama configuration uses **all available CPU threads** (8 on a quad-core with HT) and keeps the model loaded for **5 minutes** after each use (`OLLAMA_KEEP_ALIVE=5m`). On CPU-only machines (Intel MacBooks, older laptops), this saturates all cores continuously, causing thermal throttling.

**Fix — two environment variables:**

```bash
# Edit the Ollama service file
nano ~/.config/systemd/user/ollama.service

# Add these lines under [Service]:
# Environment=OLLAMA_NUM_THREADS=2
# Environment=OLLAMA_KEEP_ALIVE=0

# Then:
systemctl --user daemon-reload
systemctl --user restart ollama.service
```

| Variable | Value | Effect |
|----------|-------|--------|
| `OLLAMA_NUM_THREADS=2` | Limits to 2 CPU cores | **Massive heat reduction** — the real fix |
| `OLLAMA_KEEP_ALIVE=0` | Unloads model immediately after use | Prevents sustained load |

**Verify:**
```bash
# Check env vars are applied
cat /proc/$(pgrep -f "ollama serve")/environ 2>/dev/null | tr '\0' '\n' | grep OLLAMA

# Check temperature dropped
sensors | grep Package

# Check pressure stall info improved
cat /proc/pressure/cpu
```

**Expected results:**
- Temperature: 92°C → **50-60°C**
- PSI `some avg10`: 30%+ → **< 1%**
- Powerclamp stops: `dmesg | grep "Stop forced idle injection"`

**Important:** Do NOT reduce the model's context window (`num_ctx` / `PARAMETER num_ctx`) to fix heat. 65536 (64k) context runs at the same temperature as 4096 when threads are limited — the heat comes from CPU parallelism, not context size. The project requires 64k context for tool calls and conversation history. See `install-ollama.sh` header comments for the full diagnosis.

**On macOS (launchd):**
```bash
# Edit the plist to add EnvironmentVariables
launchctl unload ~/Library/LaunchAgents/ollama.plist
# Add OLLAMA_NUM_THREADS and OLLAMA_KEEP_ALIVE to the plist's EnvironmentVariables dict
launchctl load ~/Library/LaunchAgents/ollama.plist
```

**On fresh install:** `install-ollama.sh` now includes these env vars by default (macOS and Linux service writers). Run `bash ~/hermes-cortex/ops/scripts/install/install-ollama.sh` to regenerate the service file.

---

## 📋 Quick Reference: Common Commands

```bash
# Langfuse management
docker compose -f ops/install/deploy/docker-compose.langfuse.yml logs -f langfuse-web
docker compose -f ops/install/deploy/docker-compose.langfuse.yml logs -f langfuse-worker
docker compose -f ops/install/deploy/docker-compose.langfuse.yml down && docker compose -f ops/install/deploy/docker-compose.langfuse.yml up -d

# Dashboard
cd ~/.hermes-cortex/dashboard && source .venv/bin/activate && python3 server.py

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

**Fix — ensure `_lf()` in `~/.hermes-cortex/dashboard/server.py` appends `fromTimestamp={iso_7days_ago}` when missing from the path. Then restart: `launchctl kickstart gui/$(id -u)/com.hermes.cortex-dashboard`

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

### 9. gbrain PGLite/WASM error

**Symptom:** `[unhandledRejection] WebAssembly.Module doesn't parse at byte N`
or `PGLite failed to initialize its WASM runtime`

**Fix:** The PGLite WASM engine is unreliable under Bun. **Migrate to Postgres + pgvector** (see [`docs/gbrain-postgres-migration.md`](gbrain-postgres-migration.md)).

If you need a temporary quick-fix to reinstall the WASM runtime:
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

## 25. Loop Governance — MCP Server / Scoring Issues

### MCP server not blocking write tools

The `loop-gov-mcp.py` server blocks `write_file`, `patch`, `terminal`, `skill_manage`, and `cronjob` unless a governance lock is active. If write tools work without a lock:

```bash
# 1. Check MCP server is registered
hermes mcp list | grep loop-governance

# 2. If not registered, add it:
hermes mcp add loop-governance --command python3 --args ~/hermes-cortex/mcp-servers/loop-gov-mcp.py

# 3. Restart the Hermes session for the MCP server to load
#    → Exit and re-enter the chat session
```

### `end_change` rejected — "No scored cycle found"

This happens when you call `end_change()` but no cycle was logged with your task_id in the loop-governance DB.

```bash
# 1. Check recent cycles for your task
python3 -c "
import sqlite3, os
db = os.path.expanduser('~/.hermes-cortex/data/loop-governance.db')
c = sqlite3.connect(db)
r = c.execute('SELECT id, task_id, composite FROM loop_cycles ORDER BY id DESC LIMIT 10').fetchall()
c.close()
for row in r:
    print(f'#{row[0]} {row[1][:60]} (score={row[2]})')
"
# 2. If no cycle with your task_id exists, create one manually:
#    score-cycle --task <your-task-id> --cycle 1 --code "<description>" --pass-pct 1.0 --json
# 3. Then accept it:
#    loop-feedback accept <cycle_id> --note "..."
# 4. Then end_change() will succeed
```

### `begin_change` says lock active but you want to start fresh

A stale lock file can persist if a session was interrupted:

```bash
rm -f ~/.hermes-cortex/state/.governance-*
# Then call begin_change() again
```

### Pre-commit hook reports "No active governance session"

The pre-commit hook checks for the governance lock file as a secondary safety net. The MCP server already blocks writes without a lock, so this should not fire for MCP-connected agents.

If it fires during a direct `git commit` outside of an agent session:

```bash
# Create a governance lock first (the correct path — never --no-verify):
mcp_loop_governance_begin_change(task_id="direct-commit", description="...")
# Then commit, then:
mcp_loop_governance_end_change(task_id="direct-commit")
```

`git commit --no-verify` is a logged, audited bypass (`agent-no-verify-audit` cron) — never use it to ship a hook-rejected change.

### `score-cycle` not found

```bash
# Re-install loop-governance tools
bash ~/hermes-cortex/core/governance/setup.sh --symlinks-only
# Or re-run install.sh step 11:
bash ~/hermes-cortex/install.sh
```

### Template drift detected after cortex update

The `template-diff-check.py` script runs after every `cortex-update.sh` pull. It flags if your `~/.hermes/SOUL.md` is missing sections or has stale content.

```bash
# See what's different:
diff ~/.hermes/SOUL.md ~/hermes-cortex/docs/templates/SOUL.md
# Merge changes into your SOUL.md
# Re-run cortex-update to verify:
cortex-update --status
```

## 🍎 macOS-Specific Cortex Update Issues

Issues that appear when running `pull latest` + `cortex-update.sh` on a macOS host (all verified on macOS 14, arm64, 2026-07-31). These are distinct from the Linux service-layer differences — they break the update **script itself**.

### 20. `cortex-update.sh` aborts: `getent: command not found`

**Symptom:** The update exits early with `getent: command not found` (or silently fails under `set -euo pipefail`) on macOS.

**Root cause:** macOS has no `getent(1)`. `cortex-update.sh` (and `ops/scripts/install/os-config.sh`) resolve the real user's home with:

```bash
_home=$(getent passwd "$_user" 2>/dev/null | cut -d: -f6)
```

On macOS `getent` is not found → command substitution returns empty (or aborts the script under `pipefail`), leaving `CORTEX_HOME` / `_home` / `ORCH_HOME` / `_os_home` unset and any orch-detection logic dead.

**Fix:** guard the lookup and fall back to `$HOME`:

```bash
if command -v getent &>/dev/null; then
  _home=$(getent passwd "$_user" 2>/dev/null | cut -d: -f6)
fi
_home="${_home:-$HOME}"
```

**Status:** ✅ **Fixed in repo (2026-08-01)** — the `command -v getent` guard + `$HOME` fallback now ships in all 5 `cortex-update.sh` sites and `ops/scripts/install/os-config.sh`. Pull latest + run cortex-update to get it; no manual patch needed.

### 21. `sudo hermes-plugin-lock lock` hangs/fails on macOS

**Symptom:** During the "Locking enforcement files…" step the update aborts or hangs at `sudo hermes-plugin-lock lock`.

**Root cause:** On macOS there is no NOPASSWD sudoers rule; `sudo` prompts for a password, which fails in a non-interactive cron/agent context and aborts under `pipefail`. `chflags uchg` does **not** need root when the file is user-owned — the helper must run **without** sudo on Darwin.

**Fix:** on Darwin, invoke the deployed helper directly:

```bash
if [[ "$(uname -s)" == "Darwin" ]]; then
  bash "${CORTEX_DEPLOY_HOME}/scripts/hermes-plugin-lock" lock 2>&1 || warn "enforcement files NOT locked (macOS)"
else
  sudo hermes-plugin-lock lock 2>&1
fi
```

**Status:** ✅ **Fixed in repo (2026-08-01)** — the Darwin no-sudo branch is merged in the "Locking enforcement files…" step, and also applied to the sibling "Re-lock hook scripts after deploy" site (same flaw class).

### 22. `chflags: /usr/local/bin/hermes-plugin-lock: Permission denied` (FAILED line)

**Symptom:** The update prints:

```
chflags: /usr/local/bin/hermes-plugin-lock: Permission denied
FAILED: /usr/local/bin/hermes-plugin-lock
LOCKED: /Users/<user>/.hermes-cortex/scripts/hermes-plugin-lock
```

The doctor still passes this check (`Plugin lock helper ✅`) — it is cosmetic, not fatal.

**Root cause:** `deploy_system_scripts()` deployed the system copy to `/usr/local/bin/hermes-plugin-lock` with `sudo` earlier, so it is `root:homebrew`-owned. `chflags uchg` on a **root-owned** file requires root even on macOS. The user-owned home copy (`~/.hermes-cortex/scripts/hermes-plugin-lock`) locks fine — that is the copy the enforcer uses.

**Fix (optional):** make the system copy user-owned so `chflags` works:

```bash
sudo chown "$USER":staff /usr/local/bin/hermes-plugin-lock
~/hermes-cortex/ops/scripts/cortex-update.sh   # direct path — re-locks cleanly
```

Or accept the `FAILED:` line; the home copy is the protected one.

**Status:** ✅ **Now automatic (2026-08-01)** — `deploy_system_scripts()` chowns the Darwin system copy to the invoking user (`sudo chown "$(id -un)":staff`) on both the self-update and `sudo cp` paths. The manual chown below is no longer required on fresh deploys.

### 23. After cortex-update, `begin_change`/write tools block: lock was purged

**Symptom:** The update finishes, then your next `terminal`/`patch` call is refused with `GOVERNANCE LOCK REQUIRED`.

**Root cause:** `cortex-update.sh` runs `purge-stale-governance-locks.py` at the end, which removes **every** `.governance-*.json` lock — including your active session's. The DB cycle is the source of truth; the lock file is disposable.

**Fix:** re-acquire after every deploy:

```
mcp_loop_governance_begin_change(task_id="post-update", description="...")
```

Then score all PENDING cycles (`cycle_query` → `feedback_accept`) and `end_change` — the doctor reports `❌ PENDING cycles` until they are scored.

### 24. Doctor reports `❌ PENDING cycles` left by other sessions

**Symptom:** After an update, doctor fails on PENDING cycles even though you scored your own.

**Root cause:** Any prior session (including crons) that called `begin_change` but ended without `feedback_accept/override` leaves a PENDING cycle. They accumulate and the doctor counts them as a failure.

**Fix:** score them — for cycles whose work you can verify, `feedback_accept`; for stale/unknown ones, `feedback_override(correct_decision="MOVE_ON")` with a note.

> ✅ **Fixed (2026-08-01):** `_feedback_override` in `mcp-servers/loop-gov-mcp.py` now sets the `decision` column (`UPDATE … SET user_overrode=1, decision=?, outcome_note=?`), so PENDING cycles become `MOVE_ON` on override and the doctor clears. Workaround below kept for reference on older deployed copies:
> ```bash
> sqlite3 ~/.hermes-cortex/data/loop-governance.db \
>   "UPDATE loop_cycles SET decision='MOVE_ON' WHERE id=<id> AND user_overrode=1 AND decision='PENDING';"
> ```

### 25. Deploy ≠ load — enforcement chain needs a gateway restart to activate

**Symptom:** you ran `cortex-update.sh`, repo and deployed copies match
(`sha256sum` equal), yet the sanctioned
`bash ~/hermes-cortex/ops/scripts/cortex-update.sh --status` still returns
`GOVERNANCE LOCK REQUIRED` — the OLD behavior.

**Root cause:** `cortex-update.sh` copies the new enforcer to disk, but the
RUNNING gateway process loaded the OLD module at startup. The plugin manager
is a process-global singleton — `hermes plugins disable/enable` only writes
`config.yaml`, it does NOT hot-reload. **Deploy ≠ load.**

**Fix:** `hermes gateway restart` — agents cannot run it (lifecycle guard);
the host operator (Luke) must. Then re-verify: the sanctioned `--status`
command passes lock-free, and `... && echo hi` is still blocked. This is a
pending restart, not a code bug — do not loop re-running the deploy.

## 🧠 Scoring / Loop Governance Issues

### 19. Loop-gov MCP server fails: `ModuleNotFoundError: No module named 'hermes_models'`

**Symptom:** `hermes mcp test loop-governance` fails. The `mcp_loop_governance_*` tools (begin_change, cycle_query, feedback_accept, etc.) don't appear in the agent's tool list.

**Root cause:** The deployed `loop-gov-mcp.py` adds the wrong directory to `sys.path`. It looks for `hermes_models.py` in `~/.hermes-cortex/scripts/` but the file is deployed to `~/.hermes/scripts/hermes_models.py` by `install.sh`.

**Fix — update the import path resolver in both the deployed and source copies:**

```python
# In ~/hermes-cortex/mcp-servers/loop-gov-mcp.py
# AND deployed: ~/.hermes-cortex/scripts/loop-gov-mcp.py

# Ensure hermes_models.py is importable from any Hermes deployment
_HERMES_HOME = Path.home() / ".hermes"
_HERMES_SCRIPTS = _HERMES_HOME / "scripts"
if _HERMES_SCRIPTS.exists():
    sys.path.insert(0, str(_HERMES_SCRIPTS))

# Also check the repo-local scripts path (for dev/source runs)
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_SCRIPTS = _SCRIPT_DIR.parent / "scripts"
if _REPO_SCRIPTS.exists():
    sys.path.insert(0, str(_REPO_SCRIPTS))

from hermes_models import get_model
```

After fixing, verify:
```bash
hermes mcp test loop-governance
# Expected: "✓ Connected", "Tools discovered: 10"
```

### 20. Governance-enforcer plugin installed but not blocking writes

**Symptom:** Write tools (write_file, patch, terminal write commands) work even when no governance lock is active. The plugin files exist at `~/.hermes/plugins/governance-enforcer/` but have no effect.

**Root cause:** The plugin is symlinked in the plugins directory but **not registered** in `~/.hermes/config.yaml` under `plugins.enabled`. Hermes only loads plugins listed there.

**Fix:**
```bash
# Add the plugin to the enabled list
hermes config set plugins.enabled '["observability/langfuse", "governance-enforcer"]'

# The plugin also needs a session restart to take effect:
# On CLI: /reset
# On gateway: /restart
```

Verify:
```bash
hermes config show  # should show plugins.enabled including governance-enforcer
ls -la ~/.hermes/plugins/governance-enforcer/  # should show plugin.yaml, __init__.py
```

### 21. `governance-auditor` always reports `had_issues: true` (historical — old `score-auditor`)

**Symptom** (deprecated cron): The old `score-auditor` cron job never cleared its error state. Checking `~/.hermes/state/score-auditor.state` showed `"had_issues": true`.

**Root cause:** The `get_scored_tasks()` function in the old `score-auditor.py` searched for DB tables named `cycles` or `cycle_scores`, but the actual table created by `loop_db.py` is named `loop_cycles`. This caused `get_scored_tasks()` to return an empty set every time, making every modified file appear "unscored."

**Status:** `score-auditor` was renamed to `governance-auditor` and fully rewritten. The new implementation (`ops/scripts/manage/governance-auditor.py`) uses a file-system scan approach, not `get_scored_tasks()`, so this bug no longer applies.

### 22. Session cache / cache_search not working

**Symptom:** `cache_search()` returns no results or the tool is unavailable.

**Root cause:** The session-embeddings DB was never built or is stale. The MCP server needs it for embedding search but fails silently if the DB is missing.

**Fix — rebuild the session cache:**
```bash
PYTHONPATH=~/.hermes/scripts python3 ~/.hermes-cortex/tools/loop-governance/session_cache.py build
```

Requires:
- Ollama running with `nomic-embed-text:v1.5` pulled
- `~/.hermes/scripts/hermes_models.py` on PYTHONPATH

### 23. scoring-activity-watchdog fails: "DB not found"

**Symptom:**
```
scoring-activity-watchdog: DB not found at ~/.hermes-cortex/state/loop-governance.db
```

**Root cause:** The actual loop-governance DB lives at `~/.hermes-cortex/data/` but scripts referenced `~/.hermes-cortex/state/`. This affected 17 files across docs, core governance scripts, cron scripts, and the pre-commit hook.

**Fix applied 2026-07-13:** All references corrected from `state/` to `data/` in:
- `core/governance/score_cycle.py`, `loop_evaluator.py`, `loop_db.py`, `loop_feedback.py`, `loop_config.py`, `auto_apply.py`, `verify.sh`
- `ops/scripts/health/scoring-activity-watchdog.py`, `ops/scripts/manage/governance-auditor.py`
- `.hermes-cortex/hooks/pre-commit`
- `docs/pre-commit-scoring.md`, `docs/loop-governance-reference.md`, `docs/troubleshooting.md`
- `skills/devops/loop-governance/SKILL.md`

The MCP server (`loop-gov-mcp.py`) was also fixed to sync both slug-specific + generic lock files on `_write_lock` / `_release_lock`, preventing governance enforcer lock gaps when running from non-git cwds.

---

## Changelog

| Version | Date | Changes |
|---|---|---|
| 1.7.0 | 2026-07-13 | Added #23 (scoring-activity-watchdog DB path fix), corrected 17 stale `state/`→`data/` references across docs and core governance scripts, fixed MCP lock file sync to prevent enforcer gaps |
| 1.5.0 | 2026-06-22 | Added #24 (Alembic migration fork troubleshooting, prevention protocol, diagnostics) |
| 1.4.0 | 2026-06-10 | Rewrote #23 (Langfuse costs) — fixed schema from `langfuse.models` to `public.models`, corrected INSERT SQL for v3 schema, added opencode-zen/opencode-go provider subsection with deepseek-v4-flash-free pricing SQL |
| 1.2.0 | 2026-06-06 | Added #21 (Langfuse fromTimestamp), #22 (dashboard no-traces), #23 (costs $0.00), #24 (pf firewall), #25 (fail2ban), updated port ranges |
| 1.1.0 | 2026-06-06 | Added entry #18 (Ollama 0.0.0.0 fix), #19 (first-time admin access), #20 (Redis timeout) |
| 1.0.0 | 2026-06-05 | Initial release — 17 entries covering Docker, Dashboard, install, nginx, memory, and Linux |
