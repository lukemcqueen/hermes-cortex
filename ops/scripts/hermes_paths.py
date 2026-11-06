#!/usr/bin/env python3
"""
hermes_paths.py — BACK-COMPAT SHIM.

Canonical implementation moved to fleet_lib.paths (component-hermes-separation.md
S1a). This module re-exports fleet_lib.paths so existing callers work
unmodified. New code should import from fleet_lib.paths directly.
"""
from fleet_lib.paths import ensure_scripts_path  # noqa: F401

__all__ = ["ensure_scripts_path"]