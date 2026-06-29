---
language: shell
tags: [macos, performance, optimization, system]
title: macOS Performance Tuning
description: Memory purge, Spotlight, launchd, animations, DNS cache, disk repair, thermal monitoring
source: pattern
---

# macOS Performance Tuning

## Memory Management

```bash
# Force purge of inactive memory (free up RAM)
sudo purge

# Check memory pressure (better than Activity Monitor)
memory_pressure | head -10

# View page-ins/outs and swap usage
vm_stat | grep -E "pageins|pageouts|swapins|swapouts"

# Check swap file usage (high swap = memory pressure)
ls -lh /var/vm/swapfile* 2>/dev/null || echo "No swap files found"
ls -lh /var/vm/sleepimage 2>/dev/null || echo "No sleep image found"

# Disable swap (requires SIP disabled — use with caution)
# sudo nvram boot-args="vm_compressor=2"

# Disable sudden motion sensor (SSD-only machines)
sudo pmset -a sms 0
```

## Spotlight — Disable Indexing Per Volume

```bash
# Check current indexing status
mdutil -s /
mdutil -s /Volumes/ExternalDrive

# Disable indexing on a specific volume
sudo mdutil -i off /Volumes/ExternalDrive

# Remove index files for a volume (frees disk space)
sudo mdutil -E /Volumes/ExternalDrive

# Completely disable Spotlight for a volume
sudo mdutil -i off /Volumes/ExternalDrive
sudo mdutil -E /Volumes/ExternalDrive

# List all volumes and their indexing state
mdutil -a -s

# Re-enable later
sudo mdutil -i on /Volumes/ExternalDrive

# Exclude directories from Spotlight (per-user)
touch ~/Library/Developer/Xcode/DerivedData/.metadata_never_index
```

## launchd Optimization

```bash
# List all running user agents
launchctl list | wc -l

# List all running system daemons
sudo launchctl list | wc -l

# Disable a user agent (load on next login)
launchctl disable user/"$(id -u)"/com.apple.ScreenTimeAgent

# Disable a system daemon permanently
sudo launchctl disable system/com.apple.metadata.mds

# Find heavy launchd agents (use with ps)
ps axo pid,pcpu,pmem,comm | grep launchd | sort -k2 -rn

# List loaded plists and their status
launchctl list | grep -v "com.apple" | sort

# Example: disable crash reporter (saves CPU on dev machines)
launchctl unload -w /System/Library/LaunchAgents/com.apple.ReportCrash.plist 2>/dev/null
```

## Disable Animations & Visual Effects

```bash
# Reduce motion (accessibility) — macOS Ventura+
defaults write com.apple.universalaccess reduceMotion -bool true

# Disable mission control animation
defaults write com.apple.dock expose-animation-duration -float 0.05

# Disable app opening bounce effect
defaults write com.apple.dock launchanim -bool false

# Disable auto-hide dock delay
defaults write com.apple.dock autohide-delay -float 0
defaults write com.apple.dock autohide-time-modifier -float 0

# Disable focus ring animation
defaults write NSGlobalDomain NSToolbarTitleViewRolloverDelay -float 0

# Disable window resize animation (finder)
defaults write com.apple.finder DisableAllAnimations -bool true

# Reduce transparency (dashboard, menus)
defaults write com.apple.universalaccess reduceTransparency -bool true

# Apply dock changes
killall Dock

# Apply finder changes
killall Finder
```

## DNS & Directory Cache

```bash
# Flush DNS cache (varies by macOS version)
# macOS Ventura+ (13.x)
sudo dscacheutil -flushcache
sudo killall -HUP mDNSResponder

# macOS Monterey and earlier
# sudo killall -HUP mDNSResponder
# sudo dscacheutil -flushcache

# Verify DNS is working after flush
dscacheutil -q host -a name google.com
nslookup google.com 8.8.8.8

# Check mDNSResponder resource usage
ps aux | grep mDNSResponder

# TTL override for performance testing
# /etc/resolver/ file configuration
```

## Disk Utility Repair

```bash
# List all volumes and their disk identifiers
diskutil list

# Check filesystem (read-only, safe)
diskutil verifyVolume /

# Repair filesystem (unmounts volume first)
# For APFS:
diskutil apfs updatePreboot /
diskutil verifyVolume /

# Full repair (requires single-user mode or recovery)
# Boot: Cmd+R → Disk Utility → First Aid
# Or from terminal in recovery:
# diskutil repairVolume disk1s5s1

# Repair permissions (macOS Catalina and earlier only)
# diskutil repairPermissions /  # removed in Big Sur+

# Check S.M.A.R.T. status
diskutil info disk0 | grep -i smart
# Or using smartctl (if installed via homebrew):
# smartctl -a /dev/disk0 | grep -E "SMART|Reallocated|Pending"
```

## Thermal Monitoring

```bash
# Check current CPU temperature (requires osx-cpu-temp or similar)
# Install: brew install osx-cpu-temp
osx-cpu-temp

# Check fan speed
sudo powermetrics --samplers smc -i 1000 -n 1 | grep -i fan

# Check thermal pressure level
pmset -g therm

# Thermal throttle status
sysctl machdep.xcpm.mode
sysctl machdep.xcpm.timer_interval

# Continuous monitoring (Ctrl+C to stop)
sudo powermetrics --samplers cpu_power -i 5000

# Check if thermal throttling is active
pmset -g log | grep -i "Thermal\|throttle" | tail -5

# Disable sudden motion sensor (SSD only)
sudo pmset -a sms 0

# Optimize energy settings for performance
sudo pmset -a hibernatemode 0          # Disable hibernation (saves disk space)
sudo pmset -a autopoweroff 0           # Disable auto power-off
sudo pmset -a disksleep 0              # Prevent disk spin-down
sudo pmset -a sleep 0                  # Never sleep (desktop)
```

## System Performance Health Check

```bash
#!/bin/bash
# Quick macOS performance health check

echo "=== Memory ==="
vm_stat | perl -ne '/page size of (\d+)/ and $size=$1; /Pages free:\s+(\d+)/ and printf "Free RAM: %.2f MB\n", $1 * $size / 1048576; /Pages active:\s+(\d+)/ and printf "Active:    %.2f MB\n", $1 * $size / 1048576; /Pages wired:\s+(\d+)/ and printf "Wired:     %.2f MB\n", $1 * $size / 1048576; /Pages inactive:\s+(\d+)/ and printf "Inactive:  %.2f MB\n", $1 * $size / 1048576'
memory_pressure | grep "pressure"

echo "=== CPU Thermal ==="
pmset -g therm | head -3
sysctl -n machdep.xcpm.mode 2>/dev/null && echo "XCPM active" || echo "XCPP inactive"

echo "=== Disk ==="
diskutil info disk0 | grep -E "SMART|Total Size|Volume Used"

echo "=== Launch Daemons (non-Apple) ==="
launchctl list | grep -v com.apple | wc -l | xargs echo "User agents:"

echo "=== Swap ==="
ls /var/vm/swapfile* 2>/dev/null && echo "Swap files present" || echo "No swap files"
```