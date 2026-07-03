"""Shell additions module — 5 supplementary Shell snippet entries.

Covers: awk/sed, process management, cron/scheduled tasks, curl/jq API
interaction, and find/xargs patterns. Does NOT duplicate any of the 3 core
Shell entries (file-processing, git-workflow, docker-workflow).
"""

SNIPPETS = [

    # ── 1. awk & sed Text Processing ──
    ("shell/awk-sed.md", "shell", ["text", "util", "cli"],
     "awk & sed Text Processing",
     "Common awk and sed patterns for text processing: column extraction, "
     "pattern matching, find/replace in-place, and line deletion.",
     "pattern",
     """#!/usr/bin/env bash
set -euo pipefail

# ── awk: column extraction ──
# Extract columns from space/CSV/TSV data
awk '{print $1, $3}' file.txt
awk -F',' '{print $1, $3}' data.csv
awk -F'\\t' '{print $2}' data.tsv

# ── awk: filter rows by condition ──
awk '$3 > 100 {print $1, $3}' report.txt
awk '/ERROR/ {print NR, $0}' app.log          # lines containing ERROR
awk 'NR > 1 {print}' data.csv                 # skip header row

# ── awk: aggregation ──
awk '{sum += $1} END {print "Total:", sum}' numbers.txt
awk '{count++} END {print "Lines:", count}' file.txt
awk -F',' '{sum += $3; count++} END {print "Avg:", sum/count}' data.csv

# ── sed: find & replace in-place ──
sed -i '' 's/old_text/new_text/g' file.txt     # macOS (BSD sed)
sed -i 's/old_text/new_text/g' file.txt        # Linux (GNU sed)

# ── sed: delete lines ──
sed -i '' '/^#/d' config.ini                   # delete comment lines
sed -i '' '/^$/d' file.txt                     # delete empty lines
sed -i '' '5,10d' file.txt                     # delete lines 5-10

# ── sed: selective printing ──
sed -n '10,20p' large.log                      # print lines 10-20
sed -n '/ERROR/,/END/p' app.log                # print range between patterns

# ── sed: advanced substitutions ──
sed -i '' 's/[[:space:]]*$//' file.txt         # trim trailing whitespace
sed -i '' 's/\\(pattern\\)/\\1_modified/g' file.txt  # backreferences
"""),

    # ── 2. Process Management ──
    ("shell/process-management.md", "shell", ["sys", "util", "cli"],
     "Process Management",
     "Inspecting, controlling, and managing processes: ps, pgrep, pkill, "
     "kill, trap, nohup, disown, and background job control.",
     "pattern",
     """#!/usr/bin/env bash
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
"""),

    # ── 3. Cron & Scheduled Tasks ──
    ("shell/cron-scheduled-tasks.md", "shell", ["sys", "util", "cli"],
     "Cron & Scheduled Tasks",
     "crontab syntax, @reboot, logging, lock files to prevent overlap, "
     "and the at command for one-shot scheduling.",
     "pattern",
     """#!/usr/bin/env bash
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
"""),

    # ── 4. curl & jq API Interaction ──
    ("shell/curl-jq-api.md", "shell", ["net", "api", "cli"],
     "curl & jq API Interaction",
     "REST API calls with curl (GET, POST, headers, JSON body) and jq for "
     "filtering, selecting, transforming, and error handling.",
     "pattern",
     """#!/usr/bin/env bash
set -euo pipefail

# ── GET requests ──
# Simple GET
curl https://api.example.com/items

# GET with headers
curl -H "Authorization: Bearer $TOKEN" \\
     -H "Accept: application/json" \\
     https://api.example.com/items

# GET with query parameters
curl -G https://api.example.com/search \\
     -d "q=search term" \\
     -d "page=1" \\
     -d "limit=20"

# ── POST requests ──
# POST with JSON body
curl -X POST https://api.example.com/items \\
     -H "Content-Type: application/json" \\
     -H "Authorization: Bearer $TOKEN" \\
     -d '{"name": "New Item", "value": 42}'

# POST from file (avoids shell quoting issues)
curl -X POST https://api.example.com/items \\
     -H "Content-Type: application/json" \\
     -d @payload.json

# ── PUT / PATCH / DELETE ──
curl -X PUT -H "Content-Type: application/json" \\
     -d '{"name": "Updated"}' \\
     https://api.example.com/items/1

curl -X DELETE https://api.example.com/items/1

# ── Download files ──
curl -o output.zip -L https://example.com/file.zip
curl -O https://example.com/file.zip              # preserves filename

# ── Error handling ──
# Fail on HTTP errors, follow redirects, silent mode
curl -sfSL https://api.example.com/items > response.json || {
    echo "API call failed" >&2
    exit 1
}

# ── jq: basic filtering ──
cat response.json | jq '.'                        # pretty-print
cat response.json | jq '.data'                    # extract key
cat response.json | jq '.items[]'                 # iterate array
cat response.json | jq '.items[0]'                # first element
cat response.json | jq '.items | length'          # count elements

# ── jq: select / filter ──
cat response.json | jq '.items[] | select(.status == "active")'
cat response.json | jq '.items[] | select(.price > 100)'
cat response.json | jq '.items[] | select(.name | test("^prefix"))'

# ── jq: transform output ──
cat response.json | jq '.items[] | {id, name, price}'
cat response.json | jq '[.items[] | {id, name}]'
cat response.json | jq -r '.items[].name'          # raw strings (no quotes)

# ── jq: error handling ──
cat response.json | jq -e '.data' > /dev/null 2>&1 || {
    echo "Response missing .data field" >&2
    exit 1
}

# ── Full pipeline: curl + jq ──
curl -sfSL "https://api.github.com/repos/user/repo/issues" |
    jq -r '.[] | select(.state == "open") | "\(.number) \(.title)"'
"""),

    # ── 5. find & xargs ──
    ("shell/find-xargs.md", "shell", ["file", "util", "cli"],
     "find & xargs",
     "Locating files by name, type, size, and date using find; executing "
     "commands with -exec, parallel processing with xargs -P, and "
     "skipping directories with -prune.",
     "pattern",
     """#!/usr/bin/env bash
set -euo pipefail

# ── Find by name ──
find . -name "*.py"                         # Python files (case-sensitive)
find . -iname "*.txt"                       # case-insensitive
find . -name "config.*" -type f             # config files only
find . -name "*.tmp" -delete                # find and delete temp files

# ── Find by type ──
find . -type f                              # regular files only
find . -type d                              # directories only
find . -type l                              # symbolic links
find . -type f -name "*.sh"                 # shell scripts

# ── Find by size ──
find . -type f -size +100M                  # larger than 100 MB
find . -type f -size -1k                    # smaller than 1 KB
find . -type f -size 1024k                  # exactly 1 MB
find . -type f -size +10M -size -100M       # between 10 MB and 100 MB

# ── Find by time ──
find . -type f -mtime -7                    # modified in last 7 days
find . -type f -mtime +30                   # modified more than 30 days ago
find . -type f -mmin -60                    # modified in last 60 minutes
find . -type f -newer reference.txt         # newer than reference file
find . -type f -atime +90                   # not accessed in 90+ days

# ── Find with -prune (skip directories) ──
# Skip .git and node_modules
find . -name .git -prune -o -name node_modules -prune -o \\
     -type f -name "*.py" -print

# ── Find with -exec ──
find . -type f -name "*.log" -exec rm {} \\;        # delete each file
find . -type f -name "*.jpg" -exec mv {} ./images/ \\;  # move each file
find . -type f -name "*.html" -exec cp {} {}.bak \\;   # backup each file

# -exec with + (batch, more efficient)
find . -type f -name "*.py" -exec chmod 644 {} +
find . -type f -empty -exec rm {} +

# ── xargs: basic usage ──
find . -type f -name "*.txt" | xargs wc -l          # count lines
find . -type f -name "*.py" | xargs grep "TODO"     # search for TODO
find . -type f -name "*.log" | xargs rm              # delete logs

# ── xargs: handle special chars (null separator) ──
find . -type f -name "*.txt" -print0 | xargs -0 wc -l

# ── xargs: parallel execution ──
# Compress images in parallel (4 concurrent jobs)
find . -type f -name "*.png" -print0 |
    xargs -0 -P 4 -I {} sh -c 'convert "{}" "{}.webp"'

# ── xargs: dry run (echo) ──
find . -type f -name "*.txt" | xargs -I {} echo "Processing: {}"

# ── Combine find + xargs for safe batch processing ──
find . -type f -name "*.tmp" -print0 |
    xargs -0 -r rm -f                            # -r: skip if no input
"""),

]
