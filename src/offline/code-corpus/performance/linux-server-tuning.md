---
language: shell
tags: [linux, performance, kernel, tuning]
title: Linux Kernel Performance Tuning
description: sysctl, ulimits, I/O scheduler, transparent hugepages, tuned-adm, CPU governor
source: pattern
---

# Linux Kernel Performance Tuning

## sysctl — Network & Kernel Parameters

```bash
# Apply immediately (survives reboot only if in /etc/sysctl.conf or /etc/sysctl.d/)
sysctl -w net.core.somaxconn=65535
sysctl -w net.ipv4.tcp_max_syn_backlog=65535
sysctl -w net.core.netdev_max_backlog=65535

# Reduce TIME_WAIT socket accumulation
sysctl -w net.ipv4.tcp_fin_timeout=15
sysctl -w net.ipv4.tcp_tw_reuse=1

# VM / memory
sysctl -w vm.swappiness=10
sysctl -w vm.vfs_cache_pressure=50
sysctl -w vm.dirty_ratio=30
sysctl -w vm.dirty_background_ratio=5

# File handles
sysctl -w fs.file-max=2097152
sysctl -w fs.nr_open=2097152

# Network buffer auto-tuning limits
sysctl -w net.core.rmem_max=134217728
sysctl -w net.core.wmem_max=134217728
sysctl -w net.ipv4.tcp_rmem='4096 87380 134217728'
sysctl -w net.ipv4.tcp_wmem='4096 65536 134217728'
```

```bash
# Persist settings (write to sysctl.d)
cat > /etc/sysctl.d/99-performance.conf << 'EOF'
net.core.somaxconn = 65535
net.ipv4.tcp_max_syn_backlog = 65535
net.core.netdev_max_backlog = 65535
net.ipv4.tcp_fin_timeout = 15
net.ipv4.tcp_tw_reuse = 1
vm.swappiness = 10
vm.vfs_cache_pressure = 50
vm.dirty_ratio = 30
vm.dirty_background_ratio = 5
fs.file-max = 2097152
fs.nr_open = 2097152
net.core.rmem_max = 134217728
net.core.wmem_max = 134217728
net.ipv4.tcp_rmem = 4096 87380 134217728
net.ipv4.tcp_wmem = 4096 65536 134217728
EOF

sysctl --system  # reload all
```

## ulimits — User Limits

```bash
# /etc/security/limits.conf — open files for application user
echo "*         soft    nofile          1048576" >> /etc/security/limits.conf
echo "*         hard    nofile          1048576" >> /etc/security/limits.conf
echo "*         soft    nproc           unlimited" >> /etc/security/limits.conf
echo "*         hard    nproc           unlimited" >> /etc/security/limits.conf

# PAM session module must be enabled
grep pam_limits.so /etc/pam.d/common-session
# If missing: echo "session required pam_limits.so" >> /etc/pam.d/common-session

# Verify for a running process
cat /proc/$(pgrep -x postgres | head -1)/limits | grep "open files"
```

## I/O Scheduler

```bash
# Check current scheduler per device
cat /sys/block/*/queue/scheduler

# Set to none (NVMe/SSD) or kyber/mq-deadline (multi-queue)
echo none > /sys/block/nvme0n1/queue/scheduler
echo mq-deadline > /sys/block/sda/queue/scheduler

# Persist via udev rule
cat > /etc/udev/rules.d/60-iosched.rules << 'EOF'
# NVMe drives: no scheduler needed
ACTION=="add|change", SUBSYSTEM=="block", KERNEL=="nvme[0-9]*", ATTR{queue/scheduler}="none"
# SSDs: use mq-deadline
ACTION=="add|change", SUBSYSTEM=="block", KERNEL=="sd*[!0-9]", ATTR{queue/rotational}=="0", ATTR{queue/scheduler}="mq-deadline"
# HDDs: use bfq or mq-deadline
ACTION=="add|change", SUBSYSTEM=="block", KERNEL=="sd*[!0-9]", ATTR{queue/rotational}=="1", ATTR{queue/scheduler}="bfq"
EOF

# Tune read-ahead (SSD: 256, HDD: 1024)
blockdev --setra 256 /dev/nvme0n1
```

## Transparent HugePages

```bash
# Check current state
cat /sys/kernel/mm/transparent_hugepage/enabled
# Output: [always] madvise never

# Databases (PostgreSQL, MongoDB) usually prefer 'madvise' or 'never'
# 'always' causes memory fragmentation and allocation stalls

# Disable entirely
echo never > /sys/kernel/mm/transparent_hugepage/enabled
echo never > /sys/kernel/mm/transparent_hugepage/defrag

# Or use madvise (safest for most workloads)
echo madvise > /sys/kernel/mm/transparent_hugepage/enabled

# Persist via kernel boot parameter
# Add to GRUB_CMDLINE_LINUX in /etc/default/grub:
#   transparent_hugepage=never
# Then: update-grub && reboot
```

## tuned-adm Profiles

```bash
# Install tuned
apt install tuned -y      # Debian/Ubuntu
yum install tuned -y      # RHEL/CentOS

# List available profiles
tuned-adm list

# Available profiles include:
#   throughput-performance   — good for DB/file servers
#   latency-performance      — minimize latency, max throughput
#   network-latency          — tuned for low network latency
#   network-throughput       — tuned for high network throughput
#   virtual-guest            — optimized for VMs
#   powersave                — power efficiency
#   desktop                  — balanced desktop workload

# Apply profile
tuned-adm profile latency-performance

# Check active profile
tuned-adm active

# Create custom profile from scratch
mkdir -p /etc/tuned/myapp-profile/
cat > /etc/tuned/myapp-profile/tuned.conf << 'EOF'
[main]
summary=Custom performance profile for myapp

[sysctl]
vm.swappiness = 10
vm.dirty_ratio = 30
vm.dirty_background_ratio = 5
net.core.somaxconn = 65535
fs.file-max = 2097152

[scheduler]
runtime=0
group.ksoftirqd=0:f:11:*:*

[vm]
transparent_hugepages=never
EOF

tuned-adm profile myapp-profile
```

## CPU Governor

```bash
# Check available governors
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors
# Typical: performance powersave userspace conservative ondemand schedutil

# Current governor
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_governor

# Set all cores to performance
for cpu in /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor; do
    echo performance > "$cpu"
done

# For non-server CPUs that support intel_pstate:
#   performance = max frequency always
#   powersave   = lowest frequency
# Server CPUs (Xeon) usually only support performance

# Persist with udev or tuned
# Using tuned profile (see above) is the cleanest approach

# Verify no throttling
grep -E "cpu[0-9]+" /proc/cpuinfo | grep -c "MHz"
# All cores should be near max frequency if governor=performance
```

## Verification

```bash
# Summary of active kernel parameters
echo "=== sysctl tunables ==="
sysctl net.core.somaxconn vm.swappiness fs.file-max

echo "=== I/O scheduler ==="
cat /sys/block/*/queue/scheduler 2>/dev/null

echo "=== THP status ==="
cat /sys/kernel/mm/transparent_hugepage/enabled

echo "=== CPU governor ==="
cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor 2>/dev/null | sort -u

echo "=== limits ==="
ulimit -a
```