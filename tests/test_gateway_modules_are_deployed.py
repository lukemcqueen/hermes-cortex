#!/usr/bin/env python3
"""Every module in cortex_gateway/ must actually be DEPLOYED, not just committed.

The failure this exists for: `cortex-update.sh` syncs an EXPLICIT list of files, so a new
module (agents.py, pairing.py) sat in the repo, was imported by the deployed daemon, and was
never copied to the host. The tests stayed green because they import the REPO tree, while the
host's gateway would die with ImportError on start — a green suite hiding a broken deploy.

So: assert the register and the package directory agree, in BOTH directions.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PKG = REPO / "ops" / "scripts" / "cortex_gateway"
UPDATE = REPO / "ops" / "scripts" / "cortex-update.sh"


def _registered() -> set:
    out = set()
    for line in UPDATE.read_text().splitlines():
        line = line.strip()
        if not line.startswith("register ") or "cortex_gateway/" not in line:
            continue
        # register "ops/scripts/cortex_gateway/x.py" "${CORTEX_DEPLOY_HOME}/scripts/cortex_gateway/x.py"
        src = line.split('"')[1]
        out.add(Path(src).name)
    return out


def _modules() -> set:
    return {p.name for p in PKG.glob("*.py")}


def test_the_bus_core_the_gateway_loads_is_registered_at_the_path_it_probes():
    """The second half of the same class of bug, found by starting the deployed gateway.

    `bot_locks._connect` (used by the gateway and by msg-gateway) probes
    `~/.hermes-cortex/queue.py` FIRST, then a repo-relative path that does not exist on a
    host. So the file must be deployed at exactly that destination: the loader's probe and
    the register's destination have to agree, which is what this asserts.
    """
    dests = {}
    for line in UPDATE.read_text().splitlines():
        line = line.strip()
        if line.startswith("register ") and "core/cortex_bus/queue.py" in line:
            dests["queue.py"] = line.split('"')[3]        # the destination, 4th quoted field
    assert dests, "core/cortex_bus/queue.py is not registered — the deployed gateway cannot start"
    assert "${CORTEX_DEPLOY_HOME}/queue.py" == dests["queue.py"], (
        f"the bus core must deploy to ${{CORTEX_DEPLOY_HOME}}/queue.py (what bot_locks probes), "
        f"not {dests['queue.py']}")
    loader = (REPO / "ops" / "scripts" / "bot_locks.py").read_text()
    assert '".hermes-cortex" / "queue.py"' in loader, \
        "bot_locks no longer probes ~/.hermes-cortex/queue.py — re-derive this guard"
    print("  the bus core deploys to the exact path bot_locks probes ✓")


def test_that_guard_would_catch_a_wrong_destination():
    """Control: a register line pointing somewhere else must fail the check."""
    right = "${CORTEX_DEPLOY_HOME}/queue.py"
    wrong = "${CORTEX_DEPLOY_HOME}/scripts/queue.py"
    assert right != wrong and wrong != "${CORTEX_DEPLOY_HOME}/queue.py"
    print("  control: a wrong destination is rejected ✓")


def test_every_module_is_registered_for_deploy():
    missing = sorted(_modules() - _registered())
    assert not missing, (
        f"these cortex_gateway modules are NOT in the deploy register, so the host will get "
        f"an ImportError while the repo tests pass: {missing}. Add a register line to "
        f"ops/scripts/cortex-update.sh next to the others.")
    print(f"  all {len(_modules())} modules are registered for deploy ✓")


def test_the_register_has_no_entries_that_no_longer_exist():
    """The other direction: a register line for a deleted file is a silent no-op deploy."""
    ghosts = sorted(_registered() - _modules())
    assert not ghosts, f"deploy register names files that do not exist: {ghosts}"
    print("  no register entry points at a file that is gone ✓")


def test_the_guard_actually_detects_a_missing_module():
    """Control: prove the check fails when it should, so it cannot pass vacuously."""
    mods, reg = _modules(), _registered()
    mods.add("brand_new_agent_kind.py")            # a module nobody registered
    assert sorted(mods - reg) == ["brand_new_agent_kind.py"], \
        "the set difference must catch an unregistered module"
    print("  control: an unregistered module is detected ✓")


def test_the_agent_reply_entrypoint_is_registered_for_deploy():
    """Same class of bug, one layer further out: an ENTRYPOINT, not a package module.

    `agent-reply.py` is the fleet's agent-side reply primitive (docs/design/gateway-reply-path.md
    names it as the supported producer for `out_<agent>`), and it imports the SAME repo tree the
    directory guard above covers. It sat in the repo, deployed nowhere: the host had no
    `~/.hermes-cortex/scripts/agent-reply.py`, so the one documented way for an agent to answer a
    human did not exist on the deployed path — while every repo test passed, because they load it
    by repo path (`tests/test_agent_reply_cli.py`).
    """
    dests = {}
    for line in UPDATE.read_text().splitlines():
        line = line.strip()
        if line.startswith("register ") and "ops/scripts/agent-reply.py" in line:
            dests["agent-reply.py"] = line.split('"')[3]
    assert dests, ("ops/scripts/agent-reply.py is not in the deploy register, so the deployed host "
                   "has no agent-reply: the documented reply path cannot run there")
    assert "${CORTEX_DEPLOY_HOME}/scripts/agent-reply.py" == dests["agent-reply.py"], (
        f"agent-reply.py must deploy to ${{CORTEX_DEPLOY_HOME}}/scripts/agent-reply.py, "
        f"not {dests['agent-reply.py']}")
    # Premise: the CLI test still loads the script BY REPO PATH — that is exactly why a
    # green suite could hide a missing deployed copy, so the guard is only meaningful
    # while that stays true.
    cli_test = (REPO / "tests" / "test_agent_reply_cli.py").read_text()
    assert "agent-reply.py" in cli_test, (
        "tests/test_agent_reply_cli.py no longer loads ops/scripts/agent-reply.py by repo "
        "path — re-derive this guard's premise before trusting it")
    print("  the agent-reply entrypoint is registered for deploy (and the test that would "
          "otherwise hide its absence still loads it from the repo) ✓")


def test_the_dependent_imports_really_are_in_those_modules():
    """The guard is only meaningful if the deployed daemon imports them — verify that, too."""
    daemon = (PKG / "daemon.py").read_text()
    for mod in ("agents", "pairing"):
        assert f".{mod}" in daemon or f"import {mod}" in daemon, \
            f"daemon.py no longer references {mod}.py — update this guard's premise"
    print("  daemon.py does import the modules this guard protects ✓")
