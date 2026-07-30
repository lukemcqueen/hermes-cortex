---
title: Linux Performance Diagnostics
name: linux-performance-diagnostics
version: 1.0.0
description: Systematic "system is slow" diagnosis — baseline resource check, CPU frequency scaling analysis, process/core affinity mapping, container-level activity, and differentiation between transient vs chronic bottlenecks.
category: devops
triggers:
  - user says "system is slow", "lagging", "unresponsive", "high load", "keeps halting", "keeps freezing", "keeps crashing"
  - user asks what's using resources, why fans are spinning, why things feel sluggish
  - user reports latency issues, interactive lag, or application slowness
  - user asks you to "check why this server feels slow"
---

# Linux Performance Diagnostics

Systematic diagnosis when a user reports slowness. Start broad, narrow fast.

## Phase 1: Baseline snapshot (run ALL of these in parallel)

```bash
# Load, CPU idle, memory, swap, disk iowait
uptime && echo "---" && free -h && echo "---" && top -b -n1 | head -25

# Top CPU consumers (forces all processes, avoids top truncation)
ps aux --sort=-%cpu | head -20

# Top memory consumers
ps aux --sort=-%mem | head -10

# Swap activity + I/O + system stats (3 samples to catch bursts)
vmstat 1 3

# Disk space on root + home
df -h / /home

# Disk I/O latency (install sysstat if missing)
iostat -xz 1 1 2>/dev/null || apt-get install -y sysstat 2>/dev/null && iostat -xz 1 1
```

### 🔍 Interpreting `ps` output — spotting kernel throttle

When scanning `ps aux --sort=-%cpu`, look for `[idle_inject/N]` entries — kernel threads created by `intel_powerclamp`. Their presence means the kernel is **forcibly injecting idle cycles** into CPU cores to reduce power/heat. This is your first clue that the system is being thermally throttled at the kernel level, regardless of what cpufreq says.

Example signature:
```
USER         PID %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND
moses       7792  276 20.3 4134536 3311376 ?     Rl   17:00   3:10 llama-server ...
root          22  6.4  0.0      0     0 ?        S    16:57   0:17 [idle_inject/0]
root          25  6.4  0.0      0     0 ?        S    16:57   0:17 [idle_inject/1]
root          31  6.4  0.0      0     0 ?        S    16:57   0:17 [idle_inject/2]
...
```
Here, `idle_inject/[0-7]` are consuming ~6.4% CPU each — the kernel has decided the CPU is too hot and is actively throttling all cores.

## Phase 2: CPU frequency scaling check

A core at minimum frequency (e.g. 800 MHz) is **normal when idle**. The question is whether it scales up under load.

### Check current frequencies

```bash
grep . /sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq
```

### Check governor

```bash
cat /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
# Normal values: schedutil, ondemand, conservative. 'powersave' is a red flag.
```

### 🚨 Verify whether low-frequency cores are STUCK or just IDLE

The critical test — if a process is actively running on a low-frequency core, the frequency should rise:

```bash
# 1. Find which cores busy processes are on
ps -eo pid,comm,psr,%cpu --sort=-%cpu | head -20

# 2. Watch the suspect core's frequency over 3-5 seconds
for i in 1 2 3 4 5; do
  cat /sys/devices/system/cpu/cpu1/cpufreq/scaling_cur_freq  # change cpu# as needed
  sleep 0.5
done
```

If the frequency fluctuates up (1-4 GHz range) under load → **not stuck**, normal power-save.
If it stays pegged at minimum while a process consumes >5% CPU on that core → **stuck**.

### Cross-validation and driver identity

Always cross-validate `scaling_cur_freq` against `/proc/cpuinfo` — one source may lie, two sources agreeing rules out a reporting artifact:

```bash
grep "cpu MHz" /proc/cpuinfo | head -8
```

If both agree on the stuck-at-min frequency, the lock is real (not a driver reporting quirk).

Identify the active driver and intel_pstate mode — these determine which fix paths are available:

