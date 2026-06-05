---
language: shell
tags: [file, util, cli]
title: find & xargs
description: Locating files by name, type, size, and date using find; executing commands with -exec, parallel processing with xargs -P, and skipping directories with -prune.
source: pattern
---

```shell
#!/usr/bin/env bash
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
find . -name .git -prune -o -name node_modules -prune -o \
     -type f -name "*.py" -print

# ── Find with -exec ──
find . -type f -name "*.log" -exec rm {} \;        # delete each file
find . -type f -name "*.jpg" -exec mv {} ./images/ \;  # move each file
find . -type f -name "*.html" -exec cp {} {}.bak \;   # backup each file

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

```
