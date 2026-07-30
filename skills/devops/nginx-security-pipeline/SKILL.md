---
name: nginx-security-pipeline
version: 1.0.0
category: devops
description: >-
  Set up nginx security with IP blocking, fail2ban integration, daily automated
  scanning, and atomic deploy. Covers blocked_ips.add input, fail2ban filter,
  deploy script (backup → validate → reload), and a no_agent daily scanner cron.
  Platform-aware: macOS (Homebrew) and Linux paths.
trigger: >-
  User asks to set up nginx security, block bad IPs, set up fail2ban for nginx,
  create a daily security scanner, deploy IP blocks, or implement a blocked-IP
  pipeline. Also when asked to secure nginx against scanners or bots.
---

# nginx-security-pipeline

Set up nginx security with IP blocking, fail2ban integration, automated daily scanning, and atomic deploy.

## Architecture

```
blocked_ips.add (input)    nginx-badbots.conf (filter)    allow-ips-manual.conf (override)
         │                          │                              │
         └───────┬──────────────────┘                              │
                 │                  Strips allow-listed IPs        │
    bash deploy-blocked-ips.sh ────────────────────────────────────┘
         │
         ├── Generates blocked_ips.conf from blocked_ips.add
         ├── sudo cp to /etc/nginx/blocked_ips.conf
         ├── nginx -t (validate)
         └── Reloads fail2ban + nginx
```

The daily scanner feeds back into `blocked_ips.add`, creating a closed loop: **Logs → Detect → Append → Deploy → Protect**.

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| **nginx** | Required. Deploy scripts install configs and reload nginx. |
| **fail2ban** | Required for automated bans. Pipeline integrates with fail2ban filters. |
| **sudoers entry** | No broad script NOPASSWD needed. Only tight rules: `sudo cp /tmp/blocked_ips.conf.new /etc/nginx/blocked_ips.conf`, `nginx -t`, `nginx -s reload`. |

**Agents without nginx/fail2ban** — skip this pipeline entirely. The scanner
silently exits when nginx logs aren't found, but there's no benefit to running
it on a host without nginx.

## Files

### Source (`ops/install/deploy/nginx/`)

| File | Purpose |
|------|---------|
| `blocked_ips.add` | **Input:** bare IPs to block (one per line, no `deny`, no semicolon) |
| `nginx-badbots.conf` | fail2ban filter for archive scanners + `/storage/` crawling |
| `install-nginx-full.sh` | **Full deploy** bash script — nginx configs + SSL + blocked IPs + fail2ban. Used for fresh installs. Daily pipeline uses `deploy-blocked-ips.sh`. |
| `hermes-services-apply.py` | **Primary** Python deploy script — handles SSL, port prefix, `allow-ips-manual.conf` |
| `fix-blocked-ips.py` | **Recovery:** regenerates `blocked_ips.conf` if corrupted with bare IPs |
| `README.md` | Setup guide with platform notes |

### Per-machine (not in git)

| File | Purpose |
|------|---------|
| `/etc/nginx/allow-ips-manual.conf` | Manual allow list — `allow X.X.X.X;` per line, overrides blocked_ips.conf |
| `~/hermes-cortex/.env` | Single source of truth — gitignored per-machine config with `CORTEX_*` vars, auto-sourced by deploy scripts |

### Scanner (`ops/scripts/`)

| File | Purpose |
|------|---------|
| `nginx-security-scanner.sh` | Daily scanner — logs → detect → append → deploy |
| `nginx-threat-pipeline.sh` | **Daily pipeline** — scanner → fail2ban → deploy → git commit → push (wraps scanner, adds fail2ban ban collection and git workflow) |

## Setup Steps

### 1. Create the input files

```bash
touch "${CORTEX_REPO:-$HOME/hermes-cortex}/ops/install/deploy/nginx/blocked_ips.add"
touch "${CORTEX_REPO:-$HOME/hermes-cortex}/ops/install/deploy/nginx/nginx-badbots.conf"
```

Populate `blocked_ips.add` with known bad IPs (one per line, bare IPs only).

### 2. Configure the env file

```bash
# Edit ~/hermes-cortex/.env (gitignored) with your settings:
vim ~/hermes-cortex/.env
# Set CORTEX_SSL_CERT_PATH, CORTEX_NGINX_PORT_PREFIX, etc.
# See ~/hermes-cortex/.env.example for all available vars.
```

### 3. Deploy script auto-installed

`deploy-blocked-ips.sh` is deployed by `cortex-update.sh` to `~/.hermes/scripts/`.
No manual install needed.

### 4. Add passwordless sudo (tight rule only)

```bash
echo 'moses ALL=(root) NOPASSWD: /bin/cp /tmp/blocked_ips.conf.new /etc/nginx/blocked_ips.conf' \
  | sudo tee -a /etc/sudoers.d/hermes
```

### 5. Set up fail2ban

Copy the filter to fail2ban's filter directory:

```bash
cp nginx-badbots.conf /usr/local/etc/fail2ban/filter.d/nginx-badbots.conf
```

Add a jail entry in `jail.local`:

```ini
[nginx-badbots]
enabled  = true
port     = http,https
filter   = nginx-badbots
logpath  = /usr/local/var/log/nginx/*-access.log
maxretry = 3
bantime  = 86400
findtime = 3600
```

