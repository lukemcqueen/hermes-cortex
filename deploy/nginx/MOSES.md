# 🛡️ Moses: Nginx Security Pipeline — Instructions

## Changes Deployed

| File | What |
|------|------|
| `deploy/nginx/blocked_ips.add` | 11 storage scanner IPs (34.x, 136.x, etc.) |
| `deploy/nginx/nginx-badbots.conf` | fail2ban filter — extended archive types + `/storage/` path |
| `deploy/nginx/README.md` | Human setup + daily ops guide |
| `deploy/nginx/hermes-security-apply` | Atomic deploy script (source — install to `/usr/local/sbin/`) |
| `deploy/nginx/fix-blocked-ips.py` | Helper — regenerates `blocked_ips.conf` if corrupted with bare IPs |
| `src/scripts/nginx-security-scanner.sh` | Daily scanner — auto-detect new IPs, auto-deploy |
| `sudoers.d/hermes-security` | Passwordless sudo for deploy script + nginx + fail2ban |

## What You Need To Do

### 1. Push to agent-cortex

```bash
cd ~/hermes-cortex
git push origin main
```

### 2. Broadcast to all agents

Share this workflow so every peer can deploy security:

> **Nginx security pipeline deployed.** Run `sudo /usr/local/sbin/hermes-security-apply` to deploy.
> **Setup for a new machine:** Install the script + sudoers entry (see `deploy/nginx/README.md`).
> **Add new blocks:** Append bare IPs to `deploy/nginx/blocked_ips.add`, update `nginx-badbots.conf` filters, re-run the script.

### 3. Create the daily cron job

```bash
# cron name=daily-nginx-scanner schedule="0 6 * * *" script=nginx-security-scanner.sh no_agent=true deliver=local
```

This runs at 6 AM daily, scans logs for new suspect IPs, and auto-deploys if it finds any. Silent when clean.

### 4. Copy the daily scanner script

If any peer needs it:

```bash
cp ~/hermes-cortex/src/scripts/nginx-security-scanner.sh ~/.hermes/scripts/
chmod +x ~/.hermes/scripts/nginx-security-scanner.sh
```

## Updating the Deploy Script

The source of truth is in the repo at `deploy/nginx/hermes-security-apply`.
The installed copy at `/usr/local/sbin/hermes-security-apply` must be kept in sync.

### Install or update (requires sudo)

```bash
sudo cp ~/hermes-cortex/deploy/nginx/hermes-security-apply /usr/local/sbin/hermes-security-apply
sudo chmod 755 /usr/local/sbin/hermes-security-apply
# Verify the script runs
sudo /usr/local/sbin/hermes-security-apply
```

If the script fails with `nginx: [emerg] unexpected end of file` in `blocked_ips.conf`,
the config has bare IPs (missing `deny ... ;` wrapper). Fix it:

```bash
# Regenerate blocked_ips.conf from blocked_ips.add
python3 ~/hermes-cortex/deploy/nginx/fix-blocked-ips.py
sudo cp /tmp/blocked_ips.conf.new /etc/nginx/blocked_ips.conf      # Linux
# sudo cp /tmp/blocked_ips.conf.new /usr/local/etc/nginx/blocked_ips.conf  # macOS
sudo /usr/local/sbin/hermes-security-apply
```

For cron/agent use, copy the fix script to `~/.hermes/scripts/`:
```bash
cp ~/hermes-cortex/deploy/nginx/fix-blocked-ips.py ~/.hermes/scripts/
```

### Verify the update

```bash
# Check installed file size matches repo
ls -la /usr/local/sbin/hermes-security-apply ~/hermes-cortex/deploy/nginx/hermes-security-apply
# Confirm nginx config is valid and reloaded
sudo nginx -t && echo "✓ Config valid" || echo "✗ Config invalid"
# Check blocked IPs are active
sudo nginx -T 2>/dev/null | grep 'deny ' | wc -l
```

## Architecture Notes

```
blocked_ips.add (input)    nginx-badbots.conf (input)
         │                          │
         └───────┬──────────────────┘
                 │
    sudo hermes-security-apply
         │
         ├── Backs up old configs
         ├── Deploys nginx + zone-defs
         ├── Deduplicates includes
         ├── Appends new IPs (skip dups) — wrapped as `deny <ip>;`
         ├── Installs fail2ban filter
         ├── nginx -t (validate)
         └── Reloads fail2ban + nginx
```

The daily scanner feeds back into `blocked_ips.add`, creating a closed loop:
**Logs → Detect → Append → Deploy → Protect**.

**Important:** The deploy script APPENDS to `blocked_ips.conf` — it does not regenerate
the file from scratch. If `blocked_ips.conf` gets corrupted (e.g. bare IPs instead of
`deny <ip>;`), it must be fixed manually or via the Python fix script before the deploy
script can run successfully.
