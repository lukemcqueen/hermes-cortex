# Hermes Cortex — nginx Security Deploy Guide

This directory holds everything needed to deploy and maintain nginx
security configs: reverse proxy, rate limiting, IP blocking, and
fail2ban filters.

---

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| **nginx** | Required. The deploy script installs configs and reloads nginx. |
| **fail2ban** | Required for automated bans. The pipeline integrates with fail2ban filters. |
| **sudoers entry** | Passwordless sudo for `/usr/local/sbin/hermes-security-apply` + nginx commands. |

**Agents without nginx/fail2ban** should skip this pipeline entirely.
The scanner silently exits when nginx logs aren't found, but there's
no benefit to running it on a host without nginx.

## Files

| File | Purpose |
|------|---------|
| `hermes-services.conf` | Main nginx reverse proxy config (ports 13001–13004) |
| `hermes-zone-defs.conf` | Rate limit zones, CSP maps, direct-IP blocker |
| `blocked_ips.add` | **Input:** bare IPs to block (one per line, no `deny` keyword, no semicolon) |
| `nginx-badbots.conf` | **Input:** fail2ban filter for archive scanners + `/storage/` crawling |
| `hermes-security-apply` | Sudo-installed script that deploys all configs atomically |
| `hermes-services-apply.py` | **Alternative:** Python deploy script — auto-discovers SSL certs, supports `--dry-run` and `--validate` |
| `hermes-services.env.example` | **Template env file** — copy to `hermes-services.env`, set `CORTEX_SSL_*` vars |
| `README.md` | This file |

---

## Human Setup (one-time)

### 1. Install the deploy script

```bash
sudo install -o root -g root -m 0750 hermes-security-apply /usr/local/sbin/hermes-security-apply
```

### 2. Add passwordless sudo for the script

```bash
echo '<your-username> ALL=(root) NOPASSWD: /usr/local/sbin/hermes-security-apply' \
  | sudo tee /etc/sudoers.d/hermes-security
sudo chmod 440 /etc/sudoers.d/hermes-security
sudo visudo -cf /etc/sudoers.d/hermes-security
```

### 3. Ensure the input files exist

```bash
touch ~/hermes-cortex/deploy/nginx/blocked_ips.add
touch ~/hermes-cortex/deploy/nginx/nginx-badbots.conf
```

---

## Updating the Deploy Script

Keep `/usr/local/sbin/hermes-security-apply` in sync with the repo source at `deploy/nginx/hermes-security-apply`:

```bash
# Update installed script
sudo cp ~/hermes-cortex/deploy/nginx/hermes-security-apply /usr/local/sbin/hermes-security-apply
sudo chmod 755 /usr/local/sbin/hermes-security-apply
# Deploy
sudo /usr/local/sbin/hermes-security-apply
```

If the script fails with `nginx: [emerg] unexpected end of file` in `blocked_ips.conf`,
the config has bare IPs (missing `deny ... ;` wrapper). Fix with the helper script:

```bash
python3 ~/hermes-cortex/deploy/nginx/fix-blocked-ips.py
sudo cp /tmp/blocked_ips.conf.new /etc/nginx/blocked_ips.conf      # Linux
# sudo cp /tmp/blocked_ips.conf.new /usr/local/etc/nginx/blocked_ips.conf  # macOS
sudo /usr/local/sbin/hermes-security-apply
# Linux: sudo hermes-security-apply  (in PATH, or ~/hermes-cortex/deploy/nginx/hermes-security-apply)
```

For cron/agent use, copy the fix script to `~/.hermes/scripts/`:
```bash
cp ~/hermes-cortex/deploy/nginx/fix-blocked-ips.py ~/.hermes/scripts/
```

### Verify

```bash
# File sizes should match
ls -la /usr/local/sbin/hermes-security-apply ~/hermes-cortex/deploy/nginx/hermes-security-apply
# Config valid?
sudo nginx -t && echo "✓ Config valid"
# Active blocks
sudo nginx -T 2>/dev/null | grep 'deny ' | wc -l
```

---

## SSL Certificate Configuration

The config template (`hermes-services.conf`) uses `__SSL_CERT__` and `__SSL_CERT_KEY__`
placeholders. All three deploy scripts auto-discover certificates in this priority:

1. `CORTEX_SSL_CERT_PATH` / `CORTEX_SSL_CERT_KEY_PATH` env vars (explicit paths)
2. `CORTEX_SSL_DOMAIN` → `/etc/letsencrypt/live/<domain>/`
3. Scan all directories under `/etc/letsencrypt/live/`
4. `$HOME/certs/fullchain.pem` + `privkey.pem`

If no certs are found, the placeholders remain unchanged — SSL listeners won't
work until certs are provided.

### Setup

```bash
# 1. Copy the env template and edit
cp ~/hermes-cortex/deploy/nginx/hermes-services.env.example \
  ~/hermes-cortex/deploy/nginx/hermes-services.env

# 2. Edit with your cert paths or domain
#    CORTEX_SSL_CERT_PATH=/etc/letsencrypt/live/example.com/fullchain.pem
#    CORTEX_SSL_CERT_KEY_PATH=/etc/letsencrypt/live/example.com/privkey.pem
#    CORTEX_SSL_DOMAIN=example.com

# 3. Source it before deploying
set -a; source ~/hermes-cortex/deploy/nginx/hermes-services.env; set +a
sudo hermes-security-apply

# Or use the Python script directly with --dry-run first:
python3 ~/hermes-cortex/deploy/nginx/hermes-services-apply.py --dry-run
python3 ~/hermes-cortex/deploy/nginx/hermes-services-apply.py
```

### Env var reference

See `docs/env-vars.md` for the full reference of all `CORTEX_*` variables.

---

## Health Endpoint — No Authentication

The health server (port `xx007`, e.g. `13007`) has **no HTTP Basic Auth** — intentionally.
Moses polls every agent's health vector without managing per-agent credentials.

**Verify:**
```bash
grep -c 'auth_basic' /etc/nginx/sites-enabled/hermes-services.conf
# Health block should have 0 matches for auth_basic
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
sudo /usr/local/sbin/hermes-security-apply
```

The script does **all** of this atomically:
1. Backs up existing configs to `/etc/hermes-cortex-backups/$(date)/`
2. Deploys fresh `hermes-services.conf` + `hermes-zone-defs.conf`
3. Removes any duplicate `include hermes-zone-defs.conf` lines
4. Appends new IPs from `blocked_ips.add` — validates IPv4 format, rejects private/reserved ranges, skips duplicates (**batch-processed**: ~5 grep calls total regardless of file size, < 1s even for 2000+ IPs)
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
4. Re-run `sudo hermes-security-apply` if changes were made
5. Commit and push any new IPs/filters to the repository

See the Moses instructions for the full agent workflow.
