#!/usr/bin/env python3
"""send-skill-report.py — Agent-side: auto-send skill manifest to Moses.

Designed to run as a no_agent cron (every 6h). Reads the skills
manifest written by collect-agent-skills.sh and sends it to Moses
inbox via JSON API. Silent when no custom skills to report.

Requires CORTEX_INBOX_URL and CORTEX_INBOX_AUTH (from .env or hermes-inbox.conf).
"""

import base64
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

HOME = Path.home()

# ── Source config from .env or hermes-inbox.conf ──────────
CORTEX_INBOX_URL = os.environ.get("CORTEX_INBOX_URL", "")
CORTEX_INBOX_AUTH = os.environ.get("CORTEX_INBOX_AUTH", "")

for conf in [HOME / "hermes-cortex" / ".env",
             HOME / ".hermes-cortex" / "hermes-inbox.conf"]:
    if conf.exists():
        try:
            for line in conf.read_text().splitlines():
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
if not CORTEX_INBOX_URL:
    sys.exit(0)

STATE_DIR = HOME / ".hermes-cortex" / "state"
MANIFEST_FILE = STATE_DIR / "skills-manifest.json"
CONTENTS_FILE = STATE_DIR / "skills-contents.json"

# ── Rebuild manifest from current skills if possible ──────
collect_script = HOME / "hermes-cortex" / "ops" / "scripts" / "manage" / "collect-agent-skills.sh"
if collect_script.exists():
    subprocess.run(["bash", str(collect_script)], capture_output=True)
else:
    # Fallback: try deployed copy
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
payload = {
    "from": hostname,
    "subject": f"Skill Report: {custom_total} custom skills",
    "body": body_text,
    "topic": "reports",
    "priority": "normal",
}

# ── Send via JSON POST to agent-inbox API ───────────────────
# Use /api/send (not /api/pgmq/send — agent-inbox, not PGMQ bus)
api_url = CORTEX_INBOX_URL.rstrip("/") + "/api/send"

req = Request(
    api_url,
    data=json.dumps(payload).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
if CORTEX_INBOX_AUTH and ":" in CORTEX_INBOX_AUTH:
    encoded = base64.b64encode(CORTEX_INBOX_AUTH.encode()).decode()
    req.add_header("Authorization", f"Basic {encoded}")

try:
    urlopen(req, timeout=30)
    print(f"Sent {custom_total} custom skills to Moses inbox", flush=True)
except URLError as e:
    print(f"ERR: Failed to send skill report: {e}", flush=True)
    sys.exit(1)
