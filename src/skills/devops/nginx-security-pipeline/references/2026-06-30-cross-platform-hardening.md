# Nginx Threat Pipeline — Cross-Platform Hardening (2026-06-30)

**Summary:** Full rewrite of `nginx-threat-pipeline.sh` for cross-platform resilience.
Handles missing dependencies gracefully (fail2ban, nginx, deploy script, timeout),
and auto-detects macOS (Intel + ARM) vs Linux paths.

## Changes

### 1. Graceful exits

| Scenario | Behavior |
|----------|----------|
| fail2ban not installed | `fail2ban not installed — skipping` |
| fail2ban log not found | `fail2ban installed but no log file — skipping` |
| `deploy/nginx/` dir missing | `mkdir -p` before append |
| cortex repo missing | `cortex repo not found — skipping commit` |
| deploy script not found | `deploy-blocked-ips.sh not found — skipping` |
| nginx binary not found | `nginx not found — skipping deploy` |
| no `timeout`/`gtimeout` binary | Runs without timeout instead of failing |

### 2. Cross-platform path detection

| Concern | Detection order |
|---------|----------------|
| **timeout** | `timeout` (Linux) → `gtimeout` (macOS brew coreutils) |
| **deploy-blocked-ips.sh** | `~/.hermes/scripts/` (symlinked to Hermes home) |
| **nginx binary** | `/usr/sbin/nginx` (Linux) → `/usr/local/bin/nginx` (Mac Intel) → `/opt/homebrew/bin/nginx` (Mac ARM) |
| **fail2ban log** | `/var/log/fail2ban.log` (Linux) → `/opt/homebrew/var/log/` (Mac ARM) → `/usr/local/var/log/` (Mac Intel) |

### 3. `sudo -n` fix (from earlier cycle)

`sudo bash "$DEPLOY_SCRIPT"` → `sudo -n "$DEPLOY_SCRIPT"`
- Cron has no TTY (`requiretty` in sudoers)
- `bash` wrapper made sudo see `bash` instead of the NOPASSWD-authorized script path

> **⚠ Legacy script note:** `hermes-security-apply` (bash) deploys to `/etc/nginx/servers/` instead of
> `sites-available/`, producing the false-positive `⚠ blocked_ips.conf not yet included` warning.
> The new Python script `hermes-services-apply.py` deploys to the correct path and is the preferred
> replacement. The pipeline scripts still call the legacy version.

## Verification

- Linux (6.8.0-generic): full pipeline runs, 14 IPs found, deployed, nginx reloaded ✅
- macOS Intel: path resolution order verified by fallback chain
- macOS ARM: path resolution order verified by fallback chain

## Files

- `src/scripts/nginx-threat-pipeline.sh` — the pipeline script (tracked in repo)
- `deploy/nginx/hermes-security-apply` — deploy script (already tracked)
- `src/scripts/nginx-security-scanner.sh` — daily scanner (already tracked)
