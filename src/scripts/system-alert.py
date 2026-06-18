#!/usr/bin/env python3
"""
System resource threshold monitor — watchdog pattern.
Silent (empty stdout) when all metrics within normal range.
Non-empty stdout is delivered verbatim to the user (Telegram).
"""
import re, subprocess, sys, socket

MEM_PCT_WARN = 85
SWAP_PCT_WARN = 70
DISK_PCT_WARN = 90

alerts = []
details = []
remediations = []
HOSTNAME = socket.gethostname()[:12]

# ── Memory ──────────────────────────────────────────────────
try:
    # Use vm_stat for accurate breakdown (top inflates by counting compressed as used)
    page_size = 4096
    tr = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=5)

    def _vm_val(key, text):
        m = re.search(rf'^{key}:\s+([\d.]+)\.', text, re.MULTILINE)
        return int(m.group(1)) if m else 0

    free_pg = _vm_val("Pages free", tr.stdout)
    active_pg = _vm_val("Pages active", tr.stdout)
    inactive_pg = _vm_val("Pages inactive", tr.stdout)
    wired_pg = _vm_val("Pages wired down", tr.stdout)
    compressed = _vm_val("Pages occupied by compressor", tr.stdout) or 0

    total_pg = _vm_val("Pages", tr.stdout)  # fallback
    if not total_pg:
        tr2 = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5)
        total_bytes = int(tr2.stdout.strip())
        total_mb = round(total_bytes / 1048576, 1)
    else:
        total_mb = round(total_pg * page_size / 1048576, 1)

    # Truly in-use: active + wired pages
    used_mb = round((active_pg + wired_pg) * page_size / 1048576, 1)
    # Available for reclaim: free + inactive
    avail_mb = round((free_pg + inactive_pg) * page_size / 1048576, 1)

    pct = round(used_mb / total_mb * 100, 1) if total_mb else 0
    details.append(f"Memory: {pct}% ({used_mb}MB used + {avail_mb}MB available / {total_mb}MB total)")
    if pct > MEM_PCT_WARN:
        alerts.append(f"⚠️ Memory at {pct}% — exceeds {MEM_PCT_WARN}% threshold")
        # Auto-remediation: purge inactive memory on macOS
        try:
            subprocess.run(["purge"], capture_output=True, timeout=30)
            remediations.append(f"🔄 Ran purge to free inactive memory")
        except Exception:
            pass
except Exception as e:
    details.append(f"Memory: error ({e})")

# ── Swap ─────────────────────────────────────────────────────
try:
    r = subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True, timeout=5)
    parts = r.stdout.strip().replace("=", "").split()
    if len(parts) > 3:
        total = float(parts[1].rstrip("M"))
        used = float(parts[3].rstrip("M"))
        pct = round(used / total * 100, 1) if total else 0
        details.append(f"Swap: {pct}% ({used}MB / {total}MB)")
        if pct > SWAP_PCT_WARN:
            alerts.append(f"⚠️ Swap at {pct}% — exceeds {SWAP_PCT_WARN}% threshold")
except Exception:
    details.append("Swap: error reading")

# ── Disk ─────────────────────────────────────────────────────
try:
    r = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=5)
    lines = r.stdout.strip().split("\n")
    if len(lines) >= 2:
        parts = lines[1].split()
        for p in parts:
            if p.endswith("%"):
                pct = int(p.rstrip("%"))
                used_str = parts[2] if len(parts) > 2 else "?"
                total_str = parts[1] if len(parts) > 1 else "?"
                details.append(f"Disk: {pct}% ({used_str} / {total_str})")
                if pct > DISK_PCT_WARN:
                    alerts.append(f"⚠️ Disk at {pct}% — exceeds {DISK_PCT_WARN}% threshold")
                    # Auto-remediation: free disk space
                    try:
                        subprocess.run(["brew", "cleanup", "-s"], capture_output=True, timeout=120)
                        remediations.append("🔄 Ran brew cleanup -s")
                    except Exception:
                        pass
                    try:
                        subprocess.run(["docker", "system", "prune", "-f"], capture_output=True, timeout=60)
                        remediations.append("🔄 Ran docker system prune")
                    except Exception:
                        pass
                    # Prune old logs
                    subprocess.run(
                        ["find", str(Path.home() / ".hermes/logs"), "-name", "*.log*", "-mtime", "+7", "-delete"],
                        capture_output=True, timeout=30)
                break
except Exception:
    details.append("Disk: error reading")

# ── Load average ─────────────────────────────────────────────
try:
    r = subprocess.run(["sysctl", "-n", "vm.loadavg"], capture_output=True, text=True, timeout=5)
    parts = r.stdout.strip().strip("{}").split()
    if len(parts) >= 3:
        details.append(f"Load: {parts[0]} / {parts[1]} / {parts[2]}")
except Exception:
    pass

# ── Output ───────────────────────────────────────────────────
from datetime import datetime, timezone
kst = timezone(__import__("datetime").timedelta(hours=9))
if alerts:
    ts = datetime.now(kst).strftime("%Y-%m-%d %H:%M KST")
    print(f"🚨 {HOSTNAME} [{ts}]")
    for a in alerts:
        print(f"  {a}")
    for r in remediations:
        print(f"  {r}")
    for d in details:
        print(f"  {d}")
