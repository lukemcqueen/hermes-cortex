---
language: shell
tags: [disk, diagnostics, storage, monitoring]
title: Disk Diagnostics and Monitoring Tools
description: df, du, ncdu, iostat, iotop, smartctl, badblocks, fsck, dd benchmark, fio, lsblk, blkid
source: pattern
---

# Disk Diagnostics and Monitoring Tools

## Quick Space Assessment

```bash
# Human-readable disk space overview
df -h

# Show filesystem type and inode usage
df -hT
df -i

# Show usage for a specific mount
df -h /var/lib/postgresql

# Most detailed: all fields
df -aTh --sync
```

## Directory Size Analysis

```bash
# Top-level usage (slow on root, good for targeted directories)
du -sh /* 2>/dev/null | sort -rh | head -20

# Only N levels deep (faster)
du -d 2 -h /var 2>/dev/null | sort -rh | head -20

# Find largest files (not directories)
find /var -type f -exec du -Sh {} + 2>/dev/null | sort -rh | head -20

# Find largest directories
du -sh /var/* 2>/dev/null | sort -rh | head -10

# Show directory growth over time (compare snapshots)
du -sh /var/log
# Run periodically and record to track growth
```

## ncdu — Interactive Disk Analyzer

```bash
# Install if not present
apt install ncdu -y || yum install ncdu -y || brew install ncdu

# Analyze specific path (navigate with arrow keys)
ncdu /var

# Export report for comparison (ncdu 2.x)
ncdu /var -o /tmp/ncdu-snapshot.json
ncdu -f /tmp/ncdu-snapshot.json  # Browse offline

# Analyze with excludes
ncdu / --exclude /proc --exclude /sys --exclude /dev
```

## iostat — I/O Statistics

```bash
# Install sysstat package
apt install sysstat -y || yum install sysstat -y

# Basic: display CPU and device I/O since boot
iostat

# Extended stats (-x), continuous every 2 seconds (5 reports)
iostat -x 2 5

# Show only device stats, no CPU
iostat -d 2

# Human-readable, with I/O request sizes
iostat -xdh 5

# Key metrics:
#   %util    — percentage of time device was busy (not saturation!)
#   await    — avg I/O time (service + queue wait) in milliseconds
#   svctm    — avg service time (actual I/O processing) in ms
#   r/s, w/s — read/write requests per second
#   rkB/s, wkB/s — read/write throughput
#   aqu-sz   — average queue length

# Warning signs:
#   await > 20ms on SSD → potential issue
#   %util near 100% on HDD → device saturated
#   aqu-sz consistently > 1 → queue building up
```

## iotop — Per-Process I/O

```bash
# Install iotop
apt install iotop -y || yum install iotop -y

# Show I/O by process (requires root)
sudo iotop

# Batch mode (non-interactive) — top 5 I/O consumers
sudo iotop -b -n 5 | head -10

# Only processes with actual I/O (no idle)
sudo iotop -o

# Show cumulative I/O totals
sudo iotop -a

# JSON output for scripting
sudo iotop -b -n 1 -P -o | jq -R 'split(" ") | {pid: .[0], user: .[1], disk_read: .[2], disk_write: .[4]}'

# Key columns:
#   TID  — thread/process ID
#   PRIO — I/O priority
#   DISK READ  — bytes read per second
#   DISK WRITE — bytes written per second
#   SWAPIN     — swap usage
#   IO>        — I/O wait percentage for this process
```

## smartctl — SMART Disk Health

```bash
# Install smartmontools
apt install smartmontools -y || yum install smartmontools -y

# Check if device supports SMART
sudo smartctl -i /dev/nvme0n1
sudo smartctl -i /dev/sda

# Short health check
sudo smartctl -H /dev/sda

# Full SMART info (all attributes)
sudo smartctl -a /dev/sda

# Run a short self-test (2 minutes)
sudo smartctl -t short /dev/sda

# Run a long self-test (hours, depends on disk size)
sudo smartctl -t long /dev/sda

# Check test results
sudo smartctl -l selftest /dev/sda

# Continuous monitoring with smartd
# /etc/smartd.conf
echo '/dev/sda -a -m admin@example.com -M daily' >> /etc/smartd.conf
systemctl enable smartd && systemctl restart smartd

# Critical SMART attributes to watch:
#   Reallocated_Sector_Ct  — non-zero = bad sectors found
#   Current_Pending_Sector  — sectors waiting to be reallocated
#   Offline_Uncorrectable   — uncorrectable errors
#   Temperature_Celsius     — >55°C = warning, >60°C = critical
#   Wear_Leveling_Count     — NVMe endurance indicator
#   Media_Wearout_Indicator — SSD lifespan remaining
```

## badblocks — Surface Scan

