---
language: shell
tags: [macos, troubleshooting, disk, activity-monitor, sysdiagnose]
title: macOS Troubleshooting & Diagnostics
description: System diagnostics, disk usage, memory pressure, crash logs, and sysdiagnose.
source: pattern
---

```bash
# ── System info ──
system_profiler SPHardwareDataType    # CPU, RAM, serial
system_profiler SPSoftwareDataType    # OS version, kernel
system_profiler SPDisplaysDataType    # GPU / display
sysctl -n machdep.cpu.brand_string    # CPU model string
sysctl hw.memsize                     # total RAM in bytes

# ── Disk ──
df -h /                               # free disk space
diskutil list                         # all volumes
diskutil info /                       # filesystem details
du -sh ~/Library/Caches               # cache directory size
sudo fs_usage -w -f filesys | head    # live filesystem calls

# ── Memory & Processes ──
memory_pressure                       # memory pressure (red/yellow/green)
vm_stat                               # page-ins/outs
top -l 1 -n 10 -stats pid,mem,cpu,command  # top 10 by CPU/MEM
ps aux --sort=-%mem | head -10        # top 10 by memory

# ── Crash logs ──
log show --last 1h --predicate 'eventMessage contains "crash"'  # recent crashes
ls -lt ~/Library/Logs/DiagnosticReports/ | head -5
sudo sysdiagnose -f ~/Desktop/        # full system diagnostics (take 2-5 min)

# ── Network ──
networksetup -listallhardwareports    # all network interfaces
networksetup -getdnsservers Wi-Fi     # DNS servers
networksetup -setdnsservers Wi-Fi 1.1.1.1 8.8.8.8
dscacheutil -q host -a name google.com  # DNS cache lookup
```
