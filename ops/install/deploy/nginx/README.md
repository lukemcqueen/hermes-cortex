# Hermes Cortex — nginx Security Deploy Guide

This directory holds everything needed to deploy and maintain nginx
security configs: reverse proxy, rate limiting, IP blocking, and
fail2ban filters.

---

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| **nginx** | Required. The deploy scripts install configs and reload nginx. |
| **fail2ban** | Required for automated bans. The pipeline integrates with fail2ban filters. |
| **sudoers entry** | Passwordless sudo for `/usr/local/sbin/install-nginx-full.sh` + nginx commands. Not needed for the Python script if the user has root access via other means. |
| **Env file** | `~/hermes-cortex/.env` (gitignored) — set your `CORTEX_*` vars. The deploy scripts auto-source this. See `.env.example` for all options. |

**Agents without nginx/fail2ban** should skip this pipeline entirely.
The scanner silently exits when nginx logs aren't found, but there's
no benefit to running it on a host without nginx.

## Files

| File | Purpose |
|------|---------|
| `hermes-services.conf` | Main nginx reverse proxy config (ports 13001–13004, health, A2A) |
| `hermes-zone-defs.conf` | Rate limit zones, CSP maps, direct-IP blocker |
| `blocked_ips.add` | **Input:** bare IPs to block (one per line, no `deny` keyword, no semicolon) |
| `nginx-badbots.conf` | **Input:** fail2ban filter for archive scanners + `/storage/` crawling |
| `install-nginx-full.sh` | **Full deploy** bash script — nginx configs + SSL + blocked IPs + fail2ban. Used for fresh installs and full deploys. Daily pipeline uses `deploy-blocked-ips.sh` for incremental updates. |
| `hermes-services-apply.py` | **Primary** Python deploy script — auto-discovers SSL, supports `--dry-run`, handles port prefixes and `allow-ips-manual.conf` |
| `~/hermes-cortex/.env.example` | **Env template** — copy to `.env`, set `CORTEX_SSL_*` vars. Gitignored, auto-sourced by deploy scripts. |
| `allow-ips-manual.conf` | **Per-machine** (not in git): manual allow list at `/etc/nginx/allow-ips-manual.conf` — IPs listed here override blocked_ips.conf |
| `README.md` | This file |

---

## One-Time Setup

### 1. Configure the env file

```bash
cp ~/hermes-cortex/.env.example ~/hermes-cortex/.env
# Edit ~/hermes-cortex/.env with your cert paths, port prefix, etc.
```

The deploy scripts auto-source this file — no need to source it manually.

### 2. Install the full deploy script (required for fail2ban + fresh installs)

```bash
sudo install -o root -g root -m 0750 install-nginx-full.sh /usr/local/sbin/install-nginx-full.sh
```

### 3. Add passwordless sudo for the deploy script (required for cron usage)

```bash
echo '<your-username> ALL=(root) NOPASSWD: /usr/local/sbin/install-nginx-full.sh' \
  | sudo tee /etc/sudoers.d/hermes-security
sudo chmod 440 /etc/sudoers.d/hermes-security
sudo visudo -cf /etc/sudoers.d/hermes-security
```

No `env_keep` needed — all deploy scripts auto-source `~/hermes-cortex/.env`
internally. Set your `CORTEX_*` vars in the env file once, and every deploy picks
them up automatically.

### 4. Ensure input files exist

```bash
touch ~/hermes-cortex/deploy/nginx/blocked_ips.add
touch ~/hermes-cortex/deploy/nginx/nginx-badbots.conf
```

### 5. Create the manual allow list on each machine (recommended)

```bash
sudo tee /etc/nginx/allow-ips-manual.conf << 'EOF'
# One `allow X.X.X.X;` per line — these IPs override the block list.
# This file is NOT in git — manage locally on each machine.
EOF
```

---

## Deploying

### Preferred: Python deploy script

```bash
cd ~/hermes-cortex

# Dry-run first to see what would change
python3 deploy/nginx/hermes-services-apply.py --dry-run

# Deploy
python3 deploy/nginx/hermes-services-apply.py

# Or with explicit port prefix
CORTEX_NGINX_PORT_PREFIX=12 python3 deploy/nginx/hermes-services-apply.py
```

