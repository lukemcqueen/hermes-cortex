#!/usr/bin/env python3
"""Cortex Dashboard v2 — Enriched companion dashboard for Langfuse + Hermes."""
import base64, json, os, platform, re, shutil, sqlite3, subprocess, sys, time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from urllib.error import URLError
from urllib.request import Request, urlopen
from flask import Flask, jsonify, send_from_directory

HERMES_HOME = Path(os.environ.get("HERMES_HOME", Path.home() / ".hermes"))
STATE_DB = HERMES_HOME / "state.db"
CRON_JOBS = HERMES_HOME / "cron" / "jobs.json"
LANGFUSE_ENV = Path.home() / "langfuse" / ".env"
SCRIPTS_DIR = HERMES_HOME / "scripts"
LOGS_DIR = HERMES_HOME / "logs"
DASHBOARD_DIR = Path(__file__).parent / "static"
PORT = int(os.environ.get("CORTEX_DASHBOARD_PORT", "8901"))

# ── Langfuse credentials ──────────────────────────────────────────────
pk = sk = None
# Try ~/langfuse/.env first, then ~/.hermes/.env as fallback
for _env_candidate in [LANGFUSE_ENV, HERMES_HOME / ".env"]:
    if _env_candidate.exists():
        with open(_env_candidate) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if key in ("LANGFUSE_INIT_PROJECT_PUBLIC_KEY", "HERMES_LANGFUSE_PUBLIC_KEY"):
                        pk = val
                    elif key in ("LANGFUSE_INIT_PROJECT_SECRET_KEY", "HERMES_LANGFUSE_SECRET_KEY"):
                        sk = val
        if pk and sk:
            break

LANGFUSE_HOST = os.environ.get("LANGFUSE_HOST", "http://localhost:3000")
LANGFUSE_AUTH = None
if pk and sk:
    LANGFUSE_AUTH = base64.b64encode(f"{pk}:{sk}".encode()).decode()

# ── Flask app ──────────────────────────────────────────────────────────
app = Flask(__name__, static_folder=str(DASHBOARD_DIR), static_url_path="")
_cache = {}
_cache_lock = Lock()
CACHE_TTL = 30  # default cache TTL in seconds


def _cached(key, ttl=CACHE_TTL):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            tag = key
            if args:
                tag = f"{key}:{':'.join(str(a) for a in args)}"
            with _cache_lock:
                now = time.time()
                if tag in _cache and now - _cache[tag]["ts"] < ttl:
                    return _cache[tag]["data"]
            result = fn(*args, **kwargs)
            with _cache_lock:
                _cache[tag] = {"data": result, "ts": time.time()}
            return result
        wrapper.__name__ = fn.__name__
        return wrapper
    return decorator


def _clear_cache(prefix=None):
    with _cache_lock:
        if prefix is None:
            _cache.clear()
        else:
            for k in list(_cache.keys()):
                if k.startswith(prefix):
                    del _cache[k]


# ── Langfuse API ────────────────────────────────────────────────────────
def _lf(path, timeout=10):
    """Call Langfuse public API. Returns parsed JSON or None."""
    if not LANGFUSE_AUTH:
        return None
    try:
        # v3 API requires fromTimestamp - default to 7 days ago
        sep = "&" if "?" in path else "?"
        if "fromTimestamp" not in path:
            from_ts = ((datetime.now(timezone.utc) - timedelta(days=7)).isoformat()[:19] + "Z")
            path = f"{path}{sep}fromTimestamp={from_ts}"
        req = Request(f"{LANGFUSE_HOST}/api/public{path}")
        req.add_header("Authorization", f"Basic {LANGFUSE_AUTH}")
        req.add_header("User-Agent", "Hermes-Cortex-Dashboard/2.0")
        with urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"[lf] GET {path}: {e}", file=sys.stderr)
        return None


# ── Health ──────────────────────────────────────────────────────────────
def _find_pid(patterns):
    """Try multiple ps-based patterns, return first PID found.
    
    Uses `ps aux` instead of `pgrep` for more reliable matching on macOS.
    """
    try:
        r = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=5)
        lines = r.stdout.strip().split("\n")
    except Exception:
        return None
    
    for p in patterns if isinstance(patterns, list) else [patterns]:
        p_lower = p.lower()
        for line in lines:
            if p_lower in line.lower():
                parts = line.split()
                if len(parts) >= 2:
                    try:
                        return int(parts[1])
                    except ValueError:
                        continue
    return None


