---
name: server-hardening
description: "Comprehensive security audit and hardening for Linux servers running web services (nginx, Docker, fail2ban, UFW). Five-layer methodology: network inventory → service config review → firewall/iptables audit → fail2ban/DDoS protection → OS sysctl hardening → Docker posture → file permissions."
version: 1.8.0
author: Hermes Agent
license: MIT
platforms: [linux]
metadata:
  hermes:
    tags: [security, audit, hardening, nginx, fail2ban, ufw, docker, iptables, sysctl]
    related_skills: [requesting-code-review, hermes-agent]
---

# Server Security Audit & Hardening

Systematic five-layer methodology for auditing and hardening a Linux server
running nginx-reverse-proxied web services (Langfuse, Dashboards, APIs) alongside
Docker containers and local LLM infrastructure (Ollama).

## When to Use

- User asks for a "security audit" or "security review" of the server
- User says "harden this server", "check our security posture", "lock things down"
- After any exposure incident or before exposing a new service publicly

## Layer 1 — Network Inventory

```bash
# What's listening and where
ss -tulnp

# What's publicly reachable (compare with firewall rules)
# External check from another host:
curl -sI --max-time 5 https://<host>/
```

Flag: any service bound to `0.0.0.0` that should be localhost-only
(Ollama, mycortex, dashboards without auth).

## Layer 2 — Service Config Review

```bash
# nginx: valid config, exposed locations, TLS
nginx -t
grep -rE "proxy_pass|listen|auth_basic" /etc/nginx/sites-enabled/ | head -40

# SSH: root login, password auth
grep -E "PermitRootLogin|PasswordAuthentication|PubkeyAuthentication" /etc/ssh/sshd_config
```

## Layer 3 — Firewall / iptables Audit

```bash
ufw status verbose 2>/dev/null || iptables -L -n --line-numbers | head -30
```

Verify:
- Default policy is **deny** (or ufw default deny incoming)
- Only needed ports open (22, 80, 443)
- Docker-published ports are considered — docker bypasses ufw by default
  unless `DOCKER_USER` chains are configured

## Layer 4 — fail2ban / DDoS Protection

```bash
fail2ban-client status
fail2ban-client status sshd
fail2ban-client status nginx-badbots
```

Verify jails are active with recent bans, `ignoreip` includes your allow-list
(see `sync-allow-ips-to-fail2ban`), and maxretry/bantime are sane.

## Layer 5 — OS sysctl Hardening

Apply and persist (`/etc/sysctl.conf`):

```ini
# IP spoofing / routing
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.default.rp_filter = 1
net.ipv4.conf.all.accept_redirects = 0
net.ipv6.conf.all.accept_redirects = 0

# SYN flood / resource exhaustion
net.ipv4.tcp_syncookies = 1
net.ipv4.tcp_syn_retries = 2
net.ipv4.tcp_synack_retries = 2
```

Apply: `sysctl -p`

## Layer 6 — Docker Posture

```bash
# Privileged containers
docker ps --format '{{.Names}} {{.Privileged}}' | grep true

# Exposed ports vs firewall
docker ps --format 'table {{.Names}}\t{{.Ports}}'

# Images up to date
docker images --format 'table {{.Repository}}\t{{.Tag}}\t{{.CreatedSince}}'
```

## Layer 7 — File Permissions

```bash
# World-writable sensitive files
find /etc /var/lib -type f -perm -o+w 2>/dev/null | head -20

# SUID binaries (should be a short, known list)
find / -type f -perm -4000 2>/dev/null | head -20

# Sensitive config permissions
ls -la /etc/nginx/allow-ips-manual.conf /etc/fail2ban/jail.local 2>/dev/null
```

## Remediation

For each finding: severity → exact fix → verification. Apply remediations
one at a time, verifying the service still works after each (nginx -t,
fail2ban-client status, health endpoint).

## Pitfalls

- ❌ **Hardening a live service blindly** — reload configs, test health, then
  move on. A hardened-but-down service is worse than an exposed one.
- ❌ **Docker ignores ufw by default** — container-published ports bypass the
  host firewall unless `iptables` DOCKER_USER chains are set.
- ❌ **Runtime-only sysctl** — without `/etc/sysctl.conf` persistence, all
  hardening evaporates on reboot.

## Related
- `security-audit` — the full 14-phase pipeline (audit → cleanup)
- `linux-server-hardening` — tiered hardening priorities
- `nginx-security-pipeline` — nginx defense-in-depth
- `sync-allow-ips-to-fail2ban` — allow-list sync
