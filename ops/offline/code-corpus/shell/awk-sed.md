---
language: shell
tags: [text, util, cli]
title: awk & sed Text Processing
description: Common awk and sed patterns for text processing: column extraction, pattern matching, find/replace in-place, and line deletion.
source: pattern
---

```shell
#!/usr/bin/env bash
set -euo pipefail

# ── awk: column extraction ──
# Extract columns from space/CSV/TSV data
awk '{print $1, $3}' file.txt
awk -F',' '{print $1, $3}' data.csv
awk -F'\t' '{print $2}' data.tsv

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
sed -i '' 's/\(pattern\)/\1_modified/g' file.txt  # backreferences

```
