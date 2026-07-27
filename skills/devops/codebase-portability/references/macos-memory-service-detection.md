# macOS Memory & Service Detection Patterns

Portable patterns for detecting memory usage and service health  
on both macOS and Linux from Python scripts.

## Memory Detection

### macOS

```python
import subprocess

# Total RAM (bytes → GB)
total_b, _ = subprocess.run(
    ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5
)
total_gb = int(total_b.strip()) / 1073741824

# Current usage via vm_stat
vm_out, _ = subprocess.run(
    ["vm_stat"], capture_output=True, text=True, timeout=5
)
# Parse key page counts (each page = 16384 bytes on Apple Silicon)
pages = {}
import re
for line in vm_out.split("\n"):
    for key in ["Pages free", "Pages speculative", "Pages purgable",
                 "File-backed pages", "Pages occupied by compressor"]:
        m = re.search(rf"{re.escape(key)}:\s+(\d+)", line)
        if m:
            pages[key] = int(m.group(1))

# Approximate used = total - free_pages * page_size
page_size = 16384  # Apple Silicon page size
total_pages = int(total_b.strip()) / page_size
free_pages = pages.get("Pages free", 0) + pages.get("Pages speculative", 0) + pages.get("Pages purgable", 0)
used_gb = (total_pages - free_pages) * page_size / 1073741824
```

### Linux

```python
# via 'free -h'
out, _ = subprocess.run(["free", "-h"], capture_output=True, text=True, timeout=5)
for line in out.split("\n"):
    if line.startswith("Mem:"):
        parts = line.split()
        total, used = parts[1], parts[2]  # human-readable like "7.8Gi"

# via /proc/meminfo (raw KB)
meminfo = Path("/proc/meminfo").read_text()
import re
mem_total = re.search(r"MemTotal:\s+(\d+)", meminfo)
mem_avail = re.search(r"MemAvailable:\s+(\d+)", meminfo)
if mem_total and mem_avail:
    pct = int((1 - int(mem_avail.group(1)) / int(mem_total.group(1))) * 100)
```

## Service / Daemon Detection

### gbrain daemon

```python
import sys, subprocess

if sys.platform == "darwin":
    # launchd on macOS
    out, _ = subprocess.run(
        ["launchctl", "list", "com.gbrain.autopilot"],
        capture_output=True, text=True, timeout=5
    )
    if '"PID"' in out:
        status = "active"
    else:
        # fallback to sync-watch
        out2, _ = subprocess.run(
            ["launchctl", "list", "com.gbrain.sync-watch"],
            capture_output=True, text=True, timeout=5
        )
        status = "active (legacy)" if '"PID"' in out2 else "inactive"
else:
    # systemd on Linux
    out, _ = subprocess.run(
        ["systemctl", "--user", "is-active", "gbrain-autopilot"],
        capture_output=True, text=True, timeout=5
    )
    if out.strip() == "active":
        status = "active"
    else:
        out2, _ = subprocess.run(
            ["systemctl", "--user", "is-active", "com.gbrain.sync-watch"],
            capture_output=True, text=True, timeout=5
        )
        status = "active (legacy)" if out2.strip() == "active" else "inactive"
```

## Platform Detection Shortcut

```python
IS_MAC = sys.platform == "darwin"
IS_LINUX = sys.platform == "linux"

# Memory: macOS uses vm_stat + sysctl, Linux uses free or /proc/meminfo
# Daemons: macOS uses launchctl, Linux uses systemctl --user
# Paths: macOS often uses /opt/homebrew/ or /usr/local/, Linux uses /etc/ or /usr/
```

## Common Pitfalls

- **`free` doesn't exist on macOS** — don't use it. Use `vm_stat` + `sysctl hw.memsize`.
- **`/proc/meminfo` doesn't exist on macOS** — it's a Linux procfs artifact.
- **launchctl output format** — `"PID" = 12345` means running; `"LastExitStatus"` means exited; empty means not registered.
- **systemctl --user vs systemctl** — user services (like gbrain) are per-user, not system-wide.
- **page size differs** — Apple Silicon = 16384 bytes (16K pages), Intel Mac = 4096 bytes. Use `vm_stat` which reports in system page size.