```bash
cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_driver
# intel_pstate     → active/hardware-managed P-states. Only 'performance' and 'powersave' governors.
# intel_cpufreq    → passive/software-managed through ACPI. Full governor list (schedutil, ondemand, etc.).

cat /sys/devices/system/cpu/intel_pstate/status
# active   → hardware P-state control (HWP), OS requests are advisory
# passive  → software-managed via intel_cpufreq driver
# disable  → ACPI cpufreq fallback (older driver)

# Check intel_pstate performance ceiling (0-100%)
cat /sys/devices/system/cpu/intel_pstate/max_perf_pct
cat /sys/devices/system/cpu/intel_pstate/min_perf_pct
# min_perf_pct=20 at 4.0 GHz max → floor of 800 MHz (matches 798 MHz stuck case)
# Setting min_perf_pct=100 forces the driver to request max P-state

cat /sys/devices/system/cpu/intel_pstate/no_turbo
# 0 = turbo allowed, 1 = turbo disabled (caps at base freq)

# Check if intel_powerclamp is actively injecting idle cycles
lsmod | grep intel_powerclamp
# If loaded, check dmesg for recent injection activity:
dmesg | grep -iE '(intel_powerclamp|injection)'
# "Start idle injection to reduce power" → the kernel is forcing idle on busy cores
```

### OS-level fixes for stuck cores

Requires root (sysfs files are root-owned, 644). Approaches:

```bash
# Force governor change (needs NOPASSWD or password)
echo performance | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor

# If on intel_pstate active mode: force max performance floor
echo 100 | sudo tee /sys/devices/system/cpu/intel_pstate/min_perf_pct

# Alternatively: toggle turbo disable/re-enable to reset P-state hardware
echo 1 | sudo tee /sys/devices/system/cpu/intel_pstate/no_turbo
sleep 1
echo 0 | sudo tee /sys/devices/system/cpu/intel_pstate/no_turbo

# If intel_powerclamp is loaded, unload it
sudo modprobe -r intel_powerclamp

# Toggle between active and passive intel_pstate modes
echo passive | sudo tee /sys/devices/system/cpu/intel_pstate/status
# Try ondemand, schedutil, or performance on the passive driver
echo ondemand | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
# Then switch back to active if needed
echo active | sudo tee /sys/devices/system/cpu/intel_pstate/status

# Switching back to schedutil after unstick (intel_cpufreq driver)
echo schedutil | sudo tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor
```

Common kernel drivers: `intel_pstate` (active/hardware-managed), `intel_cpufreq` (passive/software-managed).

If sysfs is not writable (no sudo or no NOPASSWD), report the stuck cores as a finding and recommend adding a NOPASSWD rule covering these paths:
- `/usr/bin/tee /sys/devices/system/cpu/cpu*/cpufreq/scaling_governor`
- `/usr/bin/tee /sys/devices/system/cpu/intel_pstate/status`
- `/usr/bin/tee /sys/devices/system/cpu/intel_pstate/min_perf_pct`
- `/usr/bin/tee /sys/devices/system/cpu/intel_pstate/no_turbo`

## Phase 3: Process-level analysis

### Check process-to-core affinity

```bash
ps -eo pid,comm,psr,%cpu --sort=-%cpu | head -20
```

A high-CPU process on a low-frequency core (confirmed stuck) is your bottleneck.

### Check for recently restarted containers

Docker containers that just restarted (check `docker ps` uptime vs system uptime) often do catch-up work — DB replays, WAL syncs, merge operations.

```bash
docker ps --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"
```

If a clickhouse, postgres, redis, or similar data container has been up for significantly *less* time than the system, it likely restarted recently and is doing recovery work that will settle.

### Check process elapsed time vs CPU time

```bash
ps -eo pid,comm,%cpu,%mem,etime --sort=-%cpu | head -20
```

A process with a short elapsed time but high CPU% is doing startup work (should settle). A process with hours of elapsed time and sustained high CPU is a chronic issue.

## Phase 4: Thermal check

```bash
sensors 2>/dev/null
```

- 40-65°C = normal under load
- 65-80°C = warm, may throttle
- 80-95°C = throttling likely
- 95-100°C = critical (system will aggressively throttle)

Check `cpufreq` scaling alongside temps — if frequencies drop while temps are high, thermal throttling is active.

## Phase 5: Container-level investigation

When Docker is running and a container is the top consumer:

```bash
# Check container resource usage
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" | sort -k2 -r

# Check if container recently restarted
docker inspect <container> | jq '.[0].State'
```

## Report format

### Breadth-first verification before presenting

Before claiming a diagnosis is complete, verify claims against ALL relevant sources — not just the first few. When the user says "check again" or "are you sure you checked everything", something was missed:

