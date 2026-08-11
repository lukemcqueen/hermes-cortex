---
name: langfuse-observability
version: 1.0.0
description: Wire a self-hosted Langfuse instance to Hermes Agent — generate API keys, configure env vars, enable the bundled plugin, install SDK, and verify traces flow.
---

## When to use

When asked to set up Langfuse tracing for Hermes, check if Langfuse is working, or debug missing traces. Covers a self-hosted Langfuse behind Docker Compose (not Langfuse Cloud).

## Architecture

Langfuse runs as a 6-container Docker Compose stack:
- `langfuse-web` — web UI + API (port 3000)
- `langfuse-worker` — background processing
- `clickhouse` — trace storage
- `postgres` — metadata, users, API keys
- `redis` — queue / caching
- `minio` — local S3 for file uploads

Hermes sends traces via the bundled **observability/langfuse** plugin, which uses the `langfuse` Python SDK. The plugin is opt-in — it must be explicitly enabled, have credentials configured, and have the SDK installed.

## Step 1 — Check container health

```bash
docker ps --filter name=langfuse --format 'table {{.Names}}\t{{.Status}}'
```

All 6 should show `Up` (ClickHouse, Postgres, Redis, and MinIO should show `(healthy)`). If containers are missing, start them from `~/langfuse/docker-compose.yml`:

```bash
cd ~/langfuse && docker compose up -d
```

Verify the web API responds:
```bash
curl -s http://localhost:3000/api/public/health
# → {"status":"OK","version":"3.200.0"} (specific version depends on image tag)
```

## Step 2 — Generate an API key pair

Langfuse uses `pk-lf-...` (public) and `sk-lf-...` (secret) key prefixes. The full secret key is **never stored in plaintext** — only a bcrypt hash + SHA-256 fast hash. You must generate it and capture it before inserting.

### Check what keys exist

```sql
docker exec langfuse-postgres-1 psql -U postgres -d postgres \
  -c "SELECT public_key, note, created_at FROM api_keys ORDER BY created_at DESC;"
```

The provisioned key's `display_secret_key` column is truncated (e.g. `sk-lf-...e458`). **You cannot recover the full secret key.** Always generate a fresh one for the tracing integration.

### Generate and insert a new key

Use pgcrypto (bcrypt) via PostgreSQL — Python's `bcrypt` module may not be available:

```python
import hashlib, secrets, subprocess

public_key = "pk-lf-" + secrets.token_hex(16)
secret_key = "sk-lf-" + secrets.token_hex(16)
fast_hash = hashlib.sha256(secret_key.encode()).hexdigest()
key_id = secrets.token_hex(16)

sql = f"""INSERT INTO api_keys (id, project_id, public_key,
  hashed_secret_key, fast_hashed_secret_key, display_secret_key, note, created_at)
SELECT '{key_id}', 'default-project', '{public_key}',
  crypt('{secret_key}', gen_salt('bf')), '{fast_hash}',
  '{secret_key[:8]}...{secret_key[-4:]}',
  'Hermes Agent tracing key', CURRENT_TIMESTAMP;"""

# Enable pgcrypto first if needed
subprocess.run(["docker", "exec", "-i", "langfuse-postgres-1",
  "psql", "-U", "postgres", "-d", "postgres",
  "-c", "CREATE EXTENSION IF NOT EXISTS pgcrypto;"])

subprocess.run(["docker", "exec", "-i", "langfuse-postgres-1",
  "psql", "-U", "postgres", "-d", "postgres", "-c", sql])
```

**Capture and save both keys before proceeding.** The secret key cannot be retrieved after insertion.

### Verify the key authenticates

```python
import requests
auth = requests.auth.HTTPBasicAuth(public_key, secret_key)
r = requests.get("http://localhost:3000/api/public/projects", auth=auth, timeout=10)
# Should return 200
```

## Step 3 — Set Hermes env vars

Add to `~/.hermes/.env`:

```
HERMES_LANGFUSE_PUBLIC_KEY=pk-lf-<hex>
HERMES_LANGFUSE_SECRET_KEY=sk-lf-<hex>
HERMES_LANGFUSE_BASE_URL=http://localhost:3000
HERMES_LANGFUSE_ENV=local
HERMES_LANGFUSE_RELEASE=v1
HERMES_LANGFUSE_SAMPLE_RATE=1.0
```