def _pid_running(pid):
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _get_uptime():
    """Return uptime in days."""
    if sys.platform == 'linux':
        try:
            with open('/proc/uptime') as f:
                sec = float(f.read().split()[0])
            return round(sec / 86400, 1)
        except Exception:
            return 0
    # macOS
    try:
        boot = subprocess.run(["sysctl", "-n", "kern.boottime"],
                              capture_output=True, text=True, timeout=5).stdout
        # Parse: { sec = 123456, usec = 0 } Wed Jun  1 ...
        m = re.search(r'sec\s*=\s*(\d+)', boot)
        if m:
            return round((time.time() - float(m.group(1))) / 86400, 1)
    except Exception:
        pass
    return 0


def _get_disk():
    try:
        df = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=5)
        lines = df.stdout.strip().split("\n")
        if len(lines) >= 2:
            parts = lines[1].split()
            for p in parts:
                if p.endswith("%"):
                    return int(p.rstrip("%"))
    except Exception:
        pass
    return 0


def _get_load():
    """Return 1/5/15 min load averages (works on both macOS and Linux)."""
    try:
        avg1, avg5, avg15 = os.getloadavg()
        return {"1min": round(avg1, 2), "5min": round(avg5, 2), "15min": round(avg15, 2)}
    except Exception:
        return None


def _get_memory():
    """Return memory usage percentage from top (Activity Monitor compatible)."""
    try:
        return _get_detailed_memory()["pct"]
    except Exception:
        return None


def _docker_bin() -> str:
    """Locate docker binary, falling back to PATH."""
    env = os.environ.get("DOCKER_BIN")
    if env:
        return env
    found = shutil.which("docker")
    return found or "docker"

def _check_docker(name_substring):
    """Check if a Docker container with the given name substring is running."""
    docker_bin = _docker_bin()
    try:
        r = subprocess.run(
            [docker_bin, "ps", "--filter", f"name={name_substring}",
             "--format", "{{.Names}}"],
            capture_output=True, text=True, timeout=5
        )
        return r.stdout.strip() != ""
    except Exception:
        return False


def _health():
    services = {
        "Ollama": {
            "check": lambda: _find_pid(["ollama serve", "[o]llama serve"]),
            "label": "LLM Server"
        },
        "Hermes Gateway": {
            "check": lambda: _find_pid(["hermes_cli.main gateway run",
                                        "gateway run --replace"]),
            "label": "Agent Gateway"
        },
        "GBrain Sync": {
            "check": lambda: _find_pid(["gbrain.*autopilot", "gbrain.*sync", "sync-watch"]),
            "label": "Memory Sync"
        },
        "nginx": {
            "check": lambda: _find_pid(["nginx: master"]),
            "label": "Web Proxy"
        },
        "Langfuse": {
            "check": lambda: "docker" if _check_docker("langfuse") else _find_pid(["langfuse-web", "langfuse-worker"]),
            "label": "LLM Observability"
        },
    }
    result = {}
    for name, cfg in services.items():
        pid = cfg["check"]()
        result[name] = {"status": "up" if pid else "down", "pid": pid or None, "label": cfg["label"]}

    up = sum(1 for s in result.values() if s["status"] == "up")
    total = len(result)

    return {
        "overall": "healthy" if up == total else "degraded" if up > 0 else "down",
        "services": result,
        "summary": f"{up}/{total} up",
        "disk_pct": _get_disk(),
        "uptime_days": _get_uptime(),
        "load": _get_load(),
        "memory_pct": _get_memory(),
    }


# ── Langfuse Data ───────────────────────────────────────────────────────
@_cached("lf_traces", ttl=60)
def _lf_traces():
    """Fetch traces and derive model usage + cost trends."""
    data = _lf("/traces?limit=50")
    if not data:
        return {"traces": [], "trace_count": 0, "model_usage": {}, "total_cost": 0, "recent": [], "cost_daily": {}}

    traces = data.get("data", [])
    # Also fetch observations for model usage
    obs_data = _lf("/observations?limit=100")
    model_usage = {}
    total_cost = 0.0
    cost_daily = defaultdict(float)
    all_obs = obs_data.get("data", []) if obs_data else []

    for o in all_obs:
        m = o.get("model") or "unknown"
        if m not in model_usage:
            model_usage[m] = {"calls": 0, "tokens": 0, "cost": 0.0, "label": m}
        model_usage[m]["calls"] += 1
        inp = o.get("inputTokens") or 0
        out = o.get("outputTokens") or 0
        model_usage[m]["tokens"] += inp + out
        cost = o.get("totalCost") or 0
        model_usage[m]["cost"] += cost
        total_cost += cost
        # Daily cost from observation start time
        st = o.get("startTime", "")
        if st and len(st) >= 10:
            day = st[:10]
            cost_daily[day] += cost

    recent = []
    for t in traces[:15]:
        recent.append({
            "id": t.get("id", ""),
            "name": t.get("name", "") or "(unnamed)",
            "timestamp": t.get("timestamp", ""),
            "cost": t.get("totalCost", 0),
            "latency": t.get("latency", 0),
            "htmlPath": t.get("htmlPath", ""),
            "obs_count": len([o for o in all_obs if o.get("traceId") == t.get("id")]),
        })

    return {
        "traces": traces,
        "trace_count": data.get("meta", {}).get("totalItems", 0),
        "model_usage": dict(model_usage),
        "total_cost": round(total_cost, 6),
        "recent": recent,
        "cost_daily": dict(sorted(cost_daily.items())),
    }