- **All processes** — Don't check just the top 3-5 CPU consumers. Scan the full list for kernel throttle signals (`idle_inject`, `kworker`) that sit further down.
- **All cron jobs** — When assessing whether a resource change is safe, enumerate every cron that touches that resource. Don't assume the main one is fine — check the long tail.
- **All data sources** — Cross-reference sensors, PSI, dmesg, cpufreq, process list. A single source (`top` showing 58% idle) can be misleading when another (PSI showing 30% stalled) contradicts it.
- **All historical occurrences** — If the user says "this has happened many times," search sessions, logs, and dmesg archives for the same pattern. Recurrence often reveals root cause (re-updated config, recurring cron, automatic restart).

The question to ask before presenting: *"If the user says 'check again', what would I reach for that I haven't looked at yet?"* If the answer exists, look now. Present once, present complete.

Deliver as a concise table + 1-2 sentence diagnosis. Example:

```
CPU: 97.6% idle, load 1.04
RAM: 12Gi available / 15Gi
Swap: 0 used
Disk iowait: 0%
Temps: 53°C
Frequencies: scaling normally (800-3800 MHz)

Main finding: clickhouse (Docker) restarted 34 min ago, 
consuming one core at 16.6% CPU. Will settle. 
Nothing broken.
```

## Phase 6: Pressure Stall Information (PSI)

PSI from `/proc/pressure/cpu|memory|io` reveals contention that CPU idle% hides. A core can be 97% idle while tasks are still stalled.

```bash
cat /proc/pressure/cpu
# some avg10=12.39  ← 12.4% of the time, at least one task was stalled for CPU
# full avg10=0.00   ← 0% of the time, ALL tasks were stalled
```

Interpretation:
- `some avg10` > 5-10% with low CPU idle → tasks are waiting for CPU despite apparent headroom (e.g. cgroup limits, single-core bottlenecks)
- `full avg10` > 0% + `some avg10` > 20% → severe contention, system is CPU-bound
- `full avg10` ≈ `some avg10` under I/O pressure → every task is blocked on I/O

PSI catches contention that `top` misses because `top` shows aggregate CPU idle across all cores — a single saturated core doesn't look bad in the average.

## Phase 7: Diagnosing a container CPU spin

When a Docker container burns sustained CPU (15-20% for 30+ min) with no legitimate workload, it's likely an internal spin loop — poor config, verbose logging, or oversized thread pools.

### 7a. Confirm it's a spin, not work

```bash
# Check for active queries or merges inside (clickhouse example)
docker exec <container> clickhouse-client --query "SELECT count() FROM system.merges"
docker exec <container> clickhouse-client --query "SELECT * FROM system.processes WHERE query NOT LIKE '%system.processes%'"

# Check number of background threads (clickhouse)
docker exec <container> clickhouse-client --query "SELECT name, value FROM system.server_settings WHERE name LIKE '%background%' OR name LIKE '%pool%' ORDER BY name"

# Check actual thread count
docker exec <container> sh -c "ls /proc/1/task/ | wc -l"
```

A container with 700+ threads, zero active queries/merges, and sustained CPU is a spin.

### 7b. Check log verbosity (clickhouse)

The ClickHouse Alpine 25.5 image ships with `<level>trace</level>` by default — the most verbose setting:

```bash
docker exec <container> grep "<level>" /etc/clickhouse-server/config.xml
# <level>trace</level> ← BAD: logs every background iteration
```

Trace logging causes:
- 16M+ text_log entries in minutes
- 70M+ async metrics entries
- 1.5 GB log files
- Sustained CPU from write + merge pressure on system tables

Fix: inject a log level override (see 7c) and drop accumulated system tables (see 7d).

### 7c. Fix: inject config override into running container

Create a config snippet and copy into the container's `config.d/` directory (ClickHouse auto-merges these with the main config, later files override earlier ones):

```bash
# Create override file
cat > /tmp/01-log-level.xml << 'XML'
<?xml version="1.0"?>
<clickhouse>
    <logger>
        <level>warning</level>
    </logger>
</clickhouse>
XML

# Copy into container
docker cp /tmp/01-log-level.xml <container>:/etc/clickhouse-server/config.d/01-log-level.xml

# Fix ownership (ClickHouse runs as uid 101/clickhouse, not root)
docker exec <container> chown clickhouse:clickhouse /etc/clickhouse-server/config.d/01-log-level.xml
docker exec <container> chmod 644 /etc/clickhouse-server/config.d/01-log-level.xml

# Reload config via SIGHUP
docker exec <container> kill -HUP 1

# Verify it loaded
docker exec <container> tail -3 /var/log/clickhouse-server/clickhouse-server.log
# Should show: "Loaded config '/etc/clickhouse-server/config.xml', performing update on configuration"
```

