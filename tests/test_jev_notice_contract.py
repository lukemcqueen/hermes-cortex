#!/usr/bin/env python3
"""The routing notice contract, pinned against the INSTALLED plugin.

The notice is how a person sees which model a turn was routed to. It has to be quiet
when nothing was switched (a "kept" line on every turn is noise), and it has to be
controlled by the `notice` switch rather than by whether routing happened to fire.

Hermetic: the turn decision is injected, so no Jev call is made. The plugin is loaded
from the host's own install because that is the artifact under test; on a host without
the Jev layer the whole module skips rather than failing.
"""
import importlib.util
import json
import os
import pathlib
import sys

import pytest

HERMES_HOME = pathlib.Path(os.environ.get("HERMES_HOME") or (pathlib.Path.home() / ".hermes"))
PLUGIN = HERMES_HOME / "plugins" / "hermes-jev" / "__init__.py"


@pytest.fixture()
def plugin(tmp_path, monkeypatch):
    if not PLUGIN.exists():
        pytest.skip(f"hermes-jev not installed at {PLUGIN}")
    home = tmp_path / "home"
    (home / "jev").mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(home))
    # The plugin imports its vendored kit relatively, so it must load as a package.
    spec = importlib.util.spec_from_file_location(
        "hermes_jev_notice_test", PLUGIN, submodule_search_locations=[str(PLUGIN.parent)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hermes_jev_notice_test"] = mod
    spec.loader.exec_module(mod)
    mod._home = lambda: home  # keep every read inside the test's own tmp dir

    def switches(routing: str, notice: str) -> None:
        (home / "jev" / "state.json").write_text(
            json.dumps({"routing": routing, "notice": notice}), encoding="utf-8")

    mod.switches = switches
    mod._TURNS.clear()
    return mod


def _turn(mod, session: str, routed: bool, notice: str, effort=None) -> None:
    mod._TURNS[session] = {
        "turn_id": 1,
        "decision": {"routed": routed, "notice": notice},
        "effort": effort,
    }


def test_a_switched_turn_gets_the_footer_when_notice_is_on(plugin):
    plugin.switches("on", "on")
    notice = "[Jev] simple · general → qwen/qwen3.7-flash · confidence 1.00"
    _turn(plugin, "s1", True, notice)
    out = plugin._on_transform_output(response_text="body", session_id="s1")
    assert out == f"body\n\n{notice}"


def test_the_same_decision_gets_no_footer_when_notice_is_off(plugin):
    """The switch is the person's, not the router's: off means silent."""
    plugin.switches("on", "off")
    _turn(plugin, "s2", True, "[Jev] simple · general → qwen/qwen3.7-flash · confidence 1.00")
    assert plugin._on_transform_output(response_text="body", session_id="s2") is None


def test_a_kept_decision_stays_silent_even_with_notice_on(plugin):
    """Otherwise every ordinary turn carries a 'kept ...' line."""
    plugin.switches("on", "on")
    _turn(plugin, "s3", False, "[Jev] kept openrouter:deepseek/deepseek-v4.1-flash · simple general")
    assert plugin._on_transform_output(response_text="body", session_id="s3") is None


def test_an_effort_only_change_is_reported_without_a_switch(plugin):
    """The thinking budget is worth a line even when the model was kept."""
    plugin.switches("on", "on")
    _turn(plugin, "s4", False, "", effort="high")
    out = plugin._on_transform_output(response_text="body", session_id="s4")
    assert out == "body\n\n[Jev] · effort high"


def test_a_routing_notice_is_not_shown_while_routing_is_off(plugin):
    plugin.switches("off", "on")
    _turn(plugin, "s5", True, "[Jev] simple · general → qwen/qwen3.7-flash · confidence 1.00")
    assert plugin._on_transform_output(response_text="body", session_id="s5") is None


def test_an_invalidated_turn_is_never_noticed(plugin):
    """A turn the router abandoned must not claim a switch that did not happen."""
    plugin.switches("on", "on")
    _turn(plugin, "s6", True, "[Jev] simple · general → qwen/qwen3.7-flash · confidence 1.00")
    plugin._TURNS["s6"]["route_invalidated"] = True
    assert plugin._on_transform_output(response_text="body", session_id="s6") is None
