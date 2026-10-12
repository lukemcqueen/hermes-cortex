"""The /model picker must be enableable on EVERY agent host, not just this one.

Titus runs pi on macOS with no Hermes and no cortex venv; a host behind a shim cannot take
a model at all. These tests pin the portable enabler (ops/scripts/manage/gateway-model-list.py)
and the gateway's warning for a backend that has nothing to switch.

Run: python3 -m pytest tests/test_gateway_model_list_helper.py -q
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
HELPER = REPO / "ops" / "scripts" / "manage" / "gateway-model-list.py"

sys.path.insert(0, str(REPO / "ops" / "scripts"))
import cortex_gateway.daemon as DAEMON  # noqa: E402

import types  # noqa: E402


def _load_helper():
    """Import the helper by path (it is a CLI, not an installed module)."""
    spec = importlib.util.spec_from_file_location("gateway_model_list", HELPER)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def helper():
    return _load_helper()


# --- the pi capture: three outcomes, and the one that is NOT an error ----------------

PI_TABLE = """\
provider/model                          context   tools
openrouter/moonshotai/kimi-k2.6         200k      yes
openrouter/anthropic/claude-sonnet-4.5  200k      yes
openrouter/openai/gpt-5                 400k      yes
openrouter/x-ai/grok-4                  256k      yes
"""

PI_NONE = "No models matching 'zzz'.\n"


def test_parses_a_pi_table_into_model_ids(helper):
    assert helper.parse_pi_models(PI_TABLE) == [
        "openrouter/moonshotai/kimi-k2.6",
        "openrouter/anthropic/claude-sonnet-4.5",
        "openrouter/openai/gpt-5",
        "openrouter/x-ai/grok-4",
    ]


def test_no_models_matching_is_empty_not_an_error(helper):
    """pi prints 'No models matching' and exits 0 — the OUTCOME decides, not the code."""
    assert helper.parse_pi_models(PI_NONE) == []


def test_parsing_ignores_prose_and_headers(helper):
    noisy = "Loading models...\n" + PI_TABLE + "\n3 of 412 models shown.\n"
    assert len(helper.parse_pi_models(noisy)) == 4


def test_curation_dedupes_strips_and_keeps_order(helper):
    raw = [" openrouter/openai/gpt-5 ", "openrouter/openai/gpt-5", "", "  ", "openrouter/x-ai/grok-4"]
    assert helper.curate(raw) == ["openrouter/openai/gpt-5", "openrouter/x-ai/grok-4"]


# --- the block must be exactly what the daemon loads ---------------------------------

def test_block_shape_matches_what_the_daemon_reads(helper):
    block = helper.models_block(["openrouter/openai/gpt-5"], page_size=6)
    assert block == {"models": {"list": ["openrouter/openai/gpt-5"], "page_size": 6}}
    # The daemon does json.loads(config); a JSON round-trip must be lossless.
    assert json.loads(json.dumps(block)) == block


def test_block_is_installable_in_a_config_the_daemon_already_accepts(helper, tmp_path):
    cfg = tmp_path / "gateway.yaml"
    cfg.write_text(json.dumps({"backends": [], "routing": {"default": "pi"}}))
    helper.write_models(cfg, {"list": ["openrouter/openai/gpt-5"], "page_size": 6})
    data = json.loads(cfg.read_text())
    # The menu config the daemon reads is `data["models"]` — a dict OR a bare list.
    assert data["models"]["list"] == ["openrouter/openai/gpt-5"]
    assert data["models"]["page_size"] == 6


# --- writing is a merge, never a rewrite, and it is idempotent ------------------------

def test_write_preserves_every_other_key(helper, tmp_path):
    original = {
        "backends": [{"name": "pi", "kind": "command", "model": "openrouter/openai/gpt-5"}],
        "bots": [{"token_ref": "TITUS_BOT_TOKEN"}],
        "routing": {"default": "pi", "overrides": {"123": "pi"}},
    }
    cfg = tmp_path / "gateway.yaml"
    cfg.write_text(json.dumps(original, indent=2) + "\n")
    helper.write_models(cfg, {"list": ["openrouter/openai/gpt-5"], "page_size": 6})
    data = json.loads(cfg.read_text())
    for key, value in original.items():
        assert data[key] == value, f"{key} was disturbed by a models: write"
    assert data["models"]["page_size"] == 6


def test_write_is_idempotent(helper, tmp_path):
    cfg = tmp_path / "gateway.yaml"
    cfg.write_text(json.dumps({"backends": []}))
    block = {"list": ["openrouter/openai/gpt-5", "openrouter/x-ai/grok-4"], "page_size": 6}
    helper.write_models(cfg, block)
    once = cfg.read_text()
    helper.write_models(cfg, block)
    assert cfg.read_text() == once, "a second identical write changed the file"


def test_write_refuses_a_config_that_is_not_json(helper, tmp_path):
    """A real YAML config (unquoted keys) must be refused with a message, not a traceback."""
    cfg = tmp_path / "gateway.yaml"
    cfg.write_text("backends:\n  - name: pi\n    kind: command\n")
    with pytest.raises(helper.ConfigNotJSON) as exc:
        helper.write_models(cfg, {"list": ["a/b"], "page_size": 6})
    assert "JSON" in str(exc.value)
    assert cfg.read_text() == "backends:\n  - name: pi\n    kind: command\n", "file was touched"


def test_write_refuses_a_non_object_config(helper, tmp_path):
    cfg = tmp_path / "gateway.yaml"
    cfg.write_text("[1, 2, 3]")
    with pytest.raises(helper.ConfigNotJSON):
        helper.write_models(cfg, {"list": ["a/b"], "page_size": 6})


# --- checking an existing block is what a fleet sweep runs ---------------------------

def test_check_reports_blank_entries_duplicates_and_page_size(helper):
    problems = helper.check_models({"list": ["a/b", " ", "a/b"], "page_size": 0})
    joined = " | ".join(problems)
    assert "blank" in joined
    assert "duplicate" in joined
    assert "page_size" in joined


def test_check_accepts_a_good_block(helper):
    assert helper.check_models({"list": ["a/b", "c/d"], "page_size": 6}) == []


def test_check_reports_a_missing_or_badly_typed_block(helper):
    assert helper.check_models(None) != []
    assert helper.check_models({"list": "a/b"}) != []


# --- the CLI is what an operator on Titus actually runs ------------------------------

def test_cli_prints_a_block_without_touching_anything(tmp_path):
    cfg = tmp_path / "gateway.yaml"
    cfg.write_text(json.dumps({"backends": []}))
    before = cfg.read_text()
    out = subprocess.run(
        [sys.executable, str(HELPER), "--config", str(cfg), "--models", "a/b,c/d"],
        capture_output=True, text=True,
    )
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout.strip().split("\n")[-1])["models"]["list"] == ["a/b", "c/d"]
    assert cfg.read_text() == before, "the default must be a dry run"


def test_cli_write_then_check_is_clean(tmp_path):
    cfg = tmp_path / "gateway.yaml"
    cfg.write_text(json.dumps({"backends": []}))
    w = subprocess.run(
        [sys.executable, str(HELPER), "--config", str(cfg), "--models", "a/b,c/d", "--write"],
        capture_output=True, text=True,
    )
    assert w.returncode == 0, w.stderr
    c = subprocess.run(
        [sys.executable, str(HELPER), "--config", str(cfg), "--check"],
        capture_output=True, text=True,
    )
    assert c.returncode == 0, c.stdout + c.stderr


def test_cli_check_fails_on_a_broken_block(tmp_path):
    cfg = tmp_path / "gateway.yaml"
    cfg.write_text(json.dumps({"models": {"list": ["a/b", ""], "page_size": 6}}))
    c = subprocess.run(
        [sys.executable, str(HELPER), "--config", str(cfg), "--check"],
        capture_output=True, text=True,
    )
    assert c.returncode == 1
    assert "blank" in c.stdout


def test_cli_refuses_a_yaml_config_cleanly(tmp_path):
    cfg = tmp_path / "gateway.yaml"
    cfg.write_text("backends: []\n")
    w = subprocess.run(
        [sys.executable, str(HELPER), "--config", str(cfg), "--models", "a/b", "--write"],
        capture_output=True, text=True,
    )
    assert w.returncode == 1, "must fail, but with a message"
    assert "JSON" in (w.stdout + w.stderr)
    assert "Traceback" not in (w.stdout + w.stderr)


# --- "all agent systems": the menu is a no-op where the backend cannot take a model ----

def _gateway_with(backends, model_menu):
    """Gateway.__init__ only needs a transport that carries an offset."""
    return DAEMON.Gateway(transport=types.SimpleNamespace(offset=0),
                          backends=backends, model_menu=model_menu)


def test_gateway_warns_when_no_backend_can_take_a_model(capsys):
    """A shim backend (no model_args) makes the menu a silent no-op — say so at startup."""
    shim = types.SimpleNamespace(spec=types.SimpleNamespace(model_args=[]))
    _gateway_with({"titusclaude": shim}, ["a/b", "c/d"])
    err = capsys.readouterr().err
    assert "model_args" in err, f"expected a startup warning, got: {err!r}"
    assert "no-op" in err


def test_gateway_is_silent_when_a_backend_takes_a_model(capsys):
    pi = types.SimpleNamespace(spec=types.SimpleNamespace(model_args=["--model", "{model}"]))
    _gateway_with({"pi": pi}, ["a/b", "c/d"])
    assert capsys.readouterr().err == "", "no warning is due when the menu can actually apply"


def test_gateway_is_silent_without_a_menu(capsys):
    """No models: configured means the text form — nothing to warn about."""
    shim = types.SimpleNamespace(spec=types.SimpleNamespace(model_args=[]))
    _gateway_with({"titusclaude": shim}, [])
    assert capsys.readouterr().err == ""