### 6. Activate the jail

```bash
sudo fail2ban-client reload
sudo fail2ban-client status nginx-badbots
```

### 7. Create daily scanner cron

```bash
cron name=daily-nginx-scanner schedule="0 6 * * *" \
  script=nginx-security-scanner.sh no_agent=true deliver=local
```

### 7b. (Optional) Create threat pipeline cron

Adds fail2ban ban collection and git commit/push on top of the scanner:

```bash
cron name=threat-pipeline schedule="0 5 * * *" \
  script=nginx-threat-pipeline.sh no_agent=true deliver=origin
```

The pipeline:
1. Runs the scanner for new suspect IPs from nginx logs
2. Collects new banned IPs from fail2ban logs
3. Deploys via `sudo -n install-nginx-full.sh` (uses the legacy script)
4. Git-commits and pushes `blocked_ips.add` changes

> **Note:** This is a deployment-specific cron (Luke's setup). Install via `install-crons.sh` on each target host.

### 8. First deploy

```bash
# Generate and deploy blocked IPs (minimal-root)
bash ~/.hermes/scripts/deploy-blocked-ips.sh
```

## Daily Operations

### Block a new IP manually

```bash
echo "1.2.3.4" >> "${CORTEX_REPO:-$HOME/hermes-cortex}/ops/install/deploy/nginx/blocked_ips.add"
# Deploy
python3 ~/hermes-cortex/ops/install/deploy/nginx/hermes-services-apply.py
```

### Allow an IP (never block)

```bash
echo "allow 1.2.3.4;" | sudo tee -a /etc/nginx/allow-ips-manual.conf
sudo nginx -s reload
```

### What the deploy script does

1. Backs up existing configs to `/etc/hermes-cortex-backups/$(date)/`
2. Deploys fresh nginx configs (from template, with allow-ips-manual include)
3. Deduplicates include directives
4. Appends new IPs (skips duplicates, strips allow-listed IPs) — validates IPv4, rejects garbage
5. Installs fail2ban filter + jail
6. Runs `nginx -t` to validate
7. If valid: reloads nginx and fail2ban
8. If invalid: exits safely (no reload)

## Platform Differences

### macOS (Homebrew)

| Concern | Value |
|---------|-------|
| fail2ban service | `homebrew.mxcl.fail2ban` |
| nginx config dir | `/usr/local/etc/nginx/` (Intel) / `/opt/homebrew/etc/nginx/` (ARM) |
| fail2ban config dir | `/usr/local/etc/fail2ban/` (Intel) / `/opt/homebrew/etc/fail2ban/` (ARM) |
| nginx log dir | `/usr/local/var/log/nginx/` (Intel) / `/opt/homebrew/var/log/nginx/` (ARM) |
| Service manager | `launchctl` |
| Firewall backend | `pf` (built-in) |
| Sudoers permissions | `0440` |

Restart fail2ban:
```bash
sudo launchctl kickstart system/homebrew.mxcl.fail2ban
```

### Linux (apt/yum)

| Concern | Value |
|---------|-------|
| fail2ban service | `fail2ban.service` |
| nginx config dir | `/etc/nginx/` |
| fail2ban config dir | `/etc/fail2ban/` |
| nginx log dir | `/var/log/nginx/` |
| Service manager | `systemctl` |
| Firewall backend | `iptables` / `nftables` |
| Sudoers permissions | `0440` |

Restart fail2ban:
```bash
sudo systemctl reload fail2ban
```

## Pitfalls

1. **macOS fail2ban service name**: It's `homebrew.mxcl.fail2ban`, NOT `com.fail2ban` or `fail2ban`. Using the wrong name gives "Could not find service" error.

2. **blocked_ips.add format**: Bare IPs only. One per line. No `deny` keyword, no semicolon. The deploy script wraps them in `deny <ip>;` automatically.

3. **nginx -t must pass**: The deploy script refuses to reload if validation fails. Rollback: `cp <backup_dir>/* <nginx_dir>/`.

4. **Sudoers file**: Must be `0440` permissions. `visudo -cf` validates syntax.

5. **fail2ban socket on macOS**: Requires root to access. Always use `sudo fail2ban-client`.

6. **False-positive warning**: The legacy script prints `⚠ blocked_ips.conf not yet included` even when it is. This was fixed in `deploy-blocked-ips.sh`.

7. **IPv4 validation**: All scripts (`fix-blocked-ips.py`, `generate-blocked-ips.py`) validate IPv4 format and reject garbage entries. The threat pipeline also filters via `awk` before appending to `blocked_ips.add`.

8. **Log paths on Linux**: The jail `logpath` must match your OS — `/var/log/nginx/access.log` on Linux vs `/usr/local/var/log/nginx/*-access.log` on macOS Homebrew.

## Verification

```bash
# Check jail is active
sudo fail2ban-client status nginx-badbots

# Check blocked IPs are deployed
grep "^deny" /etc/nginx/blocked_ips.conf

# Check allow list is active
cat /etc/nginx/allow-ips-manual.conf

# Check nginx config is valid
sudo nginx -t

# Verify daily cron exists
cron list | grep nginx-scanner
```
