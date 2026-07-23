"""
cortex_doctor — Hermes Cortex installation health check package.

Split from the monolithic cortex-doctor.py (2177 lines) into modular
components:

- config:   Paths, constants, dynamic registries
- results:  Result tracking and formatting
- helpers:  Utility functions (run, http_get, process_running, etc.)
- checks:   All health check functions
- fix:      Auto-fix actions
- bus_alert: Bus alert dispatch for AGENTS.md reminders
- cli:      Main entry point and argument parsing

Usage (direct):
    python3 -m cortex_doctor.cli [--json|--fix|--watch|--quiet|--quick|--bus-alert]
"""

from .cli import main
from .results import Results
