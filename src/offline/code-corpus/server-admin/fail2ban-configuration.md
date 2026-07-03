---
language: shell
tags: [fail2ban, intrusion-prevention, jail, filter, ban]
title: Fail2ban Configuration
description: Comprehensive fail2ban setup — jail.conf, custom filters, actions, and ban/unban commands for SSH, nginx, and web apps
source: pattern
---

```bash
# ── 1. Install fail2ban ──
apt update && apt install -y fail2ban
# Config files:
#   /etc/fail2ban/fail2ban.conf     — global daemon settings
#   /etc/fail2ban/jail.conf         — default jails (DO NOT EDIT directly)
#   /etc/fail2ban/jail.d/*.conf     — custom overrides (use these)
#   /etc/fail2ban/filter.d/*.conf   — regex patterns for log parsing
#   /etc/fail2ban/action.d/*.conf   — ban/unban commands

# ── 2. SSH jail (most common) ──
cat > /etc/fail2ban/jail.d/sshd-local.conf << 'EOF'
[sshd]
enabled   = true
port      = ssh
filter    = sshd
logpath   = /var/log/auth.log
maxretry  = 3
bantime   = 3600
findtime  = 600
ignoreip  = 127.0.0.1/8 ::1 192.168.1.0/24
EOF

# ── 3. nginx jail (protect against auth failures, bot probes) ──
cat > /etc/fail2ban/jail.d/nginx-local.conf << 'EOF'
# Ban IPs that trigger repeated 404s (directory traversal scans)
[nginx-noscript]
enabled  = true
port     = http,https
filter   = nginx-noscript
logpath  = /var/log/nginx/access.log
maxretry = 6
bantime  = 86400
findtime = 3600

# Ban IPs hitting non-existent auth pages
[nginx-auth]
enabled  = true
port     = http,https
filter   = nginx-auth
logpath  = /var/log/nginx/error.log
maxretry = 5
bantime  = 3600
findtime = 600

# Ban IPs with too many 400/403/444 responses (bad bots)
[nginx-badbots]
enabled  = true
port     = http,https
filter   = nginx-badbots
logpath  = /var/log/nginx/access.log
maxretry = 2
bantime  = 86400
findtime = 3600
EOF

# ── 4. Custom filter example — repeat offender for WordPress XML-RPC ──
cat > /etc/fail2ban/filter.d/nginx-xmlrpc.conf << 'EOF'
[Definition]
failregex = ^<HOST> .*POST .*/xmlrpc\.php.* 200
ignoreregex =
EOF

# Then create the jail:
cat > /etc/fail2ban/jail.d/nginx-xmlrpc-local.conf << 'EOF'
[nginx-xmlrpc]
enabled  = true
port     = http,https
filter   = nginx-xmlrpc
logpath  = /var/log/nginx/access.log
maxretry = 3
bantime  = 86400
findtime = 300
EOF

# ── 5. Ban / unban commands ──
# Check jail status
fail2ban-client status sshd

# List all jails and their banned IPs
fail2ban-client status
for jail in $(fail2ban-client status | grep "Jail list:" | sed 's/.*:\s*//' | tr ',' ' '); do
    echo "=== $jail ==="
    fail2ban-client status "$jail" | grep "Banned IP list"
done

# Manually ban an IP
fail2ban-client set sshd banip 203.0.113.42

# Manually unban an IP
fail2ban-client set sshd unbanip 203.0.113.42

# Unban across all jails
fail2ban-client unban --all

# Unban a specific IP from all jails
fail2ban-client unban 203.0.113.42

# ── 6. Action overrides: email alerts on ban ──
cat > /etc/fail2ban/jail.d/action-local.conf << 'EOF'
[sshd]
action   = %(action_mwl)s           # Ban + whois report + log lines emailed
mta      = sendmail
sender   = fail2ban@example.com
destemail = admin@example.com
EOF

# ── 7. Global configuration tweaks ──
cat > /etc/fail2ban/fail2ban-local.conf << 'EOF'
[DEFAULT]
loglevel  = INFO
logtarget = /var/log/fail2ban.log
dbpurgeage = 86400    # Purge DB entries older than 1 day
EOF

# ── 8. Restart and verify ──
systemctl restart fail2ban
fail2ban-client ping               # Should reply: pong
journalctl -u fail2ban --no-pager  # Check daemon logs

# ── 9. Test the filter regex ──
fail2ban-regex /var/log/nginx/access.log /etc/fail2ban/filter.d/nginx-noscript.conf
```