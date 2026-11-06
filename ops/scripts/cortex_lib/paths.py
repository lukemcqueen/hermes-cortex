"""cortex_lib/paths.py — re-export shim for fleet_lib.paths (one-release).

Kept so the byte-identical "parent-walk finds `cortex_lib/paths.py`" bootstrap in
any non-redeployed MCP server can still locate a physical file under the OLD name
and add the canonical scripts dir to sys.path, before the import falls through to
the fleet_lib implementation below. DELETE alongside cortex_lib/__init__.py in the
release that retires the old name.
"""

from fleet_lib.paths import *  # noqa: F401,F403  (re-export every public name)
from fleet_lib.paths import (  # noqa: F401  (explicit for static readers)
    _MANIFEST_NAME,
    deploy_manifest,
    ensure_scripts_path,
    read_manifest,
    repo_resource_candidates,
    resolve_repo_resource,
)