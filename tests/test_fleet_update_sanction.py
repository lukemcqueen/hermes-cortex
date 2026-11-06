#!/usr/bin/env python3
"""P3 step-1: the deploy-script sanction must dual-accept BOTH names.

The enforcer's _is_sanctioned_fleet_update_command is the single lock-free
carve-out that lets any agent run the deploy script without a governance lock.
It sanctions the path by LITERAL regex — the compiled rule is
`(?:cortex-update|fleet-update)\.sh` (verified in plugins/governance-enforcer/
__init__.py, same family as this test) — so renaming
ops/scripts/cortex-update.sh -> ops/scripts/fleet-update.sh without widening
the gate first would lock EVERY host out of deploys (the old name's sanction
dies with the file). Step 1 widened the regex to the dual-accept form above and
this test pins BOTH that the CURRENT name still sanctions AND that the FUTURE
name (which did not exist at step-1 time) is already accepted — the plan's
"feed the future path string" verification. It drives the REAL function, so
the metachar/separator rejection is exercised too.
"""
import importlib.util
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_ENFORCER = _REPO / "plugins" / "governance-enforcer" / "__init__.py"


def _enforcer():
    spec = importlib.util.spec_from_file_location("governance_enforcer_p3test",
                                                  str(_ENFORCER))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod.__name__] = mod
    spec.loader.exec_module(mod)
    return mod


def _sanctioned(cmd: str) -> bool:
    return _enforcer()._is_sanctioned_fleet_update_command(cmd)


def test_current_name_still_sanctioned():
    assert _sanctioned(f"bash {Path.home()}/steadfaste-fleet/ops/scripts/fleet-update.sh")
    assert _sanctioned(f"bash ~/steadfaste-fleet/ops/scripts/fleet-update.sh")
    assert _sanctioned(f"{Path.home()}/steadfaste-fleet/ops/scripts/fleet-update.sh --dry-run --status")


def test_future_fleet_name_sanctioned_before_it_exists():
    # The whole point of step 1: fleet-update.sh is sanctioned NOW, before any
    # git mv — so the rename can never lock out deploys. The path need not exist.
    assert _sanctioned(f"bash {Path.home()}/steadfaste-fleet/ops/scripts/fleet-update.sh")
    assert _sanctioned(f"bash ~/steadfaste-fleet/ops/scripts/fleet-update.sh --clean-stale")


def test_non_deploy_shapes_rejected():
    for cmd in (
        f"bash ~/steadfaste-fleet/ops/scripts/some-other.sh",
        f"sudo bash {Path.home()}/steadfaste-fleet/ops/scripts/fleet-update.sh",
        f"bash ~/steadfaste-fleet/ops/scripts/fleet-update.sh -c 'x'",
        f"bash ~/steadfaste-fleet/ops/scripts/fleet-update.sh | tail -1",
    ):
        assert not _sanctioned(cmd), f"unsanctioned shape accepted: {cmd}"