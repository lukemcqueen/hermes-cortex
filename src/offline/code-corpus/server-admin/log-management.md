---
language: shell
tags: [logs, logrotate, journald, management]
title: Log Management
description: logrotate config, journalctl filtering, rsyslog centralization, retention policies, logwatch, fail2ban
source: pattern
---

# Log Management

## Logrotate — Configuration & Testing

```bash
# /etc/logrotate.conf — global settings
cat /etc/logrotate.conf | grep -v "^#" | grep -v "^$"

# Common global defaults:
#   weekly       — rotate logs weekly
#   rotate 4     — keep 4 weeks of backups
#   create       — create new log file after rotation
#   dateext      — append date to rotated filenames
#   compress     — gzip rotated logs
#   include /etc/logrotate.d — per-application configs

# Application-specific config: /etc/logrotate.d/nginx
cat > /etc/logrotate.d/nginx << 'EOF'
/var/log/nginx/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    create 0640 www-data adm
    sharedscripts
    postrotate
        if [ -f /var/run/nginx.pid ]; then
            kill -USR1 $(cat /var/run/nginx.pid)
        fi
    endscript
}
EOF

# Test config (dry run)
logrotate -d /etc/logrotate.d/nginx

# Force immediate rotation
logrotate -f /etc/logrotate.d/nginx

# Verbose run (shows what happens)
logrotate -v /etc/logrotate.conf

# Check last rotation times
ls -la /var/log/nginx/*.gz 2>/dev/null

# Key directives:
#   rotate N         — keep N rotated archives
#   maxage N         — delete logs older than N days
#   maxsize SIZE     — rotate if log exceeds SIZE (even before interval)
#   minsize SIZE     — only rotate if log exceeds SIZE AND interval passed
#   copytruncate     — copy + truncate (safe for apps that don't reopen)
#   delaycompress    — compress on next rotation (not immediately)
#   dateformat       — custom date format for archive names
#   su user group    — rotate as specific user
```

## journalctl — Filtering

```bash
# Show all logs from current boot
journalctl -b

# Show logs from previous boot
journalctl -b -1

# Follow new logs (tail -f equivalent)
journalctl -f

# Filter by service
journalctl -u nginx.service
journalctl -u ssh.service --since today

# Filter by time range
journalctl --since "2025-01-01 00:00:00" --until "2025-01-02 23:59:59"

# Relative time filters
journalctl --since "1 hour ago"
journalctl --since yesterday
journalctl --since "2 days ago" --until "1 hour ago"

# Filter by priority (0=emerg, 1=alert, 2=crit, 3=err, 4=warning, 5=notice, 6=info, 7=debug)
journalctl -p err -b       # errors and above (current boot)
journalctl -p warning      # warnings and above
journalctl -p 3 -p 4       # errors and warnings

# Filter by unit + priority
journalctl -u postgresql.service -p err --since "24 hours ago"

# Output control
journalctl -n 50           # last 50 lines
journalctl --no-pager      # no less/pager
journalctl -o json         # JSON format (importable)
journalctl -o verbose      # all structured fields
journalctl --catalog       # show message explanations

# Filter by specific field
journalctl _PID=1234
journalctl _COMM=sshd
journalctl _UID=1000 --since today

# Disk usage
journalctl --disk-usage

# Export logs for analysis
journalctl -o export > /tmp/system-logs.txt
journalctl -o json-pretty > /tmp/system-logs.json
```

## Centralized Logging with rsyslog

```bash
# --- Server (log aggregator) ---

# /etc/rsyslog.conf — enable TCP/UDP reception
cat >> /etc/rsyslog.conf << 'EOF'
# Provides UDP syslog reception
module(load="imudp")
input(type="imudp" port="514")

# Provides TCP syslog reception
module(load="imtcp")
input(type="imtcp" port="514")
EOF

# Template for organized storage
cat > /etc/rsyslog.d/remote-logs.conf << 'RSYSLOG'
template(name="RemoteLogs" type="string"
    string="/var/log/remote/%FROMHOST%/%PROGRAMNAME%/%$YEAR%-%$MONTH%-%$DAY%.log"
)
:source, !isequal, "localhost" ?RemoteLogs
& stop
RSYSLOG

systemctl restart rsyslog
ss -tlnp | grep 514  # verify listener

# --- Client (forwarding) ---

# /etc/rsyslog.d/forward.conf
cat > /etc/rsyslog.d/forward.conf << 'EOF'
# Forward all logs to central server
*.* @@logs.example.com:514     # TCP
# *.* @logs.example.com:514    # UDP (single @)
EOF

# Forward only specific facilities
# auth,authpriv.*  @@logs.example.com:514
# *.info;mail.none;authpriv.none;cron.none  @@logs.example.com:514

systemctl restart rsyslog
```