@_cached("lf_sessions", ttl=60)
def _lf_sessions():
    """Fetch Langfuse sessions."""
    data = _lf("/sessions?limit=20")
    if not data:
        return {"session_count": 0, "sessions": []}
    sessions = data.get("data", [])
    return {
        "session_count": data.get("meta", {}).get("totalItems", 0),
        "sessions": [
            {"id": s["id"], "createdAt": s.get("createdAt", "")}
            for s in sessions[:10]
        ],
    }


@_cached("lf_scores", ttl=60)
def _lf_scores():
    """Fetch evaluation scores."""
    data = _lf("/scores?limit=100")
    if not data:
        return {"score_count": 0, "score_breakdown": {}, "recent_scores": []}
    scores = data.get("data", [])
    sb = {}
    for s in scores:
        n = s.get("name", "?")
        sb.setdefault(n, {"count": 0, "sum": 0.0})
        sb[n]["count"] += 1
        sb[n]["sum"] += s.get("value", 0)
    return {
        "score_count": data.get("meta", {}).get("totalItems", 0),
        "score_breakdown": sb,
        "recent_scores": [
            {"name": s.get("name"), "value": s.get("value"),
             "comment": s.get("comment"), "traceId": s.get("traceId")}
            for s in scores[:10]
        ],
    }


# ── Hermes Local Data ──────────────────────────────────────────────────
@_cached("crons", ttl=60)
def _crons():
    if not CRON_JOBS.exists():
        return {"total": 0, "active": 0, "jobs": []}
    try:
        with open(CRON_JOBS) as f:
            data = json.load(f)
    except Exception:
        return {"total": 0, "active": 0, "jobs": []}
    jobs = data.get("jobs", [])
    job_list = []
    for j in jobs:
        s = j.get("schedule", {})
        if isinstance(s, dict):
            display = s.get("display") or s.get("expr", "")
        else:
            display = str(s)
        job_list.append({
            "name": j.get("name", "?"),
            "schedule": display,
            "enabled": j.get("enabled", True),
            "id": j.get("id", ""),
        })
    return {
        "total": len(jobs),
        "active": sum(1 for j in jobs if j.get("enabled", True)),
        "jobs": sorted(job_list, key=lambda x: (not x["enabled"], x["name"])),
    }


@_cached("sessions", ttl=30)
def _sessions():
    if not STATE_DB.exists():
        return {"total": 0, "messages": 0, "tokens": 0, "input_tokens": 0, "output_tokens": 0, "models": [], "recent": []}
    try:
        conn = sqlite3.connect(str(STATE_DB))
        c = conn.cursor()
        total = c.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        msgs = c.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        ti = c.execute("SELECT COALESCE(SUM(input_tokens),0) FROM sessions").fetchone()[0]
        to = c.execute("SELECT COALESCE(SUM(output_tokens),0) FROM sessions").fetchone()[0]
        mr = [r[0] for r in c.execute("SELECT DISTINCT model FROM sessions WHERE model IS NOT NULL AND model != ''").fetchall()]
        recent = c.execute(
            "SELECT id, title, model, started_at, message_count FROM sessions ORDER BY started_at DESC LIMIT 10"
        ).fetchall()
        conn.close()
    except Exception:
        return {"total": 0, "messages": 0, "tokens": 0, "input_tokens": 0, "output_tokens": 0, "models": [], "recent": []}
    return {
        "total": total,
        "messages": msgs,
        "tokens": ti + to,
        "input_tokens": ti,
        "output_tokens": to,
        "models": mr,
        "recent": [
            {"id": r[0], "title": r[1], "model": r[2], "started_at": r[3], "messages": r[4]}
            for r in recent
        ],
    }


