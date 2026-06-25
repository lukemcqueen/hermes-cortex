# Hermes Cortex — nginx Security Deploy Guide

This directory holds everything needed to deploy and maintain nginx
security configs: reverse proxy, rate limiting, IP blocking, and
fail2ban filters.

---

## Files

| File | Purpose |
|------|---------|
| `hermes-services.conf` | Main nginx reverse proxy config (ports 13001–13002; inbox is MCP-only, no longer proxied) |
| `hermes-zone-defs.conf` | Rate limit zones, CSP maps, direct-IP blocker |
| `blocked_ips.add` | **Input:** bare IPs to block (one per line, no `deny` keyword, no semicolon) |
| `nginx-badbots.conf` | **Input:** fail2ban filter for archive scanners + `/storage/` crawling |
| `hermes-security-apply` | Sudo-installed script that deploys all configs atomically |
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
touch "${CORTEX_REPO:-$HOME/hermes-cortex}/deploy/nginx/blocked_ips.add"
touch "${CORTEX_REPO:-$HOME/hermes-cortex}/deploy/nginx/nginx-badbots.conf"
```

---

## Daily Operation — Adding New Blocks

### Block new IPs

Append bare IPs (one per line) to `blocked_ips.add`:

```bash
echo "1.2.3.4" >> "${CORTEX_REPO:-$HOME/hermes-cortex}/deploy/nginx/blocked_ips.add"
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
