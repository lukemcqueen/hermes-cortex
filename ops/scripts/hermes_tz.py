#!/usr/bin/env python3
"""
hermes_tz.py — BACK-COMPAT SHIM.

Canonical implementation moved to fleet_lib.tz (component-hermes-separation.md
S1a). This module re-exports fleet_lib.tz so existing callers work unmodified.
New code should import from fleet_lib.tz directly.
"""
from fleet_lib.tz import (  # noqa: F401
    get_timezone,
    format_timestamp,
    get_tz_name,
    TIMEZONE_OFFSETS,
    IANA_OFFSETS,
)

__all__ = ["get_timezone", "format_timestamp", "get_tz_name",
           "TIMEZONE_OFFSETS", "IANA_OFFSETS"]