def _session_timeline():
    """Session activity per day over the last 7 days."""
    if not STATE_DB.exists():
        return {"days": []}
    try:
        conn = sqlite3.connect(str(STATE_DB))
        c = conn.cursor()
        rows = c.execute("""
            SELECT date(started_at / 1000, 'unixepoch') as day, COUNT(*) as count
            FROM sessions
            WHERE started_at > (strftime('%s', 'now') - 7*86400) * 1000
            GROUP BY day ORDER BY day
        """).fetchall()
        conn.close()
        counts = {r[0]: r[1] for r in rows}
        # Fill missing days
        from datetime import timedelta
        today = datetime.now()
        days = []
        for i in range(6, -1, -1):
            d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            days.append({"date": d, "sessions": counts.get(d, 0)})
        return {"days": days}
    except Exception:
        return {"days": []}


# ── System Monitor (btop-style) ─────────────────────────────────────────
def _get_page_size() -> int:
    """Get VM page size in bytes."""
    if sys.platform == 'linux':
        try:
            return os.sysconf('SC_PAGE_SIZE')
        except Exception:
            return 4096
    try:
        r = subprocess.run(["sysctl", "-n", "hw.pagesize"], capture_output=True, text=True, timeout=5)
        return int(r.stdout.strip())
    except Exception:
        return 16384


def _get_processes() -> dict:
    """Top processes by CPU and memory."""
    try:
        if sys.platform == 'linux':
            r = subprocess.run(
                ["ps", "axo", "pid,pcpu,pmem,rss,comm", "--sort=-pcpu"],
                capture_output=True, text=True, timeout=10,
            )
        else:
            r = subprocess.run(
                ["ps", "axo", "pid,pcpu,pmem,rss,comm", "-r"],
                capture_output=True, text=True, timeout=10,
            )
        lines = r.stdout.strip().split("\n")
        procs = []
        for line in lines[1:]:  # skip header
            parts = line.strip().split(None, 4)
            if len(parts) >= 5:
                try:
                    procs.append({
                        "pid": int(parts[0]),
                        "cpu": float(parts[1]),
                        "mem": float(parts[2]),
                        "rss_mb": round(int(parts[3]) / 1024, 1),
                        "cmd": parts[4][:60],
                    })
                except (ValueError, IndexError):
                    continue
        return {
            "by_cpu": procs[:15],
            "by_mem": sorted(procs, key=lambda p: p["rss_mb"], reverse=True)[:15],
            "total": len(procs),
        }
    except Exception:
        return {"by_cpu": [], "by_mem": [], "total": 0}


