#!/usr/bin/env python3
"""
hermes_tz.py — BACK-COMPAT SHIM.

Canonical implementation moved to cortex_lib.tz (component-hermes-separation.md
S1a). This module re-exports cortex_lib.tz so existing callers work unmodified.
New code should import from cortex_lib.tz directly.
"""
from cortex_lib.tz import (  # noqa: F401
    get_timezone,
    format_timestamp,
    get_tz_name,
    TIMEZONE_OFFSETS,
    IANA_OFFSETS,
)

__all__ = ["get_timezone", "format_timestamp", "get_tz_name",
           "TIMEZONE_OFFSETS", "IANA_OFFSETS"]