---
language: shell
tags: [audit, compliance, lynis, security-headers, nmap, scanning]
title: Server Audit & Compliance
description: Automated security auditing — lynis hardening scans, security headers checking, open port scanning, and compliance reporting
source: pattern
---

```bash
# ═══════════════════════════════════════════
#  1. Lynis — System Hardening Audit
# ═══════════════════════════════════════════

# Install Lynis
apt update && apt install -y lynis
# Or download latest from GitHub:
# wget -O - https://packages.cisofy.com/keys/cisofy-software-public.key | apt-key add -
# echo "deb https://packages.cisofy.com/community/lynis/deb stable main" > /etc/apt/sources.list.d/cisofy-lynis.list
# apt update && apt install lynis

# Run a full system audit
lynis audit system

# Audit with custom profile (skip some checks)
lynis audit system --profile /etc/lynis/custom.prf

# Show only warnings and suggestions
lynis audit system --quick 2>&1 | grep -E '(Warning|Suggestion):'

# Generate an HTML report
lynis audit system --report-file /var/log/lynis-report.dat
lynis report --view-cat  # View in terminal

# Common findings to address:
#   - File system partitioning (separate /var, /tmp, /home)
#   - Kernel hardening (sysctl settings)
#   - Unnecessary services running
#   - Missing file integrity tool (aide, tripwire, ossec)
#   - Password policy (PAM modules, minimum length, expiration)
#   - Available automatic security updates (unattended-upgrades)

# Typical remediation commands from Lynis suggestions:
apt install -y debsums aide rkhunter unattended-upgrades


# ═══════════════════════════════════════════
#  2. Security Headers Check
# ═══════════════════════════════════════════

# Check HTTP security headers with curl
curl -sI https://example.com | grep -iE '(strict-transport-security|content-security-policy|x-frame-options|x-content-type-options|x-xss-protection|referrer-policy)'

# Full header dump
curl -sI -L https://example.com

# Expected headers:
#   Strict-Transport-Security: max-age=63072000; includeSubDomains
#   Content-Security-Policy: default-src 'self'
#   X-Frame-Options: DENY
#   X-Content-Type-Options: nosniff
#   Referrer-Policy: strict-origin-when-cross-origin
#   Permissions-Policy: geolocation=(), microphone=(), camera=()

# Quick nginx header config snippet
printf '%s\n' \
  'add_header X-Frame-Options "DENY" always;' \
  'add_header X-Content-Type-Options "nosniff" always;' \
  'add_header X-XSS-Protection "0" always;' \
  'add_header Referrer-Policy "strict-origin-when-cross-origin" always;' \
  'add_header Permissions-Policy "geolocation=(),microphone=(),camera=()" always;'

# Online checkers:
#   https://securityheaders.com  (full grade: A+, A, B, C, D, F)
#   https://www.ssllabs.com/ssltest/ (SSL/TLS grade)


# ═══════════════════════════════════════════
#  3. Open Ports Scanning
# ═══════════════════════════════════════════

# Local port scan (what's listening on this server)
ss -tulpn                          # All listening TCP/UDP with process info
netstat -tulpn                     # Alternative (install net-tools if needed)
lsof -i -P -n | grep LISTEN       # Open listening ports with processes

# Remote port scan with nmap (run from a separate scanning machine)
nmap -sT -sV -p- example.com      # Full TCP scan (65535 ports)
nmap -sU -sV --top-ports 100 example.com  # Top 100 UDP ports
nmap -sS -Pn -T4 -p 22,80,443,8080 example.com  # Fast stealth scan on specific ports

# Common findings and actions:
#   Port 22 open    → change to non-default, restrict with AllowUsers
#   Port 25 open    → disable if no mail service: systemctl stop postfix
#   Port 3306 open  → MySQL should not be public; bind to 127.0.0.1
#   Port 6379 open  → Redis should not be public; bind to 127.0.0.1 + requirepass
#   Port 8080/8443  → verify these are intentional (proxies, admin panels)

# Close unnecessary ports by stopping the service or binding to localhost:
# MySQL:
sed -i 's/^bind-address.*/bind-address = 127.0.0.1/' /etc/mysql/mysql.conf.d/mysqld.cnf
systemctl restart mysql


# ═══════════════════════════════════════════
#  4. Quick Compliance Checklist
# ═══════════════════════════════════════════

cat << 'CHECKLIST'
### Server Security Quick Audit
- [ ] SSH: key-only, port changed, root disabled, AllowUsers set
- [ ] Firewall: ufw/iptables default deny inbound, allow specific ports
- [ ] Fail2ban: active jails for SSH, nginx, web apps
- [ ] SSL/TLS: valid cert, TLS 1.2+, HSTS enabled
- [ ] Automatic updates: unattended-upgrades configured
- [ ] Kernel hardening: sysctl (ip_forward, icmp_redirects, rp_filter)
- [ ] File integrity: aide/tripwire/ossec installed and running
- [ ] Auditd: system call auditing enabled
- [ ] MAC: AppArmor or SELinux in enforcing mode
- [ ] Logging: rsyslog forwarding to centralized log host
- [ ] Rootkit detection: rkhunter/chkrootkit run weekly
- [ ] Backups: verified restore test within last 30 days
CHECKLIST


# ═══════════════════════════════════════════
#  5. Automated audit script (run weekly)
# ═══════════════════════════════════════════

cat > /usr/local/bin/security-audit.sh << 'AUDIT'
#!/bin/bash
# Weekly security audit — outputs to /var/log/security-audit/

DATE=$(date +%Y%m%d-%H%M)
DIR="/var/log/security-audit"
mkdir -p "$DIR"

echo "=== Open Ports ===" > "$DIR/audit-$DATE.txt"
ss -tulpn >> "$DIR/audit-$DATE.txt"

echo -e "\n=== Listening Processes ===" >> "$DIR/audit-$DATE.txt"
lsof -i -P -n | grep LISTEN >> "$DIR/audit-$DATE.txt"

echo -e "\n=== SUID/SGID Binaries ===" >> "$DIR/audit-$DATE.txt"
find / -perm -4000 -type f 2>/dev/null >> "$DIR/audit-$DATE.txt"
find / -perm -2000 -type f 2>/dev/null >> "$DIR/audit-$DATE.txt"

echo -e "\n=== Failed SSH Logins (last 7d) ===" >> "$DIR/audit-$DATE.txt"
grep "Failed password" /var/log/auth.log | tail -50 >> "$DIR/audit-$DATE.txt"

echo -e "\n=== Lynis Warnings ===" >> "$DIR/audit-$DATE.txt"
lynis audit system --quick 2>&1 | grep -E '(Warning|Suggestion):' >> "$DIR/audit-$DATE.txt"

# Keep last 12 weeks, remove older
find "$DIR" -name 'audit-*.txt' -mtime +84 -delete
AUDIT
chmod +x /usr/local/bin/security-audit.sh

# Add to cron: weekly Monday 6 AM
echo "0 6 * * 1 root /usr/local/bin/security-audit.sh" > /etc/cron.d/security-audit
```