def _get_detailed_memory() -> dict:
    """Memory from 'top' (Activity Monitor compatible) + vm_stat breakdown."""
    if sys.platform == 'linux':
        try:
            meminfo = {}
            with open('/proc/meminfo') as f:
                for line in f:
                    parts = line.split(':')
                    if len(parts) == 2:
                        key = parts[0].strip()
                        val_str = parts[1].strip()
                        # Values in kB
                        num = re.sub(r'[^0-9]', '', val_str.split()[0]) if val_str.split() else '0'
                        meminfo[key] = int(num) if num.isdigit() else 0
            total_kb = meminfo.get('MemTotal', 0)
            # Used = total - MemAvailable if available, else total - free - buffers - cached
            avail_kb = meminfo.get('MemAvailable', 0)
            if avail_kb:
                used_kb = total_kb - avail_kb
            else:
                used_kb = total_kb - meminfo.get('MemFree', 0) - meminfo.get('Buffers', 0) - meminfo.get('Cached', 0)
            total_mb = round(total_kb / 1024, 1)
            used_mb = round(max(used_kb, 0) / 1024, 1)
            free_kb = meminfo.get('MemFree', 0)
            free_mb = round(free_kb / 1024, 1)
            active_kb = meminfo.get('Active', 0)
            active_mb = round(active_kb / 1024, 1)
            inactive_kb = meminfo.get('Inactive', 0)
            inactive_mb = round(inactive_kb / 1024, 1)
            # Linux doesn't have "wired" memory — approximate as active + slab
            slab_kb = meminfo.get('SUnreclaim', meminfo.get('Slab', 0))
            wired_mb = round(slab_kb / 1024, 1)
            # SwapCached approximates compressed memory
            compressed_kb = meminfo.get('SwapCached', 0)
            compressed_mb = round(compressed_kb / 1024, 1)
            return {
                "total_mb": total_mb,
                "used_mb": used_mb,
                "free_mb": free_mb,
                "wired_mb": wired_mb,
                "active_mb": active_mb,
                "compressed_mb": compressed_mb,
                "inactive_mb": inactive_mb,
                "pct": round(used_mb / total_mb * 100, 1) if total_mb else 0,
            }
        except Exception:
            return {"total_mb": 0, "used_mb": 0, "free_mb": 0, "wired_mb": 0,
                    "active_mb": 0, "compressed_mb": 0, "inactive_mb": 0, "pct": 0}
    total_mb = 0
    used_mb = 0
    free_mb = 0
    wired_mb = 0
    # Get total from sysctl
    try:
        tr = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5)
        total_mb = round(int(tr.stdout.strip()) / 1048576, 1)
    except Exception:
        pass
    # Parse top -l 1 for the same numbers Activity Monitor shows
    # Output: "PhysMem: 11G used (1937M wired), 4791M unused."
    try:
        r = subprocess.run(["top", "-l", "1", "-n", "0"], capture_output=True, text=True, timeout=10)
        m = re.search(r'PhysMem:\s+([\d.]+)([KMG])\s+used\s+\((\d+)([KMG])\s+wired\),\s+([\d.]+)([KMG])\s+unused', r.stdout)
        if m:
            def parse_val(val, unit):
                v = float(val)
                if unit == 'K': return v / 1024
                if unit == 'G': return v * 1024
                return v  # M
            used_mb = parse_val(m.group(1), m.group(2))
            wired_mb = float(m.group(3))
            free_mb = parse_val(m.group(5), m.group(6))
    except Exception:
        pass
    # vm_stat for accurate breakdown (handles multi-word keys)
    compressed_mb = 0
    active_mb = 0
    inactive_mb = 0
    try:
        r2 = subprocess.run(["vm_stat"], capture_output=True, text=True, timeout=5)
        pages = {}
        for line in r2.stdout.strip().split("\n"):
            # Capture full key before colon (may have multiple words/special chars)
            mm = re.match(r'^(.+?):\s+(\d+)', line)
            if mm:
                key = mm.group(1).strip().lower()
                pages[key] = int(mm.group(2))
        page_size = _get_page_size()
        def mb(val):
            return round(val * page_size / 1048576, 1)

        # Read raw counters
        active_mb     = mb(pages.get("pages active", 0))
        compressed_mb = mb(pages.get("pages stored in compressor", 0))
        inactive_mb   = mb(pages.get("pages inactive", 0))
        free_v        = pages.get("pages free", 0)
        speculative   = pages.get("pages speculative", 0)
        free_mb       = mb(free_v + speculative)

        # True used = wired + active + compressed (excludes inactive which is available)
        used_mb = wired_mb + active_mb + compressed_mb
    except Exception:
        pass
    return {
        "total_mb": total_mb,
        "used_mb": round(used_mb, 1),
        "free_mb": round(free_mb, 1),
        "wired_mb": round(wired_mb, 1),
        "active_mb": round(active_mb, 1),
        "compressed_mb": round(compressed_mb, 1),
        "inactive_mb": round(inactive_mb, 1),
        "pct": round(used_mb / total_mb * 100, 1) if total_mb else 0,
    }


def _get_swap() -> dict:
    """Swap usage."""
    if sys.platform == 'linux':
        try:
            total_kb = 0
            used_kb = 0
            with open('/proc/swaps') as f:
                lines = f.read().strip().split('\n')
                for line in lines[1:]:  # skip header
                    parts = line.split()
                    if len(parts) >= 4 and parts[2].isdigit() and parts[3].isdigit():
                        total_kb += int(parts[2])
                        used_kb += int(parts[3])
            total_mb = round(total_kb / 1024, 1)
            used_mb = round(used_kb / 1024, 1)
            free_mb = round((total_kb - used_kb) / 1024, 1)
            return {
                "total_mb": total_mb,
                "used_mb": used_mb,
                "free_mb": free_mb,
                "pct": round(used_mb / total_mb * 100, 1) if total_mb else 0,
            }
        except Exception:
            return {"total_mb": 0, "used_mb": 0, "free_mb": 0, "pct": 0}
    try:
        r = subprocess.run(["sysctl", "-n", "vm.swapusage"], capture_output=True, text=True, timeout=5)
        # Format: total = 4096.00M  used = 2610.00M  free = 1486.00M  (encrypted)
        parts = r.stdout.strip().replace("=", "").split()
        total = float(parts[1].rstrip("M")) if len(parts) > 1 else 0
        used = float(parts[3].rstrip("M")) if len(parts) > 3 else 0
        free = float(parts[5].rstrip("M")) if len(parts) > 5 else 0
        return {
            "total_mb": total,
            "used_mb": used,
            "free_mb": free,
            "pct": round(used / total * 100, 1) if total else 0,
        }
    except Exception:
        return {"total_mb": 0, "used_mb": 0, "free_mb": 0, "pct": 0}


