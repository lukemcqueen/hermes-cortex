"""cortex_lib — ONE-RELEASE shim for the renamed fleet_lib (cortex->fleet, 2026-11-06).

The canonical package is now `fleet_lib` (ops/scripts/fleet_lib/). This shim makes
every legacy `cortex_lib` import resolve to it, so code that has NOT yet been
redeployed keeps working during the transition window. DELETE this shim (and its
register() entries) in the release that retires the old name, once
`git grep -l 'cortex_lib'` proves nothing imports it.

Why it works: the real submodules live under fleet_lib. Instead of copying code,
we alias every `cortex_lib.<sub>` name in sys.modules to its `fleet_lib.<sub>`
module. Combined with the `cortex_lib/paths.py` re-exporter beside this file
(which keeps the byte-identical parent-walk bootstrap in old MCP servers able to
locate a physical file and add `scripts/` to sys.path), any of these still work:

    from cortex_lib.paths import resolve_repo_resource
    from cortex_lib.tz import get_timezone
    import cortex_lib.models
    cortex_lib.paths  (attribute access after `import cortex_lib`)
"""

import sys
import fleet_lib as _fleet  # noqa: F401  (the canonical package; re-exported below)
import fleet_lib.models  # noqa: F401  ensure submodules are attributes of fleet_lib
import fleet_lib.paths  # noqa: F401
import fleet_lib.session_repo  # noqa: F401
import fleet_lib.tools  # noqa: F401
import fleet_lib.tz  # noqa: F401

# Make `import cortex_lib` hand back the fleet_lib module object, so attribute
# access (cortex_lib.paths) and `cortex_lib.<sub>` agree with fleet_lib.
sys.modules[__name__] = _fleet

# Alias each submodule under the old name so `from cortex_lib.<sub> import X`
# resolves without shipping a file per submodule.
for _sub in ("models", "paths", "session_repo", "tools", "tz"):
    _m = getattr(_fleet, _sub, None)
    if _m is not None:
        sys.modules[f"{__name__}.{_sub}"] = _m

__all__ = []