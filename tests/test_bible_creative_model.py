#!/usr/bin/env python3
"""CREATIVE_MODEL must have a REAL consumer, and that consumer must not break other hosts.

The doctor reported `Config (CREATIVE_MODEL) — defined but zero consumer scripts
reference it` (INFO). The check was right: the variable was documented in the model
contract and read by nothing. The fix is a consumer, not a louder comment — the daily
bible reading IS the fleet's creative-text path, and it hardcoded the very id the
variable describes.

Two properties are pinned here:
  1. The doctor's OWN consumer detector sees the new read (`get_model("CREATIVE_MODEL"`,
     the form the fleet's scan recognises) and still ignores the hardcoded id it
     replaced — so the assertion is meaningful rather than tautological.
  2. A per-host `.env` may carry a BARE id (the value on this host was
     `deepseek-v4-flash`) that the remote endpoint cannot resolve: `qualify_model()`
     must fall back to the served equivalent LOUDLY, never pass it through to fail
     upstream.

Run: python3 -m pytest tests/test_bible_creative_model.py -q
"""

import contextlib
import importlib.util
import io
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_DOCTOR_CONFIG = _REPO / "ops" / "scripts" / "manage" / "cortex_doctor" / "config.py"
_MODELS = _REPO / "ops" / "scripts" / "cortex_lib" / "models.py"
_BIBLE = _REPO / "ops" / "scripts" / "agent-daily-bible-reading.py"

_DEFAULT = "deepseek/deepseek-chat"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _doctor_config():
    if str(_DOCTOR_CONFIG.parent.parent) not in sys.path:
        sys.path.insert(0, str(_DOCTOR_CONFIG.parent.parent))
    return _load(_DOCTOR_CONFIG, "doctor_config_under_test")


def test_the_bible_reading_script_is_a_creative_model_consumer():
    c = _doctor_config()
    found = c.find_script_consumers()
    assert "agent-daily-bible-reading.py" in found["CREATIVE_MODEL"], found["CREATIVE_MODEL"]
    print("  the doctor's consumer scan sees the bible reading read CREATIVE_MODEL ✓")


def test_a_hardcoded_model_id_is_not_a_consumer_and_a_read_is(tmp_path):
    """Drive the detector BOTH ways: the form removed must not count, the form shipped
    must."""
    tree = tmp_path / "ops"
    (tree / "scripts").mkdir(parents=True)
    consumer = tree / "scripts" / "consumer.py"
    consumer.write_text('LLM_MODEL = "deepseek/deepseek-chat"\n')
    c = _doctor_config()
    found = c.find_script_consumers([tree])
    assert found["CREATIVE_MODEL"] == [], found["CREATIVE_MODEL"]

    consumer.write_text(f'LLM_MODEL = get_model("CREATIVE_MODEL", "{_DEFAULT}")\n')
    found = c.find_script_consumers([tree])
    assert found["CREATIVE_MODEL"] == ["consumer.py"], found["CREATIVE_MODEL"]
    print("  a hardcoded id is not a consumer; the new read is ✓")


def test_a_bare_id_falls_back_to_the_qualified_default_and_says_so():
    mod = _load(_MODELS, "models_under_test")
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        got = mod.qualify_model("deepseek-v4-flash", _DEFAULT, endpoint="https://openrouter.ai/api/v1")
    assert got == _DEFAULT, got
    assert "WARNING" in err.getvalue() and "provider-qualified" in err.getvalue(), err.getvalue()
    print("  a bare id falls back to the served equivalent, loudly ✓")


def test_a_qualified_id_passes_through_silently():
    mod = _load(_MODELS, "models_under_test2")
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        got = mod.qualify_model("vendor/model-x", _DEFAULT)
    assert got == "vendor/model-x", got
    assert err.getvalue() == "", err.getvalue()
    print("  a provider-qualified id passes through with no warning ✓")


def test_the_script_reads_the_contract_rather_than_hardcoding():
    src = _BIBLE.read_text()
    assert 'get_model("CREATIVE_MODEL"' in src, "the script must read the model contract"
    assert f'LLM_MODEL = "{_DEFAULT}"' not in src, "the hardcoded id is back"
    print("  the script reads CREATIVE_MODEL instead of hardcoding the id ✓")


if __name__ == "__main__":
    sys.exit(__import__("pytest").main([__file__, "-q"]))
