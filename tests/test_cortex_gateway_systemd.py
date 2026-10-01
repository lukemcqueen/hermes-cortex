"""CR4 — cortex-gateway systemd unit + config.

The gateway's whole point is to serve WITHOUT the incumbent harness. These
tests pin that: the unit carries no hermes-gateway dependency, the config
example is valid + parseable, and build_gateway wires it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO / "ops" / "scripts"))

# Import at module level so the package is cached in sys.modules — immune to
# other test modules resetting sys.path between tests.
import cortex_gateway.daemon  # noqa: E402,F401
import cortex_gateway.hermes_backend  # noqa: E402,F401

UNIT = _REPO / "docs" / "templates" / "cortex-gateway.service"
EXAMPLE = _REPO / "ops" / "scripts" / "gateway.yaml.example"


def _directives(text: str) -> list[str]:
    return [ln for ln in text.splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]


def test_unit_template_exists_and_is_user_scope():
    assert UNIT.is_file()
    body = UNIT.read_text()
    assert "WantedBy=default.target" in body      # user scope
    assert "USER-LEVEL ONLY" in body              # never /etc/systemd/system


def test_unit_has_no_hermes_gateway_dependency():
    directives = _directives(UNIT.read_text())
    offenders = [ln for ln in directives if "hermes-gateway" in ln]
    assert not offenders, f"unit must not depend on the incumbent: {offenders}"


def test_unit_execstart_targets_deployed_daemon_with_config():
    body = UNIT.read_text()
    assert "cortex_gateway/daemon.py" in body
    assert "--config" in body
    assert "gateway.yaml" in body


def test_unit_sources_env_from_cortex_env_file():
    # Exactly one env source, and it is the canonical cortex env.
    envfile = [ln for ln in _directives(UNIT.read_text())
               if ln.startswith("EnvironmentFile=")]
    assert envfile == ["EnvironmentFile=-%h/hermes-cortex/.env"], envfile


def test_unit_does_not_source_hermes_env():
    """We are migrating AWAY from Hermes: the unit must not read ~/.hermes/.env.

    Matching the var NAMES is right; depending on Hermes's env file would
    re-couple the target to the incumbent.
    """
    directives = _directives(UNIT.read_text())
    offenders = [ln for ln in directives if ".hermes/.env" in ln]
    assert not offenders, f"unit must not source Hermes's env: {offenders}"


def test_example_is_pure_json_and_parseable():
    # The daemon reads it with json.loads — comments would break that.
    data = json.loads(EXAMPLE.read_text())
    assert data["bots"], "example must define at least one bot"
    assert data["bots"][0]["token_ref"]
    assert data["backends"]


def test_example_embeds_no_literal_secret():
    data = json.loads(EXAMPLE.read_text())
    assert not data.get("secret"), "secrets must come from env, never the file"


def test_build_gateway_wires_the_example(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "dummy")
    monkeypatch.setenv("GATEWAY_SECRET", "dummy")
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERS", "1001")
    monkeypatch.setenv("TELEGRAM_HOME_CHANNEL", "1001")
    gw = cortex_gateway.daemon.build_gateway(EXAMPLE)
    assert gw.default_agent
    assert gw.backends
    assert type(gw.transport).__name__ == "TelegramAdapter"
