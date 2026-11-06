"""cortex_gateway — ONE-RELEASE shim for the renamed fleet_gateway package (cortex->fleet, 2026-11-06).

The canonical package is now `fleet_gateway` (ops/scripts/fleet_gateway/; deployed
scripts/fleet_gateway/). The live gateway unit still ExecStarts
`%h/.steadfaste-fleet/scripts/cortex_gateway/daemon.py` until the P5 unit rename,
and any not-yet-redeployed thing imports `cortex_gateway.*`; this shim makes every
legacy `cortex_gateway` name resolve to the SAME module objects as `fleet_gateway`.

We alias every `cortex_gateway.<sub>` name in sys.modules to its `fleet_gateway.<sub>`
module and hand `import cortex_gateway` back the fleet_gateway module object, so all
of these keep working:

    from cortex_gateway.daemon import build_gateway
    from cortex_gateway.hermes_backend import HermesBackend
    python3 scripts/cortex_gateway/daemon.py        (relative imports resolve via the alias)
    import cortex_gateway; cortex_gateway.backend

DELETE this shim (and its register() entry) in the release that retires the old
name, once `git grep -l 'cortex_gateway'` proves nothing imports it.

This directory holds ONLY this file — do not add real modules to it.
"""

import importlib
import sys

import fleet_gateway as _fleet  # noqa: F401  (the canonical package; re-exported below)

# Make `import cortex_gateway` hand back the fleet_gateway module object.
sys.modules[__name__] = _fleet

# Alias every submodule under the old name. importlib.import_module is idempotent
# and raises if a name ever vanishes from fleet_gateway (hard error over half-alias).
for _sub in ("agents", "backend", "daemon", "guard_distinct_token", "hermes_backend",
             "models", "new_command_evidence", "pairing", "pi_control", "restarts",
             "sessions", "slash_parity_evidence", "transport"):
    sys.modules[f"{__name__}.{_sub}"] = importlib.import_module(f"fleet_gateway.{_sub}")

__all__ = []