The plugin reads `HERMES_LANGFUSE_*` vars first, then falls back to `LANGFUSE_*` (the standard Langfuse SDK env vars). The `HERMES_` prefix is preferred because the plugin validates the prefix format (`pk-lf-` / `sk-lf-`) before passing to the SDK.

## Step 4 — Install the langfuse Python SDK

```bash
# PEP 668 systems (Debian/Ubuntu 24.04+) need --break-system-packages
python3 -m pip install --break-system-packages langfuse
```

Verify:
```bash
python3 -c "import langfuse; print(langfuse.__version__)"
# → v4.12.0
```

The Hermes plugin does `from langfuse import Langfuse` at import time. Without the SDK, the entire plugin is inert (fail-open — no crash, just no traces).

## Step 5 — Enable the bundled plugin

```bash
hermes plugins enable observability/langfuse
# → ✓ Plugin observability/langfuse enabled. Takes effect on next session.
```

Verify:
```bash
hermes plugins list | grep langfuse
# → │ langfuse │ enabled │ 1.0.0 │ Optional Langfuse │ bundled │
```

## Step 6 — Test the Langfuse API directly

The Langfuse REST API at `/api/public/ingestion` accepts trace data directly. Use this for verification — the SDK's OTel-based export path has a known issue with self-hosted v3.1.0 (see Pitfalls below).

```python
import requests

auth = requests.auth.HTTPBasicAuth(
    'pk-lf-<hex>', 'sk-lf-<hex>'
)

payload = {
    "batch": [{
        "id": "verification-trace",
        "type": "trace-create",
        "body": {
            "name": "connection-test",
            "timestamp": "2026-06-28T00:00:00.000Z",
            "userId": "moses",
            "input": "test",
            "output": "success"
        }
    }]
}

r = requests.post(
    "http://localhost:3000/api/public/ingestion",
    auth=auth, json=payload, timeout=10
)
print(f"HTTP {r.status_code}: {r.json()}")
```

Read back the trace to confirm:

```python
import time; time.sleep(3)  # propagation delay
r = requests.get(
    "http://localhost:3000/api/public/traces?limit=5",
    auth=auth, timeout=10
)
print(r.json())
```

Expected output — the trace appears under `"data"` with `"name": "connection-test"`.

After starting a new Hermes session (via `/reset` in chat, or `hermes` from CLI), traces will appear at `http://localhost:3000` (or nginx port 13002 if exposed) — **if the OTLP issue below is resolved**. If traces are missing, debug the SDK export path first.

## Seed data (populating Langfuse with demo traces)

For immediate visual feedback in the dashboard, the REST API can seed traces without the SDK:

```bash
# Run the seed script (creates 4+ traces with generations, spans, scores)
~/hermes-cortex/scripts/seed-langfuse.py
```

Or manually via `scripts/install-api-key.sh` if the terminal truncates long keys.

For a full reference of REST API endpoints and payload shapes, see `references/seed-data-rest-api.md`.

## Key generation script