def _get_network_io() -> list:
    """Network I/O per interface since boot."""
    if sys.platform == 'linux':
        try:
            interfaces = []
            with open('/proc/net/dev') as f:
                lines = f.read().strip().split('\n')
                # Skip header lines (first two)
                for line in lines[2:]:
                    parts = line.split()
                    if len(parts) >= 10:
                        name = parts[0].rstrip(':')
                        # Only include physical interfaces and loopback
                        if name.startswith(('eth', 'en', 'wlan', 'lo')):
                            try:
                                ibytes = int(parts[1])
                                obytes = int(parts[9])
                                interfaces.append({
                                    "name": name,
                                    "ibytes": ibytes,
                                    "obytes": obytes,
                                    "in_mb": round(ibytes / 1048576, 1) if ibytes else 0,
                                    "out_mb": round(obytes / 1048576, 1) if obytes else 0,
                                })
                            except (ValueError, IndexError):
                                continue
            return interfaces
        except Exception:
            return []
    try:
        r = subprocess.run(
            ["netstat", "-ib"],
            capture_output=True, text=True, timeout=5,
        )
        interfaces = []
        seen = set()
        for line in r.stdout.strip().split("\n"):
            parts = line.split()
            if len(parts) >= 10 and parts[0] != "Name":
                name = parts[0].rstrip("*")
                if name.startswith("en") or name == "lo0":
                    if name in seen:
                        continue
                    seen.add(name)
                    try:
                        ibytes = int(parts[6])
                        obytes = int(parts[9])
                        interfaces.append({
                            "name": name,
                            "ibytes": ibytes,
                            "obytes": obytes,
                            "in_mb": round(ibytes / 1048576, 1) if ibytes else 0,
                            "out_mb": round(obytes / 1048576, 1) if obytes else 0,
                        })
                    except (ValueError, IndexError):
                        continue
        return interfaces
    except Exception:
        return []


_prev_network = {"snap": {}, "ts": 0}


def _get_network_rates() -> list:
    """Network I/O transfer rates in MB/s computed from cumulative delta.

    Returns rate per interface plus cumulative totals. Rate is 0 on
    first call (no prior snapshot to diff against).
    """
    global _prev_network
    now = time.time()
    current = _get_network_io()
    rates = []
    for iface in current:
        name = iface["name"]
        ibytes = iface["ibytes"]
        obytes = iface["obytes"]
        prev = _prev_network["snap"].get(name, {})
        dt = now - _prev_network["ts"] if _prev_network["ts"] else 0
        if prev and dt > 0:
            in_rate = round((ibytes - prev.get("in", ibytes)) / dt / 1048576, 3)
            out_rate = round((obytes - prev.get("out", obytes)) / dt / 1048576, 3)
        else:
            in_rate = 0.0
            out_rate = 0.0
        rates.append({
            "name": name,
            "in_mb_s": in_rate,
            "out_mb_s": out_rate,
            "in_total_mb": iface["in_mb"],
            "out_total_mb": iface["out_mb"],
        })
        _prev_network["snap"][name] = {"in": ibytes, "out": obytes}
    _prev_network["ts"] = now
    return rates


def _get_disk_io() -> dict:
    """Disk I/O statistics."""
    if sys.platform == 'linux':
        try:
            disks = []
            with open('/proc/diskstats') as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 14:
                        name = parts[2]
                        # Only physical block devices (sdX, nvmeX, vdX, xvdX)
                        if re.match(r'^(sd|nvme|vd|xvd|mmcblk)[a-z]', name):
                            reads = int(parts[3])
                            reads_sectors = int(parts[5])
                            writes = int(parts[7])
                            writes_sectors = int(parts[9])
                            # Convert sectors (512 bytes) to MB/s estimate: not a rate,
                            # but we provide cumulative sector count
                            disks.append({
                                "name": name,
                                "reads": reads,
                                "writes": writes,
                                "read_sectors": reads_sectors,
                                "write_sectors": writes_sectors,
                            })
            return {"disks": disks}
        except Exception:
            return {"disks": []}
    try:
        r = subprocess.run(
            ["iostat", "-d", "-c", "2"],
            capture_output=True, text=True, timeout=10,
        )
        lines = r.stdout.strip().split("\n")
        # iostat -d output: disk0 ... KB/t tps MB/s
        disks = []
        for line in lines:
            parts = line.split()
            if len(parts) >= 6 and parts[0].startswith("disk"):
                disks.append({
                    "name": parts[0],
                    "kb_per_t": parts[1] if len(parts) > 1 else "0",
                    "tps": parts[2] if len(parts) > 2 else "0",
                    "mb_s": parts[3] if len(parts) > 3 else "0",
                })
        return {"disks": disks}
    except Exception:
        return {"disks": []}


