#!/usr/bin/env python3
"""
cortex-doctor.py — Hermes Cortex installation health check

Like 'brew doctor' for Hermes Cortex: single command that checks
and fixes your entire installation — repo, crons, scripts,
services, system, config, governance (MCP servers, hooks), and
install footprint.

This is now a thin wrapper around the cortex_doctor package.

Usage:
    python3 cortex-doctor.py                  # full check (default)
    python3 cortex-doctor.py --json           # machine-readable output
    python3 cortex-doctor.py --fix            # auto-fix everything
    python3 cortex-doctor.py --watch          # re-check every 30s
    python3 cortex-doctor.py --quiet          # compact output
    python3 cortex-doctor.py --bus-alert      # send bus messages for actionable issues

Exit codes: 0 = pass   1 = warn   2 = fail
"""

import sys
import os

# Ensure the package directory AND the scripts parent are on the path.
# This handles both deployment (~/.hermes-cortex/scripts/) and in-repo
# (ops/scripts/manage/) layouts so that hermes_paths and lib.cortex_bus
# are importable regardless of CWD.
_this_dir = os.path.dirname(os.path.abspath(__file__))
_pkg_dir = os.path.join(_this_dir, "cortex_doctor")
if os.path.isdir(_pkg_dir):
    if _this_dir not in sys.path:
        sys.path.insert(0, _this_dir)
    # In-repo case: hermes_paths.py lives in ops/scripts/ (parent of manage/)
    _parent = os.path.dirname(_this_dir)
    _hermes_paths = os.path.join(_parent, "hermes_paths.py")
    if os.path.exists(_hermes_paths) and _parent not in sys.path:
        sys.path.insert(0, _parent)

from cortex_doctor.cli import main

if __name__ == "__main__":
    main()