**Ownership trap**: Files copied via `docker cp` inherit the host user's UID. The container's clickhouse process (UID 101) cannot read them. Always `chown clickhouse:clickhouse` after `docker cp`ing config files.

**Persistence**: add a volume mount in docker-compose.yml so the override survives recreation:

```yaml
services:
  clickhouse:
    volumes:
      - ./clickhouse-config.d/01-log-level.xml:/etc/clickhouse-server/config.d/01-log-level.xml:ro
```

### 7d. Fix: drop accumulated system log tables

If trace logging was on for a while, the system log tables already accumulated millions of rows that will trigger merge loops when the log level is reduced:

```bash
docker exec <container> clickhouse-client --query "SELECT database, table, sum(rows) AS rows, formatReadableSize(sum(bytes_on_disk)) AS size FROM system.parts WHERE active=1 GROUP BY database, table ORDER BY sum(bytes_on_disk) DESC"
```

Truncate the large ones:
```bash
docker exec <container> clickhouse-client --query "TRUNCATE TABLE system.text_log"
docker exec <container> clickhouse-client --query "TRUNCATE TABLE system.trace_log"
docker exec <container> clickhouse-client --query "TRUNCATE TABLE system.asynchronous_metric_log"
docker exec <container> clickhouse-client --query "TRUNCATE TABLE system.metric_log"
docker exec <container> clickhouse-client --query "TRUNCATE TABLE system.query_log"
docker exec <container> clickhouse-client --query "TRUNCATE TABLE system.processors_profile_log"
```

These are internal clickhouse system tables — Langfuse doesn't read them. Truncation is safe.

### 7e. Low-memory clickhouse configuration

For single-server deployments where clickhouse doesn't need full throughput, see the reference file at `references/clickhouse-low-memory-config.md` for a comprehensive config that reduces background pool sizes, throttles system log collection intervals, and disables unused tables.

## Container resource capping (docker update)

### memory-swap gotcha

When a container was started with unlimited memory (swap=0), setting `--memory` alone makes Docker try to auto-set swap to 2x memory, which conflicts with the previous unlimited value:

```bash
docker update --cpus="0.5" --memory="512m" <container>
# Error: Memory limit should be smaller than already set memoryswap limit
```

**Fix**: always pass `--memory-swap` equal to `--memory` to disable swap explicitly:
```bash
docker update --cpus="0.5" --memory="1g" --memory-swap="1g" <container>
```

Verify:
```bash
docker inspect <container> --format 'CPUs={{.HostConfig.NanoCpus}} Memory={{.HostConfig.Memory}}'
# CPUs=500000000 = 0.5 cores, Memory=1073741824 = 1GB
```

### Persisting limits in compose

`cpus:` and `mem_limit:` are service-level keys in Docker Compose v3 (not under `deploy.resources` — those are Swarm-only):

```yaml
services:
  <service>:
    image: ...
    # ── Resource limits: prevent CPU contention with agent services ──
    cpus: 0.5
    mem_limit: 1g
```

## Phase 8: Firmware-level lock detection

When **every OS-level fix fails** — governor changes accepted, min_perf_pct set to 100, intel_pstate toggled between active/passive, turbo toggled, powerclamp unloaded — and the frequency never budges from minimum:

### 8a. Confirm it's a firmware lock

All three sources must agree on the stuck frequency for a lock confirmation, not a reporting bug:

```bash
# Source 1: cpufreq sysfs
grep . /sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq
# Source 2: /proc/cpuinfo (cross-validates)
grep "cpu MHz" /proc/cpuinfo | head -8
# Source 3: hardware sensor (temps normal, no thermal throttling)
sensors 2>/dev/null | grep -E '(Core|Package)'
```

A firmware lock has a distinct signature: **all cores pegged to the exact same minimum frequency** (typically 798-800 MHz on Haswell/Broadwell) regardless of driver, governor, or performance floor setting. OS writes are silently accepted (no errors) but have zero effect on actual frequency.

### 8b. Check RAPL power limits

RAPL (Running Average Power Limit) can silently clamp frequency even when thermal throttling is not active:

```bash
# List RAPL domains
ls /sys/class/powercap/
cat /sys/class/powercap/intel-rapl:0/name

# Check package power constraint
cat /sys/class/powercap/intel-rapl:0/constraint_0_power_limit_uw
# Value in microwatts — divide by 1,000,000 for watts
# If PL1 clamp is enabled (MSR register bit 1), CPU is power-capped
```

PL1 clamp can be checked via `rdmsr`:

