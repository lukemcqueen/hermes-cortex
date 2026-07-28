---
language: shell
tags: [cleanup, disk, maintenance, sysadmin]
title: Server Disk Cleanup
description: journalctl vacuum, apt clean, docker prune, old kernel removal, logrotate, truncate logs, find+delete, ncdu
source: pattern
---

# Server Disk Cleanup

## Quick Disk Usage Overview

```bash
# Identify what's consuming space
df -h
du -sh /* 2>/dev/null | sort -rh | head -20
du -sh /var/* 2>/dev/null | sort -rh | head -10
du -sh /home/* 2>/dev/null | sort -rh | head -10
```

## journalctl — System Log Cleanup

```bash
# Check current journal usage
journalctl --disk-usage

# Vacuum by size (keep under 500MB)
journalctl --vacuum-size=500M

# Vacuum by time (keep last 7 days)
journalctl --vacuum-time=7d

# Vacuum by file count (keep 5 most recent files)
journalctl --vacuum-files=5

# Set persistent journal size limit (/etc/systemd/journald.conf)
cat >> /etc/systemd/journald.conf << 'EOF'
SystemMaxUse=500M
MaxFileSec=7day
EOF

# Restart journald to apply config
systemctl restart systemd-journald

# Verify after vacuum
journalctl --disk-usage
```

## APT Package Cache Cleanup

```bash
# Remove downloaded package files (.deb)
apt clean

# Remove only obsolete packages (still keeps latest versions)
apt autoclean

# Remove orphaned dependencies
apt autoremove --purge -y

# Show package cache size before/after
du -sh /var/cache/apt/archives/
apt clean
du -sh /var/cache/apt/archives/

# Remove unused snap packages
snap list --all | awk '/disabled/{print $1, $3}' | while read snapname rev; do
    sudo snap remove "$snapname" --revision="$rev"
done
```

## Docker Cleanup

```bash
# Prune everything unused (containers, images, networks, build cache)
# CAUTION: removes all unused resources
docker system prune -af

# Less aggressive: only dangling resources
docker system prune

# Prune only images
docker image prune -af

# 🔴 DANGER — NEVER run in automated cleanup scripts
# Docker volumes contain irreplaceable data (databases, state).
# Only the user should manually delete volumes in an interactive terminal.
# Prune only volumes (WARNING: deletes data)
docker volume prune -af

# Prune build cache
docker builder prune -af

# Show reclaimable space estimate
docker system df

# Selective: remove images older than 30 days
docker image prune -af --filter "until=720h"

# Cleanup docker overlay disk space (if docker uses overlay2)
du -sh /var/lib/docker/overlay2/
```

## Old Kernel Removal (Debian/Ubuntu)

```bash
# List installed kernels
dpkg --list | grep -E 'linux-image-[0-9]+' | awk '{print $2}'

# Show current running kernel
uname -r

# Remove old kernels (keep current + 1 backup)
# Automatic method:
apt autoremove --purge -y

# Manual: remove specific old kernels
apt purge -y $(dpkg -l 'linux-image-*' | awk '/^ii/{print $2}' | grep -v $(uname -r) | head - -2)

# Remove old headers too
apt purge -y $(dpkg -l 'linux-headers-*' | awk '/^ii/{print $2}' | grep -v $(uname -r) | head - -2)

# On RHEL/CentOS/Fedora:
# package-cleanup --oldkernels --count=2
```

## Logrotate Configuration

```bash
# /etc/logrotate.d/ — add custom rotation for application logs
cat > /etc/logrotate.d/myapp << 'EOF'
/var/log/myapp/*.log {
    daily
    missingok
    rotate 14
    compress
    delaycompress
    notifempty
    copytruncate
    maxsize 100M
    dateext
    postrotate
        systemctl reload myapp 2>/dev/null || true
    endscript
}
EOF

# Test logrotate config (dry run)
logrotate -d /etc/logrotate.d/myapp

# Force rotation (even if not time yet)
logrotate -f /etc/logrotate.d/myapp

# Check when logs were last rotated
ls -la /var/log/myapp/*.gz 2>/dev/null

# Global settings in /etc/logrotate.conf
grep -v "^#" /etc/logrotate.conf | grep -v "^$"
```

## Truncate Large Log Files (Safe Methods)

```bash
# SAFE: truncate in place (doesn't break open file handles)
truncate -s 0 /var/log/large.log

# Alternative: use :> (no-op redirect)
:> /var/log/large.log

# Find and truncate files larger than 1GB
find /var/log -type f -size +1G -exec truncate -s 0 {} \;

# Check largest log files before truncating
find /var/log -type f -exec ls -lh {} \; | sort -k5 -rh | head -10

# CAUTION: Never use rm + restart for active logs — use truncate/copytruncate
```

## Find + Delete Old Files

```bash
# Delete files older than 30 days in /tmp
find /tmp -type f -atime +30 -delete 2>/dev/null

# Delete rotated logs older than 90 days
find /var/log -name "*.gz" -o -name "*.1" -o -name "*.old" | xargs rm -f

# Delete core dumps older than 7 days
find /var/crash -type f -mtime +7 -delete 2>/dev/null

# Delete old audit logs
find /var/log/audit -mtime +365 -delete 2>/dev/null

# Delete old package cache files (snap, flatpak)
find /var/lib/snapd/cache -type f -mtime +7 -delete 2>/dev/null

# Dry run before deleting (replace -delete with -print)
find /tmp -atime +30 -print
```

## ncdu — Interactive Disk Analysis

```bash
# Install ncdu
apt install ncdu -y           # Debian/Ubuntu
yum install ncdu -y           # RHEL/CentOS
brew install ncdu              # macOS

# Analyze root filesystem (use with caution on live servers)
# Runs as root to see all files
sudo ncdu /

# Analyze specific directory
ncdu /var/log

# Export report for later review
ncdu /var -o /tmp/ncdu-report.tar.gz
# View later:
ncdu -f /tmp/ncdu-report.tar.gz

# Exclude patterns (ncdu 2.x)
# ~/.config/ncdu/config:
# [patterns]
# exclude = /proc
# exclude = /sys
# exclude = /dev
```

## Full Cleanup Script

```bash
#!/bin/bash
# Safe daily cleanup routine — run as root

set -euo pipefail

echo "=== 1. journalctl vacuum ==="
journalctl --vacuum-size=500M

echo "=== 2. APT cleanup ==="
apt clean
apt autoclean
apt autoremove --purge -y

echo "=== 3. Docker prune ==="
docker system prune -af --filter "until=24h" 2>/dev/null || echo "Docker not available"

echo "=== 4. Truncate oversized logs ==="
find /var/log -type f -size +500M -exec truncate -s 0 {} \;

echo "=== 5. Old temp files ==="
find /tmp -type f -atime +7 -delete 2>/dev/null

echo "=== 6. Report ==="
df -h /
echo ""
echo "Largest directories:"
du -sh /var/log /var/cache /tmp /home 2>/dev/null | sort -rh
```