#!/usr/bin/env python3
"""agent-inbox.py — Delivers new Moses inbox messages to the user.

Runs every 10m as a no_agent cron. Checks agent-inbox for new messages
addressed to Moses. Truly silent (no stdout) when nothing new.

Depends on inbox-flag.py for detection state (inbox-flag-seen file).
"""
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

HOME = Path.home()
INBOX_DIR = HOME / "agent-inbox-private" / "inbox"
SEEN_FILE = HOME / ".hermes-cortex" / "state" / "inbox-flag-seen"
KST = timezone(timedelta(hours=9))


def load_seen() -> set[str]:
    if SEEN_FILE.exists():
        return {line.strip() for line in SEEN_FILE.read_text().splitlines() if line.strip()}
    return set()


def format_for_telegram(messages: list[dict]) -> str:
    """Format new messages for Telegram delivery."""
    lines = [f"📬 {len(messages)} new inbox message(s):", ""]
    for m in messages:
        from_ = m.get("from", "?")
        subj = m.get("subject", "(no subject)")
        ts = m.get("timestamp", "")
        ts_str = f" [{ts}]" if ts else ""
        lines.append(f"**{from_}**{ts_str}")
        lines.append(f"  _{subj}_")
        lines.append("")
    return "\n".join(lines).strip()


def main() -> int:
    seen = load_seen()

    if not INBOX_DIR.exists():
        return 1

    new_messages = []
    for f in sorted(INBOX_DIR.iterdir()):
        if not f.name.endswith(".md"):
            continue
        if f.name in seen:
            continue

        # Check if addressed to Moses
        is_moses = f.name.rstrip(".md").endswith("-moses")
        if not is_moses:
            try:
                content = f.read_text(encoding="utf-8", errors="replace")
                topic_match = re.search(r"^topic:\s*(.+)$", content, re.MULTILINE)
                to_match = re.search(r"^to:\s*(.+)$", content, re.MULTILINE)
                if (topic_match and topic_match.group(1).strip().lower() == "moses") or \
                   (to_match and to_match.group(1).strip().lower() == "moses"):
                    is_moses = True
            except Exception:
                continue

        if not is_moses:
            continue

        try:
            content = f.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        msg_from = "unknown"
        msg_subject = "(no subject)"
        msg_time = ""

        mf = re.search(r"^from:\s*(.+)$", content, re.MULTILINE)
        ms = re.search(r"^subject:\s*(.+)$", content, re.MULTILINE)
        if mf:
            msg_from = mf.group(1).strip()
        if ms:
            msg_subject = ms.group(1).strip()

        ts_match = re.match(r"(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})", f.name)
        if ts_match:
            y, mo, d, h, mi, s = ts_match.groups()
            msg_time = f"{y}-{mo}-{d}T{h}:{mi}:{s}"

        new_messages.append({"from": msg_from, "subject": msg_subject, "timestamp": msg_time, "filename": f.name})
        seen.add(f.name)

    # Save seen state (same file as inbox-flag.py)
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text("\n".join(sorted(seen)) + "\n")

    if not new_messages:
        # Truly silent — no stdout = no delivery
        return 0

    print(format_for_telegram(new_messages))
    return 0


if __name__ == "__main__":
    sys.exit(main())
