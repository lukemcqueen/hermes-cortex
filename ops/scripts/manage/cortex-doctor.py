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

# Ensure the package directory is on the path
_pkg_dir = os.path.join(os.path.dirname(__file__), "cortex_doctor")
if os.path.isdir(_pkg_dir) and _pkg_dir not in sys.path:
    sys.path.insert(0, os.path.dirname(__file__))

from cortex_doctor.cli import main

if __name__ == "__main__":
    main()
