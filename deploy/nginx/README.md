# Hermes Cortex — nginx Security Deploy Guide

This directory holds everything needed to deploy and maintain nginx
security configs: reverse proxy, rate limiting, IP blocking, and
fail2ban filters.

---

## Platform Notes: macOS vs Linux

This pipeline was built and tested on **macOS 12 Monterey** with Homebrew-managed nginx and fail2ban. If deploying on Linux, adjust:

| Concern | macOS (Homebrew) | Linux (apt/yum) |
|---------|-----------------|-----------------|
| fail2ban service | `homebrew.mxcl.fail2ban` | `fail2ban.service` |
| nginx config dir | `/usr/local/etc/nginx/` | `/etc/nginx/` |
| fail2ban config dir | `/usr/local/etc/fail2ban/` | `/etc/fail2ban/` |
| nginx log dir | `/usr/local/var/log/nginx/` | `/var/log/nginx/` |
| Service manager | `launchctl` | `systemctl` |
| Firewall backend | `pf` (built-in) | `iptables` / `nftables` |
| Sudoers permissions | `0440` (no `r--r-----`) | `0440` (same) |

**Fail2ban service restart on macOS:**
```bash
sudo launchctl kickstart system/homebrew.mxcl.fail2ban   # reload
sudo launchctl bootout system/homebrew.mxcl.fail2ban      # stop
sudo launchctl bootstrap system /usr/local/opt/fail2ban/homebrew.mxcl.fail2ban.plist  # start
```

**On Linux**, replace with:
```bash
sudo systemctl reload fail2ban
sudo systemctl restart fail2ban
```

The deploy script (`hermes-security-apply`) auto-detects `fail2ban-client` and works on both platforms — just ensure the paths in `jail.local` match your OS.

---

## Files

| File | Purpose |
|------|---------|
| `hermes-services.conf` | Main nginx reverse proxy config (ports 13001–13006) |
| `hermes-zone-defs.conf` | Rate limit zones, CSP maps, direct-IP blocker |
| `blocked_ips.add` | **Input:** bare IPs to block (one per line, no `deny` keyword, no semicolon) |
| `nginx-badbots.conf` | fail2ban filter for archive scanners + `/storage/` crawling |
| `hermes-security-apply` | Deploy script — sudo-installed to `/usr/local/sbin/` |
| `README.md` | This file |

---

## Human Setup (one-time)

### 1. Install the deploy script

```bash
sudo install -o root -g wheel -m 0750 hermes-security-apply /usr/local/sbin/hermes-security-apply
```

### 2. Add passwordless sudo for the script

```bash
echo '$(whoami) ALL=(root) NOPASSWD: /usr/local/sbin/hermes-security-apply' \
  | sudo tee /etc/sudoers.d/hermes-security
sudo chmod 440 /etc/sudoers.d/hermes-security
sudo visudo -cf /etc/sudoers.d/hermes-security
```

### 3. Ensure the input files exist

```bash
touch ~/hermes-cortex/deploy/nginx/blocked_ips.add
touch ~/hermes-cortex/deploy/nginx/nginx-badbots.conf
```

### 4. Run the deploy for the first time

```bash
sudo /usr/local/sbin/hermes-security-apply
```

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
4. Appends new IPs from `blocked_ips.add` (skips duplicates)
5. Installs fail2ban filter + jail config
6. Runs `nginx -t` to validate
7. Reloads nginx and fail2ban

**If nginx -t fails, nothing is reloaded** — the script exits safely.

---

## Automated Daily Scan

A cron job runs at 6 AM daily (`src/scripts/nginx-security-scanner.sh`):

1. Scans nginx access logs for IPs with ≥10 requests in 60 minutes
2. Checks fail2ban logs for newly banned IPs
3. Appends new IPs to `blocked_ips.add`
4. Re-runs `sudo hermes-security-apply` if changes were made
5. Silent when no suspect traffic found

Create the cron:

```bash
cron name=daily-nginx-scanner schedule="0 6 * * *" script=nginx-security-scanner.sh no_agent=true deliver=local
```

---

## Architecture

```
blocked_ips.add (input)    nginx-badbots.conf (input)
         │                          │
         └───────┬──────────────────┘
                 │
    sudo hermes-security-apply
         │
         ├── Backs up old configs
         ├── Deploys zone-defs + services
         ├── Deduplicates includes
         ├── Appends new IPs (skip dups)
         ├── Installs fail2ban filter + jail
         ├── nginx -t (validate)
         └── Reloads fail2ban + nginx
```

The daily scanner feeds back into `blocked_ips.add`, creating a closed loop:
**Logs → Detect → Append → Deploy → Protect**.
