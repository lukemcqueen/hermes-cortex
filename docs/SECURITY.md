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
8. [Recovery — What To Do If Something Goes Wrong](#8-recovery--what-to-do-if-something-goes-wrong)
9. [Security FAQ](#9-security-faq)

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
docker compose -f ~/hermes-cortex/docker-compose.langfuse.yml down
docker compose -f ~/hermes-cortex/docker-compose.langfuse.yml up -d
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
| **11002** | Langfuse (via nginx) | 🟡 MEDIUM — Requires password | Uses Basic Auth (username/password) |
| **11003** | Dashboard (via nginx) | 🟡 MEDIUM — Requires password | Uses Basic Auth (username/password) |
| **9090** | MinIO S3 storage | 🟡 MEDIUM — Requires password | ✅ **Automatically secured by the installer** — strong password generated |

### 📋 Quick port check

To see what ports are open on your machine:

```bash
lsof -i -P | grep LISTEN
```

If you see `*:PORT` (with `*`), it's accessible to your network.
If you see `localhost:PORT` or `127.0.0.1:PORT`, it's local-only.

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
| `/usr/local/etc/nginx/.htpasswd` | `-rw-r-----` (640) | Web passwords |

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
chmod 640 /usr/local/etc/nginx/.htpasswd
```

---

## 5. Secrets & Passwords — Where They Live

### 🗺️ Map of secret locations

| What | Where | Format |
|------|-------|--------|
| **Langfuse passwords** | `~/langfuse/.env` | Key=Value pairs |
| **Hermes API keys** | `~/.hermes/.env` | Key=Value pairs |
| **Auth tokens** | `~/.hermes/auth.json` | JSON |
| **Web passwords** | `/usr/local/etc/nginx/.htpasswd` | Hashed passwords |
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

### 🛡️ On public WiFi (coffee shop, airport, hotel)

Your machine is more exposed on public networks. Take extra precautions:

1. ✅ **Keep your firewall on** at all times
2. ✅ **Don't start Docker** unless you need it (stop with `launchctl bootout gui/$(id -u)/com.docker.docker`)
3. ✅ **Use a VPN** if you need to access your Hermes remotely
4. ✅ **Turn off SSH** if you don't need it: System Settings → Sharing → Remote Login → Off
5. ❌ **Don't open ports to the internet** unless you really know what you're doing

---

## 8. Recovery — What To Do If Something Goes Wrong

> **📖 Also see [`docs/troubleshooting.md`](./troubleshooting.md)** for 17 common issues and step-by-step fixes covering Docker, Dashboard, install, nginx, memory, and Linux.

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
docker compose -f ~/hermes-cortex/docker-compose.langfuse.yml restart
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

## Quick Reference

| Task | Command |
|------|---------|
| Check firewall | `/usr/libexec/ApplicationFirewall/socketfilterfw --getglobalstate` |
| Check open ports | `lsof -i -P \| grep LISTEN` |
| Check file permissions | `ls -la ~/.hermes/.env` |
| View Langfuse credentials | `cat ~/langfuse/.env` (but don't share!) |
| Restart Langfuse | `docker compose -f ~/hermes-cortex/docker-compose.langfuse.yml restart` |
| View system logs | `cat ~/.hermes/logs/gateway.log` |
| Check Ollama status | `launchctl list \| grep ollama` |
| Lock a file to your user | `chmod 600 filename` |

---

> **Last updated:** June 2026
>
> **Questions?** Open an issue on GitHub or ask in the Hermes community.
>
> **Found a security issue?** Please report it privately — see the repo's security policy.
