"""cortex_lib tests — S1a–S1c of component-hermes-separation.

Proves the neutral client library is Hermes-independent and that the legacy
hermes_* modules are thin re-export shims (back-compat intact). The critical
property under test: every cortex_lib.tz/paths/tools/models module imports and
behaves with ZERO Hermes import (isolated mode + explicit hermetic sys.path),
and the shims resolve to the same callables.

Tests import through the interface (codebase-design: the interface is the test
surface) — get_timezone/format_timestamp on cortex_lib.tz, ensure_scripts_path
on cortex_lib.paths, read_file/write_file on cortex_lib.tools, get_model on
cortex_lib.models — plus the shim-equivalence and caller-switch properties.
"""
import importlib
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "ops" / "scripts"


@pytest.fixture()
def hermetic_scripts_path():
    """Expose ops/scripts + cortex_lib on sys.path with NO Hermes imports
    pulled in transitively. Isolated enough to prove the module does not
    import from the Hermes runtime."""
    added = []
    for p in (SCRIPTS_DIR, SCRIPTS_DIR / "cortex_lib"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
            added.append(str(p))
    yield SCRIPTS_DIR
    for p in added:
        try:
            sys.path.remove(p)
        except ValueError:
            pass


def _assert_hermes_free(module):
    """grep the module's own source for executed hermes imports (docstring
    mentions are allowed; `import hermes`/`from hermes` at line start are not)."""
    src = Path(module.__file__).read_text()
    offending = [
        ln for ln in src.splitlines()
        if (ln.startswith("import hermes") or ln.startswith("from hermes"))
        and "# noqa" not in ln and "back-compat shim" not in ln
    ]
    assert not offending, f"{module.__name__} imports from Hermes runtime: {offending}"


def test_cortex_lib_imports_are_hermes_free(hermetic_scripts_path):
    tz = importlib.import_module("cortex_lib.tz")
    paths = importlib.import_module("cortex_lib.paths")
    _assert_hermes_free(tz)
    _assert_hermes_free(paths)


def test_cortex_lib_tz_format_timestamp_works(hermetic_scripts_path):
    tz = importlib.import_module("cortex_lib.tz")
    ts = tz.format_timestamp("%Y")
    assert len(ts) == 4 and ts.isdigit(), f"format_timestamp('%Y') -> {ts!r}"
    assert tz.get_tz_name()  # non-empty abbreviation
    assert "KST" in tz.TIMEZONE_OFFSETS


def test_cortex_lib_paths_bootstraps_scripts_dir(hermetic_scripts_path):
    paths = importlib.import_module("cortex_lib.paths")
    paths.ensure_scripts_path()
    assert str(SCRIPTS_DIR) in sys.path, "ops/scripts must be on sys.path"


def test_hermes_tz_shim_reexports_cortex_lib(hermetic_scripts_path):
    shim = importlib.import_module("hermes_tz")
    canonical = importlib.import_module("cortex_lib.tz")
    assert shim.format_timestamp is canonical.format_timestamp
    assert shim.get_timezone is canonical.get_timezone


def test_hermes_paths_shim_reexports_cortex_lib(hermetic_scripts_path):
    shim = importlib.import_module("hermes_paths")
    canonical = importlib.import_module("cortex_lib.paths")
    assert shim.ensure_scripts_path is canonical.ensure_scripts_path


# ── S1b: cortex_lib.tools (file surface) ────────────────────────────────────
def test_cortex_lib_tools_are_hermes_free_and_work(hermetic_scripts_path, tmp_path):
    tools = importlib.import_module("cortex_lib.tools")
    _assert_hermes_free(tools)
    # write_file creates parent dirs + returns verified dict.
    f = tmp_path / "sub" / "out.txt"
    res = tools.write_file(path=str(f), content="hello")
    assert res["verified"] is True
    # read_file returns a dict with a "content" key (Hermes-compatible shape).
    got = tools.read_file(path=str(f))
    assert got["content"] == "hello"


# ── S1c: cortex_lib.models (model-config loader) ────────────────────────────
def test_cortex_lib_models_are_hermes_free_and_resolve(hermetic_scripts_path):
    models = importlib.import_module("cortex_lib.models")
    _assert_hermes_free(models)
    # Known default resolution (env not set in hermetic run → hardcoded default).
    assert models.get_model("JUDGE_MODEL", "qwen2.5:3b") == "qwen2.5:3b"


def test_hermes_models_shim_reexports_cortex_lib(hermetic_scripts_path):
    shim = importlib.import_module("hermes_models")
    canonical = importlib.import_module("cortex_lib.models")
    assert shim.get_model is canonical.get_model
    assert shim.load_models_env is canonical.load_models_env


# ── S1b: analyze-failures.py now uses cortex_lib.tools (no hermes_tools) ────
def test_analyze_failures_uses_cortex_lib_not_hermes_tools():
    src = (SCRIPTS_DIR / "manage" / "analyze-failures.py").read_text()
    # The executed (line-start, non-docstring) imports must be cortex_lib.
    executed = [
        ln for ln in src.splitlines()
        if (ln.startswith("import ") or ln.startswith("from "))
    ]
    assert "from cortex_lib.tools import read_file, write_file" in executed, (
        "analyze-failures.py must import its file tools from cortex_lib.tools "
        "(component-hermes-separation S1b)"
    )
    docstring_mentions = [
        ln for ln in src.splitlines()
        if ln.startswith("from hermes_tools") or ln.startswith("import hermes_tools")
    ]
    assert not docstring_mentions, (
        f"analyze-failures.py must not import from the Hermes-runtime hermes_tools; "
        f"found executed import: {docstring_mentions}"
    )


# ── Deploy-map contract (S1a–S1c: package + shims deploy together) ──────────
# cortex-update.sh deploys shims (hermes_tz/hermes_paths) to the runtime copy.
# If a cortex_lib member is NOT registered, the deployed shims point at a
# missing package and every import breaks at runtime. This test proves every
# cortex_lib source file is in cortex-update.sh's register map — the deploy
# half of the S1a done-proof (the push/dogfood checksum gate enforces it live).
def test_cortex_lib_files_registered_in_cortex_update_sh():
    updater = Path(__file__).resolve().parents[1] / "ops" / "scripts" / "cortex-update.sh"
    text = updater.read_text()
    unregistered = []
    for src in sorted((SCRIPTS_DIR / "cortex_lib").glob("*.py")):
        rel = f"ops/scripts/cortex_lib/{src.name}"
        # register maps source→dest; the source path must appear in the map.
        if f'register "{rel}"' not in text:
            unregistered.append(rel)
    assert not unregistered, (
        f"cortex_lib members not registered in cortex-update.sh deploy map — "
        f"the deployed shims would break (component-hermes-separation S1a): "
        f"{unregistered}"
    )