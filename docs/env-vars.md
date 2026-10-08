# Hermes Cortex — Environment Variable Reference

All `CORTEX_*` environment variables used across the nginx deploy pipeline
and related scripts. New variables should be added here with all fields.

---

## Env File

The env file lives at `~/hermes-cortex/.env` (gitignored) — the single source of truth
for all Cortex environment variables. It's auto-sourced by deploy scripts and `cortex-update.sh`.
Every reference now points here: the old `~/.hermes-cortex/cortex-bus.conf` name was
migrated into this one file (`consolidate-env.sh` performed the merge; the deploy dir
holds no `.env`). `~/.hermes/.env` is **Hermes-owned** — provider keys, Telegram,
browser/terminal settings — and is never merged here.

```bash
# Copy the template, then edit
cp ~/hermes-cortex/.env.example ~/hermes-cortex/.env
# Edit with your settings:
vim ~/hermes-cortex/.env
# Consolidate the bus conf into the single file (idempotent):
bash ~/.hermes-cortex/scripts/consolidate-env.sh
```

## Variable Reference

| Variable | Default | Scripts | Purpose |
|----------|---------|---------|---------|
| `CORTEX_REPO` | `$HOME/hermes-cortex` | `cortex-update.sh`, `hermes-services-apply.py` | Path to the hermec-cortex repo. Multiple scripts source templates and configs from here. |
|| `CORTEX_SKIP_NGINX` | _(unset)_ | `cortex-update.sh`, `hermes-services-apply.py` | When set to any value, skip nginx config deploy, test, and reload. ||
|| `CORTEX_FORCE_DEPLOY` | _(unset)_ | `cortex-update.sh`, `hermes-services-apply.py` | When set to `1`, re-resolve SSL certs and port prefix from env/auto-detect instead of preserving existing values from the live config. |
|| `CORTEX_NGINX_PORT_PREFIX` | `13` | `cortex-update.sh`, `hermes-services-apply.py` | Two-digit port prefix for nginx server blocks. Template ships as `13xxx`; set to `12` (Joseph), `14` (Esther), etc. |
|| `CORTEX_SSL_CERT_PATH` | *(auto-detect)* | `hermes-services-apply.py`, `cortex-update.sh` | Explicit SSL certificate path. Overrides all auto-detection. |
|| `CORTEX_SSL_CERT_KEY_PATH` | *(auto-detect)* | `hermes-services-apply.py`, `cortex-update.sh` | Explicit SSL certificate key path. Overrides all auto-detection. |
|| `CORTEX_SSL_DOMAIN` | *(auto-scan)* | `hermes-services-apply.py`, `cortex-update.sh` | Domain name for Let's Encrypt cert lookup at `/etc/letsencrypt/live/<domain>`. When unset, scans all directories under `/etc/letsencrypt/live/`. |
| `HERMES_SERVICES` | _(unset ⇒ auto)_ | `hermes-services-apply.py`, `install-nginx-full.sh` | Comma-separated nginx service opt-ins: `dashboard,langfuse,health,grafana,bus,metrics` (or `all` / `extra`). The extras bundle is grafana (xx003) + bus (xx004). **Unset is the default**: extras stay off, while the push-metrics sink (xx005, `metrics-sink.conf`) deploys automatically wherever a local VictoriaMetrics answers — that default exists because the push client is universal but the sink used to be opt-in and defaulted off. Set it explicitly to override; a list without `metrics` keeps xx005 off. |
| `CORTEX_VM_HEALTH_URL` | `http://127.0.0.1:8428/-/healthy` | `hermes-services-apply.py`, `install-nginx-full.sh` | Backend health probe behind the push-metrics auto-detect gate. Repoint it if VictoriaMetrics runs on a non-default address. |
| `CORTEX_VM_QUERY_URL` | _(derived)_ | `cortex-doctor` (Metrics arrival age) | Pin the sink the arrival check queries. Unset, it derives from this host's `VICTORIA_METRICS_URL`/`_FALLBACK_URL` in push order (local backend last), so it asks the sink that actually receives. |
| `CORTEX_METRICS_STALE_MINUTES` | `30` | `cortex-doctor` (Metrics arrival age) | Warn when an agent that has pushed before has not been seen at the sink for this long (6 missed 5m ticks). |
| `CORTEX_VM_FRESHNESS_METRIC` | `node_uptime_seconds` | `cortex-doctor` (Metrics arrival age) | Series used to measure arrival age per agent. Pick a metric every pushing agent reports. |

### Agent-side metrics push (read by `agent-push-metrics.sh`, set in `~/hermes-cortex/.env`)

