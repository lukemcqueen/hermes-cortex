#!/usr/bin/env python3
"""orch-skill-report-process.py — Orchestrator-side: compile agent skill reports
from the PGMQ bus into a digest for Moses to review.

Reads messages from the inbox_moses PGMQ queue, filters for skill-report
messages (topic: reports, subject: "Skill Report:"), extracts skill data,
and produces a formatted digest.

Replaced the retired v1 HTTP /api/inbox with direct PGMQ queue reads.

Usage:
    python3 orch-skill-report-process.py              # show pending reports
    python3 orch-skill-report-process.py --all        # show ALL reports (not just new)
    python3 orch-skill-report-process.py --mark-read  # archive processed reports
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# ── Config from environment ─────────────────────────────────
CORTEX_BUS_URL = os.environ.get("CORTEX_BUS_URL", "http://127.0.0.1:8903")
CORTEX_BUS_TOKEN = os.environ.get("CORTEX_BUS_TOKEN", "")

# Try reading from .env if env vars not set
if not CORTEX_BUS_TOKEN:
    for conf in [Path.home() / "hermes-cortex" / ".env",
                 Path.home() / ".hermes-cortex" / "cortex-bus.conf",
                 Path.home() / ".hermes" / "cortex-bus.conf"]:
        if conf.exists():
            try:
                for line in conf.read_text().splitlines():
                    line = line.strip()
                    if line.startswith("CORTEX_BUS_TOKEN="):
                        val = line.split("=", 1)[1].strip().strip("'\"")
                        if val:
                            CORTEX_BUS_TOKEN = val
                    elif line.startswith("CORTEX_BUS_URL=") and not CORTEX_BUS_URL:
                        val = line.split("=", 1)[1].strip().strip("'\"")
                        if val:
                            CORTEX_BUS_URL = val
            except (IOError, OSError, UnicodeDecodeError, ValueError) as e:
                # Config file unreadable or malformed — log and try next location
                print(f"[config] Warning: skipping {conf}: {e}", file=sys.stderr)
        if CORTEX_BUS_TOKEN:
            break

BUS_URL = CORTEX_BUS_URL.rstrip("/")
STATE_DIR = Path(os.environ.get("CORTEX_DEPLOY_HOME", Path.home() / ".hermes-cortex")) / "state"
PROCESSED_MARKER = STATE_DIR / "last-skill-report-processed.txt"
QUEUE = "inbox_moses"


def bus_request(endpoint: str, data: dict | None = None, method: str | None = None) -> dict:
    """Make an authenticated request to the PGMQ bus API."""
    url = f"{BUS_URL}{endpoint}"
    headers = {
        "Authorization": f"Bearer {CORTEX_BUS_TOKEN}",
        "Content-Type": "application/json",
    }
    body = json.dumps(data).encode() if data else None
    http_method = method or ("POST" if data else "GET")

    try:
        req = Request(url, data=body, headers=headers, method=http_method)
        with urlopen(req, timeout=15) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except HTTPError as e:
        err_body = e.read().decode() if e.fp else ""
        print(f"WARN: HTTP {e.code} on {endpoint}: {err_body[:200]}", file=sys.stderr)
        return {}
    except (URLError, OSError, json.JSONDecodeError) as e:
        print(f"WARN: Request failed on {endpoint}: {e}", file=sys.stderr)
        return {}


def read_queue_messages(queue: str, vt: int = 30, limit: int = 10) -> list[dict]:
    """Read messages from a PGMQ queue. Returns list of message dicts."""
    payload = {"queue": queue, "vt": vt, "limit": limit}
    resp = bus_request("/api/pgmq/read", payload)
    if not resp:
        return []
    # PGMQ read returns a single message dict (not a list)
    if isinstance(resp, dict) and resp.get("msg_id"):
        return [resp]
    return []


def archive_message(queue: str, msg_id: str) -> bool:
    """Move a processed message from the queue to the archive table.
    Uses POST /api/pgmq/archive (preserves message in bus.archives).
    NEVER use DELETE /api/pgmq/delete — that hard-purges with no archive."""
    if not msg_id:
        return False
    resp = bus_request("/api/pgmq/archive", {"queue": queue, "msg_id": msg_id, "archived_by": "orch-skill-report-process"}, method="POST")
    return "detail" not in resp


def extract_skill_report(msg: dict) -> dict | None:
    """Extract skill report data from a bus message.
    Returns dict with from, subject, body, timestamp or None if not a skill report.
    """
    inner = msg.get("body", {})
    if isinstance(inner, str):
        try:
            inner = json.loads(inner)
        except json.JSONDecodeError:
            return None
    if not isinstance(inner, dict):
        return None

    subject = inner.get("subject", "") or ""
    topic = inner.get("topic", "") or ""

    # Only process skill report messages
    if "skill report" not in subject.lower() and topic.lower() != "reports":
        return None

    return {
        "from": inner.get("from", "?"),
        "subject": subject,
        "body": inner.get("body", ""),
        "timestamp": msg.get("enqueued_at", ""),
        "msg_id": msg.get("msg_id", ""),
    }


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
    max_iterations = int(os.environ.get("MAX_READ_ITERATIONS", "20"))

    # Read messages from inbox_moses queue (PGMQ)
    all_reports = []
    seen_msg_ids = set()

    for iteration in range(max_iterations):
        messages = read_queue_messages(QUEUE, vt=60, limit=10)
        if not messages:
            break  # No more messages

        for msg in messages:
            msg_id = msg.get("msg_id", "")
            if not msg_id or msg_id in seen_msg_ids:
                continue
            seen_msg_ids.add(msg_id)

            report = extract_skill_report(msg)
            if report:
                all_reports.append(report)

    if not all_reports:
        return  # Silent — no skill reports found

    # Filter out already-processed reports
    last_processed = ""
    if PROCESSED_MARKER.exists():
        last_processed = PROCESSED_MARKER.read_text().strip()

    if last_processed and not show_all:
        new_reports = [r for r in all_reports if r.get("msg_id", "") > last_processed]
        if not new_reports:
            return  # All already processed
        all_reports = new_reports

    # Sort by sender
    all_reports.sort(key=lambda r: r.get("from", ""))

    # Format digest
    digest = format_digest(all_reports)
    print(digest)

    # Archive messages if --mark-read
    if mark_read_flag:
        archived_count = 0
        for report in all_reports:
            msg_id = report.get("msg_id", "")
            if msg_id:
                if archive_message(QUEUE, msg_id):
                    archived_count += 1

        # Record latest processed message ID
        latest_id = max(r.get("msg_id", "") for r in all_reports)
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        PROCESSED_MARKER.write_text(latest_id)
        print(f"\n*Archived {archived_count}/{len(all_reports)} report(s) from bus queue*")


if __name__ == "__main__":
    main()
