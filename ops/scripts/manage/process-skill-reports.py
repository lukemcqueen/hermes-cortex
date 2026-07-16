#!/usr/bin/env python3
"""process-skill-reports.py — Moses-side: compile agent skill reports
from the inbox into a digest for Moses to review.

Reads inbox messages from the "reports" topic and identifies
skill-report messages (subject: "Skill Report:").

Output: formatted digest to stdout (Telegram-friendly Markdown).
         Silent when no new reports since last processed.

Usage:
    python3 process-skill-reports.py              # show pending reports
    python3 process-skill-reports.py --all        # show ALL reports (not just new)
    python3 process-skill-reports.py --mark-read  # mark processed reports as read
"""

import base64
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

# ── Config from environment ─────────────────────────────────
# CORTEX_BUS_FALLBACK_URL is the primary source, with fallback to CORTEX_INBOX_URL
CORTEX_BUS_FALLBACK_URL = os.environ.get("CORTEX_BUS_FALLBACK_URL", "") or os.environ.get("CORTEX_INBOX_URL", "")
CORTEX_BUS_AUTH = os.environ.get("CORTEX_BUS_AUTH", "") or os.environ.get("CORTEX_INBOX_AUTH", "")

# Try reading from .env if env vars not set
if not CORTEX_BUS_FALLBACK_URL:
    for conf in [Path.home() / "hermes-cortex" / ".env",
                 Path.home() / ".hermes" / "cortex-bus.conf"]:
        if conf.exists():
            try:
                for line in conf.read_text().splitlines():
                    line = line.strip()
                    if line.startswith("CORTEX_BUS_FALLBACK_URL="):
                        val = line.split("=", 1)[1].strip().strip("'\"")
                        if val:
                            CORTEX_BUS_FALLBACK_URL = val
                    elif line.startswith("CORTEX_INBOX_URL="):
                        val = line.split("=", 1)[1].strip().strip("'\"")
                        if val:
                            CORTEX_BUS_FALLBACK_URL = val
                    elif line.startswith("CORTEX_BUS_AUTH="):
                        val = line.split("=", 1)[1].strip().strip("'\"")
                        if val:
                            CORTEX_BUS_AUTH = val
                    elif line.startswith("CORTEX_INBOX_AUTH="):
                        val = line.split("=", 1)[1].strip().strip("'\"")
                        if val:
                            CORTEX_BUS_AUTH = val
            except Exception:
                pass
        if CORTEX_BUS_FALLBACK_URL:
            break

INBOX_URL = CORTEX_BUS_FALLBACK_URL.rstrip("/")
STATE_DIR = Path(os.environ.get("CORTEX_DEPLOY_HOME", Path.home() / ".hermes-cortex")) / "state"
PROCESSED_MARKER = STATE_DIR / "last-skill-report-processed.txt"

TOPIC_FILTER = "reports"

def build_auth_header() -> dict:
    """Build Basic Auth header if credentials available."""
    if CORTEX_BUS_AUTH and ":" in CORTEX_BUS_AUTH:
        encoded = base64.b64encode(CORTEX_BUS_AUTH.encode()).decode()
        return {"Authorization": "Basic " + encoded}
    return {}

def fetch_inbox_messages(topic: str = "", unread_only: bool = True) -> list[dict]:
    """Fetch inbox messages from the agent inbox API."""
    url = f"{INBOX_URL}/api/inbox"
    params = []
    if topic:
        params.append(f"topic={topic}")
    if unread_only:
        params.append("unread_only=true")
    if params:
        url += "?" + "&".join(params)

    try:
        req = Request(url)
        for k, v in build_auth_header().items():
            req.add_header(k, v)
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        return data.get("messages", [])
    except (URLError, json.JSONDecodeError, OSError) as e:
        print(f"WARN: Could not fetch inbox: {e}", file=sys.stderr)
        return []