| Variable | Default | Purpose |
|----------|---------|---------|
| `VICTORIA_METRICS_URL` | _(unset = push disabled)_ | Prometheus-compatible import endpoint on the sink host (the xx005 proxy). Unset ⇒ the cron exits 0 with "metrics push disabled (this is optional)". |
| `VICTORIA_METRICS_FALLBACK_URL` | _(unset)_ | Second sink tried after the primary exhausts its retries. Must point at the peer's **xx005** port (e.g. `14005` on a `14xxx` host) — pointing it at a grafana port (xx003) makes a working primary look broken. |
| `PUSH_METRICS_STATE_FILE` | `~/.hermes-cortex/state/push-metrics.state` | Outage bookkeeping (consecutive failures, last alert). |
| `PUSH_METRICS_ALERT_COOLDOWN_S` | `21600` (6h) | How long the client stays quiet after the first alert of an outage, so a root-blocked sink yields one alert per 6h instead of one error per 5m tick. |

### Identity, model & fleet variables (`~/hermes-cortex/.env`)

**NAMES ONLY — values live in the gitignored env file.** An agent needing a
value reads it from the env file, never from this doc or from memory. These
names are the contract — never invent a new name without checking here first
(Rule 11: never invent config or env names).

| Variable | Purpose |
|---|---|
| `AGENT_NAME` | Agent identity (esther/moses/titus/…) — identity is env-derived ONLY, never hostname/USER fallback |
| `CODING_MODEL` | Coding task model |
| `CREATIVE_MODEL` | Creative/content model |
| `JUDGE_MODEL` | Governance judge model |
| `ADVERSARIAL_TRIAGE_MODEL` | Faster "System One" model for the close-gate's finding triage. **Unset = triage DISABLED** — the gate then behaves exactly as it did before triage existed, with the reviewer's severities unchanged. It is **not** a chat-completions model: see `docs/runbooks/review-triage-jev.md` |
| `JUDGMENT_CONFIG_PATH` | Optional override for the judgment client's provider/routing config. Default: `judgment-providers.yaml` beside `judgment.py`. Set per host to route triage to your own judge |
| `TYPESAFE_API_KEY` | Credential for the Jev judge (`typesafe/jev-router`). **Name only — the value lives in the gitignored env file.** Without it the `review-triage` class cannot run and triage stays off (fail-safe) |
| `CORTEX_ENV_FILE` | Explicit path to the env file the **gate** reads for its own config (reviewer backend/model, triage switch, credentials). Unset ⇒ it resolves `$CORTEX_REPO/.env` (default `~/hermes-cortex/.env`), then the deploy root, and only **last** `~/.hermes/.env` |
| `CORTEX_REPO` | Cortex repo root, used to locate the canonical env when `CORTEX_ENV_FILE` is unset |
| `ADVERSARIAL_REVIEW_BACKEND` | Who reviews a complex change before it can close: `llm` (default; canonical fleet-wide) or `agent` (fallback-only — offline/test-execution needs). **All agents configure the same way**: `llm` + `ADVERSARIAL_REVIEWER_MODEL=deepseek/deepseek-v4-pro`. See `docs/runbooks/review-triage-jev.md` |
| `ADVERSARIAL_REVIEWER_MODEL` | _llm backend._ The reviewer model. Use a model DIFFERENT from the worker's — a model reviewing its own output is not a review |
| `ADVERSARIAL_REVIEW_LIGHT_MODEL` | _llm backend._ Model for the **light-but-complex** review tier (2026-10-06). The tier changes the **transport, not the model**: a change that crosses the complexity gate but is NOT an always-review surface and stays under the heavy bar (≥10 files or ≥200 added+removed lines) is reviewed over a fast chat-completions call instead of spawning a coding agent — and it uses `ADVERSARIAL_REVIEWER_MODEL` (the canonical `deepseek/deepseek-v4-pro`) like every other review. Set this ONLY to review the light tier with a different model on purpose; before 2026-10-08 it defaulted to `deepseek/deepseek-v4-flash-0731`, which nothing had chosen. Heavy changes (enforcement/governance files, or above the heavy bar) keep the deep backend. **Enforcement is unchanged** — every complex change still needs an independent CLEAN verdict before the lock releases. See `docs/runbooks/review-triage-jev.md` |
| `ADVERSARIAL_REVIEW_BASE_URL` | _llm backend._ Chat-completions base URL (default OpenRouter). Point it at a local/self-hosted endpoint to review without a remote provider |
| `ADVERSARIAL_REVIEW_API_KEY_ENV` | _llm backend._ NAME of the credential variable to read. When set it is honoured **strictly** — no silent fallback to another credential. Never the value |
| `ADVERSARIAL_REVIEW_AGENT_CMD` | _agent backend._ The coding-agent CLI invocation for reviews; the prompt is passed on **stdin**. Must put the agent in its read-only mode — a reviewer that can write can fix its own objections |
| `ADVERSARIAL_REVIEW_AGENT_NAME` | _agent backend._ The agent's identity, used to refuse **self-review** when it matches the change's git author |
| `ADVERSARIAL_REVIEW_AGENT_TIMEOUT` | _agent backend._ Seconds to wait for the reviewing agent (default 900). **Clamped to `REVIEWER_TIMEOUT_CEILING` (240s), like every reviewer budget** — a budget at or above the MCP client's 300s call window is an unobservable hang, not a longer wait. To wait longer, raise the client's own ceiling (`mcp_servers.<name>.timeout`) instead. See `docs/runbooks/review-triage-jev.md` |
| `EMBEDDING_MODEL` | Embedding model (local Ollama: `nomic-embed-text:v1.5`) |
| `LLM_CRON_MODEL` | Cron LLM model. Controls **installer pinning only** — an unpinned cron RUNS on the main model (`model.default`), not on this value. Provider-specific id form (`deepseek/deepseek-v4.1-flash` on openrouter) |
| `LLM_CRON_PROVIDER` | Cron LLM provider (`openrouter`), same scope as above. Never a free tier that can stop resolving — a dead free pin falls through to a PAID route while reporting `ok` |
| `HERMES_CRON_TIMEOUT` | Cron timeout budget |
| `HERMES_TIMEZONE` | Fleet timezone (Asia/Seoul, KST) |
| `IS_ORCHESTRATOR` | Orchestrator flag (host-derived) |
| `IS_SERVER` | Server-mode flag |
| `CORTEX_BASE` | Cortex base path |
| `CORTEX_DOMAIN` | Fleet public domain (values never in repo) |
| `CORTEX_BASIC_AUTH` | Basic-auth credential pair |
| `CORTEX_BUS_URL` | Bus primary endpoint (env-first — see ADR history) |
| `CORTEX_BUS_FALLBACK_URL` | Bus fallback endpoint |
| `CORTEX_BUS_TOKEN` | Bus bearer token |
| `CORTEX_BUS_PG_*` (HOST/PORT/DB/USER/PASS) | Bus Postgres connection |
| `CORTEX_INBOX_URL` | Agent inbox v2 API base |
| `CORTEX_NGINX_PORT_PREFIX` | Nginx port prefixing |

