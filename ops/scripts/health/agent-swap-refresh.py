#!/usr/bin/env python3
"""agent-swap-refresh.py — Daily swap refresh (no_agent cron).

Safety: only runs when available RAM > swap_used + 1 GB buffer.
Silent when conditions not met (safe no-op).
Needs NOPASSWD sudo for: /sbin/swapoff, /sbin/swapon
"""
import os
import re
import subprocess
import sys
from pathlib import Path

def _kv(key: str, text: str) -> int:
    m = re.search(rf"^{key}:\s+(\d+)", text, re.MULTILINE)
    return int(m.group(1)) * 1024 if m else 0

def main():
    if not sys.platform.startswith("linux"):
        return  # silent no-op on macOS

    try:
        with open("/proc/meminfo") as f:
            meminfo = f.read()
    except Exception:
        return

    swap_total = _kv("SwapTotal", meminfo)
    swap_free = _kv("SwapFree", meminfo)
    swap_used = swap_total - swap_free
    mem_avail = _kv("MemAvailable", meminfo)

    # Safety: need 1 GB buffer over swap usage
    buffer_bytes = 1 * 1024 * 1024 * 1024  # 1 GB

    if mem_avail < swap_used + buffer_bytes:
        return  # silent — not safe to refresh

    try:
        result = subprocess.run(
            ["sudo", "/sbin/swapoff", "-a"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            print(f"[agent-swap-refresh] swapoff failed: {result.stderr.strip()}")
            return

        result = subprocess.run(
            ["sudo", "/sbin/swapon", "-a"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            print(f"[agent-swap-refresh] swapon failed: {result.stderr.strip()}")
            return

        used_gb = round(swap_used / (1024**3), 1)
        avail_gb = round(mem_avail / (1024**3), 1)
        print(f"[agent-swap-refresh] Swap refreshed ({used_gb}GB moved to RAM, {avail_gb}GB available)")

    except FileNotFoundError:
        print("[agent-swap-refresh] sudo or swapoff not found — missing NOPASSWD sudo entry?")
    except subprocess.TimeoutExpired:
        print("[agent-swap-refresh] swapoff/swapon timed out (>120s)")

if __name__ == "__main__":
    main()
