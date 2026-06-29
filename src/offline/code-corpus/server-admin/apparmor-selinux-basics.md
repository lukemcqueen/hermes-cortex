---
language: shell
tags: [apparmor, selinux, mandatory-access-control, security, profiles, auditing]
title: AppArmor & SELinux Basics
description: Mandatory Access Control (MAC) fundamentals — AppArmor profiles, enforce/complain modes, SELinux contexts, booleans, and audit log analysis
source: pattern
---

```bash
# ═══════════════════════════════════════════
#  APPARMOR (Ubuntu/Debian default)
# ═══════════════════════════════════════════

# ── Check status ──
aa-status                     # Shows loaded profiles and processes
sudo apparmor_status          # Same as aa-status
cat /sys/kernel/security/apparmor/profiles

# ── Profile modes ──
# Enforce:  policy enforced, violations blocked and logged
# Complain: policy NOT enforced, violations only logged (learning mode)

# Set a profile to complain mode (for testing/debugging)
sudo aa-complain /usr/sbin/nginx
# Set a profile back to enforce mode
sudo aa-enforce /usr/sbin/nginx

# Disable a profile temporarily
sudo aa-disable /etc/apparmor.d/usr.sbin.nginx

# ── Create a simple AppArmor profile ──
# Generate an auto-profile from log entries (learning mode):
sudo aa-genprof /usr/bin/myapp
# Then in another terminal exercise the application; aa-genprof prompts
# you to allow/deny each access.

# Manual profile example for /usr/local/bin/custom-server:
cat > /etc/apparmor.d/usr.local.bin.custom-server << 'PROFILE'
#include <tunables/global>

/usr/local/bin/custom-server {
  #include <abstractions/base>
  #include <abstractions/openssl>

  /etc/custom-server/config r,
  /var/log/custom-server/* w,
  /var/run/custom-server.pid rw,
  /data/custom-server/** rwk,

  # Deny everything else by default (implicit)
}
PROFILE

# Load the profile
sudo apparmor_parser -r /etc/apparmor.d/usr.local.bin.custom-server
sudo aa-enforce /usr/local/bin/custom-server

# ── Log inspection (AppArmor) ──
sudo journalctl -t audit | grep -i apparmor        # systemd journal
sudo grep -i apparmor /var/log/syslog              # syslog
sudo ausearch -m AVC -ts recent | grep apparmor    # auditd (if installed)

# Common AppArmor DENIED message format:
# audit: type=1400 apparmor="DENIED" operation="open"
#   profile="/usr/sbin/nginx" name="/etc/shadow"
#   pid=1234 comm="nginx" requested_mask="r" denied_mask="r"

# ── Useful utilities ──
sudo aa-logprof                   # Scan logs and update profiles interactively
sudo aa-audit /usr/sbin/nginx     # Set to audit mode (log everything, policy active)


# ═══════════════════════════════════════════
#  SELINUX (RHEL/CentOS/Fedora default)
# ═══════════════════════════════════════════

# ── Check status ──
getenforce                        # Enforcing | Permissive | Disabled
sestatus                          # Detailed status

# ── Toggle modes (immediate, non-persistent) ──
sudo setenforce 0                 # Permissive (log only, no blocking)
sudo setenforce 1                 # Enforcing (block violations)

# Persistent mode change in /etc/selinux/config:
#   SELINUX=enforcing
#   SELINUX=permissive
#   SELINUX=disabled

# ── File contexts ──
ls -Z /var/www/html/index.html    # View SELinux context
# Example output: system_u:object_r:httpd_sys_content_t:s0

# Restore default context
sudo restorecon -Rv /var/www/html

# Set a custom context
sudo semanage fcontext -a -t httpd_sys_content_t "/srv/myapp(/.*)?"
sudo restorecon -Rv /srv/myapp

# ── Booleans (toggle SELinux policy features) ──
sudo getsebool -a                 # List all booleans
sudo getsebool httpd_can_network_connect
sudo setsebool -P httpd_can_network_connect on     # -P makes persistent

# ── Audit logs (SELinux) ──
sudo ausearch -m AVC -ts today    # Today's denials
sudo ausearch -m AVC -ts recent   # Most recent
sudo aureport -a                   # Summary of all denials

# Readable translation of an AVC denial:
# ausearch says: avc: denied { read } for pid=1234 comm="nginx"
#   name="index.html" scontext=system_u:system_r:httpd_t:s0
#   tcontext=unconfined_u:object_r:admin_home_t:s0
#   tclass=file
# Translation: nginx (httpd_t) tried to read a file labeled admin_home_t
#   instead of httpd_sys_content_t. Fix: restorecon the file.

# ── Troubleshooting helper (SELinux) ──
sudo sealert -a /var/log/audit/audit.log   # Generate human-readable suggestions
sudo dnf install -y setroubleshoot         # Install sealert if missing

# ── Put SELinux in permissive mode temporarily for debugging ──
sudo setenforce 0
# Reproduce the issue. If it works, SELinux is the blocker.
# Find and fix the denial:
sudo grep "SELinux" /var/log/messages | tail -20
sudo setenforce 1

# ── Summary comparison ──
# AppArmor:  profile-per-binary, paths, easier for single-app servers
# SELinux:  label-per-object, type enforcement, steeper curve, finer granularity
# Both:     MAC layers that confine processes beyond standard Unix permissions
```