### Health-probe variables (`~/.hermes/.env` — the file the gateway/cron reads)

| Variable | Purpose |
|---|---|
| `ORCH_HEALTH_URLS` | Active orchestrator's health probe targets (failover watchdog) |
| `BACKUP_ORCH_HEALTH_URLS` | Standby orchestrator's health probe targets (failover watchdog) |

### Hermes agent variables (`~/.hermes/.env`)

Hermes-owned — never merged into the Cortex env.

| Variable | Purpose |
|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek API credential |
| `TELEGRAM_BOT_TOKEN` | Telegram bot credential |
| `TELEGRAM_ALLOWED_USERS` | Allowed Telegram user IDs |
| `TELEGRAM_HOME_CHANNEL` | Default delivery channel (Esther: Luke DM) |
| `TELEGRAM_API_BASE` | Telegram Bot API base URL for the messaging gateway (`msg-gateway.py`) |

### Rules

1. **Never hardcode a value that has an env var.** The bus URLs were
   over-scrubbed in the 2026-08-24 history rewrite because they were
   hardcoded in scripts — the fix moved them to env (commit `9a95ceb8`).
2. **Never invent a name** — survey this registry first.
3. **Auth-gated liveness** uses `CORTEX_BUS_URL` + token; `/health` alone
   is insufficient.

---

## SSL Cert Discovery & Preservation

By default, all three deploy scripts **preserve** the port prefix and SSL cert
paths from the existing deployed config. They only auto-discover new values if
the existing config has placeholders (`__SSL_CERT__`) or if `CORTEX_FORCE_DEPLOY=1`
is set (or `--force` passed to the Python script).

To force re-evaluation on the next deploy:

```bash
# Re-resolve SSL certs and port prefix from scratch (Python script, primary)
python3 ~/hermes-cortex/ops/install/deploy/nginx/hermes-services-apply.py --force

# Or with the legacy bash script (not recommended)
# CORTEX_FORCE_DEPLOY=1 sudo install-nginx-full.sh
```

### Discovery Order (when not preserved)

All three scripts follow the same priority:

