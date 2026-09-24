# Hermes Cortex — Environment Variable Reference

All `CORTEX_*` environment variables used across the nginx deploy pipeline
and related scripts. New variables should be added here with all fields.

---

## Env File

The env file lives at `~/hermes-cortex/.env` (gitignored) — the single source of truth
for all Cortex environment variables. It's auto-sourced by deploy scripts and `cortex-update.sh`.
`~/.hermes-cortex/cortex-bus.conf` is a **symlink** to it (the failover watchdog updates
the URL keys in place). `~/.hermes/.env` is **Hermes-owned** — provider keys, Telegram,
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

### Agent-side metrics push (read by `agent-push-metrics.sh`, set in `~/.hermes-cortex/.env`)

| Variable | Default | Purpose |
|----------|---------|---------|
| `VICTORIA_METRICS_URL` | _(unset = push disabled)_ | Prometheus-compatible import endpoint on the sink host (the xx005 proxy). Unset ⇒ the cron exits 0 with "metrics push disabled (this is optional)". |
| `VICTORIA_METRICS_FALLBACK_URL` | _(unset)_ | Second sink tried after the primary exhausts its retries. Must point at the peer's **xx005** port (e.g. `14005` on a `14xxx` host) — pointing it at a grafana port (xx003) makes a working primary look broken. |
| `PUSH_METRICS_STATE_FILE` | `~/.hermes-cortex/state/push-metrics.state` | Outage bookkeeping (consecutive failures, last alert). |
| `PUSH_METRICS_ALERT_COOLDOWN_S` | `21600` (6h) | How long the client stays quiet after the first alert of an outage, so a root-blocked sink yields one alert per 6h instead of one error per 5m tick. |

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