`scripts/install-api-key.sh` is a self-contained script that:
1. Generates a fresh `pk-lf-`/`sk-lf-` key pair in Python
2. Hashes the secret key with bcrypt (matching Langfuse's format)
3. Computes SHA-256 fast hash
4. Inserts into the `api_keys` table
5. Updates `~/.hermes/.env` with the new keys
6. Prints only the public key — the secret key flows directly into the DB and `.env`

Run it whenever the old key is lost or truncated. Safe to run multiple times (generates unique keys).

## Debugging zero traces

When Langfuse is healthy (all Docker containers up, health endpoint responds) but no traces appear in the UI:

**1. Check gateway process env vars vs .env timestamp**

The most common cause: the Hermes gateway process started **before** the `.env` file was updated with Langfuse credentials. The running process inherited the old environment and never picks up changes made to `.env` after launch.

```bash
# Check when the gateway process started
ps -p $(systemctl --user show hermes-gateway.service -p MainPID 2>/dev/null | cut -d= -f2) -o lstart=

# Check when .env was last modified
stat ~/.hermes/.env | grep Modify

# Check if the running process has Langfuse env vars
tr '\0' '\n' < /proc/$(systemctl --user show hermes-gateway.service -p MainPID 2>/dev/null | cut -d= -f2)/environ | grep -i langfuse
```

If the process started **before** `.env` was updated, the gateway has no Langfuse credentials. Fix: restart it.

**2. Restart the gateway (BLOCKED from inside — ask the user)**

The Hermes lifecycle guard (`cron/lifecycle_guard.py`, enforced in `tools/terminal_tool.py` and the cron tool) **hard-blocks any gateway restart/stop from inside the gateway process** — `systemctl restart hermes-gateway`, `hermes gateway restart`, `pkill` on the gateway, and any script that contains those patterns are all refused with `force=True` having no effect. Deliberately laundering the command (base64, remote-host indirection, variable indirection) to dodge the scan is a trust violation — don't.

The sanctioned path: **ask the user to run it from a shell outside the gateway**:

```bash
hermes gateway restart
# or, directly:
systemctl --user restart hermes-gateway.service
```

The session reconnects automatically after restart (~5s). Alternatively a `/reset` in chat creates a new session, but if the gateway process itself predates the `.env` change, new sessions still inherit the stale env — a real restart is required.

**3. Verify traces are flowing after restart**

```bash
PK="pk-lf-<your-public-key>"
SK="sk-lf-<your-secret-key>"
AUTH=$(echo -n "${PK}:${SK}" | base64 -w0)
curl -s -H "Authorization: Basic ${AUTH}" \
  "http://localhost:3000/api/public/traces?fromTimestamp=2026-07-10T00:00:00Z&limit=5" | \
  python3 -c "import json,sys; d=json.load(sys.stdin); print(f'{d[\"meta\"][\"totalItems\"]} traces')"
```

**4. Additional checks if still zero**

- Verify the plugin is enabled: `hermes plugins list | grep langfuse`
- Check the sample rate: `grep HERMES_LANGFUSE_SAMPLE_RATE ~/.hermes/.env` (should be `1.0` for 100%)
- Check Langfuse project exists with the right key: `curl -s -H "Authorization: Basic ${AUTH}" http://localhost:3000/api/public/projects`
- Directly POST a test trace and read it back (see Step 6 above) — if this works but Hermes traces still don't appear, the issue is in the plugin/SDK path

## Pitfalls

- **The scores API ignores `traceId` filters (langfuse issue #11121).** `GET /api/public/scores?traceId=X` returns ALL scores regardless of the parameter (confirmed on 3.206.0 through 3.225.1). Never build dedup logic on per-trace score queries. Fetch `name=overall` scores page-by-page and build the scored-trace set locally. See the `langfuse-self-hosted` skill's "Public scores API ignores traceId filters" section for the full pattern.
- **A green cron status is not evidence of scoring.** The LLM-judge scorer reported `last_status: ok` for 9 days while posting zero scores (the traceId-filter bug above made every trace look already-scored, and it auto-quieted). The scorer now exits 1 when it found candidates but judged none. Verify scores in ClickHouse (`SELECT count() FROM default.scores`), never the cron status.
- **qwen2.5-coder:3b is broken as a judge model** — emits whitespace on every prompt. Use `qwen2.5:3b` (set `JUDGE_MODEL=qwen2.5:3b` in `~/hermes-cortex/.env`).
- **Traces API requires `fromTimestamp` since 3.225.1** — omitting it returns HTTP 400 InvalidRequestError.
- **Doctor check:** `cortex-doctor`'s `check_langfuse_observability` surfaces version drift (running container vs compose pin) and scoring staleness (scores older than traces). Orchestrator-only, skips when Langfuse isn't installed.
- SDK v4.12.0 exports traces via OTel's OTLP over HTTP, NOT via the REST API. Langfuse server **must** expose `/api/public/otel/v1/traces` or the SDK silently drops every trace with `Failed to export span batch code: 404`.

**Langfuse v3.1.0 does NOT have this endpoint** — traces are silently dropped on any self-hosted v3.1.0 deployment. **Upgrading to v3.200.0+ resolves this completely.** After upgrade:

```python
# The SDK auto-discovers the OTLP endpoint from base_url — no manual OTEL env var needed
from langfuse import Langfuse
client = Langfuse(public_key=..., secret_key=..., base_url='http://localhost:3000')

trace_id = client.create_trace_id(seed='verify')
with client.start_as_current_observation(
    trace_context={'trace_id': trace_id}, name='test', as_type='chain',
    input='x', end_on_exit=True,
):
    with client.start_as_current_observation(
        trace_context={'trace_id': trace_id}, name='llm', as_type='generation',
        input='prompt', output='resp',
    ):
        pass
client.flush()
```

Wait 2-3 seconds for Postgres → ClickHouse propagation, then read back:

```python
import requests; import time; time.sleep(3)
auth = requests.auth.HTTPBasicAuth(public_key, secret_key)
r = requests.get(f'http://localhost:3000/api/public/observations?trace_id={trace_id}', auth=auth)
print(r.json()['data'])  # Should list 2 observations (chain + generation)
```

If traces are missing, check the version first: `curl -s http://localhost:3000/api/public/health`.

**Fix summary:** upgrade Langfuse to v3.200.0+ (`docker compose down && docker compose up -d` with updated image tags). The SDK then works with `base_url` alone — no `OTEL_EXPORTER_OTLP_ENDPOINT` manual config needed.

- **`/api/public/traces/{id}/observations` returns 404 on v3.207.0+.** Use `/api/public/observations?traceId=<id>` (camelCase) — verified live 2026-08-11. This broke the LLM-judge scorer (plugin traces carry content in observations, not at trace level); fixed in `ops/scripts/manage/agent-llm-judge-scorer.py`.
- **`/api/public/scores` IGNORES the `traceId` query filter on v3.207.0+.** It returns every score in the project regardless of the filter value (verified: a nonexistent trace id still returned all 4 project scores). `name=` filtering works; per-trace dedup must be done client-side (fetch all scores, filter by the item's `traceId` field). Same fix location.
- **The `langfuse` plugin must be explicitly enabled, the SDK installed, AND 7 `HERMES_LANGFUSE_*` vars present in `~/.hermes/.env`** — plus a gateway restart (from a shell outside the gateway). All five were missing on esther 2026-08-11: plugin `not enabled`, no SDK, no keys, zero `api_keys` rows in Postgres, zero rows in ClickHouse — while the health watchdog reported "ok" hourly because it only checks containers/web/merge failures, never trace flow. After wiring, verify the REAL path: a live session's trace appears in `default.traces` with `environment=local`.
- **The full secret key is gone once inserted.** Langfuse only stores a bcrypt hash + SHA-256 fast hash. The `display_secret_key` column is truncated (first 8 + last 4 chars). If you lose the secret key, delete the old API key and generate a new pair.
- **Plugin is session-gated.** Enabling the plugin or changing env vars has zero effect on a running session. The user must `/reset` or start a new `hermes` process.
- **Langfuse API calls must handle ConnectionResetError and retry.** Python's `urllib.request.urlopen()` raises `OSError` (not `HTTPError` or `URLError`) for TCP-level resets — common under Docker networking. Always catch `OSError` (covers `ConnectionResetError`, `TimeoutError`) in addition to `HTTPError` and `URLError`. Implement a 2-attempt retry with 2s backoff for transient failures. HTTP 4xx/5xx should NOT be retried — they indicate application errors:
  ```python
  def _lf_get(path, retries=2):
      for attempt in range(retries):
          try:
              with urllib.request.urlopen(req, timeout=10) as resp:
                  return json.loads(resp.read())
          except urllib.error.HTTPError:
              return None
          except (urllib.error.URLError, OSError) as e:
              if attempt < retries - 1: time.sleep(2)
      return None
  ```
  Apply the same pattern to `_lf_post()`. The `llm-judge-scorer.py` in Hermes Cortex implements this — search that file for the full reference pattern.
- **`check_health()` doesn't exist on Langfuse v4 SDK.** The `Langfuse()` constructor succeeds silently even with bad credentials — it queues traces and only fails on flush. Verify with an actual `trace()` call instead.
- **Two env var prefixes.** `HERMES_LANGFUSE_PUBLIC_KEY` is checked first, `LANGFUSE_PUBLIC_KEY` is the fallback. Set both if you want parity. The `HERMES_` prefix is validated for proper `pk-lf-` / `sk-lf-` format and rejects placeholders — but if you only set the standard `LANGFUSE_*` vars, the validation pass is skipped.
- **Key display truncation.** The terminal tool truncates long strings (70+ chars) for display with `...`. The full 64-hex-char `sk-lf-` key may not be readable from terminal output. Always use the all-in-one script (`scripts/install-api-key.sh`) that writes directly to `.env` without needing to display the key.
- **Duplicate keys accumulate.** Every key-generation run adds another row. `DELETE FROM api_keys WHERE note NOT LIKE 'Hermes Agent%'` to clean old provisioned keys, or delete by specific `id`.
- **The SDK accepts both `host=` and `base_url=`.** In Langfuse SDK v4, both parameters work but `base_url` has highest precedence and cannot be overridden by env vars. The Hermes plugin uses `base_url` internally. When testing directly, either works but `base_url` is preferred per the Langfuse docs (`Langfuse(public_key=..., secret_key=..., base_url=...)`). Using `host=` works but may be deprecated in future SDK versions.
- **Nginx reverse proxy.** Langfuse is typically exposed on port 13002 behind auth_basic. The `HERMES_LANGFUSE_BASE_URL` should point to the internal Docker address (`http://localhost:3000`), not the nginx proxy, to avoid auth headers conflicting.
- **Worker needs a restart after ClickHouse migration.** If Langfuse updates and changes the ClickHouse schema, the worker container may fail silently. Check `docker logs langfuse-langfuse-worker-1 --tail 20` if traces stop appearing.
- **Token analytics config.** Hermes has `show_token_analytics: false` in its config — this is a display toggle, not a tracing toggle. It does not affect Langfuse plugin behavior.
- **ClickHouse config XML files must be world-readable (`chmod 644`).** Docker mounts them with `:ro`, but ClickHouse runs as a non-root user inside the container. If the files are `600` (owner-only), ClickHouse crashes on startup with `Access to file denied: /etc/clickhouse-server/config.d/*.xml` and goes into a restart loop. Always `chmod 644 ~/langfuse/clickhouse-config.d/*.xml` before bringing up the stack for the first time.
- **ClickHouse 25.5 SIGSEGV bug with aggressive thread pool reduction.** Reducing more than 2 background pool settings simultaneously causes ClickHouse to crash with SIGSEGV (exit code 139) or exit code 36 during initialization. The safe config is in `hermes-cortex/deploy/clickhouse-config.d/02-low-memory.xml` — it only reduces the two most impactful pool settings (`background_pool_size=13`, `background_schedule_pool_size=16`) and leaves all others at defaults. The `max_thread_pool_size` / `thread_pool_queue_size` must stay at defaults (10000) — reducing them triggers the same crash when combined with reduced background pools.
- **Profile-level defaults go in `users.d/`, not `config.d/`.** The repo has a `03-profile-defaults.xml` file that sets `max_threads=2`, `max_memory_usage=500MB`, `max_block_size=4096`. This must be mounted at `/etc/clickhouse-server/users.d/03-profile-defaults.xml` (not `config.d/`) so ClickHouse applies it as a user profile default. Add the volume mount to the ClickHouse service in docker-compose.yml.
- **`docker compose restart` does NOT re-read env vars or config files.** After changing `docker-compose.yml`, the ClickHouse config XMLs, or the `.env` file, you must run `docker compose down && docker compose up -d`. A plain `docker compose restart` silently keeps the old configuration and env vars. This is stated in the docker-compose.yml header comment but easy to miss.
- **Langfuse image tags should be pinned to a specific semver, not floating.** The docker-compose.yml template may use floating tags (`:2`/`:3`). The hermes-cortex repo pins to `:3.200.0` which is tested with the current ClickHouse config and provides OTLP support. Don't float tags unless you verify the ClickHouse schema and OTLP endpoint match.
- **The health-check version changes with upgrades.** The old health response was `{"status":"OK","version":"2.95.11"}`. After updating from `:3.1.0` → `:3.200.0`, it becomes `{"status":"OK","version":"3.200.0"}`. Don't hardcode version checks — verify the OTLP endpoint works instead (`curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:3000/api/public/otel/v1/traces` should return 401, not 404).
- **ClickHouse resource limits in single-server setups.** The docker-compose.yml uses `cpus: 1.0`, `mem_limit: 2g`, `memswap_limit: 2g` for ClickHouse. These prevent CPU contention with agent services. If these are too low for your workload, ClickHouse may OOM and restart. The healthcheck picks it back up automatically (`5s interval, 5s timeout, 5 retries`). However, raising `mem_limit` too high on a shared server risks starving the Hermes agent itself — cap it based on total available RAM.

## References

- `references/deploy-guide.md` — condensed deployment reference: file structure,
  permission fix, restart procedure, image tags, quick-reference issue table