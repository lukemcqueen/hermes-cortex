#!/usr/bin/env python3
"""
cortex_lib/paths.py — Path setup helper (canonical, Hermes-independent).

Canonical home of the path logic in hermes_paths.py. Moved so no fleet component
requires the Hermes runtime to resolve it. `hermes_paths` remains as a thin
re-export shim (see component-hermes-separation.md S1a).

Adds the canonical scripts directory to sys.path so that scripts in
subdirectories (ops/offline/, ops/services/, etc.) can import shared modules
like cortex_lib.models regardless of where they're deployed.

Usage at the top of any script that imports from the scripts dir:

    from cortex_lib.paths import ensure_scripts_path
    ensure_scripts_path()
    from cortex_lib.models import get_model
"""

import sys
from pathlib import Path


def ensure_scripts_path() -> None:
    """Add the scripts directory to sys.path if not already present.

    Works both in-repo (ops/offline/, ops/services/, mcp-servers/) and at
    deployment (~/.hermes-cortex/scripts). This module now lives at
    ops/scripts/cortex_lib/, so the canonical scripts dir (ops/scripts) is
    its parent — NOT the old hermes_paths.py location where `scripts` was a
    sibling of this module's dir.
    """
    cortex_lib_dir = Path(__file__).resolve().parent      # .../ops/scripts/cortex_lib
    # Check both the repo layout and the deployed layout.
    candidates = [
        cortex_lib_dir.parent,              # ops/scripts/         (in-repo, canonical)
        Path.home() / ".hermes-cortex" / "scripts",
    ]
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_dir() and str(resolved) not in sys.path:
            sys.path.insert(0, str(resolved))
