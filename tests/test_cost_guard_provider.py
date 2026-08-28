"""Hermetic tests for the cost-guard cron scheduler provider.

Verifies the guard decision logic (block/exempt/disabled) and the
get_due_jobs filter wrapper WITHOUT a live gateway. The provider imports
cron.* from the hermes-agent tree, so this test runs under the hermes-agent
venv with HERMES_HOME pointed at a temp dir.

Run:
    HERMES_HOME=/tmp/cost-guard-test ~/.hermes/hermes-agent/venv/bin/python \
        -m pytest tests/test_cost_guard_provider.py -v
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure the hermes-agent tree is importable (cron.*, hermes_cli.*).
_AGENT = os.path.expanduser("~/.hermes/hermes-agent")
if _AGENT not in sys.path:
    sys.path.insert(0, _AGENT)

from cron.scheduler_provider import InProcessCronScheduler  # noqa: E402

# The plugin under test — prefer the deployed copy, fall back to repo source.
_REPO_ROOT = Path(__file__).resolve().parents[1]
_PLUGIN = Path(_AGENT) / "plugins" / "cron_providers" / "cost-guard" / "__init__.py"
if not _PLUGIN.exists():
    _PLUGIN = _REPO_ROOT / "plugins" / "cron_providers" / "cost-guard" / "__init__.py"
if not _PLUGIN.exists():
    raise FileNotFoundError(f"cost-guard provider not found (tried {_PLUGIN})")

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location("cost_guard_provider", _PLUGIN)
assert _spec is not None and _spec.loader is not None
_provider_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_provider_mod)


def _job(job_id: str = "job-1", name: str = "agent-demo") -> dict:
    return {"id": job_id, "name": name}


class _FakeConfig:
    """Point _cfg() at a controllable dict without touching config.yaml.

    NOTE: _cfg() already unwraps config.yaml's cron.cost_guard block, so the
    fake returns the UNWRAPPED guard dict directly (not the full config).
    """

    def __init__(self, guard_cfg: dict):
        self._guard_cfg = guard_cfg

    def load_config(self):
        return self._guard_cfg


@pytest.fixture(autouse=True)
def _isolated_config(monkeypatch):
    """Default: guard enabled, no exemptions, multiplier 8."""
    fake = _FakeConfig({"enabled": True, "exempt": [], "multiplier": 8.0})
    monkeypatch.setattr(_provider_mod, "_cfg", fake.load_config)
    yield


# ── Guard decision helpers ──────────────────────────────────────────────


def test_provider_is_builtin_subclass():
    assert issubclass(_provider_mod.CostGuardCronScheduler, InProcessCronScheduler)


def test_provider_name():
    assert _provider_mod.CostGuardCronScheduler().name == "cost-guard"


def test_guard_enabled_default():
    assert _provider_mod._guard_enabled() is True


def test_guard_disabled_explicit():
    fake = _FakeConfig({"enabled": False})
    _provider_mod._cfg = fake.load_config
    assert _provider_mod._guard_enabled() is False


def test_exempt_names_parsing():
    fake = _FakeConfig({"exempt": ["agent-critical", "orch-nightly"]})
    _provider_mod._cfg = fake.load_config
    assert _provider_mod._exempt_names() == {"agent-critical", "orch-nightly"}


def test_multiplier_parsing():
    fake = _FakeConfig({"multiplier": 12.5})
    _provider_mod._cfg = fake.load_config
    assert _provider_mod._multiplier() == 12.5


def test_multiplier_invalid_falls_back():
    fake = _FakeConfig({"multiplier": "not-a-number"})
    _provider_mod._cfg = fake.load_config
    assert _provider_mod._multiplier() == 8.0


# ── should_block decision matrix ────────────────────────────────────────


def test_should_block_disabled_guard_allows(monkeypatch):
    fake = _FakeConfig({"enabled": False})
    monkeypatch.setattr(_provider_mod, "_cfg", fake.load_config)
    monkeypatch.setattr(_provider_mod, "_guard_enabled", lambda: False)
    assert _provider_mod._should_block(_job()) is False


def test_should_block_exempt_name_allows(monkeypatch):
    fake = _FakeConfig({"enabled": True, "exempt": ["agent-critical"]})
    monkeypatch.setattr(_provider_mod, "_cfg", fake.load_config)
    monkeypatch.setattr(
        _provider_mod, "_exempt_names", lambda: {"agent-critical"}
    )
    assert _provider_mod._should_block(_job(name="agent-critical")) is False


def test_should_block_missing_id_allows(monkeypatch):
    assert _provider_mod._should_block({"name": "agent-x"}) is False


def test_should_block_verdict_block_true(monkeypatch):
    # Patch at the source module — the provider imports should_fire lazily
    # inside _should_block, so patching _provider_mod.should_fire is a no-op.
    import cron.max_cost_guard as _mcg

    monkeypatch.setattr(
        _mcg,
        "should_fire",
        lambda job_id, job_name=None: {"decision": "block", "reason": "over"},
    )
    assert _provider_mod._should_block(_job()) is True


def test_should_block_verdict_allow_false(monkeypatch):
    import cron.max_cost_guard as _mcg

    monkeypatch.setattr(
        _mcg,
        "should_fire",
        lambda job_id, job_name=None: {"decision": "allow", "reason": "ok"},
    )
    assert _provider_mod._should_block(_job()) is False


def test_should_block_guard_error_fails_open(monkeypatch):
    import cron.max_cost_guard as _mcg

    def _boom(job_id, job_name=None):
        raise RuntimeError("db missing")

    monkeypatch.setattr(_mcg, "should_fire", _boom)
    assert _provider_mod._should_block(_job()) is False


# ── get_due_jobs filter wrapper ─────────────────────────────────────────


def test_due_filter_removes_blocked_only(monkeypatch):
    due = [
        _job("job-a", "agent-a"),
        _job("job-b", "agent-b"),
        _job("job-c", "agent-c"),
    ]

    def _orig():
        return list(due)

    blocked_ids = {"job-b"}

    def _should_block(job):
        return job.get("id") in blocked_ids

    monkeypatch.setattr(_provider_mod, "_should_block", _should_block)
    filt = _provider_mod._make_due_filter(_orig)
    result = filt()
    assert [j["id"] for j in result] == ["job-a", "job-c"]


def test_due_filter_no_blocked_passthrough(monkeypatch):
    due = [_job("job-a", "agent-a"), _job("job-b", "agent-b")]

    def _orig():
        return list(due)

    monkeypatch.setattr(_provider_mod, "_should_block", lambda j: False)
    filt = _provider_mod._make_due_filter(_orig)
    assert filt() == due


def test_due_filter_empty_passthrough(monkeypatch):
    def _orig():
        return []

    monkeypatch.setattr(_provider_mod, "_should_block", lambda j: True)
    filt = _provider_mod._make_due_filter(_orig)
    assert filt() == []


def test_due_filter_original_error_propagates(monkeypatch):
    def _orig():
        raise OSError("lock")

    filt = _provider_mod._make_due_filter(_orig)
    with pytest.raises(OSError):
        filt()