def _get_docker_stats() -> list:
    """Per-container resource usage via docker stats."""
    try:
        docker_bin = "/usr/local/bin/docker"
        if not os.path.exists(docker_bin):
            docker_bin = "docker"
        r = subprocess.run(
            [docker_bin, "stats", "--no-stream", "--format",
             '{{json .}}'],
            capture_output=True, text=True, timeout=10,
        )
        containers = []
        for line in r.stdout.strip().split("\n"):
            if line:
                try:
                    c = json.loads(line)
                    containers.append({
                        "name": c.get("Name", "?"),
                        "cpu_pct": c.get("CPUPerc", "0%").rstrip("%"),
                        "mem_usage": c.get("MemUsage", "0B / 0B").split(" / ")[0].strip(),
                        "mem_pct": c.get("MemPerc", "0%").rstrip("%"),
                        "net_io": c.get("NetIO", "0B / 0B"),
                        "block_io": c.get("BlockIO", "0B / 0B"),
                        "pids": c.get("PIDs", "0"),
                    })
                except (json.JSONDecodeError, KeyError):
                    continue
        return containers
    except Exception:
        return []


def _get_thread_count() -> dict:
    """Total processes and thread count."""
    if sys.platform == 'linux':
        try:
            # Process count
            r = subprocess.run(["ps", "-eo", "pid"], capture_output=True, text=True, timeout=5)
            procs = len(r.stdout.strip().split("\n")) - 1  # minus header
            # Thread count from /proc/stat
            threads = 0
            with open('/proc/stat') as f:
                for line in f:
                    if line.startswith('processes '):
                        # Total processes created since boot, not current threads
                        pass
                    elif line.startswith('threads '):
                        try:
                            threads = int(line.split()[1])
                        except (ValueError, IndexError):
                            pass
            # Fallback: count thread dirs in /proc
            if not threads:
                try:
                    for pid_entry in os.listdir('/proc'):
                        if pid_entry.isdigit():
                            task_dir = f'/proc/{pid_entry}/task'
                            if os.path.isdir(task_dir):
                                threads += len(os.listdir(task_dir))
                except Exception:
                    pass
            return {"processes": procs, "threads": threads}
        except Exception:
            return {"processes": 0, "threads": 0}
    try:
        r = subprocess.run(["ps", "-eo", "pid"], capture_output=True, text=True, timeout=5)
        procs = len(r.stdout.strip().split("\n")) - 1  # minus header
        tr = subprocess.run(
            ["sysctl", "-n", "kern.num_threads"],
            capture_output=True, text=True, timeout=5,
        )
        threads = int(tr.stdout.strip()) if tr.stdout.strip() else 0
        return {"processes": procs, "threads": threads}
    except Exception:
        return {"processes": 0, "threads": 0}


