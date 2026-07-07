#!/usr/bin/env python3
"""process-skill-reports.py — Moses-side: compile agent skill reports
from the inbox into a digest for Moses to review.

Reads messages from the "reports" topic in the agent inbox and
identifies skill-report messages (subject: "Skill Report:").

Output: formatted digest to stdout (Telegram-friendly Markdown).
         Silent when no new reports since last processed.

Usage:
    python3 process-skill-reports.py              # show pending reports
    python3 process-skill-reports.py --all        # show ALL reports (not just new)
    python3 process-skill-reports.py --mark-read  # mark processed reports as read
"""

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

INBOX_URL = os.environ.get("AGENT_INBOX_URL", "https://your-domain.com:13004")
STATE_DIR = Path(os.environ.get("CORTEX_DEPLOY_HOME", Path.home() / ".hermes-cortex")) / "state"
PROCESSED_MARKER = STATE_DIR / "last-skill-report-processed.txt"

TOPIC_FILTER = "reports"


def fetch_inbox_messages(topic: str = "") -> list[dict]:
    """Fetch inbox messages from the agent inbox API."""
    url = f"{INBOX_URL}/api/inbox?unread_only=true"
    if topic:
        url += f"&topic={topic}"

    try:
        req = Request(url)
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        return data.get("messages", [])
    except (URLError, json.JSONDecodeError, OSError) as e:
        print(f"WARN: Could not fetch inbox: {e}", file=sys.stderr)
        return []


def fetch_all_inbox_messages(topic: str = "") -> list[dict]:
    """Fetch ALL inbox messages (not just unread)."""
    url = f"{INBOX_URL}/api/inbox"
    if topic:
        url += f"?topic={topic}"

    try:
        req = Request(url)
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
        return data.get("messages", [])
    except (URLError, json.JSONDecodeError, OSError) as e:
        print(f"WARN: Could not fetch inbox: {e}", file=sys.stderr)
        return []


def mark_read(message_id: str) -> bool:
    """Mark an inbox message as read via the frontend endpoint."""
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
        if line.startswith("•"):
            # Format: • skill-name (category) — N lines
            match = re.match(
                r"•\s+(.+?)(?:\s+\((.+?)\))?\s*[—–-]+\s*(\d+)\s+lines",
                line,
            )
            if match:
                skills.append({
                    "name": match.group(1).strip(),
                    "category": match.group(2).strip() if match.group(2) else "",
                    "lines": int(match.group(3)),
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
            lines.append("| Skill | Category | Lines |")
            lines.append("|-------|----------|-------|")
            for s in skills:
                cat = s["category"] if s["category"] else "—"
                lines.append(f"| `{s['name']}` | {cat} | {s['lines']} |")
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
        messages = fetch_all_inbox_messages(topic=TOPIC_FILTER)
    else:
        messages = fetch_inbox_messages(topic=TOPIC_FILTER)

    if not messages:
        # Silent exit — no new reports
        return

    # Filter to skill-report messages only
    reports = [m for m in messages if "skill report" in m.get("subject", "").lower()]

    if not reports:
        return  # Silent

    # Check if we've already processed these
    last_processed = ""
    if PROCESSED_MARKER.exists():
        last_processed = PROCESSED_MARKER.read_text().strip()

    if last_processed and not show_all:
        # Filter to reports newer than last processed
        new_reports = []
        for r in reports:
            # Use timestamp or filename for comparison
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