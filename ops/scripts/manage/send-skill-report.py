#!/usr/bin/env python3
"""send-skill-report.py — Agent-side: auto-send skill manifest to Moses via Agent Bus.

Designed to run as a no_agent cron (every 6h). Reads the skills
manifest written by collect-agent-skills.sh and sends it to Moses
via PGMQ Agent Bus. Silent when no custom skills to report.

Requires (from ~/.hermes-cortex/cortex-bus.conf, ~/hermes-cortex/.env,
  or env vars):
  CORTEX_BUS_URL         — Moses Agent Bus URL (primary)
  CORTEX_BUS_FALLBACK_URL — Esther Agent Bus URL (fallback)
  CORTEX_BUS_TOKEN       — Bearer token for bus auth

For remote agents, CORTEX_BUS_URL must point to Moses's external bus
endpoint (e.g. https://bus.example.org:13004).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

HOME = Path.home()


def _load_env(path: Path) -> dict:
    """Load key=value pairs from a config file."""
    env = {}
    if path.exists():
        try:
            for line in path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip("'\"")
        except OSError:
            pass
    return env


def _resolve_var(key: str, default: str = "") -> str:
    """Resolve env var from env → config files → default."""
    val = os.environ.get(key)
    if val:
        return val
    for cfg_path in [
        HOME / ".hermes-cortex" / "cortex-bus.conf",
        HOME / "hermes-cortex" / ".env",
    ]:
        cfg = _load_env(cfg_path)
        if key in cfg and cfg[key]:
            return cfg[key]
    return default


# ── Resolve connection config ──
BUS_URL = _resolve_var("CORTEX_BUS_URL")
if not BUS_URL:
    BUS_URL = _resolve_var("CORTEX_BUS_FALLBACK_URL")
BUS_TOKEN = _resolve_var("CORTEX_BUS_TOKEN")

# ── Resolve auth ──
# Local (127.0.0.1/localhost): Bearer token
# Remote (external via nginx): Basic auth
CORTEX_BASIC_AUTH = _resolve_var("CORTEX_BASIC_AUTH")

def _is_local(url: str) -> bool:
    """Check if a URL points to localhost."""
    host = url.split("://")[-1].split("/")[0].split(":")[0]
    return host in ("127.0.0.1", "localhost", "::1")

def _build_auth_headers(url: str) -> dict[str, str]:
    """Build auth headers appropriate for the connection type."""
    if _is_local(url):
        return {"Authorization": f"Bearer {BUS_TOKEN}"} if BUS_TOKEN else {}
    # Remote via nginx — use Basic auth
    if CORTEX_BASIC_AUTH:
        import base64
        encoded = base64.b64encode(CORTEX_BASIC_AUTH.encode()).decode()
        return {"Authorization": f"Basic {encoded}"}
    return {}

# ── Silent exit if not configured ──
if not BUS_URL or not BUS_TOKEN:
    sys.exit(0)

STATE_DIR = HOME / ".hermes-cortex" / "state"
MANIFEST_FILE = STATE_DIR / "skills-manifest.json"
CONTENTS_FILE = STATE_DIR / "skills-contents.json"

# ── Rebuild manifest from current skills ──
collect_script = HOME / "hermes-cortex" / "ops" / "scripts" / "manage" / "collect-agent-skills.sh"
if collect_script.exists():
    subprocess.run(["bash", str(collect_script)], capture_output=True)
else:
    deployed = HOME / ".hermes-cortex" / "scripts" / "collect-agent-skills.sh"
    if deployed.exists():
        subprocess.run(["bash", str(deployed)], capture_output=True)

# ── Silent exit if no manifest or no custom skills ──
if not MANIFEST_FILE.exists():
    sys.exit(0)

manifest = json.loads(MANIFEST_FILE.read_text())
custom_total = manifest.get("custom_skills", 0)
if custom_total == 0:
    sys.exit(0)

contents = []
if CONTENTS_FILE.exists():
    contents = json.loads(CONTENTS_FILE.read_text())

# ── Build message body ──
hostname = os.uname().nodename
lines = []
lines.append(f"━━━ Skill Report — {hostname} ━━━")
lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}")
lines.append(f"Total skills installed: {manifest.get('total_skills', 0)}")
lines.append(f"Custom skills (not upstream): {custom_total}")
lines.append("")

for i, s in enumerate(manifest.get("skills", [])):
    name = s.get("name", "?")
    catg = s.get("category", "")
    tag = f" ({catg})" if catg else ""
    lines.append(f"== Skill: {name}{tag} ==")
    lines.append(f"Lines: {s.get('lines', 0)} | Age: {s.get('age_days', 0)}d")
    lines.append(f"Description: {s.get('summary', '')}")
    lines.append("")
    lines.append("--- Full content ---")
    lines.append(contents[i] if i < len(contents) else "(content unavailable)")
    lines.append("--- End skill ---")
    lines.append("")

body_text = "\n".join(lines)

# ── Send via PGMQ Agent Bus ──
bus_url = BUS_URL.rstrip("/")
api_url = f"{bus_url}/api/pgmq/send"

payload = {
    "queue": "inbox_moses",
    "message": {
        "from": hostname,
        "subject": f"Skill Report: {custom_total} custom skills",
        "body": body_text,
        "topic": "reports",
    },
}

req = Request(
    api_url,
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "Content-Type": "application/json",
        **_build_auth_headers(bus_url),
    },
    method="POST",
)

try:
    with urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode())
    msg_id = result.get("msg_id", "?")
    print(f"Sent {custom_total} custom skills from {hostname} to Moses (msg_id={msg_id[:8]})", flush=True)
except URLError as e:
    body = ""
    if hasattr(e, 'read'):
        try:
            body = e.read().decode()[:200]
        except Exception:
            body = str(e)
    print(f"ERR: Failed to send skill report: HTTP {getattr(e, 'code', '?')} {body}", flush=True)
    sys.exit(1)
except (OSError, json.JSONDecodeError) as e:
    print(f"ERR: Failed to send skill report: {e}", flush=True)
    sys.exit(1)
