#!/usr/bin/env python3
"""
hermes_tz.py — Timezone helper for Hermes Cortex monitoring scripts.

Defaults to system local timezone, allows override via HERMES_TIMEZONE env var.

Usage:
    from hermes_tz import get_timezone, format_timestamp
    
    tz = get_timezone()  # Returns timezone object
    ts = format_timestamp()  # Returns formatted string like "2026-06-19 08:48 KST"
    ts = format_timestamp("%Y-%m-%dT%H:%M:%S%z")  # Custom format
"""
from __future__ import annotations

import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Any

# Common timezone offsets (hours from UTC)
# NOTE: CST is ambiguous (China Standard +8 vs Central US -6).
# We use unambiguous keys. For China Standard Time, prefer "CNST".
# For China Standard Time alias, use "CST_CN" (Chinese CST) explicitly.
TIMEZONE_OFFSETS = {
    "UTC": 0,
    "GMT": 0,
    "KST": 9,
    "JST": 9,
    "CNST": 8,
    "CST_CN": 8,
    "HKT": 8,
    "SGT": 8,
    "IST": 5.5,
    "GST": 4,
    "EAT": 3,
    "MSK": 3,
    "EET": 2,
    "CET": 1,
    "BST": 1,
    "WET": 0,
    "AST": -4,
    "EST": -5,
    "CST_US": -6,
    "MST": -7,
    "PST": -8,
    "AKST": -9,
    "HST": -10,
}

# IANA timezone names (for pytz-like behavior without dependency)
# Maps common names to offset hours
IANA_OFFSETS = {
    "Asia/Seoul": 9,
    "Asia/Tokyo": 9,
    "Asia/Shanghai": 8,
    "Asia/Hong_Kong": 8,
    "Asia/Singapore": 8,
    "Asia/Kolkata": 5.5,
    "Asia/Dubai": 4,
    "Europe/Moscow": 3,
    "Europe/Berlin": 1,
    "Europe/London": 0,
    "Europe/Paris": 1,
    "America/New_York": -5,
    "America/Chicago": -6,
    "America/Denver": -7,
    "America/Los_Angeles": -8,
    "America/Anchorage": -9,
    "Pacific/Honolulu": -10,
    "Australia/Sydney": 10,
    "Australia/Melbourne": 10,
    "Pacific/Auckland": 12,
}


def get_timezone() -> timezone:
    """
    Get timezone object based on HERMES_TIMEZONE env var or system default.
    
    Priority:
    1. HERMES_TIMEZONE env var (e.g., "KST", "Asia/Seoul", "UTC+9", "-0500")
    2. System local timezone (via datetime.now().astimezone())
    3. Fallback to UTC
    
    Returns:
        datetime.timezone object
    """
    tz_spec = os.environ.get("HERMES_TIMEZONE", "").strip()
    
    if not tz_spec:
        # No override — use system local timezone
        local_dt = datetime.now().astimezone()
        if local_dt.tzinfo is not None:
            return local_dt.tzinfo  # type: ignore
        return timezone.utc  # Fallback if somehow tzinfo is None
    
    # Try to parse the timezone specification
    tz_spec_upper = tz_spec.upper()
    
    # Check common abbreviations (KST, JST, EST, etc.)
    if tz_spec_upper in TIMEZONE_OFFSETS:
        offset_hours = TIMEZONE_OFFSETS[tz_spec_upper]
        return timezone(timedelta(hours=offset_hours), tz_spec_upper)
    
    # Check IANA names (Asia/Seoul, America/New_York, etc.)
    if tz_spec in IANA_OFFSETS:
        offset_hours = IANA_OFFSETS[tz_spec]
        # Use the IANA name as the timezone name
        return timezone(timedelta(hours=offset_hours), tz_spec)
    
    # Try to parse offset format: "+0900", "-0500", "UTC+9", "UTC-5"
    import re
    
    # Match formats like "+0900", "-0500", "+9", "-5"
    match = re.match(r"^([+-])(\d{1,2}):?(\d{2})?$", tz_spec)
    if match:
        sign = 1 if match.group(1) == "+" else -1
        hours = int(match.group(2))
        minutes = int(match.group(3)) if match.group(3) else 0
        offset = timedelta(hours=sign * hours, minutes=sign * minutes)
        return timezone(offset, f"UTC{sign*hours:+03d}")
    
    # Try UTC+9 or UTC-5 format
    match = re.match(r"^UTC([+-])(\d{1,2})$", tz_spec_upper)
    if match:
        sign = 1 if match.group(1) == "+" else -1
        hours = int(match.group(2))
        offset = timedelta(hours=sign * hours)
        return timezone(offset, tz_spec_upper)
    
    # Unknown format — fall back to system local
    local_dt = datetime.now().astimezone()
    if local_dt.tzinfo is not None:
        return local_dt.tzinfo  # type: ignore
    return timezone.utc


def format_timestamp(fmt: Optional[str] = None) -> str:
    """
    Format current timestamp using configured timezone.
    
    Args:
        fmt: Optional format string. Default: "%Y-%m-%d %H:%M %Z"
    
    Returns:
        Formatted timestamp string
    """
    if fmt is None:
        fmt = "%Y-%m-%d %H:%M %Z"
    
    tz = get_timezone()
    return datetime.now(tz).strftime(fmt)


def get_tz_name() -> str:
    """
    Get the timezone name/abbreviation for display.
    
    Returns:
        Timezone name (e.g., "KST", "EST", "UTC+0900")
    """
    tz = get_timezone()
    # Try to get a nice name
    name = tz.tzname(datetime.now(tz))
    if name:
        return name
    # Fallback to offset format
    offset = tz.utcoffset(datetime.now(tz))
    if offset:
        total_seconds = int(offset.total_seconds())
        hours, remainder = divmod(abs(total_seconds), 3600)
        minutes = remainder // 60
        sign = "+" if total_seconds >= 0 else "-"
        return f"UTC{sign}{hours:02d}:{minutes:02d}"
    return "UTC"


if __name__ == "__main__":
    # Test output
    print(f"Timezone: {get_tz_name()}")
    print(f"Timestamp: {format_timestamp()}")
    print(f"ISO format: {format_timestamp('%Y-%m-%dT%H:%M:%S%z')}")
    print(f"HERMES_TIMEZONE={os.environ.get('HERMES_TIMEZONE', '(not set)')}")
