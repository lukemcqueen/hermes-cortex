"""cortex_doctor — ONE-RELEASE shim for the renamed fleet_doctor package (cortex->fleet, 2026-11-06).

The canonical package is now `fleet_doctor` (ops/scripts/manage/fleet_doctor/; deployed
scripts/fleet_doctor/). The deployed `cortex-doctor.py` entrypoint (hyphen name retained
until the P3 hyphen sweep) does:

    _pkg_dir = os.path.join(_this_dir, "fleet_doctor")   # this shim dir is NOT that
    from fleet_doctor.cli import main

so every legacy `cortex_doctor` import during the one-release window must resolve here:
we alias every `cortex_doctor.<sub>` name in sys.modules to its `fleet_doctor.<sub>`
module and hand `import cortex_doctor` back the fleet_doctor module object. This keeps
working:

    from cortex_doctor.cli import main
    python3 -m cortex_doctor.cli [--json|--fix|...]
    import cortex_doctor; cortex_doctor.Results

DELETE this shim (and its register() entry) in the release that retires the old name,
once `git grep -l 'cortex_doctor'` proves nothing imports it.

This directory holds ONLY this file — do not add real modules to it.
"""

import importlib
import sys

import fleet_doctor as _fleet  # noqa: F401  (the canonical package; re-exported below)

# Make `import cortex_doctor` hand back the fleet_doctor module object.
sys.modules[__name__] = _fleet

# Alias every submodule under the old name so legacy imports resolve without
# shipping files. importlib.import_module is idempotent and raises if a name
# ever vanishes from fleet_doctor (a hard error beats a half-alias).
for _sub in ("bus_alert", "checks", "cli", "config", "dispositions", "fix",
             "helpers", "immutability", "jev", "mcp_names", "results",
             "task_integrity"):
    sys.modules[f"{__name__}.{_sub}"] = importlib.import_module(f"fleet_doctor.{_sub}")

__all__ = []