```bash
# READ-ONLY test (safe, non-destructive)
sudo badblocks -sv /dev/sda

# Read-write test (DESTRUCTIVE — wipes data!)
# sudo badblocks -wsv /dev/sda

# Check specific partition (read-only)
sudo badblocks -sv /dev/sda1

# Run on unmounted partition, capture bad blocks to file
# sudo badblocks -o /tmp/bad-blocks.txt /dev/sda1

# Output: progress + total bad blocks found
# Zero bad blocks = healthy media
```

## fsck — Filesystem Check

```bash
# Unmount before checking (required for most operations)
# umount /dev/sda1

# Check filesystem (read-only)
sudo fsck /dev/sda1

# Force check even if clean
sudo fsck -f /dev/sda1

# Auto-repair (use with caution in production)
sudo fsck -y /dev/sda1

# Check all filesystems in /etc/fstab (skips network mounts)
sudo fsck -A -R -a

# Check ext4 filesystem specifically
sudo fsck.ext4 -fn /dev/sda1   # read-only + verbose
# sudo fsck.ext4 -fy /dev/sda1  # force repair

# Check XFS filesystem
sudo xfs_repair -n /dev/sda1   # dry run
# sudo xfs_repair /dev/sda1     # repair (requires unmount)
```

## dd — Disk Benchmark

```bash
# Sequential write benchmark (1GB, write 1M blocks)
dd if=/dev/zero of=/tmp/write-test bs=1M count=1024 conv=fdatasync oflag=direct

# Sequential read benchmark
dd if=/tmp/write-test of=/dev/null bs=1M count=1024 iflag=direct

# Show results:
#   "1073741824 bytes (1.1 GB) copied, 2.345 s, 458 MB/s"

# Sequential write with different block sizes
for bs in 4k 64k 1M 64M; do
    echo "Block size: $bs"
    dd if=/dev/zero of=/tmp/write-test-$bs bs=$bs count=1024 2>&1 | tail -1
done

# Clean up
rm -f /tmp/write-test /tmp/write-test-*

# WARNING: dd of=/dev/sda can destroy data — always double-check output file
```

## fio — IOPS & Latency Testing

```bash
# Install fio
apt install fio -y || yum install fio -y

# Random read IOPS test (4K, 32 depth, 60s)
fio --name=randread --ioengine=libaio --iodepth=32 --rw=randread \
    --bs=4k --direct=1 --size=1G --numjobs=1 --runtime=60 \
    --group_reporting --filename=/tmp/fio-test

# Random write IOPS test
fio --name=randwrite --ioengine=libaio --iodepth=32 --rw=randwrite \
    --bs=4k --direct=1 --size=1G --numjobs=1 --runtime=60 \
    --group_reporting --filename=/tmp/fio-test

# Mixed 70/30 read/write with latency percentiles
fio --name=mixed --ioengine=libaio --iodepth=16 --rw=randrw \
    --rwmixread=70 --bs=4k --direct=1 --size=1G --runtime=60 \
    --lat_percentiles=1 --percentile_list=50:90:99:99.9 \
    --group_reporting --filename=/tmp/fio-test

# Sequential throughput test
fio --name=seqread --ioengine=libaio --iodepth=64 --rw=read \
    --bs=1M --direct=1 --size=4G --runtime=30 \
    --group_reporting --filename=/tmp/fio-test

# Cleanup
rm -f /tmp/fio-test

# Key metrics in results:
#   IOPS (read/write)     — random workload performance
#   bw (bandwidth)        — sequential throughput
#   clat (completion latency) — 50th/90th/99th percentile
#   slat (submission latency) — kernel submission overhead
```

## Device Identification

```bash
# List block devices with hierarchy
lsblk
lsblk -f          # filesystem info
lsblk -o NAME,SIZE,TYPE,MOUNTPOINT,FSTYPE,UUID  # custom columns
lsblk -t          # topology (alignment, min/opt I/O)

# Block device attributes
blkid              # UUID and filesystem type
blkid -o list      # human-readable
blkid -s UUID /dev/sda1

# Find a disk by mount point
lsblk /var

# SCSI device details
lsscsi

# DMI/disk hardware info (if available)
sudo dmidecode -t memory 2>/dev/null | grep -A5 "Physical Memory Array"
```

## Full Diagnostic Script

```bash
#!/bin/bash
# Quick disk health diagnostic
set -euo pipefail

echo "=== Devices ==="
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINT | grep -v loop

echo "=== S.M.A.R.T. Status ==="
for dev in /dev/sd[a-z] /dev/nvme[0-9]n[0-9]; do
    [ -e "$dev" ] || continue
    echo "--- $dev ---"
    sudo smartctl -H "$dev" 2>/dev/null | grep -E "SMART overall-health|SMART Health Status" || echo "  No SMART data"
done

echo "=== I/O Stats (since boot) ==="
iostat -x 1 3
```