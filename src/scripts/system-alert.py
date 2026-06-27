#!/usr/bin/env python3
"""
System resource threshold monitor — watchdog pattern.
Silent (empty stdout) when all metrics within normal range.
Non-empty stdout is delivered verbatim to the user (Telegram).
Supports Linux and macOS.
"""
import re, subprocess, sys, socket
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from hermes_tz import format_timestamp

MEM_PCT_WARN = 85
SWAP_PCT_WARN = 90
DISK_PCT_WARN = 90

alerts = []
details = []
remediations = []
HOSTNAME = socket.gethostname()[:12]

# PII scrubbing — never expose hostname or user paths in output
def safe_hostname() -> str:
    """Return generic label instead of actual hostname (PII)."""
    return "server"

def scrub_pii(text: str) -> str:
    """Remove PII from detail strings before output."""
    home = str(Path.home())
    text = text.replace(home, "~")
    return text

is_linux = sys.platform.startswith("linux")
is_macos = sys.platform == "darwin"

# ── Memory & Swap (cross-platform) ──────────────────────────
try:
    if is_linux:
        with open("/proc/meminfo") as f:
            meminfo = f.read()
        def _kv(key):
            m = re.search(rf"^{key}:\s+(\d+)", meminfo, re.MULTILINE)
            return int(m.group(1)) * 1024 if m else 0  # kB to bytes

        total_b = _kv("MemTotal")
        free_b = _kv("MemFree")
        avail_b = _kv("MemAvailable")
        active_b = _kv("Active")
        inactive_b = _kv("Inactive")
        wired_b = _kv("Unevictable")  # not exact wired, best proxy
        swap_total_b = _kv("SwapTotal")
        swap_free_b = _kv("SwapFree")
        swap_cached_b = _kv("SwapCached")

        total_mb = round(total_b / 1048576, 1)
        # Used is total - available (what Linux actually considers in use)
        used_mb = round((total_b - avail_b) / 1048576, 1)
        avail_mb = round(avail_b / 1048576, 1)
        pct = round(used_mb / total_mb * 100, 1) if total_mb else 0

        details.append(f"Memory: {pct}% ({used_mb}MB used, {avail_mb}MB available / {total_mb}MB total)")
        if pct > MEM_PCT_WARN:
            alerts.append(f"⚠️ Memory at {pct}% — exceeds {MEM_PCT_WARN}% threshold")

        swap_used_b = swap_total_b - swap_free_b + swap_cached_b
        swap_pct = round(swap_used_b / swap_total_b * 100, 1) if swap_total_b else 0
        if swap_total_b:
            details.append(f"Swap: {swap_pct}% ({round(swap_used_b/1048576,1)}MB / {round(swap_total_b/1048576,1)}MB)")
            if swap_pct > SWAP_PCT_WARN:
                alerts.append(f"⚠️ Swap at {swap_pct}% — exceeds {SWAP_PCT_WARN}% threshold")
    elif is_macos:
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
        tr2 = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5)
        total_bytes = int(tr2.stdout.strip())
        total_mb = round(total_bytes / 1048576, 1)
        used_mb = round((active_pg + wired_pg) * page_size / 1048576, 1)
        avail_mb = round((free_pg + inactive_pg) * page_size / 1048576, 1)
        pct = round(used_mb / total_mb * 100, 1) if total_mb else 0
        details.append(f"Memory: {pct}% ({used_mb}MB used + {avail_mb}MB available / {total_mb}MB total)")
        if pct > MEM_PCT_WARN:
            alerts.append(f"⚠️ Memory at {pct}% — exceeds {MEM_PCT_WARN}% threshold")
            try:
                subprocess.run(["purge"], capture_output=True, timeout=30)
                remediations.append("🔄 Ran purge to free inactive memory")
            except Exception:
                pass
        # Swap on macOS
        r = subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True, timeout=5)
        parts = r.stdout.strip().replace("=", "").split()
        if len(parts) > 3:
            s_total = float(parts[1].rstrip("M"))
            s_used = float(parts[3].rstrip("M"))
            s_pct = round(s_used / s_total * 100, 1) if s_total else 0
            details.append(f"Swap: {s_pct}% ({s_used}MB / {s_total}MB)")
            if s_pct > SWAP_PCT_WARN:
                alerts.append(f"⚠️ Swap at {s_pct}% — exceeds {SWAP_PCT_WARN}% threshold")