def mark_read(message_id: str) -> bool:
    """Mark an inbox message as read."""
    url = f"{INBOX_URL}/read/{message_id}"
    try:
        req = Request(url)
        with urlopen(req, timeout=10):
            return True
    except (URLError, OSError) as e:
        print(f"WARN: Could not mark {message_id} as read: {e}", file=sys.stderr)
        return False

def parse_skills_from_body(body: str) -> list[dict]:
    """Parse skill entries from the report body text."""
    skills = []
    for line in body.split("\n"):
        line = line.strip()
        if line.startswith("==") and "Skill:" in line:
            # Format: == Skill: name (category) ==
            match = re.match(r"==\s+Skill:\s+(.+?)(?:\s+\((.+?)\))?\s+==", line)
            if match:
                skills.append({
                    "name": match.group(1).strip(),
                    "category": match.group(2).strip() if match.group(2) else "",
                })
    return skills

def extract_custom_count(body: str) -> int:
    """Extract the custom_skills count from the report body."""
    match = re.search(r"Custom skills[^:]*:\s*(\d+)", body)
    return int(match.group(1)) if match else 0

def extract_total_count(body: str) -> int:
    """Extract the total_skills count."""
    match = re.search(r"Total skills[^:]*:\s*(\d+)", body)
    return int(match.group(1)) if match else 0

def format_digest(reports: list[dict]) -> str:
    """Format skill reports into a Telegram-friendly digest."""
    if not reports:
        return ""

    lines = []
    lines.append("## 🧠 Skill Reports Received\n")
    lines.append(f"*{len(reports)} agent(s) reported custom skills*\n")

    for report in reports:
        sender = report.get("from", "?")
        subject = report.get("subject", "")
        body = report.get("body", "")
        timestamp = report.get("timestamp", "")

        custom_count = extract_custom_count(body)
        total_count = extract_total_count(body)
        skills = parse_skills_from_body(body)

        lines.append(f"### {sender}")
        lines.append(f"`{timestamp}` | {total_count} total, **{custom_count} custom**\n")

        if skills:
            lines.append("| Skill | Category |")
            lines.append("|-------|----------|")
            for s in skills:
                cat = s["category"] if s["category"] else "—"
                lines.append(f"| `{s['name']}` | {cat} |")
        else:
            lines.append("*(structured skill list not available — see inbox for full report)*")

        lines.append("")

    lines.append("---")
    lines.append("*To evaluate: `skill_view(name=\"<skill>\")` then decide on upstreaming via `public-contribution` skill*\n")

    return "\n".join(lines)

def main():
    show_all = "--all" in sys.argv
    mark_read_flag = "--mark-read" in sys.argv

    # Fetch messages
    if show_all:
        messages = fetch_inbox_messages(topic=TOPIC_FILTER, unread_only=False)
    else:
        messages = fetch_inbox_messages(topic=TOPIC_FILTER, unread_only=True)

    if not messages:
        return  # Silent — no new messages

    # Filter to skill-report messages only
    reports = [m for m in messages if "skill report" in m.get("subject", "").lower()]

    if not reports:
        return  # Silent

    # Check if we've already processed these
    last_processed = ""
    if PROCESSED_MARKER.exists():
        last_processed = PROCESSED_MARKER.read_text().strip()

    if last_processed and not show_all:
        new_reports = []
        for r in reports:
            msg_id = r.get("id", r.get("filename", ""))
            if msg_id > last_processed:
                new_reports.append(r)
        reports = new_reports

    if not reports:
        return  # All already processed

    # Sort by sender name
    reports.sort(key=lambda r: r.get("from", ""))

    # Format digest
    digest = format_digest(reports)
    print(digest)

    # Mark read if requested
    if mark_read_flag:
        for report in reports:
            msg_id = report.get("id", report.get("filename", ""))
            if msg_id:
                mark_read(msg_id)

        # Record latest processed message ID
        latest_id = max(
            r.get("id", r.get("filename", "")) for r in reports
        )
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        PROCESSED_MARKER.write_text(latest_id)
        print(f"\n*Marked {len(reports)} report(s) as read*")


if __name__ == "__main__":
    main()
