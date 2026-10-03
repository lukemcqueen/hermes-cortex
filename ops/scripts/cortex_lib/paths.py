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


# ── Resolving a REPO-RELATIVE resource, in-repo or deployed ──────────────
#
# The deployed path of a repo file CANNOT be derived from the repo path. The
# deploy map is per-file: of 289 register() calls in cortex-update.sh, 192 follow
# no rule —
#
#     ops/scripts/manage/task-db.py            -> scripts/task-db.py
#     ops/scripts/manage/agent-no-verify-audit.py -> scripts/manage/agent-...
#     mcp-servers/task-mcp.py                  -> scripts/task-mcp.py
#
# so any guess (strip `ops/`, strip a subdir, try a short list) resolves in the
# repo and FAILS AFTER A DEPLOY, on a host, far from the edit. Every component
# used to hand-roll its own guess — task-mcp tried four paths, loop-gov two (the
# first of which, <deploy>/tools/ops/scripts/judgment.py, exists in NEITHER
# layout), cortex-context-mcp two.
#
# The fix is to stop guessing. cortex-update.sh already holds the mapping as data
# (its register() map), so it WRITES it out as `deploy-manifest.tsv` and these
# functions READ it. One source of truth: the register() lines.
#
# Use these. Never hand-roll a candidate list: pass the repo-relative path you
# would write in the repo.

_MANIFEST_NAME = "deploy-manifest.tsv"


def _repo_roots():
    """Ancestors that look like the repo (they hold `ops/scripts/`)."""
    return [p for p in Path(__file__).resolve().parents
            if (p / "ops" / "scripts").is_dir()]


def read_manifest(path) -> dict:
    """Parse a ``deploy-manifest.tsv`` into a repo-path → deployed-path map."""
    mapping = {}
    for line in Path(path).read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) == 2:
            mapping[parts[0]] = parts[1]
    return mapping


def deploy_manifest():
    """The generated repo-path → deployed-path map, or {} when absent.

    Written by cortex-update.sh. Absent in the repo (where the paths are already
    correct) and on a host that has never been deployed.
    """
    for parent in Path(__file__).resolve().parents:
        manifest = parent / _MANIFEST_NAME
        if manifest.is_file():
            return read_manifest(manifest)
    return {}


def resolve_repo_resource(rel: str):
    """Resolve a REPO-RELATIVE path (e.g. ``ops/scripts/judgment.py``) here.

    REPO layout: the path as written, from the repo root.
    DEPLOYED layout: looked up in ``deploy-manifest.tsv`` — never guessed.

    Returns ``None`` when the resource is absent. Callers must treat that as a
    LOUD error, never a silent skip, and should report
    :func:`repo_resource_candidates` so the message says where it looked.
    """
    rel_path = Path(rel)
    for root in _repo_roots():
        candidate = root / rel_path
        if candidate.is_file():
            return candidate
    deployed = deploy_manifest().get(rel)
    if deployed:
        candidate = Path(deployed)
        if candidate.is_file():
            return candidate
    return None


def repo_resource_candidates(rel: str) -> list:
    """Every path :func:`resolve_repo_resource` would have tried, in order.

    Exists so a failure can say *where* it looked instead of only *that* it
    failed — the difference between a one-line fix and a hunt.
    """
    out = [root / Path(rel) for root in _repo_roots()]
    deployed = deploy_manifest().get(rel)
    out.append(Path(deployed) if deployed
               else Path(f"<{_MANIFEST_NAME}: no entry for {rel!r}>"))
    return out
