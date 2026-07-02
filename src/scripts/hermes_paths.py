#!/usr/bin/env python3
"""
hermes_paths.py — Path setup helper for Hermes Cortex scripts.

Adds the canonical scripts directory to sys.path so that scripts in
subdirectories (src/offline/, src/web-cache/, etc.) can import shared
modules like hermes_models.py regardless of where they're deployed.

Usage at the top of any script that imports from hermes_models:

    from hermes_paths import ensure_scripts_path
    ensure_scripts_path()
    from hermes_models import get_model
"""

import sys
from pathlib import Path


def ensure_scripts_path() -> None:
    """Add the scripts directory to sys.path if not already present.

    Works both in-repo (src/offline/, src/web-cache/, src/mcp-servers/)
    and at deployment (~/.hermes-cortex/offline/, ~/.hermes-cortex/tools/).
    """
    this_dir = Path(__file__).resolve().parent
    # Check both the repo layout and the deployed layout
    candidates = [
        this_dir.parent / "scripts",       # src/offline/ → src/scripts/  (in-repo)
        this_dir.parent / ".." / "scripts", # further up
        Path.home() / ".hermes-cortex" / "scripts",
    ]
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved.is_dir() and str(resolved) not in sys.path:
            sys.path.insert(0, str(resolved))
