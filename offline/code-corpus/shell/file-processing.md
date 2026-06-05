---
language: shell
tags: [file, util, cli]
title: File Processing Scripts
description: Common shell one-liners and scripts for file processing.
source: pattern
---

```shell
#!/usr/bin/env bash
set -euo pipefail

# Loop over files with extension
for f in *.txt; do
    echo "Processing $f"
    wc -l "$f"
done

# Find and replace in files
find . -name '*.py' -type f -exec sed -i '' 's/old_text/new_text/g' {} +

# Backup files with date
for f in *.config; do
    cp "$f" "${f}.bak.$(date +%Y%m%d)"
done

# Batch rename (prefix)
for f in *.jpg; do
    mv "$f" "vacation_$f"
done

# Check disk usage per directory
du -sh */ | sort -rh | head -10

# Extract tar.gz
tar -xzf archive.tar.gz -C /target/dir

# Find large files (>100MB)
find . -type f -size +100M -exec ls -lh {} \; | awk '{print $5, $NF}'

# Monitor log file in real-time
tail -f /var/log/system.log | grep --line-buffered ERROR

# CPU/memory per process
ps aux --sort=-%cpu | head -5
```