```bash
sudo apt install -y msr-tools && sudo modprobe msr
sudo rdmsr 0x610  # MSR_PKG_POWER_LIMIT
```

Parse the result:
```
python3 -c "
msr = 0x$(sudo rdmsr 0x610)
pl1_clamp = (msr >> 1) & 1
pl1_en = msr & 1
print(f'PL1 enabled={pl1_en} clamp={pl1_clamp}')
"
# clamp=1 means the CPU will throttle to stay within the power budget
```

### 8c. Check for Apple SMC firmware lock (MacBooks)

On MacBooks running Linux (`applesmc` driver visible in `sensors`), the System Management Controller firmware can enforce a frequency floor independently of the OS kernel. This is the most common cause of an unbreakable frequency lock on Apple hardware.

Detection:
```bash
# Check for applesmc
ls /sys/devices/platform/applesmc.768/ 2>/dev/null && echo "Apple SMC present"

# Check fans — if they're suspiciously low for the load (e.g. 2100 RPM at load 5+),
# the firmware is keeping the CPU clocked down
cat /sys/devices/platform/applesmc.768/fan1_input

# Check pm_profile (2 = laptop/mobile)
cat /sys/firmware/acpi/pm_profile
```

Resolution options for MacBook firmware lock:
- **SMC reset** (most effective): Power off, press Left Shift + Control + Option + Power for 10 seconds, release, power on. No data loss — resets power management controller.
- **Reboot** — sometimes the lock clears on a fresh boot.
- **Kernel parameter** `processor.max_cstate=1` in `/etc/default/grub` (prevents deep C-states that trigger the firmware lock). Requires reboot after `update-grub`.
- **Accept** — the server runs at ~800 MHz (20% of max). Fans stay quiet, power draw is minimal. Document it as a known constraint.

### 8d. The OS-writes-accepted-but-frequency-unmoved litmus

If you've done ALL of these and frequency hasn't moved:
✅ Changed governor (multiple times)
✅ Toggled intel_pstate active/passive
✅ Set min_perf_pct = 100
✅ Toggled no_turbo
✅ Unloaded intel_powerclamp
✅ Checked RAPL (no clamp active)
✅ Temps normal (not thermal)
→ **The firmware is overriding OS P-state requests.** Document the lock, offer SMC reset or reboot, move on.

## Phase 9: Kernel thermal throttle detection (intel_powerclamp)

This is the most common cause of "system halts" on CPU-only MacBooks and thin laptops running LLM inference. Unlike frequency throttling (which just slows down cores), powerclamp **actively wastes CPU cycles** by injecting idle, making the system feel stuck even though load is low.

### 9a. The three-way diagnostic signature

All three must be present to confirm active kernel thermal throttling:

