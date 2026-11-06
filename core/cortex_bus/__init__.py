"""cortex_bus — ONE-RELEASE shim for the renamed fleet_bus package (cortex->fleet, 2026-11-06).

The canonical package is now `fleet_bus` (core/fleet_bus/). The live gateway runs
`uvicorn fleet_bus.server:app` from the repo (WorkingDirectory/PYTHONPATH = core/),
so this shim exists ONLY for code that has not yet been redeployed or pulled:
every legacy `cortex_bus` import resolves to the same module objects.

Why it works: the real submodules live under fleet_bus (server, queue, validate,
auth, circuit_breaker, ratelimit, and the workflow subpackage). Instead of
copying code, we alias every `cortex_bus.<sub>` name in sys.modules to its
`fleet_bus.<sub>` module, and finally hand `import cortex_bus` back the fleet_bus
module object. Any of these legacy forms keep working unchanged:

    from cortex_bus.queue import NotAvailableError
    from cortex_bus.server import app          (uvicorn app path)
    import cortex_bus.workflow.router
    cortex_bus.validate                        (attribute access)

DELETE this shim in the release that retires the old name, once
`git grep -l 'cortex_bus'` proves nothing imports it (except this file and the
schema comment).

This directory holds ONLY this file — do not add real modules to it.
"""

import importlib
import sys

import fleet_bus as _fleet  # noqa: F401  (the canonical package; re-exported below)
import fleet_bus.auth  # noqa: F401
import fleet_bus.circuit_breaker  # noqa: F401
import fleet_bus.queue  # noqa: F401
import fleet_bus.ratelimit  # noqa: F401
import fleet_bus.server  # noqa: F401
import fleet_bus.validate  # noqa: F401
import fleet_bus.workflow  # noqa: F401
import fleet_bus.workflow.db  # noqa: F401
import fleet_bus.workflow.dispatcher  # noqa: F401
import fleet_bus.workflow.human_gate  # noqa: F401
import fleet_bus.workflow.router  # noqa: F401
import fleet_bus.workflow.sla_watchdog  # noqa: F401
import fleet_bus.workflow.yaml_loader  # noqa: F401

# Make `import cortex_bus` hand back the fleet_bus module object, so attribute
# access (cortex_bus.server) and `cortex_bus.<sub>` agree with fleet_bus.
sys.modules[__name__] = _fleet

# Alias each submodule (and the workflow subpackage's modules) under the old
# name so `from cortex_bus.<sub> import X` resolves without shipping files.
# importlib.import_module is idempotent and raises if a name ever vanishes from
# fleet_bus (a hard error beats a half-alias).
for _sub in ("auth", "circuit_breaker", "queue", "ratelimit", "server",
             "validate", "workflow", "workflow.db", "workflow.dispatcher",
             "workflow.human_gate", "workflow.router", "workflow.sla_watchdog",
             "workflow.yaml_loader"):
    sys.modules[f"{__name__}.{_sub}"] = importlib.import_module(f"fleet_bus.{_sub}")

__all__ = []
