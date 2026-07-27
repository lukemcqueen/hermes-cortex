---
name: threat-defense-pipeline
description: "Layered defense system: fail2ban jails + nginx IP blocking + daily auto-deploy pipeline. How to add blocked IPs, check jails, and deploy."
version: 1.0.0
author: Moses (hermes-cortex)
platforms: [linux, macos]
trigger: when adding blocked IPs, checking threat activity, or troubleshooting blocked connections
---

# Threat Defense Pipeline

## Overview

Hermes Cortex runs a **three-layer defense** against port scanning and brute force:

```
Layer 1: fail2ban (sshd + nginx-badbots jails)  → auto-bans at OS/nginx level
Layer 2: nginx-security-scanner (log scanner)    → finds suspect IPs in nginx logs
Layer 3: threat-pipeline cron (daily 5AM)        → deploys + commits blocked IPs
```

## How to Add a Blocked IP

The single source of truth is **`ops/install/deploy/nginx/blocked_ips.add`** in the hermes-cortex repo. One IP per line.

### Quick add (for agents with repo access):

```bash
cd ~/hermes-cortex
echo "1.2.3.4" >> ops/install/deploy/nginx/blocked_ips.add
```

### Commit and deploy immediately:

```bash
cd ~/hermes-cortex
git add ops/install/deploy/nginx/blocked_ips.add
# SKIP_SCORE=1 has been REMOVED. Use _create_gov_lock instead
# (see nginx-threat-pipeline.sh for the temp lock pattern)
git commit -m "auto: block <reason> [pipeline]"
# No SKIP_PRE_PUSH needed — the pipeline scripts create a temp
# governance lock before pushing (see nginx-threat-pipeline.sh)
git push origin main
```

Then deploy live:

```bash
# Deploy blocked IPs (minimal-root)
bash ~/.hermes/scripts/deploy-blocked-ips.sh
```

### OR let the daily pipeline handle it:

The pipeline runs at **05:00 KST daily**. It automatically:
1. Scans nginx logs for suspect IPs
2. Collects fail2ban bans
3. Adds new IPs to `blocked_ips.add`
4. Commits and pushes to GitHub
5. Deploys to nginx (reloads config)
6. Reloads fail2ban nginx-badbots jail

If the pipeline finds no new IPs, it stays silent (watchdog pattern).

## ⚠ Private IP Filtering (RFC 1918)

All three IP collection paths in the pipeline **reject private/reserved IPs**:

| Path | File | Filter |
|------|------|--------|
| nginx log scanner | `ops/scripts/manage/nginx-security-scanner.sh` | `^127.\|10.\|172.(16-31).\|192.168.\|0.\|169.254.\|224.\|240.` |
| fail2ban extraction (scanner) | `ops/scripts/manage/nginx-security-scanner.sh` | Same regex — added 2026-07-07 |
| fail2ban extraction (pipeline) | `ops/scripts/manage/nginx-threat-pipeline.sh` | `grep -vE` on private ranges — added 2026-07-07 |
| agent-submitted IPs | `ops/scripts/manage/nginx-threat-pipeline.sh` step 0 | Same `grep -vE` — added 2026-07-07 |
| Config generator | `ops/install/deploy/nginx/fix-blocked-ips.py` | `PRIVATE_RANGES` regex in `is_valid_public_ip()` |

**Why this matters:** fail2ban can ban a LAN IP (your gateway/router) when attackers hit your server through its NAT. Without filtering, the pipeline blindly adds gateway IPs to the blocklist. These filters prevent that.

**If you ever need to add a private IP to the blocklist** (unusual — only if nginx is behind an internal reverse proxy), add it to `/etc/nginx/allow-ips-manual.conf` instead to ensure it's never blocked.

## fail2ban Jails

| Jail | Target | Ban Action |
|------|--------|------------|
| `sshd` | SSH brute force | iptables ban |
| `nginx-badbots` | Bad bot HTTP traffic | iptables ban |

### Check jail status:

```bash
sudo fail2ban-client status                  # list all jails
sudo fail2ban-client status sshd             # sshd ban list
```

## Pipeline Self-Healing

The threat-pipeline script (`ops/scripts/manage/nginx-threat-pipeline.sh`) uses `deploy-blocked-ips.sh` for minimal-root deploy:
- Generates `blocked_ips.conf` from `blocked_ips.add` using `fix-blocked-ips.py` (no root)
- Deploys with a single tight `sudo cp` rule (one specific path only)
- Validates with `sudo nginx -t`, reloads with `sudo nginx -s reload`
- Git commits use a temp governance lock (see nginx-threat-pipeline.sh `_create_gov_lock` pattern) — no bypass flags needed
- Git pushes (SKIP_PRE_PUSH=1 has been removed — pre-push hook is mandatory)

## Manual Deploy (for agents with sudo access)

```bash
# Deploy blocked IPs (minimal-root — only needs sudo cp)
bash ~/.hermes/scripts/deploy-blocked-ips.sh

# Or from the repo directly:
bash ~/hermes-cortex/ops/scripts/manage/deploy-blocked-ips.sh
```

Generates `blocked_ips.conf` from `blocked_ips.add`, deploys with `sudo cp`,
validates with `nginx -t`, and reloads nginx. No broad sudo script needed.

## Architecture

```
     fail2ban ──> iptables ban (immediate)
         │
    nginx scanner ──> blocked_ips.add ──> pipeline ──> git commit/push
                                                    │
                                             install-nginx-full.sh
                                                    │
                                              nginx reload
                                              fail2ban reload
```