## Log Retention Policies

```bash
# --- Journald retention (/etc/systemd/journald.conf) ---
cat >> /etc/systemd/journald.conf << 'EOF'
# Limits
SystemMaxUse=500M
SystemMaxFileSize=100M
MaxFileSec=1month
RuntimeMaxUse=128M

# Sync interval
SyncIntervalSec=5m
EOF
systemctl restart systemd-journald

# --- Rsyslog retention (/etc/logrotate.d/rsyslog) ---
cat > /etc/logrotate.d/rsyslog << 'EOF'
/var/log/syslog
/var/log/messages
/var/log/auth.log
/var/log/kern.log
/var/log/debug
/var/log/mail.log
/var/log/daemon.log
{
    rotate 12
    weekly
    missingok
    notifempty
    compress
    delaycompress
    sharedscripts
    postrotate
        systemctl restart rsyslog >/dev/null 2>&1 || true
    endscript
}
EOF

# --- Application-specific retention examples ---
# Nginx: keep 30 days
# PostgreSQL: keep 7 days (WAL is handled separately)
# Application JSON logs: keep 90 days

# Policy template per app:
#   Daily rotation
#   Compress after 1 day
#   Keep N versions (N = retention_days / rotation_interval)
#   Example: 90 days retention, daily = rotate 90
```

## Logwatch — Weekly Summary

```bash
# Install logwatch
apt install logwatch -y || yum install logwatch -y

# Run manually for last 7 days
logwatch --detail high --range "between -7 days and today" \
         --service All --output stdout

# Weekly email report (default config)
logwatch --detail med --range "between -7 days and today" \
         --service All --mailto admin@example.com

# Hourly/daily report
logwatch --detail low --range today --service sshd

# /usr/share/logwatch/default.conf/logwatch.conf
#   Detail = Medium
#   MailTo = admin@example.com
#   Range = between -7 days and today

# Cron job for weekly logwatch
# /etc/cron.weekly/00logwatch
# Already installed by default on Debian/Ubuntu

# Check last report
zcat /var/cache/logwatch/logwatch.*.gz 2>/dev/null | head -50

# Customize services (e.g., only sshd + nginx)
logwatch --detail high --range "between -7 days and today" \
         --service sshd --service nginx
```

## fail2ban — Log Monitoring & Blocking

```bash
# Install
apt install fail2ban -y || yum install fail2ban -y

# Check status
fail2ban-client status
fail2ban-client status sshd

# /etc/fail2ban/jail.local — local overrides
cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime = 3600
findtime = 600
maxretry = 5
ignoreip = 127.0.0.1/8 10.0.0.0/8 192.168.0.0/16
action = iptables-multiport[name=%(__name__)s, port="%(port)s", protocol=tcp]

[sshd]
enabled = true
port = 22
logpath = %(sshd_log)s
maxretry = 3
bantime = 86400

[nginx-http-auth]
enabled = true
logpath = /var/log/nginx/error.log

[nginx-botsearch]
enabled = true
logpath = /var/log/nginx/access.log
maxretry = 2
findtime = 600
bantime = 604800
EOF

systemctl restart fail2ban

# View banned IPs
fail2ban-client banned

# Unban an IP
fail2ban-client set sshd unbanip 203.0.113.42

# Log monitoring (live)
tail -f /var/log/fail2ban.log

# Create custom jail for app logs
cat > /etc/fail2ban/jail.d/myapp.local << 'EOF'
[myapp-auth]
enabled = true
port = http,https
logpath = /var/log/myapp/access.log
maxretry = 5
findtime = 300
bantime = 3600
EOF

# Regex filter for custom log format
cat > /etc/fail2ban/filter.d/myapp-auth.conf << 'EOF'
[Definition]
failregex = ^.*FAILED_LOGIN from <HOST>.*$
ignoreregex =
EOF
```

## Log Management Health Check

```bash
#!/bin/bash
# Quick log management audit

echo "=== Journald Usage ==="
journalctl --disk-usage

echo ""
echo "=== Logrotate Status ==="
logrotate -d /etc/logrotate.conf 2>&1 | grep -E "error|warning" || echo "No errors"

echo ""
echo "=== Largest Log Files ==="
find /var/log -type f -exec ls -lh {} \; 2>/dev/null | sort -k5 -rh | head -10

echo ""
echo "=== fail2ban ==="
fail2ban-client status 2>/dev/null | head -5 || echo "fail2ban not running"

echo ""
echo "=== rsyslog ==="
systemctl is-active rsyslog
ss -tlnp 2>/dev/null | grep -E "514|6514" || echo "No syslog listeners"

echo ""
echo "=== Logrotate Last Run ==="
ls -la /var/lib/logrotate/status 2>/dev/null || echo "No status file"
```