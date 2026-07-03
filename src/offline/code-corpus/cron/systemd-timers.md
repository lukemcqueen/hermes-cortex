---
language: shell
tags: [systemd, timers, scheduling, cron-alternative]
title: systemd Timers
description: systemd timers as a modern cron alternative — .timer + .service units, OnCalendar syntax, Persistent=true, systemctl list-timers, monotonic timers (OnBootSec, OnUnitActiveSec), and timer logging/journalctl patterns.
source: pattern
---

```bash
# ═══════════════════════════════════════════════════════════════
# SYSTEMD TIMERS — MODERN CRON ALTERNATIVE
# ═══════════════════════════════════════════════════════════════
#
# systemd timers replace cron with declarative unit files, built-in
# logging, dependency management, and failure tracking. Each timer
# needs TWO files: a .timer (schedule) and a .service (what to run).


# ═══════════════════════════════════════════════════════════════
# BASIC EXAMPLE — Daily Backup
# ═══════════════════════════════════════════════════════════════

# ── /etc/systemd/system/daily-backup.service ──
[Unit]
Description=Daily backup job
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
ExecStart=/home/me/scripts/backup.sh
StandardOutput=journal
StandardError=journal

# ── /etc/systemd/system/daily-backup.timer ──
[Unit]
Description=Run daily backup at 2:30 AM
Requires=daily-backup.service

[Timer]
OnCalendar=daily
Persistent=true
RandomizedDelaySec=300

[Install]
WantedBy=timers.target

# ── Enable and start ──
sudo systemctl daemon-reload
sudo systemctl enable daily-backup.timer
sudo systemctl start daily-backup.timer

# ── Check status ──
# systemctl status daily-backup.timer
# systemctl status daily-backup.service
# journalctl -u daily-backup.service --since "1 hour ago"


# ═══════════════════════════════════════════════════════════════
# OnCalendar SYNTAX — More Flexible Than Cron
# ═══════════════════════════════════════════════════════════════

# ── Cron equivalents ──
# Cron:   0 2 * * *         →  OnCalendar=daily
# Cron:   */15 * * * *      →  OnCalendar=*:0/15
# Cron:   0 9 * * 1-5       →  OnCalendar=Mon..Fri 09:00:00
# Cron:   0 0 1 * *         →  OnCalendar=monthly
# Cron:   @hourly           →  OnCalendar=hourly

# ── Full format ──
# OnCalendar=DayOfWeek Year-Month-Day Hour:Minute:Second
#
# Examples:
OnCalendar=daily                      # every day at midnight
OnCalendar=daily 09:30:00             # every day at 9:30 AM
OnCalendar=*-*-* 02:30:00             # every day at 2:30 AM
OnCalendar=Mon..Fri 09:00:00          # weekdays at 9 AM
OnCalendar=Sat,Sun 10:00:00           # weekends at 10 AM
OnCalendar=*:0/15                     # every 15 minutes
OnCalendar=*-*-01 00:00:00            # 1st of every month
OnCalendar=*-01-01 00:00:00           # Jan 1st (yearly)

# ── Ranges and lists ──
OnCalendar=Mon..Fri 08:00..17:00:00   # every hour during business hours
OnCalendar=Mon 00:00:00               # every Monday at midnight

# ── Human-readable aliases ──
# minutely, hourly, daily, monthly, yearly
# weekly, quarterly, semiannually


# ═══════════════════════════════════════════════════════════════
# PERSISTENT=TRUE — Catch Up on Missed Runs
# ═══════════════════════════════════════════════════════════════

[Timer]
OnCalendar=daily
Persistent=true

# When Persistent=true:
# - If the timer was supposed to fire while the system was OFF,
#   the service runs IMMEDIATELY when the system boots.
# - Without it, missed runs are skipped entirely.
# - Equivalent to cron's anacron behavior.

# ── Best for: maintenance tasks (backups, cleanup, updates) ──
# that must run even if the machine was powered off at the scheduled time.


# ═══════════════════════════════════════════════════════════════
# TIMER STATUS WITH systemctl list-timers
# ═══════════════════════════════════════════════════════════════

# ── List active timers and their next trigger ──
systemctl list-timers

# ── List ALL timers (including inactive/disabled) ──
systemctl list-timers --all

# ── Example output ──
# NEXT                          LEFT        LAST                          PASSED    UNIT                     ACTIVATES
# Mon 2026-06-29 02:30:00 UTC  5h left     Mon 2026-06-28 02:30:01 UTC  19h ago   daily-backup.timer       daily-backup.service

# ── Show timer unit contents ──
systemctl cat daily-backup.timer

# ── Show timer's current state ──
systemctl status daily-backup.timer

# ── Show service's last run details ──
systemctl status daily-backup.service


# ═══════════════════════════════════════════════════════════════
# MONOTONIC TIMERS — Relative to System Events
# ═══════════════════════════════════════════════════════════════

# Monotonic timers fire relative to a system event (boot, unit activation),
# NOT at a wall-clock time. Perfect for recurring checks, health probes,
# and maintenance that should run on a schedule relative to now.

[Timer]
OnBootSec=5min             # Run 5 minutes after boot
OnUnitActiveSec=1h         # Then run 1 hour after each activation
# (Combined: runs 5min after boot, then every hour thereafter)

# ── Other monotonic directives ──
OnStartupSec=30s           # 30 seconds after systemd started (≈boot)
OnUnitInactiveSec=1h       # 1 hour after the unit LAST stopped

# ── Full monotonic calendar example: periodic health check ──
# /etc/systemd/system/node-health.service
# [Service]
# Type=oneshot
# ExecStart=/home/me/scripts/health-check.sh
#
# /etc/systemd/system/node-health.timer
# [Unit]
# Description=Health check every 5 minutes
# [Timer]
# OnBootSec=1min
# OnUnitActiveSec=5min
# [Install]
# WantedBy=timers.target


# ═══════════════════════════════════════════════════════════════
# TIMER LOGGING
# ═══════════════════════════════════════════════════════════════

# ── View service logs ──
journalctl -u daily-backup.service
journalctl -u daily-backup.service --since "1 hour ago"
journalctl -u daily-backup.service -f                    # follow (tail -f)

# ── View timer logs ──
journalctl -u daily-backup.timer

# ── Log to a file instead of journal (service unit) ──
# [Service]
# Type=oneshot
# ExecStart=/home/me/scripts/backup.sh
# StandardOutput=append:/var/log/cron/backup.log
# StandardError=append:/var/log/cron/backup.log

# ── View all timer-triggered service runs ──
journalctl --since "2026-06-28 00:00:00" --until "2026-06-29 00:00:00" \
  _SYSTEMD_UNIT=daily-backup.service

# ── Check if a specific run happened ──
systemctl show daily-backup.service --property=ActiveEnterTimestamp


# ═══════════════════════════════════════════════════════════════
# TIPS & TRICKS
# ═══════════════════════════════════════════════════════════════

# ── Randomize start to avoid thundering herd ──
[Timer]
OnCalendar=*:0/15
RandomizedDelaySec=60     # adds 0-60 seconds of random delay

# ── Accuracy vs. precision ──
# OnCalendar=hourly          fires at *:00:00 (every hour on the dot)
# OnCalendar=*-*-* *:00:00   same thing, explicit

# ── Test an OnCalendar expression without installing ──
systemd-analyze calendar daily
systemd-analyze calendar "Mon..Fri 09:00:00"
systemd-analyze calendar "*-*-* 02:30:00"

# ── Show all future trigger times ──
systemd-analyze calendar --iterations=5 "Mon..Fri 09:00:00"

# ── Debug a timer that won't fire ──
systemctl list-timers --all | grep mytimer
journalctl -u mytimer.timer -n 50
systemctl show mytimer.timer | grep -i "result\|active\|trigger\|last"

# ── Manually trigger a timer's service ──
sudo systemctl start daily-backup.service
```