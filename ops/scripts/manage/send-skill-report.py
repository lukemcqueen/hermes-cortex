#!/usr/bin/env python3
"""send-skill-report.py — Agent-side: auto-send skill manifest to Moses via Agent Bus.

Designed to run as a no_agent cron (every 6h). Reads the skills
manifest written by collect-agent-skills.sh and sends it to Moses
via PGMQ Agent Bus. Silent when no custom skills to report.

Requires (from ~/hermes-cortex/.env):
  CORTEX_BUS_URL      — Moses Agent Bus URL (e.g. http://localhost:8903)
  CORTEX_BUS_TOKEN    — Bearer token for bus auth

For remote agents, CORTEX_BUS_URL must point to Moses's external bus
endpoint (not localhost).
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

HOME = Path.home()

# ── Source config from .env ─────────────────────────────────
CORTEX_INBOX_URL = os.environ.get("CORTEX_INBOX_URL", "")
CORTEX_INBOX_AUTH = os.environ.get("CORTEX_INBOX_AUTH", "")

env_file = HOME / "hermes-cortex" / ".env"
if env_file.exists() and (not CORTEX_INBOX_URL or not CORTEX_INBOX_AUTH):
    try:
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            v = v.strip().strip("'\"")
            if k == "CORTEX_INBOX_URL" and not CORTEX_INBOX_URL:
                CORTEX_INBOX_URL = v
            elif k == "CORTEX_INBOX_AUTH" and not CORTEX_INBOX_AUTH:
                CORTEX_INBOX_AUTH = v
    except Exception:
        pass

# ── Silent exit if not configured ─────────────────────────
if not CORTEX_INBOX_URL or not CORTEX_INBOX_AUTH:
    sys.exit(0)

STATE_DIR = HOME / ".hermes-cortex" / "state"
MANIFEST_FILE = STATE_DIR / "skills-manifest.json"
CONTENTS_FILE = STATE_DIR / "skills-contents.json"

# ── Rebuild manifest from current skills ───────────────────
collect_script = HOME / "hermes-cortex" / "ops" / "scripts" / "manage" / "collect-agent-skills.sh"
if collect_script.exists():
    subprocess.run(["bash", str(collect_script)], capture_output=True)
else:
    deployed = HOME / ".hermes-cortex" / "scripts" / "collect-agent-skills.sh"
    if deployed.exists():
        subprocess.run(["bash", str(deployed)], capture_output=True)

# ── Silent exit if no manifest or no custom skills ────────
if not MANIFEST_FILE.exists():
    sys.exit(0)

manifest = json.loads(MANIFEST_FILE.read_text())
custom_total = manifest.get("custom_skills", 0)
if custom_total == 0:
    sys.exit(0)

contents = []
if CONTENTS_FILE.exists():
    contents = json.loads(CONTENTS_FILE.read_text())

# ── Build message body ─────────────────────────────────────
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

# ── Send via Agent Bus Inbox API ─────────────────────────────
# Inbox expects: POST /api/send with Basic auth (user:pass)
# Body: {"from": ..., "to": ..., "subject": ..., "body": ..., "topic": ...}
import base64

bus_url = CORTEX_INBOX_URL.rstrip("/")
api_url = f"{bus_url}/api/send"

# Build Basic auth header from user:pass
auth_b64 = base64.b64encode(CORTEX_INBOX_AUTH.encode()).decode()

payload = {
    "from": hostname,
    "to": "moses",
    "subject": f"Skill Report: {custom_total} custom skills",
    "body": body_text,
    "topic": "reports",
}

req = Request(
    api_url,
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Basic {auth_b64}",
    },
    method="POST",
)

try:
    urlopen(req, timeout=30)
    print(f"Sent {custom_total} custom skills from {hostname} to Moses inbox", flush=True)
except URLError as e:
    print(f"ERR: Failed to send skill report: {e}", flush=True)
    sys.exit(1)