What it does:
1. Auto-discovers SSL certs from Let's Encrypt, env vars, or system paths
2. Preserves the existing port prefix (no accidental port shift)
3. Deploys `hermes-services.conf` to `sites-available/` and symlinks to `sites-enabled/`
4. Presences `allow-ips-manual.conf` include
5. Runs `nginx -t` (as root via sudo) to validate
6. Reloads nginx gracefully

### Legacy: bash deploy script

```bash
sudo /usr/local/sbin/install-nginx-full.sh
```

**Known issue with the legacy script:** It writes to `/etc/nginx/servers/` instead of
`sites-available/`, so the live config at `sites-enabled/` is NOT updated by this
script. The `⚠ blocked_ips.conf not yet included in nginx config` warning is a
**false positive** — the script checks a path it doesn't actually update. Use the
Python script instead.

If the legacy script fails with `nginx: [emerg] unexpected end of file` in `blocked_ips.conf`,
the config has bare IPs (missing `deny ... ;` wrapper). Fix with the helper script:

```bash
python3 ~/hermes-cortex/deploy/nginx/fix-blocked-ips.py
sudo cp /tmp/blocked_ips.conf.new /etc/nginx/blocked_ips.conf      # Linux
# sudo cp /tmp/blocked_ips.conf.new /usr/local/etc/nginx/blocked_ips.conf  # macOS
sudo /usr/local/sbin/install-nginx-full.sh
```

---

## Updating the System Script (Legacy)

Only needed if your pipeline cron references `/usr/local/sbin/install-nginx-full.sh`:

```bash
sudo cp ~/hermes-cortex/deploy/nginx/install-nginx-full.sh /usr/local/sbin/install-nginx-full.sh
sudo chmod 755 /usr/local/sbin/install-nginx-full.sh
```

### Verify

```bash
# Python script shows what it would do
python3 ~/hermes-cortex/deploy/nginx/hermes-services-apply.py --dry-run
# Config valid?
sudo nginx -t && echo "✓ Config valid"
```

---

## SSL Certificate Configuration

The config template (`hermes-services.conf`) uses `__SSL_CERT__` and `__SSL_CERT_KEY__`
placeholders. All deploy scripts auto-discover certificates in this priority:

1. `CORTEX_SSL_CERT_PATH` / `CORTEX_SSL_CERT_KEY_PATH` env vars (explicit paths)
2. `CORTEX_SSL_DOMAIN` → `/etc/letsencrypt/live/<domain>/`
3. Scan all directories under `/etc/letsencrypt/live/`
4. `$HOME/certs/fullchain.pem` + `privkey.pem`

If no certs are found, the placeholders remain unchanged — SSL listeners won't
work until certs are provided.

### Setup

```bash
# 1. Copy the env template (stays in repo, never goes to nginx)
cp ~/hermes-cortex/.env.example ~/hermes-cortex/.env
# 2. Edit with your settings
vim ~/hermes-cortex/.env

# 2. Edit with your cert paths or domain
#    CORTEX_SSL_CERT_PATH=/etc/letsencrypt/live/example.com/fullchain.pem
#    CORTEX_SSL_CERT_KEY_PATH=/etc/letsencrypt/live/example.com/privkey.pem
#    CORTEX_SSL_DOMAIN=example.com

# 3. Deploy (auto-sources the env file internally)
python3 ~/hermes-cortex/deploy/nginx/hermes-services-apply.py --dry-run
python3 ~/hermes-cortex/deploy/nginx/hermes-services-apply.py
```

### Env var reference

See `docs/env-vars.md` for the full reference of all `CORTEX_*` variables.

---

## Manual IP Allow List

To ensure certain IPs are NEVER blocked (even by fail2ban), add them to the
manual allow list on each machine:

```bash
echo "allow YOUR.IP.HERE;" | sudo tee -a /etc/nginx/allow-ips-manual.conf
sudo nginx -s reload
```

This file is included in nginx config BEFORE `blocked_ips.conf`, so `allow`
rules run first and override any `deny` rules for those IPs.

The deploy pipeline (`install-nginx-full.sh`) also strips allow-listed IPs
from the block list during deployment, so fail2ban cannot accidentally add
them to `blocked_ips.conf`.

This file is NOT in the git repo — manage it locally on each agent machine.

---

## Health Endpoint — No Authentication

