---
name: security-audit
version: 2.3.0
category: devops
description: >-
  Full-pipeline Ubuntu/Debian server security + cleanup. Audits DDoS
  protection, anti-spam, system hardening, kernel, firewall, SSH, nginx,
  Docker, fail2ban. Then produces actionable remediation, reboot
  survivability check, and post-remediation disk optimization (Docker
  prune, journal trim, orphaned packages, apt cache). Use when the user
  says 'security audit', 'harden the server', 'check our defenses',
  'any cleanup we can do', or asks about any single hardening area.
---

# Security Audit — Ubuntu/Debian Server

> **Trigger:** User says "security audit", "harden the server", "check our defenses", "DDoS protection", "anti-spam", "lock down", "any cleanup we can do", "server optimization", or asks about any single hardening area.
>
> **Works as a full pipeline:** Phase 1-10 (audit) → Phase 11 (remediation) → Phase 12 (reboot verify) → Phase 14 (cleanup/optimization). When the user starts with "check
> <one area>", run only that phase, then offer the full pipeline.

## Audit Phases (1–10)

| Phase | Area | What's checked |
|-------|------|----------------|
| 1 | DDoS protection | nginx rate limits, fail2ban jails, connection limits |
| 2 | Anti-spam | Postfix/Rspamd config if present, open relays |
| 3 | System hardening | `/etc/sysctl.conf` (net.ipv4 defaults), kernel params |
| 4 | Kernel | `uname -r`, security patches, `/proc/sys` tunables |
| 5 | Firewall | ufw/iptables rules, default policy, open ports |
| 6 | SSH | `sshd_config` (root login, password auth, PermitRootLogin), key-only |
| 7 | nginx | TLS config, exposed admin panels, header security |
| 8 | Docker | container exposure, privileged containers, image age |
| 9 | fail2ban | jail status, ban counts, ignoreip correctness |
| 10 | Users & files | sudoers, world-writable files, SUID binaries |

Each phase ends with a **verdict + severity** (🔴 critical / 🟡 warn / ✅ ok)
and the evidence command output that produced it.

## Remediation (Phase 11)

For every 🔴/🟡 finding, produce the exact remediation command, its impact
(restart required? downtime?), and apply it after confirmation. Key remediations:

```bash
# SSH hardening
sed -i 's/^#*PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config
sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
systemctl reload ssh

# Kernel hardening (apply to /etc/sysctl.conf for persistence)
net.ipv4.conf.all.rp_filter = 1
net.ipv4.conf.all.accept_redirects = 0
net.ipv6.conf.all.accept_redirects = 0
```

## Reboot Survivability (Phase 12)

Check that every security setting survives a reboot:

```bash
# Verify persistent config (not runtime-only)
sysctl -p 2>&1 | head -20          # should show applied values
# Confirm fail2ban/ufw/nginx are enabled at boot
systemctl is-enabled fail2ban ufw nginx
```

## Cleanup / Optimization (Phase 14)

After remediation, reclaim disk and tidy the system:

```bash
# Docker cleanup (idempotent, non-destructive by default)
docker system prune -f --filter "until=168h"   # images older than 7d

# Journal trim
journalctl --vacuum-time=7d

# Orphaned packages
apt-get autoremove --purge -y

# apt cache
apt-get clean
```

> **Unattended destructive actions default to no-op.** If any prune is
> ambiguous or could delete data the user didn't intend, stop and ask —
> disk pressure can be remediated; deleted data cannot.

## Reporting Format

Deliver a compact report:

```
## Security Audit — <host>
Phases run: 1-10 (audit) + 11 (remediation) + 14 (cleanup)
🔴 N critical | 🟡 M warnings | ✅ K clean

### Critical findings
- <finding> — evidence: <command output snippet> — fix: <command>

### Applied remediations
- <what was changed> — verified: <post-change output>
```

## Related
- `server-hardening` — five-layer hardening methodology (complementary)
- `linux-server-hardening` — tiered hardening with priorities
- `nginx-security-pipeline` — nginx-specific defense
- `threat-defense-pipeline` — fail2ban + nginx blocking layer
