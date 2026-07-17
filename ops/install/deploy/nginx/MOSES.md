# 🛡️ Moses: Nginx Security Pipeline — Instructions

## Changes Deployed

| File | What |
|------|------|
| `ops/install/deploy/nginx/blocked_ips.add` | 11 storage scanner IPs (34.x, 136.x, etc.) |
| `ops/install/deploy/nginx/nginx-badbots.conf` | fail2ban filter — extended archive types + `/storage/` path |
| `ops/install/deploy/nginx/README.md` | Human setup + daily ops guide |
| `ops/install/deploy/nginx/install-nginx-full.sh` | **Legacy** bash deploy script — now superseded by `hermes-services-apply.py` |
| `ops/install/deploy/nginx/hermes-services-apply.py` | **Primary** Python deploy script — auto-SSL, port prefix, allow-ips-manual |
| `ops/install/deploy/nginx/fix-blocked-ips.py` | Helper — regenerates `blocked_ips.conf` if corrupted with bare IPs |
| `ops/scripts/nginx-security-scanner.sh` | Daily scanner — auto-detect new IPs, auto-deploy |
| `sudoers.d/hermes-security` | Passwordless sudo for deploy script + nginx + fail2ban |

## What You Need To Do

### 1. Push to hermes-cortex

```bash
cd ~/hermes-cortex
git push origin main
```

### 2. Broadcast to all agents

Share this workflow so every peer can deploy security:

> **Nginx security pipeline deployed.** Run `python3 ~/hermes-cortex/ops/install/deploy/nginx/hermes-services-apply.py` to deploy.
> **Setup for a new machine:** Copy the env template, install the legacy script (if needed), see `ops/install/deploy/nginx/README.md`.
> **Add new blocks:** Append bare IPs to `ops/install/deploy/nginx/blocked_ips.add`, update `nginx-badbots.conf` filters, re-run the script.
> **Manual allow list:** Add `allow IP;` to `/etc/nginx/allow-ips-manual.conf` on each machine to prevent blocks.

### 3. Create the daily cron job

```bash
# cron name=daily-nginx-scanner schedule="0 6 * * *" script=nginx-security-scanner.sh no_agent=true deliver=local
```

This runs at 6 AM daily, scans logs for new suspect IPs, and auto-deploys if it finds any. Silent when clean.

### 4. Copy the daily scanner script

If any peer needs it:

```bash
cp ~/hermes-cortex/ops/scripts/manage/nginx-security-scanner.sh ~/.hermes/scripts/
chmod +x ~/.hermes/scripts/nginx-security-scanner.sh
```

## How to Deploy

### Preferred: Python script

```bash
cd ~/hermes-cortex
python3 ops/install/deploy/nginx/hermes-services-apply.py --dry-run  # preview
python3 ops/install/deploy/nginx/hermes-services-apply.py             # deploy
```

### Legacy (used by cron pipeline)

```bash
sudo /usr/local/sbin/install-nginx-full.sh
```

**Known false positive:** The legacy script prints `⚠ blocked_ips.conf not yet included in nginx config`.
This happens because the script writes to `/etc/nginx/servers/` (not `sites-available/`) and checks a
path it doesn't update. The live config is correct. Use the Python script to avoid this warning.

## Updating the System Script (Legacy)

Only needed if your pipeline cron references `/usr/local/sbin/install-nginx-full.sh`:

```bash
sudo cp ~/hermes-cortex/ops/install/deploy/nginx/install-nginx-full.sh /usr/local/sbin/install-nginx-full.sh
sudo chmod 755 /usr/local/sbin/install-nginx-full.sh
```

### Verify the update

```bash
# Python dry-run shows what would change
python3 ~/hermes-cortex/ops/install/deploy/nginx/hermes-services-apply.py --dry-run
# Confirm nginx config is valid
sudo nginx -t && echo "✓ Config valid" || echo "✗ Config invalid"
```

## Manual IP Allow List

To prevent specific IPs from being blocked (e.g. your office, a partner service):

```bash
echo "allow YOUR.IP.HERE;" | sudo tee -a /etc/nginx/allow-ips-manual.conf
sudo nginx -s reload
```

This file is included BEFORE `blocked_ips.conf` in the nginx config, so allow rules
take priority. The deploy pipeline also strips these IPs from the block list.
The file is NOT in git — manage locally on each machine.

## Architecture Notes

```
blocked_ips.add (input)    nginx-badbots.conf (input)    allow-ips-manual.conf (override)
         │                          │                              │
         └───────┬──────────────────┘                              │
                 │                        Strips allow-listed IPs  │
    install-nginx-full.sh ──────────────────────────────────────────┘
         │
         ├── Backs up old configs
         ├── Deploys nginx + zone-defs
         ├── Deduplicates includes
         ├── Appends new IPs (batch dedup) — validates IPv4, rejects private,
         │   skips dups via `grep -vxF -f`, and strips allow-listed IPs
         ├── Installs fail2ban filter
         ├── nginx -t (validate)
         └── Reloads fail2ban + nginx
```

The daily scanner feeds back into `blocked_ips.add`, creating a closed loop:
**Logs → Detect → Append → Deploy → Protect**.

**Private IP filter:** All collection paths (nginx log scan, fail2ban extraction,
agent-submitted IPs) reject RFC 1918 private ranges (127.x, 10.x, 172.16-31.x,
192.168.x, 0.x, 169.254.x, 224.x, 240.x). This was added 2026-07-07 after
fail2ban banned a gateway IP through NAT, contaminating the blocklist.

**Important:** The deploy script APPENDS to `blocked_ips.conf` — it does not regenerate
the file from scratch. If `blocked_ips.conf` gets corrupted (e.g. bare IPs instead of
`deny <ip>;`), it must be fixed manually or via the Python fix script before the deploy
script can run successfully.