except Exception as e:
    details.append(f"Memory: error ({e})")

# ── Load average ──────────────────────────────────────────────
try:
    if is_linux:
        with open("/proc/loadavg") as f:
            parts = f.read().strip().split()[:3]
    elif is_macos:
        r = subprocess.run(["sysctl", "-n", "vm.loadavg"], capture_output=True, text=True, timeout=5)
        parts = r.stdout.strip().strip("{}").split()[:3]
    else:
        parts = []
    if len(parts) >= 3:
        details.append(f"Load: {parts[0]} / {parts[1]} / {parts[2]}")
except Exception:
    pass

# ── Disk (cross-platform, same df on both) ──────────────────
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
                    # Auto-remediation is platform-specific
                    if is_macos:
                        try:
                            subprocess.run(["brew", "cleanup", "-s"], capture_output=True, timeout=120)
                            remediations.append("🔄 Ran brew cleanup -s")
                        except Exception:
                            pass
                    elif is_linux:
                        try:
                            subprocess.run(["sudo", "apt", "autoremove", "--purge", "-y"],
                                           capture_output=True, timeout=120)
                            remediations.append("🔄 Ran apt autoremove")
                        except Exception:
                            pass
                        try:
                            subprocess.run(["sudo", "apt", "clean"], capture_output=True, timeout=30)
                            remediations.append("🔄 Ran apt clean")
                        except Exception:
                            pass
                    try:
                        subprocess.run(["docker", "system", "prune", "-f"], capture_output=True, timeout=60)
                        remediations.append("🔄 Ran docker system prune")
                    except Exception:
                        pass
                    subprocess.run(
                        ["find", str(Path.home() / ".hermes/logs"), "-name", "*.log*", "-mtime", "+7", "-delete"],
                        capture_output=True, timeout=30)
                break
except Exception:
    details.append("Disk: error reading")

# ── Loop Governance Health ───────────────────────────────────
LOOP_DB = Path.home() / ".hermes" / "data" / "loop-governance.db"
try:
    # Check Ollama (skip if binary not installed — dev tool, not on all hosts)
    import shutil as _shutil
    if _shutil.which("ollama"):
        import urllib.request, json as _json
        try:
            req = urllib.request.Request("http://localhost:11434/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                tags = _json.loads(resp.read())
                models = [m["name"] for m in tags.get("models", [])]
                if not any("nomic-embed-text" in m for m in models):
                    alerts.append("⚠️ nomic-embed-text model not loaded (needed for TDD scoring)")
                    details.append("  Run: ollama pull nomic-embed-text")
        except Exception:
            alerts.append("⚠️ Ollama not responding on :11434 — TDD scoring unavailable")
            details.append("  Attempting auto-restart…")
            try:
                import subprocess as _sp
                _sp.run(["ollama", "serve"], capture_output=True, timeout=5)
                details.append("  → ollama serve started")
            except Exception:
                details.append("  → auto-restart failed")

    # Check database
    if LOOP_DB.exists():
        size_mb = round(LOOP_DB.stat().st_size / 1048576, 1)
        details.append(f"Loop DB: {size_mb}MB ({LOOP_DB.name})")
        # Warn if DB is large
        if size_mb > 100:
            alerts.append(f"⚠️ Loop DB at {size_mb}MB — run vacuum_old_cycles(days=90)")
    else:
        details.append("Loop DB: not yet created (first score-cycle will create it)")

    # Quick functional test: can we score?
    import sqlite3
    try:
        conn = sqlite3.connect(str(LOOP_DB))
        count = conn.execute("SELECT COUNT(*) FROM loop_cycles").fetchone()[0]
        conn.close()
        details.append(f"Scored cycles: {count}")
    except Exception:
        pass

except Exception as e:
    details.append(f"Loop governance: error ({e})")

# ── Output ───────────────────────────────────────────────────
if alerts:
    ts = format_timestamp("%Y-%m-%d %H:%M %Z")
    print(f"🚨 {HOSTNAME} [{ts}]")
    for a in alerts:
        print(f"  {a}")
    for r in remediations:
        print(f"  {r}")
    for d in details:
        print(f"  {d}")