def _get_temp() -> dict:
    """Temperature and thermal state (no sudo needed)."""
    if sys.platform == 'linux':
        try:
            # Try lm-sensors first
            r = subprocess.run(
                ["sensors", "-u"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0 and r.stdout.strip():
                return {"therm_raw": r.stdout.strip()[:200]}
            # Fallback: try thermal zone files
            temps = []
            tz_dir = '/sys/class/thermal'
            if os.path.isdir(tz_dir):
                for entry in sorted(os.listdir(tz_dir)):
                    temp_path = os.path.join(tz_dir, entry, 'temp')
                    if os.path.isfile(temp_path):
                        try:
                            with open(temp_path) as f:
                                raw = int(f.read().strip())
                            temps.append(f"{entry}: {raw / 1000:.1f}°C")
                        except Exception:
                            continue
            if temps:
                return {"therm_raw": ", ".join(temps)[:200]}
            return {"therm_raw": ""}
        except Exception:
            return {"therm_raw": ""}
    try:
        r = subprocess.run(
            ["pmset", "-g", "therm"],
            capture_output=True, text=True, timeout=5,
        )
        return {"therm_raw": r.stdout.strip()[:200]}
    except Exception:
        return {"therm_raw": ""}


@_cached("system", ttl=15)
def _system():
    """Full system monitor snapshot."""
    return {
        "processes": _get_processes(),
        "memory": _get_detailed_memory(),
        "swap": _get_swap(),
        "network": _get_network_rates(),
        "disk_io": _get_disk_io(),
        "containers": _get_docker_stats(),
        "threads": _get_thread_count(),
        "temp": _get_temp(),
    }


def _sysinfo():
    """System metadata."""
    info = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "hermes_home": str(HERMES_HOME),
        "python": subprocess.run([sys.executable, "--version"], capture_output=True, text=True, timeout=5).stdout.strip(),
        "state_db_size": STATE_DB.stat().st_size if STATE_DB.exists() else 0,
        "script_count": len(list(SCRIPTS_DIR.glob("*.py"))),
    }
    if sys.platform == 'linux':
        try:
            os_release = {}
            if os.path.exists('/etc/os-release'):
                with open('/etc/os-release') as f:
                    for line in f:
                        if '=' in line:
                            k, v = line.strip().split('=', 1)
                            os_release[k] = v.strip('"')
            pretty = os_release.get('PRETTY_NAME', '')
            if pretty:
                info["os"] = pretty
            else:
                info["os"] = platform.platform()
        except Exception:
            info["os"] = platform.platform()
    else:
        try:
            r = subprocess.run(["sw_vers", "-productVersion"], capture_output=True, text=True, timeout=5)
            info["os"] = f"macOS {r.stdout.strip()}"
        except Exception:
            info["os"] = "macOS"
    try:
        r = subprocess.run(["uname", "-m"], capture_output=True, text=True, timeout=5)
        info["arch"] = r.stdout.strip()
    except Exception:
        info["arch"] = "?"
    return info


# ── API Routes ─────────────────────────────────────────────────────────

@app.route("/api/health")
@_cached("health", ttl=15)
def api_health():
    return jsonify(_health())


@app.route("/api/langfuse")
@_cached("langfuse", ttl=60)
def api_langfuse():
    return jsonify({
        "traces": _lf_traces(),
        "sessions": _lf_sessions(),
        "scores": _lf_scores(),
    })


@app.route("/api/crons")
@_cached("crons_api", ttl=60)
def api_crons():
    return jsonify(_crons())


@app.route("/api/sessions")
@_cached("sessions_api", ttl=30)
def api_sessions():
    return jsonify(_sessions())


@app.route("/api/sysinfo")
@_cached("sysinfo", ttl=120)
def api_sysinfo():
    return jsonify(_sysinfo())


@app.route("/api/system")
@_cached("system_api", ttl=15)
def api_system():
    return jsonify(_system())


# ── Agent Health ──────────────────────────────────────────────

AGENT_HEALTH_FILE = HERMES_HOME / "state" / "agent-health-data.json"

@app.route("/api/agents")
@_cached("agents", ttl=60)
def api_agents():
    """Read structured health data written by agent-health-monitor.py."""
    if AGENT_HEALTH_FILE.exists():
        try:
            data = json.loads(AGENT_HEALTH_FILE.read_text())
            return jsonify(data)
        except (json.JSONDecodeError, OSError) as e:
            return jsonify({"error": str(e)})
    return jsonify({})


def _agents_data() -> dict:
    """Non-cached helper for /api/all aggregation."""
    if AGENT_HEALTH_FILE.exists():
        try:
            return json.loads(AGENT_HEALTH_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


@app.route("/api/all")
def api_all():
    """Aggregated snapshot — no additional caching (individual endpoints handle it)."""
    return jsonify({
        "health": _health(),
        "langfuse": {
            "traces": _lf_traces(),
            "sessions": _lf_sessions(),
            "scores": _lf_scores(),
        },
        "agents": _agents_data(),
        "crons": _crons(),
        "sessions": _sessions(),
        "session_timeline": _session_timeline(),
        "system": _system(),
        "sysinfo": _sysinfo(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


@app.route("/")
def index():
    return send_from_directory(str(DASHBOARD_DIR), "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(str(DASHBOARD_DIR), path)


# ── Main ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"Cortex Dashboard v2 → http://127.0.0.1:{PORT}")
    print(f"  Langfuse: {LANGFUSE_HOST} ({'authed' if LANGFUSE_AUTH else 'no creds'})")
    print(f"  Hermes: {HERMES_HOME}")
    print(f"  Cache TTL: {CACHE_TTL}s")
    app.run(host="127.0.0.1", port=PORT, debug=False)