1. **Explicit env var** — `CORTEX_SSL_CERT_PATH` and `CORTEX_SSL_CERT_KEY_PATH` both set. Paths are trusted directly (no user-level readability check — certs are often in root-protected `/etc/letsencrypt/`). `nginx -t` catches invalid paths at deploy time.
2. **Let's Encrypt by domain** — `CORTEX_SSL_DOMAIN` set → `/etc/letsencrypt/live/<domain>/fullchain.pem` + `privkey.pem`
3. **Let's Encrypt scan** — scan all directories in `/etc/letsencrypt/live/` for valid certs
4. **Self-signed** — `$HOME/certs/fullchain.pem` + `privkey.pem` (or `cert.pem` + `privkey.pem`)
5. **System fallback** — `/etc/ssl/certs/` and `/etc/ssl/private/`

If nothing is found, `__SSL_CERT__` and `__SSL_CERT_KEY__` placeholders are left
unchanged in the deployed config. nginx will fail to validate and reload until
valid cert paths are provided — this is intentional. SSL is mandatory, not opt-in.

---

## Deploy Script Comparison

||| Feature | `cortex-update.sh` | `install-nginx-full.sh` | `hermes-services-apply.py` |
||---------|-------------------|------------------------|---------------------------|
|| Language | Bash | Bash **(legacy, deprecated)** | **Python (primary — use this)** |
| Run by | `cortex-update.sh` (auto-update) | sudo / cron | Manual or script pipeline |
| OS-aware paths | ✓ (via `os-config.sh`) | ✓ (inline) | ✓ (inline) |
| `__NGINX_CONFIG_DIR__` | ✓ | ✓ | ✓ |
| `__NGINX_LOG_DIR__` | ✓ | ✓ | ✓ |
| `__HTPASSWD_FILE__` | ✓ | ✓ | ✓ |
| `__CORTEX_HOME__` | ✓ | ✗ | ✓ |
| `__SSL_CERT__` / `__SSL_CERT_KEY__` | ✓ | ✓ | ✓ |
| Port prefix translation | ✓ (sed) | ✗ **no** | ✓ (re) |
| Live port range preserve | ✓ | ✗ **no** | ✓ |
| `allow-ips-manual.conf` support | ✓ (via template) | ✓ (via template + strip logic) | ✓ (via template) |
| Deploys to correct path | ✓ | ✗ writes to `/etc/nginx/servers/` instead of `sites-available/` | ✓ |
| Dry-run mode | ✗ | ✗ | ✓ |
| nginx -t before reload | ✓ | ✓ | ✓ |
| `CORTEX_SKIP_NGINX` | ✓ | ✗ | ✓ |

---

## Script Usage

### cortex-update.sh (auto-deploy)

```bash
# Defaults — auto-detects everything
bash ~/hermes-cortex/ops/scripts/cortex-update.sh

# With custom SSL and port prefix
CORTEX_SSL_CERT_PATH=/etc/letsencrypt/live/mydomain.com/fullchain.pem \
CORTEX_SSL_CERT_KEY_PATH=/etc/letsencrypt/live/mydomain.com/privkey.pem \
CORTEX_NGINX_PORT_PREFIX=12 \
bash ~/hermes-cortex/ops/scripts/cortex-update.sh

# Skip nginx entirely (scripts-only update)
CORTEX_SKIP_NGINX=1 bash ~/hermes-cortex/ops/scripts/cortex-update.sh
```

> ⚠ **Legacy script:** `install-nginx-full.sh` is deprecated. Use `hermes-services-apply.py` above instead.
>
> ```bash
> sudo install-nginx-full.sh
> ```

### hermes-services-apply.py (Python deploy)

```bash
# Auto-detect
python3 ~/hermes-cortex/ops/install/deploy/nginx/hermes-services-apply.py

# Dry-run (no files changed)
python3 ~/hermes-cortex/ops/install/deploy/nginx/hermes-services-apply.py --dry-run

# Explicit domain
python3 ~/hermes-cortex/ops/install/deploy/nginx/hermes-services-apply.py --domain mydomain.com

# Validate only
python3 ~/hermes-cortex/ops/install/deploy/nginx/hermes-services-apply.py --validate
```

---

## Template Placeholders

These placeholders in `ops/install/deploy/nginx/hermes-services.conf` are substituted at
deploy time by all three scripts above:

| Placeholder | Substituted with | Example value |
|-------------|-----------------|---------------|
| `__NGINX_CONFIG_DIR__` | OS-aware nginx root directory | `/etc/nginx` |
| `__NGINX_LOG_DIR__` | OS-aware nginx log directory | `/opt/homebrew/var/log/nginx` |
| `__HTPASSWD_FILE__` | htpasswd file path | `/opt/homebrew/etc/nginx/.htpasswd` |
| `__CORTEX_HOME__` | User home directory | `/Users/luke` |
| `__SSL_CERT__` | SSL certificate file | `/etc/letsencrypt/live/example.com/fullchain.pem` |
| `__SSL_CERT_KEY__` | SSL certificate key | `/etc/letsencrypt/live/example.com/privkey.pem` |
