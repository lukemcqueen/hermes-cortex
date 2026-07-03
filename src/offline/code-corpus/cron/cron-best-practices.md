---
language: shell
tags: [cron, best-practices, automation, reliability]
title: Cron Best Practices
description: Production cron job patterns — idempotent scripts, lock files with flock, randomizing start times, the no-agent pattern for cheap jobs, scripts over inline commands, PATH exports, and error handling in script before cron exit.
source: pattern
---

```bash
# ═══════════════════════════════════════════════════════════════
# CRON BEST PRACTICES
# ═══════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════
# 1. SCRIPTS OVER INLINE COMMANDS
# ═══════════════════════════════════════════════════════════════

# BAD — fragile, hard to test, hard to debug:
# 0 2 * * * cd /data && tar -czf backup-$(date +\%Y\%m\%d).tgz documents/ && rsync -av backup-*.tgz backup@server:/backups/

# GOOD — call a checked-in, testable script:
0 2 * * * /home/me/scripts/daily-backup.sh

# Inside daily-backup.sh:
#   #!/bin/bash
#   set -euo pipefail
#   cd /data
#   tar -czf "backup-$(date +%F).tgz" documents/
#   rsync -av "backup-$(date +%F).tgz" backup@server:/backups/

# Benefits:
#   - Testable manually: ./daily-backup.sh
#   - Version-controlled (git)
#   - Supports set -euo pipefail
#   - Easier to add logging, error handling, lock files


# ═══════════════════════════════════════════════════════════════
# 2. SET PATH AND ENVIRONMENT AT THE TOP OF THE SCRIPT
# ═══════════════════════════════════════════════════════════════

# cron provides a minimal environment — always set your own.

# Inside a cron script:
#   #!/bin/bash
#   set -euo pipefail
#
#   # ── PATH — cron's default is /usr/bin:/bin, add what you need ──
#   export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/home/me/bin"
#
#   # ── Other environment ──
#   export HOME=/home/me
#   export LANG=en_US.UTF-8
#
#   # ── Script-specific ──
#   export BACKUP_DIR=/data/backups
#   export APP_ENV=production

# ── Or use the script's own directory for relative PATH ──
# SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# export PATH="$SCRIPT_DIR/../bin:$PATH"


# ═══════════════════════════════════════════════════════════════
# 3. ERROR HANDLING — CATCH FAILURES IN THE SCRIPT
# ═══════════════════════════════════════════════════════════════

# Inside a cron script:
#   #!/bin/bash
#   set -euo pipefail
#
#   LOGFILE="/var/log/cron/myjob.log"
#   exec >> "$LOGFILE" 2>&1
#
#   cleanup() {
#     echo "[$(date +%F %T)] Cleaning up temporary files..."
#     rm -rf /tmp/myjob-*
#   }
#   trap cleanup EXIT
#
#   echo "[$(date +%F %T)] Starting job"
#
#   if ! some-command; then
#     echo "[ERROR] some-command failed with exit code $?"
#     # Optionally email alert:
#     # tail -5 "$LOGFILE" | mail -s "[CRON] myjob failed on $(hostname)" ops@example.com
#     exit 1
#   fi
#
#   echo "[$(date +%F %T)] Job completed successfully"

# ── Important: cron captures the script's exit code ──
# Non-zero exit → cron considers the job failed.
# Set set -e (or set -euo pipefail) so your script exits on first error.


# ═══════════════════════════════════════════════════════════════
# 4. LOCK FILES — PREVENT CONCURRENT EXECUTION WITH flock
# ═══════════════════════════════════════════════════════════════

# ── Using flock in crontab (preferred) ──
# The flock utility prevents a script from running if a previous
# instance is still executing. Essential for jobs whose duration
# might exceed the cron interval.
#
# */5 * * * * /usr/bin/flock -n /tmp/myjob.lock /home/me/scripts/myjob.sh
#
#   -n = non-blocking: if lock is held, skip this run immediately
#   -w 10 = wait up to 10 seconds for the lock, then skip
#   -E 0 = exit code 0 when skipping (don't trigger MAILTO alert)
#   -E 0 is useful with -n so skipped runs don't send failure emails

# ── Common patterns ──

# Skip if running — don't wait, don't alert:
# */5 * * * * /usr/bin/flock -n -E 0 /tmp/myjob.lock /home/me/scripts/myjob.sh

# Wait up to 30s for lock, fail if can't acquire:
# */5 * * * * /usr/bin/flock -w 30 /tmp/myjob.lock /home/me/scripts/myjob.sh

# ── Using flock inside a script ──
# #!/bin/bash
# set -euo pipefail
# LOCKFILE="/tmp/myjob.lock"
# exec 200>"$LOCKFILE"
# flock -n 200 || { echo "Another instance is running — exiting"; exit 0; }
# # ... rest of script follows ...

# ── Why flock over mkdir-based locking ──
# flock is atomic, releases automatically on process exit,
# handles signals gracefully, and doesn't leave stale lock dirs.


# ═══════════════════════════════════════════════════════════════
# 5. IDEMPOTENT SCRIPTS
# ═══════════════════════════════════════════════════════════════

# An idempotent script produces the same outcome whether run once
# or a hundred times. This makes recovery from failures trivial.

# ── Patterns for idempotence ──

# Check-before-act:
# if [ ! -f "/data/backup-$(date +%F).tgz" ]; then
#     tar -czf "/data/backup-$(date +%F).tgz" documents/
# fi
# rsync -av "/data/backup-$(date +%F).tgz" backup@server:/backups/

# Create-if-not-exists (mkdir -p):
# mkdir -p /data/backups

# Upsert pattern (idempotent DB mutation):
# psql -c "INSERT INTO runs (date, status) VALUES (current_date, 'ok')
#          ON CONFLICT (date) DO UPDATE SET status = 'ok';"

# ── Resources that are naturally idempotent ──
#   rsync, cp -n, mkdir -p, git pull --rebase,
#   apt-get install -y, terraform apply, kubectl apply


# ═══════════════════════════════════════════════════════════════
# 6. RANDOMIZE START TIMES
# ═══════════════════════════════════════════════════════════════

# ── Using shell $RANDOM to spread load ──
# Avoid thundering-herd problems when many machines start at :00.

# Random minute offset (0-59), run hourly:
# In crontab:
# SHELL=/bin/bash
# 0 * * * * sleep $((RANDOM % 60)) && /home/me/scripts/check.sh

# Random delay on a daily job (0-300 seconds):
# 0 2 * * * sleep $((RANDOM % 300)) && /home/me/scripts/daily.sh

# ── systemd alternative (cleaner) ──
# [Timer]
# OnCalendar=daily
# RandomizedDelaySec=300


# ═══════════════════════════════════════════════════════════════
# 7. THE "NO_AGENT" PATTERN — CHEAP JOBS
# ═══════════════════════════════════════════════════════════════

# Some jobs should run with zero configuration overhead — no
# virtualenv, no npm install, no JVM. These are "no-agent" jobs.

# ── Characteristics ──
#   - Written in POSIX shell or awk (no dependencies)
#   - No external package requirements
#   - Uses only tools on a stock system (curl, grep, cut, tr, etc.)
#   - Inline where tiny, script where medium
#   - Self-contained, no config files

# ── Example: TCP port health check (pure curl + date) ──
# #!/bin/sh
# HOSTS="web-01 web-02 web-03"
# PORT=443
# for HOST in $HOSTS; do
#   if curl -sf -o /dev/null --connect-timeout 5 "https://$HOST:$PORT/health"; then
#     echo "OK $HOST:$PORT"
#   else
#     echo "FAIL $HOST:$PORT"
#   fi
# done

# ── When NOT to use no_agent ──
# When you need Python/Node/Ruby libraries, DB connectors,
# or anything beyond awk/sed/grep/curl. Use a proper script
# in those cases, or wrap the tool in a Docker container.


# ═══════════════════════════════════════════════════════════════
# 8. COMPLETE PRODUCTION CRON SCRIPT TEMPLATE
# ═══════════════════════════════════════════════════════════════

<<'SCRIPT'
#!/bin/bash
# ── Production cron job template ──
set -euo pipefail

# ── Environment ──
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
export LANG=en_US.UTF-8

# ── Config ──
SCRIPT_NAME="$(basename "$0")"
LOGDIR="/var/log/cron"
LOGFILE="$LOGDIR/$SCRIPT_NAME.log"
LOCKFILE="/tmp/$SCRIPT_NAME.lock"
HEARTBEAT_URL="https://hc-ping.com/your-uuid"

# ── Ensure log directory exists ──
mkdir -p "$LOGDIR"

# ── Redirect all output ──
exec >> "$LOGFILE" 2>&1

# ── Lock (non-blocking, skip if running) ──
exec 200>"$LOCKFILE"
flock -n -E 0 200 || { echo "[$(date +%F %T)] Skipped — another instance running"; exit 0; }

# ── Trap for cleanup ──
cleanup() {
    echo "[$(date +%F %T)] Finished (exit code: $?)"
}
trap cleanup EXIT

# ── Main ──
echo "[$(date +%F %T)] Starting $SCRIPT_NAME"

# Your actual work here...
if some-command; then
    # Ping health check on success
    curl -fsS -m 10 --retry 3 "$HEARTBEAT_URL" > /dev/null 2>&1 || true
else
    # Ping failure to health check
    curl -fsS -m 10 --retry 3 "$HEARTBEAT_URL/fail" > /dev/null 2>&1 || true
    exit 1
fi
SCRIPT
```