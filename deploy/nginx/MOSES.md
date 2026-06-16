# 🛡️ Moses: Nginx Security Pipeline — Instructions

## Changes Deployed

| File | What |
|------|------|
| `deploy/nginx/blocked_ips.add` | 11 storage scanner IPs (34.x, 136.x, etc.) |
| `deploy/nginx/nginx-badbots.conf` | fail2ban filter — extended archive types + `/storage/` path |
| `deploy/nginx/README.md` | Human setup + daily ops guide |
| `deploy/nginx/hermes-security-apply` | Atomic deploy script (already installed at `/usr/local/sbin/`) |
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
         ├── Appends new IPs (skip dups)
         ├── Installs fail2ban filter
         ├── nginx -t (validate)
         └── Reloads fail2ban + nginx
```

The daily scanner feeds back into `blocked_ips.add`, creating a closed loop:
**Logs → Detect → Append → Deploy → Protect**.
