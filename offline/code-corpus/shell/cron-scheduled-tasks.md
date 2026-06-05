---
language: shell
tags: [sys, util, cli]
title: Cron & Scheduled Tasks
description: crontab syntax, @reboot, logging, lock files to prevent overlap, and the at command for one-shot scheduling.
source: pattern
---

```shell
#!/usr/bin/env bash
set -euo pipefail

# ── Crontab format ──
# ┌───────── minute (0-59)
# │ ┌──────── hour   (0-23)
# │ │ ┌─────── day of month (1-31)
# │ │ │ ┌────── month (1-12)
# │ │ │ │ ┌───── day of week (0-7, 0|7 = Sun)
# │ │ │ │ │
# * * * * * command_to_run

# ── Common crontab entries ──
# Every day at 3:30 AM
# 30 3 * * * /home/user/bin/backup.sh

# Every Monday at 9 AM
# 0 9 * * 1 /home/user/bin/weekly-report.sh

# Every 15 minutes
# */15 * * * * /home/user/bin/health-check.sh

# First day of every month at midnight
# 0 0 1 * * /home/user/bin/monthly-cleanup.sh

# ── @reboot: run once on startup ──
# @reboot /home/user/bin/start-services.sh

# ── Crontab commands ──
crontab -l                          # list current crontab
crontab -e                          # edit crontab
crontab -r                          # remove crontab
crontab /path/to/crontab.txt       # install from file

# ── Logging ──
# Redirect stdout and stderr to a log file:
# 30 3 * * * /home/user/bin/backup.sh >> /var/log/backup.log 2>&1

# ── Lock file to prevent overlap ──
# Place this at the top of your cron script:
LOCKFILE="/tmp/$(basename "$0").lock"
if ! mkdir "$LOCKFILE" 2>/dev/null; then
    echo "Already running (lock held at $LOCKFILE)" >&2
    exit 1
fi
trap 'rm -rf "$LOCKFILE"' EXIT

# ── at: one-shot scheduling ──
echo "backup.sh" | at now + 1 hour
echo "shutdown -h now" | at 23:00
atq                                 # list pending at jobs
atrm <job_id>                       # remove an at job

# ── Cron environment variables ──
# Set these at the top of your crontab:
# SHELL=/bin/bash
# PATH=/usr/local/bin:/usr/bin:/bin
# MAILTO=admin@example.com
# HOME=/home/user

```
