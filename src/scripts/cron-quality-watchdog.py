#!/usr/bin/env python3
"""
Cron Output Quality Watchdog — no_agent script.

Runs every 10 minutes. Checks the most recent delivery output from
every LLM-driven (no_agent=False) cron job for quality issues:

  - QUALITY_G_BLOCKED token → cron agent self-blocked
  - Output oversized (> 6000 chars) → possible runaway
  - Output empty on a job that should produce content → silent failure
  - High ratio of non-ASCII / control chars → possible gibberish

SILENT when everything is clean. Produces output ONLY when an issue
is detected (classic watchdog pattern — no news is good news).
"""

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ── Config ──────────────────────────────────────────────────────────────────
CRON_OUTPUT_DIR = Path(os.path.expanduser("~/.hermes/cron/output"))
CRON_JOBS_FILE = Path(os.path.expanduser("~/.hermes/cron/jobs.json"))
QUALITY_BLOCK_TOKEN = "QUALITY_G_BLOCKED"
MAX_CHARS = 6000
SUSPICIOUS_UNICODE_RATIO = 0.30  # if >30% of chars are non-ASCII/latin1
SILENT_IS_ZERO = 5  # bytes — output smaller than this when job should produce content

# LLM-driven crons we monitor (no_agent=False, prompt-based)
MONITORED_CRONS = [
    "agent-inbox-check",
    "agent-auto-remediate",
    "weekly-loop-eval",
    "local-agent-daily-news-brief",
    "local-agent-daily-system-brief",
    "local-agent-daily-finance-brief",
    "gbrain-update-sync",
    "gbrain-nightly-dream",
]


# ── Helpers ─────────────────────────────────────────────────────────────────
def _get_jobs() -> list[dict]:
    """Load the cron jobs registry."""
    if not CRON_JOBS_FILE.exists():
        return []
    try:
        with open(CRON_JOBS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("jobs", [])
    except (json.JSONDecodeError, OSError):
        return []


def _find_latest_output(name: str) -> str | None:
    """Read the most recent output file for a named cron job."""
    job_dir = CRON_OUTPUT_DIR / name
    if not job_dir.is_dir():
        return None
    latest = job_dir / "latest.md"
    if latest.exists():
        try:
            return latest.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None
    # Fallback: find the newest .md file
    files = sorted(job_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    # Exclude latest.md itself (already checked)
    for fp in files:
        if fp.name != "latest.md":
            try:
                return fp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
    return None


def _is_empty_or_whitespace(text: str) -> bool:
    return not text or not text.strip()


def _count_suspicious_chars(text: str) -> int:
    """Count non-printable/non-ASCII characters that suggest gibberish."""
    count = 0
    for ch in text:
        cp = ord(ch)
        # Control characters (except common whitespace)
        if cp < 32 and cp not in (9, 10, 13):  # tab, newline, CR
            count += 1
        # Surrogates/unusual high codepoints
        elif 0xD800 <= cp <= 0xDFFF:
            count += 1
        # Very high unicode that usually indicates encoding corruption
        elif cp > 0x1FFFF:
            count += 1
        # Repeated replacement characters
        elif ch == "\ufffd":
            count += 1
    return count


def _is_repetitive_gibberish(text: str) -> bool:
    """Check for extremely repetitive patterns."""
    if len(text) < 50:
        return False
    # Check if a short substring dominates the output
    for length in [5, 10, 20]:
        if len(text) >= length * 3:
            chunks = [text[i:i+length] for i in range(0, len(text), length)]
            # If any chunk appears more than 30% of the time
            from collections import Counter
            chunk_counts = Counter(chunks)
            most_common_count = chunk_counts.most_common(1)[0][1]
            if most_common_count > len(chunks) * 0.3:
                return True
    return False


# ── Main ────────────────────────────────────────────────────────────────────
def main() -> None:
    issues: list[str] = []

    for name in MONITORED_CRONS:
        # Skip jobs that don't exist in the registry
        content = _find_latest_output(name)
        if content is None:
            continue

        # Check 1: QUALITY_G_BLOCKED token
        if QUALITY_BLOCK_TOKEN in content:
            issues.append(f"🔴 {name}: AGENT SELF-BLOCKED (QUALITY_G_BLOCKED token found)")
            continue

        # Check 2: Empty output
        if _is_empty_or_whitespace(content):
            issues.append(f"🟡 {name}: empty output (possible silent failure)")
            continue

        # Check 3: Oversized output
        if len(content) > MAX_CHARS:
            issues.append(
                f"🟠 {name}: oversized output ({len(content)} chars, "
                f"limit {MAX_CHARS}) — possible runaway"
            )

        # Check 4: Gibberish unicode
        total_chars = len(content)
        suspicious = _count_suspicious_chars(content)
        if total_chars > 0 and (suspicious / total_chars) > SUSPICIOUS_UNICODE_RATIO:
            issues.append(
                f"🔴 {name}: high ratio of suspicious chars "
                f"({suspicious}/{total_chars} = {suspicious/total_chars:.0%}) "
                f"— possible encoding corruption"
            )

        # Check 5: Repetitive gibberish
        if _is_repetitive_gibberish(content):
            issues.append(f"🔴 {name}: extremely repetitive content — possible gibberish")

    if not issues:
        # Silent — no news is good news
        sys.exit(0)

    # Build a compact report
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"## Cron Quality Watchdog — {now}")
    print()
    print(f"{len(issues)} issue(s) detected:")
    print()
    for issue in issues:
        print(f"- {issue}")
    print()
    print("Check ~/.hermes/cron/output/<name>/ for full output.")
    print(f"To investigate: `cat ~/.hermes/cron/output/<name>/latest.md`")


if __name__ == "__main__":
    main()