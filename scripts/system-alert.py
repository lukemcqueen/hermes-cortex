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

# ── Memory ──────────────────────────────────────────────────
try:
    r = subprocess.run(["top", "-l", "1", "-n", "0"], capture_output=True, text=True, timeout=10)
    m = re.search(r'PhysMem:\s+([\d.]+)([KMG])\s+used\s+\((\d+)([KMG])\s+wired\),\s+([\d.]+)([KMG])\s+unused', r.stdout)
    if m:
        def to_mb(val, unit):
            v = float(val)
            if unit == 'K': return v / 1024
            if unit == 'G': return v * 1024
            return v
        used_mb = round(to_mb(m.group(1), m.group(2)), 1)
        tr = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5)
        total_mb = round(int(tr.stdout.strip()) / 1048576, 1)
        pct = round(used_mb / total_mb * 100, 1)
        details.append(f"Memory: {pct}% ({used_mb}MB / {total_mb}MB)")
        if pct > MEM_PCT_WARN:
            alerts.append(f"⚠️ Memory at {pct}% — exceeds {MEM_PCT_WARN}% threshold")
except Exception:
    details.append("Memory: error reading")

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
if alerts:
    hostname = socket.gethostname()
    print(f"🚨 *System Alert — {hostname}*")
    print("")
    for a in alerts:
        print(a)
    print("")
    print("── Current State ──")
    for d in details:
        print(f"  {d}")
