---
language: shell
tags: [cron, logging, monitoring, health]
title: Cron Logging & Monitoring
description: Cron logging patterns — stdout/stderr redirection with timestamps, log rotation, health check pings (Cronitor, Dead Man's Snitch, Heartbeat), monitoring failures with systemd timers, and email-on-failure jobs.
source: pattern
---

```bash
# ═══════════════════════════════════════════════════════════════
# CRON LOGGING PATTERNS
# ═══════════════════════════════════════════════════════════════

# ── 1. Basic stdout+stderr to log file ──
0 2 * * * /home/me/scripts/backup.sh >> /var/log/cron/backup.log 2>&1

# ── 2. Separate stdout and stderr ──
0 2 * * * /home/me/scripts/backup.sh >> /var/log/cron/backup.log 2>> /var/log/cron/backup.err

# ── 3. Timestamped log file per run ──
0 2 * * * /home/me/scripts/backup.sh >> /var/log/cron/backup-$(date +\%Y\%m\%d).log 2>&1

# ── 4. Logger wrapper — prepend timestamp to every line ──
0 2 * * * /home/me/scripts/backup.sh 2>&1 | while IFS= read -r line; do echo "$(date '+%F %T') $line"; done >> /var/log/cron/backup.log

# ── 5. Rotating log with timestamp and job name ──
# In the script itself:
#   log() { echo "[$(date '+%F %T')] $*" >> /var/log/cron/backup.log; }
#   log "Starting backup"
#   rsync -avz /data /backup && log "Backup OK" || log "Backup FAILED"
#   log "Backup finished"


# ═══════════════════════════════════════════════════════════════
# LOG ROTATION FOR CRON OUTPUT
# ═══════════════════════════════════════════════════════════════

# ── /etc/logrotate.d/cron-jobs ──
/var/log/cron/*.log {
    daily
    rotate 30
    compress
    delaycompress
    missingok
    notifempty
    copytruncate
    dateext
    dateformat -%Y%m%d
    maxsize 100M
}

# ── Per-job rotation (inside a cron script) ──
# Rotate log if it exceeds 50MB:
# LOG=/var/log/cron/myjob.log
# [ "$(stat -f%z "$LOG" 2>/dev/null || echo 0)" -gt 52428800 ] && mv "$LOG" "$LOG.old"
# exec >> "$LOG" 2>&1


# ═══════════════════════════════════════════════════════════════
# HEALTH CHECK PINGS
# ═══════════════════════════════════════════════════════════════

# ── Dead Man's Snitch ──
# Get a unique URL from https://deadmanssnitch.com
# Add this to the END of your cron job so it only pings on success:
0 6 * * * /home/me/scripts/daily-report.sh && curl -fsS https://nosnch.in/your-uuid > /dev/null

# ── Cronitor ──
# Get a monitor key from https://cronitor.io
# Wrap your command with the Cronitor CLI:
0 6 * * * cronitor exec your-monitor-key /home/me/scripts/daily-report.sh

# ── Healthchecks.io ──
# Free service; get a UUID from https://healthchecks.io
# Ping START before running, then SUCCESS or FAIL at the end:
@daily /home/me/scripts/backup.sh \
  && curl -fsS -m 10 --retry 3 https://hc-ping.com/your-uuid \
  || curl -fsS -m 10 --retry 3 https://hc-ping.com/your-uuid/fail

# ── Manual heartbeat with curl ──
# For a custom service:
*/5 * * * * /home/me/scripts/heartbeat.sh

# Inside heartbeat.sh:
#   STATUS=$(pgrep -x myservice > /dev/null 2>&1 && echo "up" || echo "down")
#   curl -fsS -X POST -H "Content-Type: application/json" \
#     -d "{\"host\":\"$(hostname)\",\"service\":\"myservice\",\"status\":\"$STATUS\"}" \
#     https://monitor.internal/beat


# ═══════════════════════════════════════════════════════════════
# MONITORING CRON FAILURES WITH SYSTEMD TIMERS
# ═══════════════════════════════════════════════════════════════

# ── systemd timers have built-in failure tracking ──
# systemctl list-timers --all  # shows last trigger + next trigger
# systemctl status myjob.service  # shows last run's exit code & logs
# journalctl -u myjob.service --since "1 hour ago"  # view recent output

# ── OnFailure hook (systemd service unit) ──
# [Service]
# ExecStart=/home/me/scripts/backup.sh
# OnFailure=failure-notify@%n.service
#
# Then create failure-notify@.service:
# [Unit]
# Description=Notify on %i failure
# [Service]
# Type=oneshot
# ExecStart=/home/me/scripts/notify-failure.sh %i
#
# Script:
#   TO="ops@example.com"
#   SERVICE="$1"
#   LOG=$(journalctl -u "$SERVICE" --since "5 min ago" --no-pager 2>&1 | tail -20)
#   echo -e "Service $SERVICE failed.\n\nRecent logs:\n$LOG" | mail -s "[ALERT] $SERVICE failed" "$TO"


# ═══════════════════════════════════════════════════════════════
# CRON JOBS THAT EMAIL ON FAILURE
# ═══════════════════════════════════════════════════════════════

# ── Pattern: run command, capture exit code, email on failure ──
0 2 * * * /home/me/scripts/backup-with-email.sh

# Inside backup-with-email.sh:
#   #!/bin/bash
#   LOGFILE="/var/log/cron/backup.log"
#   To="ops@example.com"
#   exec >> "$LOGFILE" 2>&1
#
#   echo "[$(date)] Starting backup"
#   rsync -avz /data /backup
#   RC=$?
#
#   if [ $RC -ne 0 ]; then
#     SUBJECT="[CRON FAIL] backup.sh exited with code $RC on $(hostname)"
#     mail -s "$SUBJECT" "$TO" < "$LOGFILE"
#   fi
#
#   # Ping health check — only on success, so silence = alert
#   [ $RC -eq 0 ] && curl -fsS https://hc-ping.com/your-uuid
#
#   exit $RC

# ── Alternative: email the last N lines only ──
#   tail -50 "$LOGFILE" | mail -s "[CRON FAIL] backup failed on $(hostname)" "$TO"

# ── Using MAILTO in crontab (simplest, but no control) ──
# MAILTO=ops@example.com
# All stdout/stderr from cron jobs will be emailed to ops.
# WARNING: every line of output triggers an email. Good for
# jobs that produce output ONLY on error via explicit echo/log.
```