The health server (port `xx007`, e.g. `13007`) has **no HTTP Basic Auth** — intentionally.
Moses polls every agent's health vector without managing per-agent credentials.

**Verify:**
```bash
# Config is written to sites-available/, symlinked in sites-enabled/
ls -la /etc/nginx/sites-available/hermes-services.conf
ls -la /etc/nginx/sites-enabled/hermes-services.conf  # → ../sites-available/hermes-services.conf
# Health block should have 0 matches for auth_basic
grep -c 'auth_basic' /etc/nginx/sites-enabled/hermes-services.conf
```

The health endpoint exposes only a compact 9-element ternary status vector
(CPU load, services, crons, disk, etc.). No secrets, no PII, no write operations.
Rate limited to 6 requests/minute per IP.

---

## Daily Operation — Adding New Blocks

### Block new IPs

Append bare IPs (one per line) to `blocked_ips.add`:

```bash
echo "1.2.3.4" >> ~/hermes-cortex/deploy/nginx/blocked_ips.add
```

### Update fail2ban filters

Edit `nginx-badbots.conf` with new `failregex` patterns as needed.

### Deploy everything

```bash
# Preferred
python3 ~/hermes-cortex/deploy/nginx/hermes-services-apply.py

# Legacy (still works for IPs, but doesn't handle allow-ips-manual or port prefix)
sudo /usr/local/sbin/install-nginx-full.sh
```

The deploy script does **all** of this atomically:
1. Backs up existing configs to `/etc/hermes-cortex-backups/$(date)/`
2. Deploys fresh `hermes-services.conf` + `hermes-zone-defs.conf`
3. Removes any duplicate `include hermes-zone-defs.conf` lines
4. Appends new IPs from `blocked_ips.add` — validates IPv4 format, rejects private/reserved ranges, skips duplicates, **strips any IPs listed in `allow-ips-manual.conf`**
5. Replaces `/etc/fail2ban/filter.d/nginx-badbots.conf`
6. Runs `nginx -t` to validate
7. Reloads fail2ban and nginx

**If nginx -t fails, nothing is reloaded** — the script exits safely.

---

## Automated Daily Scan (for agents)

A cron job should run daily to:
1. Scan nginx access logs for suspicious IPs (high request rates, `/storage/` hits, archive file scans)
2. Check fail2ban logs for emerging patterns
3. Append new IPs to `blocked_ips.add`
4. Re-run the deploy if changes were made
5. Commit and push any new IPs/filters to the repository

The pipeline (`ops/scripts/manage/nginx-threat-pipeline.sh`) handles all of this.

---

## Migration: Legacy `deploy/` Symlink → Canonical `ops/install/deploy/nginx/`

If you previously had this repo before the reorganization, you may have a
legacy symlink that causes issues. Run this checklist once after pulling:

### 1. Remove the legacy symlink

```bash
cd ~/hermes-cortex
# Check if deploy is a symlink (not a real directory)
ls -la deploy 2>/dev/null
# If it shows: deploy -> ops/install/deploy
rm deploy
echo "✓ Legacy symlink removed"
```

**Warning:** `rm deploy` (without trailing slash) removes only the symlink.
`rm -rf deploy/` (WITH trailing slash) follows the symlink and deletes
the canonical files in `ops/install/deploy/nginx/` — do not add the slash.

### 2. Verify the fix script reads from the canonical path

```bash
cd ~/hermes-cortex
grep "source = os.path.join" ops/install/deploy/nginx/fix-blocked-ips.py
# Should show: ops/install/deploy/nginx/blocked_ips.add
# If it still says deploy/nginx/blocked_ips.add, pull the latest:
git pull origin main
```

### 3. Pull the latest IPs and deploy

```bash
cd ~/hermes-cortex
git pull origin main
sudo -n ops/install/deploy/nginx/fix-blocked-ips.py
# Expect: "✓ Generated: 14000+ blocked IPs"
```

### 4. Pull updated scripts

```bash
bash ops/scripts/cortex-update.sh --force-all
```

### 5. Verify no leftover symlinks

```bash
cd ~/hermes-cortex
find . -maxdepth 2 -name 'deploy' -type l 2>/dev/null && \
  echo "⚠ Legacy symlink still exists" || echo "✓ Clean"
```
