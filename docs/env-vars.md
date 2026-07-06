# Hermes Cortex — Environment Variable Reference

All `CORTEX_*` environment variables used across the nginx deploy pipeline
and related scripts. New variables should be added here with all fields.

---

## Env File Template

The env file lives at `deploy/hermes-services.env` (NOT in `deploy/nginx/`) to make
clear it is **sourced only** — never deployed to nginx. Only `*.conf` files from
`deploy/nginx/` get deployed to the nginx config directory.

```bash
# Copy the template to the deploy/ directory (one level above nginx/)
cp ~/hermes-cortex/deploy/hermes-services.env.example \
  ~/hermes-cortex/deploy/hermes-services.env
# Edit, then source:
set -a; source ~/hermes-cortex/deploy/hermes-services.env; set +a
sudo hermes-security-apply
```

## Variable Reference

| Variable | Default | Scripts | Purpose |
|----------|---------|---------|---------|
| `CORTEX_REPO` | `$HOME/hermes-cortex` | `cortex-update.sh`, `hermes-security-apply`, `hermes-services-apply.py` | Path to the hermec-cortex repo. Multiple scripts source templates and configs from here. |
| `CORTEX_SKIP_NGINX` | _(unset)_ | `cortex-update.sh`, `hermes-services-apply.py` | When set to any value, skip nginx config deploy, test, and reload. |
| `CORTEX_FORCE_DEPLOY` | _(unset)_ | `hermes-security-apply`, `cortex-update.sh`, `hermes-services-apply.py` | When set to `1`, re-resolve SSL certs and port prefix from env/auto-detect instead of preserving existing values from the live config. |
| `CORTEX_NGINX_PORT_PREFIX` | `13` | `cortex-update.sh`, `hermes-services-apply.py` | Two-digit port prefix for nginx server blocks. Template ships as `13xxx`; set to `12` (Joseph), `14` (Esther), etc. |
| `CORTEX_SSL_CERT_PATH` | *(auto-detect)* | `hermes-services-apply.py`, `hermes-security-apply`, `cortex-update.sh` | Explicit SSL certificate path. Overrides all auto-detection. |
| `CORTEX_SSL_CERT_KEY_PATH` | *(auto-detect)* | `hermes-services-apply.py`, `hermes-security-apply`, `cortex-update.sh` | Explicit SSL certificate key path. Overrides all auto-detection. |
| `CORTEX_SSL_DOMAIN` | *(auto-scan)* | `hermes-services-apply.py`, `hermes-security-apply`, `cortex-update.sh` | Domain name for Let's Encrypt cert lookup at `/etc/letsencrypt/live/<domain>/`. When unset, scans all directories under `/etc/letsencrypt/live/`. |

---

## SSL Cert Discovery & Preservation

By default, all three deploy scripts **preserve** the port prefix and SSL cert
paths from the existing deployed config. They only auto-discover new values if
the existing config has placeholders (`__SSL_CERT__`) or if `CORTEX_FORCE_DEPLOY=1`
is set (or `--force` passed to the Python script).

To force re-evaluation on the next deploy:

```bash
# Re-resolve SSL certs and port prefix from scratch
CORTEX_FORCE_DEPLOY=1 sudo hermes-security-apply

# Or with the Python script
python3 deploy/nginx/hermes-services-apply.py --force
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

| Feature | `cortex-update.sh` | `hermes-security-apply` | `hermes-services-apply.py` |
|---------|-------------------|------------------------|---------------------------|
| Language | Bash | Bash | Python |
| Run by | `cortex-update.sh` (auto-update) | sudo / cron | Manual or script pipeline |
| OS-aware paths | ✓ (via `os-config.sh`) | ✓ (inline) | ✓ (inline) |
| `__NGINX_CONFIG_DIR__` | ✓ | ✓ | ✓ |
| `__NGINX_LOG_DIR__` | ✓ | ✓ | ✓ |
| `__HTPASSWD_FILE__` | ✓ | ✓ | ✓ |
| `__CORTEX_HOME__` | ✓ | ✗ | ✓ |
| `__SSL_CERT__` / `__SSL_CERT_KEY__` | ✓ | ✓ | ✓ |
| Port prefix translation | ✓ (sed) | ✗ | ✓ (re) |
| Live port range preserve | ✓ | ✗ | ✓ |
| Dry-run mode | ✗ | ✗ | ✓ |
| nginx -t before reload | ✓ | ✓ | ✓ |
| `CORTEX_SKIP_NGINX` | ✓ | ✗ | ✓ |

---

## Script Usage

### cortex-update.sh (auto-deploy)

```bash
# Defaults — auto-detects everything
bash ~/hermes-cortex/src/scripts/cortex-update.sh

# With custom SSL and port prefix
CORTEX_SSL_CERT_PATH=/etc/letsencrypt/live/mydomain.com/fullchain.pem \
CORTEX_SSL_CERT_KEY_PATH=/etc/letsencrypt/live/mydomain.com/privkey.pem \
CORTEX_NGINX_PORT_PREFIX=12 \
bash ~/hermes-cortex/src/scripts/cortex-update.sh

# Skip nginx entirely (scripts-only update)
CORTEX_SKIP_NGINX=1 bash ~/hermes-cortex/src/scripts/cortex-update.sh
```

### hermes-security-apply (sudo deploy)

```bash
# Auto-detect SSL certs
sudo hermes-security-apply

# Explicit cert paths
CORTEX_SSL_CERT_PATH=/etc/letsencrypt/live/mydomain.com/fullchain.pem \
CORTEX_SSL_CERT_KEY_PATH=/etc/letsencrypt/live/mydomain.com/privkey.pem \
sudo hermes-security-apply
```

### hermes-services-apply.py (Python deploy)

```bash
# Auto-detect
python3 ~/hermes-cortex/deploy/nginx/hermes-services-apply.py

# Dry-run (no files changed)
python3 ~/hermes-cortex/deploy/nginx/hermes-services-apply.py --dry-run

# Explicit domain
python3 ~/hermes-cortex/deploy/nginx/hermes-services-apply.py --domain mydomain.com

# Validate only
python3 ~/hermes-cortex/deploy/nginx/hermes-services-apply.py --validate
```

---

## Template Placeholders

These placeholders in `deploy/nginx/hermes-services.conf` are substituted at
deploy time by all three scripts above:

| Placeholder | Substituted with | Example value |
|-------------|-----------------|---------------|
| `__NGINX_CONFIG_DIR__` | OS-aware nginx config directory | `/opt/homebrew/etc/nginx/servers` |
| `__NGINX_LOG_DIR__` | OS-aware nginx log directory | `/opt/homebrew/var/log/nginx` |
| `__HTPASSWD_FILE__` | htpasswd file path | `/opt/homebrew/etc/nginx/.htpasswd` |
| `__CORTEX_HOME__` | User home directory | `/Users/luke` |
| `__SSL_CERT__` | SSL certificate file | `/etc/letsencrypt/live/example.com/fullchain.pem` |
| `__SSL_CERT_KEY__` | SSL certificate key | `/etc/letsencrypt/live/example.com/privkey.pem` |
