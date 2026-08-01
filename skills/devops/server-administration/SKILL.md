---
name: server-administration
version: 1.10.0
category: devops
description: >-
  Ongoing IT & Security Administration for production Linux servers.
  Covers routine health checks, Docker container diagnosis, security tool
  verification, system resource monitoring, and the mindset of keeping
  services running and the system clean. Used as the daily-driver skill
  by the server's IT admin.
---

# Server Administration

> **Trigger:** User says "health check", "security posture", "how are things",
> "server status", "check the server", or any routine admin inquiry.
> Also triggered when the user clarifies their role as IT/admin and you need
> to adopt the admin mindset.

> **IT Admin Mindset:** Your priority is uptime first, security second,
> hygiene third. Production services must keep running. Diagnose before
> fixing. Check the impact of any change on running containers first.
> Report issues with severity levels so the admin can triage.

### Phase 0: Quick Health Triage

When the admin asks "how are things", run this compact sweep first:

```bash
# Load (1m/5m/15m)
uptime
# Disk
df -h / | tail -1
# Memory
free -h | head -2
# Docker containers (all, with status)
docker ps -a --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
# Failed units
systemctl --failed --no-legend | head -10
```

Report: `1 line per issue` with severity (🔴 down / 🟡 degraded / ✅ ok).

### Phase 1: Routine Health Checks

| Check | Command | Watch for |
|-------|---------|-----------|
| Disk | `df -h` | >80% usage → alert |
| Memory | `free -h` | swap-in-heavy → OOM risk |
| Load | `uptime` | load > cores → investigate |
| Docker | `docker ps` | restarting/exited containers |
| Systemd | `systemctl --failed` | failed units |
| Logs | `journalctl -p err -n 30 --since today` | repeated errors |

### Phase 2: Docker Container Diagnosis

When a container is unhealthy:

1. `docker ps -a` — is it running, restarting, or exited?
2. `docker logs --tail 50 <container>` — the error
3. `docker inspect <container> --format '{{.State.ExitCode}}'` — exit code
4. `docker stats <container> --no-stream` — resource exhaustion?
5. Restart only after understanding the failure: `docker compose up -d <svc>`

### Phase 3: Security Tool Verification

Confirm the defense stack is actually enforcing:

```bash
# fail2ban active jails
fail2ban-client status
# firewall rules loaded
ufw status verbose || iptables -L -n | head -20
# nginx active + config valid
systemctl is-active nginx && nginx -t
# allowed/blocked IP lists current
tail -5 /etc/nginx/allow-ips-manual.conf 2>/dev/null
```

### Phase 4: System Resource Monitoring

- **CPU**: `top -bn1 | head -15` — find the hog
- **Disk I/O**: `iostat -x 1 3` or `iotop -bn1` (if installed)
- **Network**: `ss -tulnp` — unexpected listening ports
- **Processes**: `ps aux --sort=-%mem | head -10`

## Reporting Severity Levels

| Severity | Meaning | Example | Action |
|----------|---------|---------|--------|
| 🔴 Critical | Service down / data at risk | Container exited, disk full | Fix immediately |
| 🟡 Warning | Degraded but running | Disk >80%, load high | Schedule fix |
| ✅ OK | Healthy | All green | Nothing |

## Admin Rules

- **Uptime first** — never restart a working service "to be safe".
- **Diagnose before fixing** — reproduce the failure, understand it, then act.
- **Check impact before any change** — will it affect running containers?
- **Verify after every change** — health check before and after.
- **Escalate honestly** — if a fix needs intervention you can't perform,
  report it with evidence rather than claiming success.

## Related
- `linux-performance-diagnostics` — deep "system is slow" diagnosis
- `staging-server-operations` — staging-specific ops
- `security-audit` / `server-hardening` — security pipelines
