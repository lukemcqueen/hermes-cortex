#!/usr/bin/env python3
"""The doctor's `Jev decision layer` check — and the cost rule it exists for.

Hermetic: the module is imported by path, its catalog cache and its current-model
lookup are repointed at fixtures, and HERMES_HOME is a temp dir. No network, no
live state.

The rule under test is the one a doc could not hold: pools are FIRST FIT WINS, so
a pool that leads with a model dearer than the one the host already runs is a real
cost mistake — WARN while routing is off (a trap waiting for the switch), FAIL once
routing is `on` (actual money). `hard` is exempt: escalating the genuinely hard
work is the tier's purpose.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

MODULE = (Path(__file__).resolve().parents[1] / "ops" / "scripts" / "manage"
          / "cortex_doctor" / "jev.py")
SPEC = importlib.util.spec_from_file_location("cortex_doctor_jev_under_test", MODULE)
assert SPEC is not None and SPEC.loader is not None, f"cannot load {MODULE}"
jev = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(jev)


class Collector:
    """Minimal stand-in for cortex_doctor.results.Results."""

    def __init__(self):
        self.rows = []

    def add(self, name, status, detail="", fix=""):
        self.rows.append({"name": name, "status": status, "detail": detail, "fix": fix})

    @property
    def last(self):
        return self.rows[-1]


CATALOG = {
    "openrouter": {"models": {
        "deepseek/deepseek-v4.1-flash": {"cost": {"input": 0.14, "output": 0.42}},   # 0.56
        "qwen/qwen3.7-flash": {"cost": {"input": 0.01, "output": 0.04}},             # 0.05
        "moonshotai/kimi-k2.7-code": {"cost": {"input": 0.90, "output": 2.76}},      # 3.66
        "openai/gpt-5.3-codex": {"cost": {"input": 3.00, "output": 12.75}},          # 15.75
    }},
}


@pytest.fixture
def doctor(tmp_path, monkeypatch):
    """A temp host: HERMES_HOME, a fixture catalog, and a known current model."""
    home = tmp_path / "hermes"
    (home / "plugins" / "hermes-jev").mkdir(parents=True)
    (home / "plugins" / "hermes-jev" / "plugin.yaml").write_text("name: hermes-jev\n")
    cache = tmp_path / "models_dev.json"
    cache.write_text(json.dumps(CATALOG))
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr(jev, "CATALOG_CACHE", cache)
    monkeypatch.setattr(jev, "_current_model", lambda: "deepseek/deepseek-v4.1-flash")
    return home


def _pools(home, tiers):
    path = home / "jev" / "routing.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"tiers": tiers}))
    return path


def _mode(home, mode):
    path = home / "jev" / "state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"routing": mode}))


def test_not_installed_is_a_warn_with_the_installer_in_the_fix(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "empty-home"))
    monkeypatch.setattr(jev.shutil, "which", lambda _name: None)
    res = Collector()

    jev.check_jev_layer(res)

    assert res.last["status"] == "WARN"
    assert "install-jev-layer.sh" in res.last["fix"], "the fix must name the one command"


def test_installed_without_pools_cannot_route(doctor):
    res = Collector()

    jev.check_jev_layer(res)

    assert res.last["status"] == "WARN"
    assert "no routing pools" in res.last["detail"]


def test_cheapest_first_pools_pass(doctor):
    _pools(doctor, {"simple": {"coding": ["openrouter:qwen/qwen3.7-flash"]},
                    "medium": {"coding": ["openrouter:deepseek/deepseek-v4.1-flash"]}})
    res = Collector()

    jev.check_jev_layer(res)

    assert res.last["status"] == "PASS", res.last
    assert "$0.560/M" in res.last["detail"], "the current model's real price is reported"


def test_a_dear_pool_head_warns_and_names_the_pool(doctor):
    _pools(doctor, {"medium": {"coding": ["openrouter:moonshotai/kimi-k2.7-code",
                                          "openrouter:deepseek/deepseek-v4.1-flash"]}})
    res = Collector()

    jev.check_jev_layer(res)

    assert res.last["status"] == "WARN"
    assert "medium/coding" in res.last["detail"]
    assert "3.660" in res.last["detail"] and "0.560" in res.last["detail"], \
        "both prices must be shown, or the reader cannot judge it"


def test_the_same_pool_FAILS_once_routing_is_armed(doctor):
    """Off is a trap; on is money."""
    _pools(doctor, {"medium": {"coding": ["openrouter:moonshotai/kimi-k2.7-code"]}})
    _mode(doctor, "on")
    res = Collector()

    jev.check_jev_layer(res)

    assert res.last["status"] == "FAIL", res.last


def test_hard_escalation_is_not_a_cost_finding(doctor):
    """`hard` is SUPPOSED to lead with a dearer model."""
    _pools(doctor, {"hard": {"coding": ["openrouter:openai/gpt-5.3-codex"]}})
    _mode(doctor, "on")
    res = Collector()

    jev.check_jev_layer(res)

    assert res.last["status"] == "PASS", res.last


def test_the_same_model_at_two_prices_is_not_a_finding(doctor):
    """A bare configured id and a provider-prefixed pool entry are the SAME model —
    resolving them through different lookups flagged it as dearer than itself."""
    _pools(doctor, {"medium": {"general": ["openrouter:deepseek/deepseek-v4.1-flash"]}})
    res = Collector()

    jev.check_jev_layer(res)

    assert res.last["status"] == "PASS", res.last
