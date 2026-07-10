---
language: shell
tags: [sys, util, cli]
title: Process Management
description: Inspecting, controlling, and managing processes: ps, pgrep, pkill, kill, trap, nohup, disown, and background job control.
source: pattern
---

```shell
#!/usr/bin/env bash
set -euo pipefail

# ── Inspecting processes ──
ps aux                              # all processes (BSD-style)
ps auxf                            # forest view (hierarchy)
ps -ef                             # all processes (System V style)
ps -eo pid,ppid,cmd,%mem,%cpu --sort=-%cpu | head -10  # top 10 by CPU

# ── Finding processes ──
pgrep -f "python my_script"       # find PID by full command
pgrep -u "$USER"                   # find all PIDs for current user
pgrep -x nginx                     # exact match on process name
pidof mysqld                       # find PID by name (shortcut)

# ── Sending signals ──
pkill -f "python my_script"       # kill by full command
pkill -9 -u "$USER" chrome        # SIGKILL all chrome by user
kill -15 "$PID"                    # SIGTERM (graceful)
kill -9 "$PID"                     # SIGKILL (force)
kill -0 "$PID"                     # test if process exists (no-op)

# ── Trap: clean-up on exit ──
cleanup() {
    echo "Cleaning up..."
    rm -f /tmp/temp_$$.lock
    kill "$child_pid" 2>/dev/null || true
}
trap cleanup EXIT ERR INT TERM

# Long-running background task with trap
sleep 1000 &
child_pid=$!
echo "Background PID: $child_pid"

# ── nohup: persist after logout ──
nohup python long_task.py > output.log 2>&1 &
nohup ./my_server --port 8080 &

# ── disown: remove job from shell's job table ──
long_running_rsync &
disown                              # survives shell exit

# ── Background job control ──
sleep 100 &                         # start in background (job 1)
tail -f /var/log/system.log &      # start in background (job 2)
jobs                                # list background jobs
fg %1                               # bring job 1 to foreground
bg %2                               # resume job 2 in background
kill %1                             # kill job 1

```
