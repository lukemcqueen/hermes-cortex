---
language: shell
tags: [cron, scheduling, automation, syntax]
title: Cron Scheduling Reference
description: Complete cron syntax reference — fields, special strings, crontab management, environment variables, PATH issues, MAILTO, and logging output patterns.
source: pattern
---

```bash
# ═══════════════════════════════════════════════════════════════
# CRON SYNTAX REFERENCE
# ═══════════════════════════════════════════════════════════════

# ── The five time fields ──
#  ┌───────── minute (0-59)
#  │ ┌──────── hour   (0-23)
#  │ │ ┌─────── day of month (1-31)
#  │ │ │ ┌────── month (1-12)
#  │ │ │ │ ┌──── day of week (0-7, both 0 and 7 = Sunday)
#  │ │ │ │ │
#  * * * * *  command_to_run

# ── Common examples ──
# Every minute
* * * * * /usr/bin/logger "cron tick"

# Every day at 2:30 AM
30 2 * * * /home/me/scripts/daily-backup.sh

# Every weekday (Mon-Fri) at 9 AM
0 9 * * 1-5 /home/me/scripts/start-of-day.sh

# First day of every month at midnight
0 0 1 * * /home/me/scripts/monthly-report.sh

# Every 15 minutes
*/15 * * * * /home/me/scripts/quarterly-check.sh

# Twice daily — 6 AM and 6 PM
0 6,18 * * * /home/me/scripts/twice-daily.sh

# Every hour during business hours (8 AM — 5 PM Mon-Fri)
0 8-17 * * 1-5 /home/me/scripts/business-hours.sh


# ═══════════════════════════════════════════════════════════════
# SPECIAL STRINGS (shorthand equivalents)
# ═══════════════════════════════════════════════════════════════

@reboot      # Run once at startup (after cron daemon starts)
@yearly      # 0 0 1 1 *       — Jan 1st at midnight
@annually    # same as @yearly
@monthly     # 0 0 1 * *       — 1st of every month
@weekly      # 0 0 * * 0       — Sunday at midnight
@daily       # 0 0 * * *       — midnight
@midnight    # same as @daily
@hourly      # 0 * * * *       — top of every hour

# Example:
@daily /home/me/scripts/daily-cleanup.sh
@reboot /home/me/scripts/ensure-tunnels.sh


# ═══════════════════════════════════════════════════════════════
# CRONTAB MANAGEMENT
# ═══════════════════════════════════════════════════════════════

# ── Edit your crontab ──
crontab -e

# ── List your crontab ──
crontab -l

# ── List another user's crontab (root) ──
sudo crontab -l -u www-data

# ── Remove your crontab ──
crontab -r

# ── Install a crontab file ──
crontab /path/to/my-crontab.txt

# ── Edit with a specific editor ──
EDITOR=vim crontab -e
EDITOR=nano crontab -e

# ── Pipe current crontab for safe editing ──
crontab -l > ~/crontab-backup-$(date +%F).txt
crontab -r

# ═══════════════════════════════════════════════════════════════
# ENVIRONMENT VARIABLES IN CRONTAB
# ═══════════════════════════════════════════════════════════════

# ── Shell and PATH ──
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/home/me/bin

# ── Common variables ──
HOME=/home/me
LOGNAME=me
MAILTO=me@example.com

# ── Custom variables ──
BACKUP_DIR=/data/backups
APP_ENV=production
PYTHONPATH=/home/me/myapp

# ── PATH is the most common footgun ──
# cron runs with a minimal PATH (/usr/bin:/bin) by default.
# Always set PATH explicitly or use absolute paths for every command.
#
# BAD — will fail if 'docker' isn't in cron's minimal PATH:
# */5 * * * * docker system prune -f
#
# GOOD — absolute path:
*/5 * * * * /usr/bin/docker system prune -f
#
# BETTER — explicit PATH at top of crontab:
# PATH=/usr/local/bin:/usr/bin:/bin:/usr/local/sbin
# */5 * * * * docker system prune -f

# ── MAILTO controls where cron sends stdout/stderr ──
MAILTO=""             # Discard all output (no email)
MAILTO="me@ex.com"    # Email output to this address
# If MAILTO is unset, cron mails output to the crontab owner


# ═══════════════════════════════════════════════════════════════
# CAPTURING OUTPUT (better than relying on cron's mail)
# ═══════════════════════════════════════════════════════════════

# Redirect stdout and stderr to a log file:
0 2 * * * /home/me/scripts/backup.sh >> /var/log/backup.log 2>&1

# Append timestamped log:
0 2 * * * /home/me/scripts/backup.sh >> /var/log/backup-$(date +\%Y\%m\%d).log 2>&1

# ── IMPORTANT: % in cron must be escaped ──
# In crontab, % is a special character (newline/command separator).
# Use \% inside date format strings.
  # Right:  $(date +\%Y\%m\%d)
  # Wrong:  $(date +%Y%m%d)

# Completely suppress output (no email, no log):
0 3 * * * /home/me/scripts/silent-job.sh > /dev/null 2>&1
```