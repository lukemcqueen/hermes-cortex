# 🔒 Security Guide — Hermes Cortex

> **For everyone — from first-time users to system administrators.**
>
> This guide explains how to keep your Hermes Cortex installation secure.
> You don't need to be a security expert to follow it.

> **💡 This guide applies to the latest version of the installer.** Run `git pull` and re-run `install.sh` to apply all security fixes.

---

## Table of Contents

1. [Installation Security Checklist](#1-installation-security-checklist)
2. [Everyday Security Habits](#2-everyday-security-habits)
3. [Understanding Your System's Exposed Ports](#3-understanding-your-systems-exposed-ports)
4. [File Permissions — Who Can Read Your Files](#4-file-permissions--who-can-read-your-files)
5. [Secrets & Passwords — Where They Live](#5-secrets--passwords--where-they-live)
6. [Docker Security](#6-docker-security)
7. [Network & Firewall](#7-network--firewall)
   - [pf Firewall (packet filter)](#-advanced-pf-firewall-packet-filter)
   - [fail2ban — Auto-ban Attacks](#-fail2ban--auto-ban-brute-force-attacks)
8. [Recovery — What To Do If Something Goes Wrong](#8-recovery--what-to-do-if-something-goes-wrong)
9. [Security FAQ](#9-security-faq)
10. [Post-Install Security Hardening](#10-post-install-security-hardening)

---

## 1. Installation Security Checklist

✅ **The installer does these automatically.** But it's good to know what's happening:

- **Strong passwords** are generated for every service (Postgres, ClickHouse, Redis, MinIO, Langfuse)
- All passwords are stored in `~/langfuse/.env` — **readable only by you** (chmod 600)
- Hermes configuration files (`config.yaml`, `auth.json`, `.env`) are locked to your user only
- Ollama is configured to listen **only on your local machine** (not the network)

### What YOU should do after install:

1. **Enable your firewall** — see [Network & Firewall](#7-network--firewall)
2. **Back up your `.env` file** — `cp ~/langfuse/.env ~/langfuse/.env.backup`
3. **Read the rest of this guide** — especially the Everyday Security Habits section
4. **Set a passphrase on your SSH key** (if you use SSH) — `ssh-keygen -p -f ~/.ssh/id_ed25519`

---

## 2. Everyday Security Habits

### 🔑 The Golden Rules

| Rule | Why |
|------|-----|
| **Never share your `.env` file** | It contains all your service passwords |
| **Keep your computer updated** | macOS: System Settings → Software Update |
| **Don't disable your firewall** | See firewall section below |
| **Use a strong login password** | Your Mac password protects everything |
| **Log out when stepping away** | Lock screen: `Ctrl+Cmd+Q` |

### 🛡️ What NOT to do

| ❌ Don't | Instead |
|----------|---------|
| Share your `~/.hermes/` directory | Keep it private (already locked to you) |
| Expose ports to the internet | Use a VPN if you need remote access |
| Use default passwords | The installer generates strong ones |
| Commit `.env` files to git | The repo's `.gitignore` blocks them |
| Turn off FileVault (macOS) | Keep disk encryption enabled |

### 🔄 When to rotate (change) your passwords

The installer generates strong passwords. You only need to change them if:

- You suspect someone gained access to your computer
- You shared your `.env` file with someone
- You see unusual activity in your Langfuse traces

To rotate passwords:

```bash
# Generate new passwords
openssl rand -hex 20   # Postgres
openssl rand -hex 16   # ClickHouse
openssl rand -hex 32   # Redis, MinIO secret, encryption keys

# Update ~/langfuse/.env with new values
# Then restart Langfuse:
docker compose -f ~/hermes-cortex/ops/install/deploy/docker-compose.langfuse.yml down
docker compose -f ~/hermes-cortex/ops/install/deploy/docker-compose.langfuse.yml up -d
```

---

## 3. Understanding Your System's Exposed Ports

> **A "port" is like a door into your computer. Some doors should only open from inside your house.**

### 🚪 Ports that are SAFE (localhost only)

These services only listen on your own machine. Other computers on your network **cannot** reach them:

| Port | Service | Safe? |
|------|---------|-------|
| **8901** | Cortex Dashboard | ✅ Local only |
| **3000** | Langfuse Web UI | ✅ Local only |
| **5432** | PostgreSQL database | ✅ Local only |
| **6379** | Redis cache | ✅ Local only |
| **8123** | ClickHouse HTTP | ✅ Local only |
| **9000** | ClickHouse native | ✅ Local only |
| **9091** | MinIO Console | ✅ Local only |

### 🚪 Ports that are NOT safe

These services are accessible from other computers on your network:

> ⚠️ **On a home WiFi network**, this usually means only your family's devices can reach these. On **public WiFi** (coffee shop, hotel, airport), **anyone** on that network can try to connect.

| Port | Service | Risk | How to fix |
|------|---------|------|------------|
| **11434** | Ollama API | 🔴 **HIGH** — Anyone can run AI models | ✅ **Automatically secured by the installer** — bound to localhost |
| **8080** | nginx default | 🟡 MEDIUM — Shows server info | ✅ **Automatically secured by the installer** — tokens hidden |
| **13001** | Dashboard (via nginx) | 🟡 MEDIUM — Requires Basic Auth | Uses username/password |
| **13002** | Langfuse (via nginx) | 🟡 MEDIUM — Requires Basic Auth | Uses username/password |
| **9090** | MinIO S3 storage | 🟡 MEDIUM — Requires password | ✅ **Automatically secured by the installer** — strong password generated |

### 📋 Quick port check

To see what ports are open on your machine:

```bash
lsof -i -P | grep LISTEN
```

If you see `*:PORT` (with `*`), it's accessible to your network.
This is the expected nginx posture — all proxy listeners expose services
externally with SSL. Never use `localhost:PORT` or `127.0.0.1:PORT` for
nginx reverse proxy listeners.

---

## 4. File Permissions — Who Can Read Your Files

Hermes is designed to keep your data private by setting strict file permissions. Here's what you should know:

### ✅ Correctly locked (only you can read)

| File | Permission | Contains |
|------|-----------|----------|
| `~/.hermes/.env` | `-rw-------` (600) | API keys, tokens |
| `~/.hermes/auth.json` | `-rw-------` (600) | Auth tokens |
| `~/.hermes/config.yaml` | `-rw-------` (600) | Full configuration |
| `~/.hermes/state.db` | `-rw-------` (600) | All conversations |
| `~/langfuse/.env` | `-rw-------` (600) | Service passwords |
| `~/.ssh/` | `drwx------` (700) | SSH keys |
| `~/.ssh/id_ed25519` | `-rw-------` (600) | Private SSH key |
| `$NGINX_HTPASSWD` (Linux: `/etc/nginx/.htpasswd`, macOS: `/usr/local/etc/nginx/.htpasswd`) | `-rw-r-----` (640) | Web passwords |

### 🔍 How to check permissions

```bash
ls -la ~/.hermes/.env       # Should show: -rw-------
ls -la ~/.ssh/              # Should show: drwx------
ls -la ~/.hermes/state.db   # Should show: -rw-------
```

### 🛠️ How to fix incorrect permissions

```bash
chmod 600 ~/.hermes/state.db ~/.hermes/state.db-wal ~/.hermes/state.db-shm
chmod 600 ~/.hermes/logs/*.log
chmod 640 ${NGINX_HTPASSWD:-/usr/local/etc/nginx/.htpasswd}     # Linux: /etc/nginx/.hermes-htpasswd
```

---

## 5. Secrets & Passwords — Where They Live

### 🗺️ Map of secret locations

| What | Where | Format |
|------|-------|--------|
| **Langfuse passwords** | `~/langfuse/.env` | Key=Value pairs |
| **Hermes API keys** | `~/.hermes/.env` | Key=Value pairs |
| **Auth tokens** | `~/.hermes/auth.json` | JSON |
| **Web passwords** | `$NGINX_HTPASSWD` (Linux: `/etc/nginx/.htpasswd`, macOS: `/usr/local/etc/nginx/.htpasswd`) | Hashed passwords |
| **SSH keys** | `~/.ssh/id_ed25519` | Private key |
| **GitHub token** | `~/.config/gh/hosts.yml` | OAuth token |

### 📝 Best practices

1. **Back up your `.env` file** — without it, you can't restart Langfuse
2. **Don't email your secrets** — use a password manager (macOS Keychain works great)
3. **Don't paste passwords into chat** — not even in screenshots
4. **Don't commit `.env` files to git** — the installer blocks this automatically

### 🔐 How passwords are generated

The installer uses `openssl rand -hex N` which creates cryptographic-quality random strings. These are:

- **Postgres password**: 20 hex bytes (160 bits of entropy)
- **ClickHouse password**: 16 hex bytes (128 bits)
- **Redis auth**: 32 hex bytes (256 bits)
- **MinIO secret**: 32 hex bytes (256 bits)
- **Langfuse encryption key**: 32 hex bytes (256 bits)

These are **stronger than typical human-chosen passwords**. You don't need to change them unless you suspect a breach.

---

## 6. Docker Security

If you're using the Langfuse Docker stack (server profile), here's what you should know:

### ✅ Secured by default

- All Docker data uses named volumes (not host folders)
- Postgres, Redis, and ClickHouse have strong passwords
- Services only listen on `localhost` (127.0.0.1)
- Langfuse telemetry is disabled (no data sent to external servers)
- nginx rate-limits login attempts to prevent brute-force attacks

### ⚠️ Caveats

- Containers run with default Docker security (not rootless)
- No automatic image updates — run `docker compose pull` periodically
- Docker Desktop runs as a background service (launched at login)

### 🔄 Updating Docker images

```bash
cd ~/langfuse  # or wherever your docker-compose.yml lives
docker compose pull
docker compose down
docker compose up -d
```

---

## 7. Network & Firewall

> **Your firewall is like a bouncer at a club — it decides who gets in.**

### Checking if your firewall is on

**macOS:**
```bash
/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate
# Should say: "Firewall is enabled."
```

**Linux (if applicable):**
```bash
sudo ufw status
# Should say: "Status: active"
```

### What the firewall does

When enabled, your firewall:
- ✅ Blocks incoming connection attempts by default
- ✅ Hides your computer from network scanners (stealth mode)
- ✅ Only allows specific apps to receive connections (nginx, Python, etc.)
- ❗ **Does NOT block outgoing connections** (you can still browse the web)

### Setting up the firewall

**macOS:**
1. Open **System Settings → Network → Firewall**
2. Click **Turn On**
3. Click **Options** and enable **"Enable stealth mode"**
4. Block all incoming connections except for essential services

**Or use the command line:**
```bash
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --setglobalstate on
sudo /usr/libexec/ApplicationFirewall/socketfilterfw --setstealthmode on
```

### 🛡️ Advanced: pf Firewall (packet filter)

The built-in macOS firewall only controls **application-level** access. For defense-in-depth, use **pf (packet filter)** — the kernel-level firewall that macOS uses internally. This is **not** installed by default but recommended for server deployments.

**What pf adds over the app firewall:**
- Default-deny rules — block everything except explicitly allowed ports
- Port ranges — open only the ports you need (e.g., `13001-13099`)
- Rate limiting — prevent brute-force attacks on SSH or web auth
- fail2ban integration — auto-block IPs that trigger too many auth failures

**Basic pf setup:**

Create `/etc/pf.anchors/hermes`:
```conf
# ── Hermes Cortex pf rules ──────────────────────────────
# Default: deny all incoming connections
block in log all

# ── Allow established connections ──
pass in proto tcp from any to any keep state

# ── Local loopback — unrestricted ──
pass quick on lo0 all

# ── Allowed external services ──
pass in proto tcp to any port 22           # SSH (rate-limited below)
pass in proto tcp to any port 990          # FTPS (if needed)

# ── nginx proxy ports (web access via HTTPS) ──
pass in proto tcp to any port 13001:13099

# ── SSH rate limiting (max 10 conn, max 5 in 60s) ──
pass in proto tcp to any port 22 \
    max-src-nodes 10 \
    max-src-states 5 \
    max-src-conn-rate 5/60 \
    overload <bruteforce> flush global

# ── fail2ban integration ──
anchor "f2b/*"

# ── Block overloaded IPs ──
block drop log quick from <bruteforce> to any
```

Load it:
```bash
# Include in pf.conf:
echo 'anchor "hermes"' | sudo tee -a /etc/pf.conf
echo 'load anchor "hermes" from "/etc/pf.anchors/hermes"' | sudo tee -a /etc/pf.conf

# Apply:
sudo pfctl -f /etc/pf.conf

# Enable pf (starts at boot on macOS):
sudo pfctl -e
```

**Verify pf is loaded:**
```bash
sudo pfctl -s rules
sudo pfctl -s info
```

> ⚠️ **Warning:** pf rules apply immediately. Always test via a second SSH session before closing your current one, or you could lock yourself out.

### 🤖 fail2ban — Auto-ban Brute-Force Attacks

fail2ban monitors log files for repeated auth failures and temporarily bans offending IPs using pf anchors. It provides an extra layer of defense beyond nginx's built-in rate limiting.

**What it protects:**

| Jail | Trigger | Ban escalation |
|------|---------|---------------|
| `nginx-http-auth` | Multiple Basic Auth failures | 1h → 2h → 4h → 4wk |
| `nginx-limit-req` | Exceeding nginx rate limits | 1h → 2h → 4h → 4wk |
| `nginx-botsearch` | Probing admin/exploit URLs | 1h → 2h → 4h → 4wk |
| `nginx-bad-request` | Malformed HTTP requests | 1h → 2h → 4h → 4wk |

**Installation:**
```bash
# Install fail2ban
brew install fail2ban

# Create jail.local with macOS paths
cat > /usr/local/etc/fail2ban/jail.local << 'F2B'
[DEFAULT]
ignoreip = 127.0.0.1/8 ::1
bantime = 1h
findtime = 10m
maxretry = 5
banaction = pf
banaction_allports = pf
action = %(action_)s

[nginx-http-auth]
enabled = true
logpath = /usr/local/var/log/nginx/error.log

[nginx-limit-req]
enabled = true
logpath = /usr/local/var/log/nginx/error.log

[nginx-botsearch]
enabled = true
logpath = /usr/local/var/log/nginx/access.log

[nginx-bad-request]
enabled = true
logpath = /usr/local/var/log/nginx/error.log
F2B

# Ensure pf anchor includes fail2ban
echo 'anchor "f2b/*"' | sudo tee -a /etc/pf.anchors/hermes

# Create fail2ban run directory
sudo mkdir -p /usr/local/var/lib/fail2ban

# Start fail2ban
sudo launchctl load /usr/local/opt/fail2ban/homebrew.mxcl.fail2ban.plist

# Verify
sudo fail2ban-client status
```

**Check banned IPs:**
```bash
sudo fail2ban-client status nginx-http-auth
sudo pfctl -a "f2b/nginx-http-auth" -s table
```

---

### 🔐 SSL/TLS Certificates — Let's Encrypt & Certbot

> **Critical:** SSL certificates and private keys are **machine-local secrets**. They must **never** enter the hermes-cortex repo (`.gitignore` blocks `*.pem`, `*.key`, `*.crt`, `*.p12`).

#### How It Works

- **Certbot** (Let's Encrypt client) manages certs via systemd timer (`certbot.timer`) — renews twice daily automatically
- **Cert locations:** `/etc/letsencrypt/live/<domain>/fullchain.pem` (cert) + `privkey.pem` (private key)
- **Private key permissions:** `root:root 600` — only root can read
- **nginx terminates TLS** — upstream services (Hermes, Langfuse, dashboard) receive plain HTTP on localhost

#### Per-Machine Strategy (Default & Recommended)

**Each agent machine runs its own Certbot.** This is the safest approach because:

1. Let's Encrypt validates domain control per-server (HTTP-01 challenge) — copying certs between machines breaks validation
2. Private keys never leave the machine — zero distribution risk
3. Renewal is fully automatic and isolated per machine
4. No rate-limit sharing across machines

```bash
# On each machine needing HTTPS:
sudo apt-get update && sudo apt-get install certbot python3-certbot-nginx
sudo certbot --nginx -d your.domain.com
```

#### When to Use Wildcard Certs (Advanced)

Only if you have **many subdomains on the same domain** managed by the same team:

```bash
# Requires DNS-01 challenge (DNS API credentials needed)
certbot certonly --dns-cloudflare -d "*.yourdomain.com"
```

**Risks of wildcard:**
- Single private key protects all subdomains (larger blast radius if compromised)
- Requires DNS API tokens (additional secret to protect)
- Let's Encrypt rate limits are stricter for wildcard certs

#### Secure Copy (Exceptional Cases Only)

If you must copy certs between machines (e.g., disaster recovery):

```bash
# On SOURCE machine (encrypt with age):
tar -cz /etc/letsencrypt/live/yourdomain.com | age -r <recipient-pubkey> > certs.tar.gz.age

# On DEST machine (decrypt):
age -d -i <private-key> certs.tar.gz.age | tar -xz -C /
```

**Audit requirement:** Log who copied, when, which cert, and why.

#### Monitoring & Alerting

Auto-remediation (Phase 3) checks cert expiry daily:

| Threshold | Action |
|-----------|--------|
| < 30 days | Warning logged |
| < 7 days | Critical alert sent |
| Expired | Emergency alert + auto-remediation attempts renew |

```bash
# Manual check:
certbot certificates
openssl x509 -enddate -noout -in /etc/letsencrypt/live/yourdomain.com/fullchain.pem
```

#### Emergency: Compromised or Expired Cert

```bash
# 1. Revoke (if compromised):
sudo certbot revoke --cert-path /etc/letsencrypt/live/yourdomain.com/fullchain.pem

# 2. Re-issue (Certbot keeps archive of old certs):
sudo certbot certonly --nginx -d yourdomain.com --force-renewal

# 3. Reload nginx:
sudo nginx -t && sudo nginx -s reload
```

#### Repo Boundaries

| In hermes-cortex (public) | Machine-local (private) |
|---------------------------|-------------------------|
| `hermes-services.conf` with commented SSL placeholders | `/etc/letsencrypt/` — all certs & keys |
| Docs explaining how to enable SSL | `~/langfuse/.env` — service passwords |
| `.gitignore` blocking `*.pem`, `*.key` | SSH keys, API tokens |

---

### 🛡️ On public WiFi (coffee shop, airport, hotel)

1. ✅ **Keep your firewall on** at all times
2. ✅ **Don't start Docker** unless you need it (stop with `launchctl bootout gui/$(id -u)/com.docker.docker`)
3. ✅ **Use a VPN** if you need to access your Hermes remotely
4. ✅ **Turn off SSH** if you don't need it: System Settings → Sharing → Remote Login → Off
5. ❌ **Don't open ports to the internet** unless you really know what you're doing

---

## 8. Recovery — What To Do If Something Goes Wrong

> **📖 Also see [`docs/troubleshooting.md`](./troubleshooting.md)** for many common issues and step-by-step fixes covering Docker, Dashboard, install, nginx, memory, Langfuse data, and Linux.

### 🚨 I think someone accessed my Hermes

1. **Disconnect from the internet** — unplug ethernet or turn off WiFi
2. **Change ALL passwords** — run the installer again or manually update `~/langfuse/.env`
3. **Rotate API keys** — regenerate Telegram bot token, Langfuse keys, etc.
4. **Check the logs** — `cat ~/.hermes/logs/gateway.log`
5. **Scan for unauthorized access** — `last` shows recent logins

### 🔑 I lost my `.env` file

1. **Check backups** — do you have `~/langfuse/.env.backup`?
2. **Re-run the installer** — it regenerates all passwords (services need restart)
3. **If you remember any passwords**, write them down first

### 🐳 Docker won't start

```bash
# Check Docker Desktop is running
launchctl list | grep docker

# Restart Docker
launchctl kickstart gui/$(id -u)/com.docker.docker

# Check container status
docker ps -a

# Restart Langfuse stack
docker compose -f ~/hermes-cortex/ops/install/deploy/docker-compose.langfuse.yml restart
```

### 💻 I can't access the Dashboard

```bash
# Check if the dashboard is running
curl -s http://localhost:8901/api/health

# Restart the dashboard
launchctl kickstart gui/$(id -u)/com.hermes.cortex-dashboard

# Check nginx
nginx -t && nginx -s reload
```

---

## 9. Security FAQ

### "Is my data safe if my computer is stolen?"

If you have **FileVault enabled** (macOS full-disk encryption):
- ✅ Your Hermes data is encrypted when the computer is off
- ❗ But if the computer is awake and unlocked, the thief has full access

**What to do:**
1. Change all passwords immediately from another device
2. Revoke the Telegram bot token
3. Remove authorized SSH keys from your servers

### "Should I use a VPN?"

Only if you need to access your Hermes from outside your home network. For local-only use, a properly configured firewall is sufficient.

### "Can I run Hermes on a public cloud server?"

Yes, but you MUST:
1. Set up a proper firewall (allow only your IP)
2. Use TLS/SSL certificates (Let's Encrypt is free)
3. Enable all authentication (nginx Basic Auth + Langfuse login)
4. Never expose Ollama to the internet

### "Does Hermes send my data anywhere?"

- **Ollama**: May send anonymous telemetry to Google Cloud (can be disabled with `OLLAMA_DEBUG=1`)
- **Langfuse**: Telemetry is disabled by default now
- **Hermes Agent**: Connects to Telegram and OpenAI/xAI/Anthropic APIs you configure
- **This repo**: No telemetry — it's just files on your computer

### "How do I update securely?"

```bash
cd ~/hermes-cortex
git pull
bash install.sh  # Safe to re-run — it's idempotent
```

The installer preserves your existing passwords (doesn't overwrite `.env` files).

---

## 10. Post-Install Security Hardening

The installer covers the basics. For a **production-ready security posture**, prompt your Hermes agent with any of these:

### 10.1 Set up nginx SSL (external access only)

**Prompt your agent:** "Set up external HTTPS access via nginx with Let's Encrypt"

**What your agent should do:**
Configures nginx to listen with SSL on external ports:
- Each server block uses `listen PORT ssl;` (external, SSL) — never `127.0.0.1:PORT`
- SSL certs from Let's Encrypt (or set `CORTEX_SSL_CERT_PATH` in `~/.hermes/hermes-cortex.env`)
- Basic Auth on all non-health endpoints
- The health endpoint (:xx007) has no auth for Moses/Esther polling

Configure TLS with Let's Encrypt via certbot. Moses/Esther pull certs from Joseph's server — do not generate local certs.

### 10.2 Harden nginx

**Prompt your agent:** "Harden my nginx — rate limits, security headers, connection limits"

**What your agent should do:**
- Add rate limit zones to the `http` block: 20 req/s general, 5 req/s auth, burst
- Add connection limit zone: 10 connections per IP
- Add security headers: X-Frame-Options, X-Content-Type-Options, X-XSS-Protection, Referrer-Policy
- Hide nginx version (`server_tokens off`)
- Harden buffers and timeouts
- Test config with `nginx -t` and reload

### 10.3 Set up pf firewall

**Prompt your agent:** "Set up the pf firewall with default-deny rules"

**What your agent should do:**
1. Create `/etc/pf.anchors/hermes` with default-deny, allow only ports 22 (SSH, rate-limited), 990 (FTPS, optional), 13001-13099 (nginx proxies)
2. Add SSH rate limiting: max 5 connections in 60 seconds per source
3. Add fail2ban anchor: `anchor "f2b/*"`
4. Append include lines to `/etc/pf.conf`
5. Load with `sudo pfctl -f /etc/pf.conf && sudo pfctl -e`
6. Verify with `sudo pfctl -s rules`

### 10.4 Install fail2ban

**Prompt your agent:** "Install and configure fail2ban with 4 nginx jails"

**What your agent should do:**
1. Install fail2ban via Homebrew
2. Create `/usr/local/etc/fail2ban/jail.local` with 4 jails:
   - `nginx-http-auth` — Basic Auth brute force, escalates 1h→2h→4h→4wk
   - `nginx-limit-req` — Rate limit violations
   - `nginx-botsearch` — Admin/exploit URL probing
   - `nginx-bad-request` — Malformed HTTP requests
3. Use `pf` as the ban action (creates pf anchor)
4. Create the run directory and start the service
5. Verify all 4 jails are active

### 10.5 Verify your security posture

**Prompt your agent:** "Run a security posture check"

**What your agent should do:**
Check each of these and report status:
1. Firewall active: `sudo pfctl -s info | grep "Status"`
2. Only expected ports open: `lsof -i -P | grep LISTEN` (should show 22, 990, 13001-13099, and localhost services)
3. Ollama is localhost-only: `lsof -iTCP:11434 -sTCP:LISTEN -P -n` (should show `localhost`, not `*`)
4. fail2ban jails active: `sudo fail2ban-client status` (should list 4 jails)
5. nginx config valid: `nginx -t`
6. Secrets locked down: check permissions on `~/langfuse/.env`, `~/.hermes/.env`, `~/.ssh/`

---

## Quick Reference

| Task | Command |
|------|---------|
| Check firewall | `/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate` |
| Check open ports | `lsof -i -P \| grep LISTEN` |
| Check file permissions | `ls -la ~/.hermes/.env` |
| View Langfuse credentials | `cat ~/langfuse/.env` (but don't share!) |
| Restart Langfuse | `docker compose -f ~/hermes-cortex/ops/install/deploy/docker-compose.langfuse.yml restart` |
| View system logs | `cat ~/.hermes/logs/gateway.log` |
| Check Ollama status | `launchctl list \| grep ollama` |
| Lock a file to your user | `chmod 600 filename` |

---

> **Last updated:** June 2026
>
> **Questions?** Open an issue on GitHub or ask in the Hermes community.
>
> **Found a security issue?** Please report it privately — see the repo's security policy.
