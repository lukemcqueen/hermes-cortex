---
language: python
tags: [util, pattern, io]
title: Datetime Formatting & Parsing
description: Working with datetime, timezone-aware timestamps, strftime/strptime, timedelta arithmetic, dateutil parser, and ISO 8601 formatting.
source: pattern
---

```python
from datetime import datetime, timezone, timedelta
from typing import Optional

try:
    from dateutil import parser as dateutil_parser
    from dateutil.tz import gettz
    HAS_DATEUTIL = True
except ImportError:
    HAS_DATEUTIL = False


# ---- Constants ---- #
ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%f%z"
HUMAN_FORMAT = "%Y-%m-%d %H:%M:%S %Z"
LOGFILE_FORMAT = "%Y%m%d_%H%M%S"


def now_utc() -> datetime:
    """Return the current UTC time with timezone info."""
    return datetime.now(timezone.utc)


def format_iso(dt: Optional[datetime] = None) -> str:
    """Format a datetime as ISO 8601; defaults to now_utc."""
    return (dt or now_utc()).strftime(ISO_FORMAT)


def parse_iso(text: str) -> datetime:
    """Parse an ISO 8601 string back to a timezone-aware datetime."""
    return datetime.strptime(text, ISO_FORMAT)


def smart_parse(text: str, tz_name: str = "UTC") -> Optional[datetime]:
    """Flexible date parsing using dateutil (if available), falling back to strptime guesses."""
    if HAS_DATEUTIL:
        dt = dateutil_parser.parse(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=gettz(tz_name))
        return dt
    # fallback: try common formats
    for fmt in [ISO_FORMAT, HUMAN_FORMAT, "%Y-%m-%d", "%d/%m/%Y"]:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def human_readable(dt: Optional[datetime] = None) -> str:
    """Return a human-friendly string like '2025-01-15 14:30:00 UTC'."""
    dt = dt or now_utc()
    return dt.strftime(HUMAN_FORMAT)


def time_ago(dt: datetime, reference: Optional[datetime] = None) -> str:
    """Return a relative time description (e.g. '3 hours ago', '2 days ago')."""
    ref = reference or now_utc()
    diff = ref - dt
    seconds = int(diff.total_seconds())
    if seconds < 0:
        return "in the future"
    intervals = [
        (365 * 86400, "year"),
        (30 * 86400, "month"),
        (7 * 86400, "week"),
        (86400, "day"),
        (3600, "hour"),
        (60, "minute"),
    ]
    for divisor, unit in intervals:
        count = seconds // divisor
        if count >= 1:
            return f"{count} {unit}{'s' if count > 1 else ''} ago"
    return "just now"


# ---- Example ---- #
if __name__ == "__main__":
    now = now_utc()
    print("Now (ISO):", format_iso(now))
    print("Now (human):", human_readable(now))
    print("Parsed back:", parse_iso(format_iso(now)))
    print("Time ago (5h back):", time_ago(now - timedelta(hours=5, minutes=20)))

    yesterday = now - timedelta(days=1)
    print("Yesterday:", human_readable(yesterday))

    if HAS_DATEUTIL:
        parsed = smart_parse("Jan 15, 2025 3:30 PM EST")
        print("Parsed (dateutil):", parsed)

```