| Signal | Command | Red flag |
|--------|---------|----------|
| **`idle_inject` threads** | `ps aux --sort=-%cpu \| grep idle_inject` | Multiple `[idle_inject/N]` consuming 5-10% CPU each |
| **High temperature** | `sensors \| grep Package` | CPU package > 80°C (above the CPU's `high` threshold) |
| **Elevated PSI** | `cat /proc/pressure/cpu` | `some avg10` > 5% (tasks stalled for CPU despite apparent headroom) |

If **all three** are present, the kernel is forcibly throttling the CPU. If only one or two are present, investigate other causes first.

### 9b. Confirming powerclamp is the culprit

```bash
# Check if intel_powerclamp kernel module is loaded
lsmod | grep intel_powerclamp

# Check dmesg for throttle events
dmesg | grep -iE '(intel_powerclamp|idle injection|Start idle|Stop forced)'
# "Start idle injection to reduce power" → active throttle
# "Stop forced idle injection" → throttle released (CPU cooled)
```

The dmesg timestamps tell you how quickly the system heated up after boot and whether the throttle repeated.

### 9c. The correct fix: reduce load, don't remove powerclamp

**🚨 Do not unload intel_powerclamp when temps are > 80°C.** Removing the thermal safety net lets the CPU continue to cook toward the critical threshold (typically 100°C), which can cause thermal shutdown, hardware damage, or system panic.

The correct approach is to identify and reduce the heat source:

```bash
# 1. Find the heat source (top CPU consumers)
ps aux --sort=-%cpu | head -10

# 2. Check if it's an LLM model (llama-server, ollama)
# If yes → reduce compute load (see 9d)
# If no → is it a container spin loop? (see Phase 7)
# Is it a build/compile? Kill it or renice.

# 3. Once the heat source is reduced, powerclamp will stop on its own
```

Verify the fix worked:
```bash
sensors | grep Package          # Should drop below 80°C
dmesg | grep "Stop forced idle" # Should appear if it was active
cat /proc/pressure/cpu          # some avg10 should drop below 1%
```

### 9d. Ollama/LLM-inference thermal mitigation (CPU-only)

LLM inference on CPU is the most common thermal throttle trigger. When `llama-server` or `ollama` runners appear as the top CPU consumer:

**1. Limit CPU threads (biggest lever)** — Thread count is the dominant heat factor, not context size. Reducing from all cores to 2 threads drops power draw by ~60% with minimal latency impact for a 3B model. A Haswell-era MacBook verified this: 65536 context with 2 threads ran at 58°C — essentially the same as 4096 context at 54°C.

Set in Ollama's systemd service:
```ini
[Service]
Environment=OLLAMA_NUM_THREADS=2
```

**2. Set Ollama keep-alive to 0** — A model kept loaded after use maintains residual heat. `OLLAMA_KEEP_ALIVE=0` unloads the model immediately after each inference, letting the CPU cool between requests. Set in the same systemd service:

```ini
Environment=OLLAMA_KEEP_ALIVE=0
```

**3. If you must reduce context, check ALL consumers first** — Context reduction is a legitimate option when thread limiting alone isn't enough, but never change a system-wide parameter without tracing every consumer. Before reducing `num_ctx`:

   - Enumerate every cron that uses the local model (both no_agent scripts and LLM-driven loops)
   - Check file sizes of documents the crons read (SOUL.md, AGENTS.md, MEMORY.md, USER.md)
   - Verify the project's documented minimum standard (running with 4096 when the project requires 65536 breaks silently — inputs truncate without error)

   On a Haswell MacBook, thread limiting + keep-alive made context reduction unnecessary: 65536 ran at 58°C, same as 4096 at 54°C.

**4. Check for duplicate model runners** — Multiple concurrent llama-server processes multiply heat output. Kill unnecessary ones with `kill -9 <PID>`.

**5. Hardware maintenance** — On machines >5 years old, dried-out thermal paste is the underlying cause. Cleaning the heatsink and replacing paste can drop temps 10-15°C.

### 9e. When to escalate (firmware lock)

If load is reduced, temps are normal (60-75°C), but `idle_inject` threads persist and powers are high, proceed to **Phase 8: Firmware-level lock detection**. The Apple SMC on MacBooks can enforce frequency floors independently of the OS kernel.

## Pitfalls

- **iostat may not be installed.** Check with `command -v iostat` first, or use `iostat -xz 1 1 2>/dev/null || echo "install sysstat"`. Don't fail the investigation over it.
- **Clickhouse on Docker**: clickhouse uses port 8123 (HTTP) and 9000 (native protocol) internally in the Docker network — may not be exposed to host. Don't report it as "not responding" if you can't reach it on the host interface. Check `docker ps` port mapping.
- **schedutil governor + intel_cpufreq**: This combination on Haswell/Broadwell mobile CPUs occasionally gets stuck at min frequency. The fix is governor toggle or module reload. If the governor toggle doesn't unstick it (and nothing else does either), it's a firmware-level lock, not a schedutil bug — proceed to Phase 8.
- **cpufreq sysfs is root-owned (644)**. You can read but not write without sudo. If no NOPASSWD rule covers cpufreq, you can only report the finding.
- **MacBook firmware lock (applesmc)**: On Apple hardware running Linux, the SMC firmware can lock ALL cores at minimum frequency (~798-800 MHz) regardless of OS driver, governor, or performance settings. OS writes are accepted silently but have zero effect. The signature is all cores at exactly the same min frequency while load is high. Resolution: SMC reset (power off → Shift+Control+Option+Power 10s), or reboot. See `references/macbook-cpu-frequency-lock.md` for full session detail.
- **LLM thermal throttle (MacBook on CPU)**: CPU-only LLM inference on thin laptops (especially pre-2015 MacBooks) frequently triggers `intel_powerclamp` kernel throttling. See `references/macbook-llm-thermal-throttling.md` for a full session trace with before/after measurements, plus Ollama-specific mitigation steps.
- **When changing system parameters, enumerate ALL consumers first.** Changing a project-standard value (like model context from 65536 to 4096) without interviewing every cron, script, and workflow that depends on it produces silent breakage. The user will say "check again" — and they'll be right. Always ask: *"If someone set this value, why? What breaks if I lower it?"*
