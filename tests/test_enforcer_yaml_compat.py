"""Contract tests for the governance-enforcer's runtime-tolerant YAML loading.

Agent runtimes differ in which YAML library they ship: the git-install venv has
PyYAML (`import yaml`), while the pm-managed environments ship only `ruamel.yaml`.
A bare `import yaml` inside the on_session_start hook therefore crashed the entire
hook on those hosts and the cron skills bootstrap died silently.

`_safe_load_yaml()` resolves the loader at call time; both paths are pinned here so
a future edit cannot silently drop the fallback (or change what the manifest parse
returns).
"""

from __future__ import annotations

import importlib.util
import io
import sys
from pathlib import Path

import pytest

PLUGIN = (
    Path(__file__).resolve().parent.parent
    / "plugins"
    / "governance-enforcer"
    / "__init__.py"
)

DOC = """\
always:
  - name: task-start
  - name: agent-flow
blocking:
  - always-task-start
"""


@pytest.fixture(scope="module")
def enforcer():
    spec = importlib.util.spec_from_file_location("enforcer_yaml_under_test", PLUGIN)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _names(manifest):
    return [entry["name"] for entry in manifest["always"]]


def test_parses_manifest_with_pyyaml_when_available(enforcer):
    manifest = enforcer._safe_load_yaml(io.StringIO(DOC))

    assert _names(manifest) == ["task-start", "agent-flow"]
    assert manifest["blocking"] == ["always-task-start"]


def test_falls_back_to_ruamel_when_pyyaml_is_missing(enforcer, monkeypatch):
    """The pm-managed runtime: `import yaml` unavailable, ruamel.yaml present."""
    pytest.importorskip("ruamel.yaml")
    monkeypatch.setitem(sys.modules, "yaml", None)  # makes `import yaml` raise ImportError

    manifest = enforcer._safe_load_yaml(io.StringIO(DOC))

    assert _names(manifest) == ["task-start", "agent-flow"]


def test_ruamel_fallback_matches_pyyaml_output(enforcer, monkeypatch):
    """The fallback must be SEMANTICALLY identical, not merely non-crashing."""
    pytest.importorskip("yaml")
    pytest.importorskip("ruamel.yaml")
    doc = DOC + "values: [1, true, 0.5, 'text', null]\nnested:\n  inner: {a: 1, b: 'two'}\n"

    with_pyyaml = enforcer._safe_load_yaml(io.StringIO(doc))
    monkeypatch.setitem(sys.modules, "yaml", None)
    with_ruamel = enforcer._safe_load_yaml(io.StringIO(doc))

    assert with_ruamel == with_pyyaml


def test_real_manifest_parses_identically_with_both_loaders(enforcer, monkeypatch):
    """The deployed manifest every host actually reads, both loaders, equal result."""
    pytest.importorskip("yaml")
    pytest.importorskip("ruamel.yaml")
    manifest_path = Path.home() / ".hermes-cortex" / "skills.yaml"
    if not manifest_path.exists():
        pytest.skip(f"no deployed manifest at {manifest_path}")

    with manifest_path.open() as handle:
        with_pyyaml = enforcer._safe_load_yaml(handle)
    monkeypatch.setitem(sys.modules, "yaml", None)
    with manifest_path.open() as handle:
        with_ruamel = enforcer._safe_load_yaml(handle)

    assert with_ruamel == with_pyyaml
    assert _names(with_ruamel)  # the always section must survive either loader


def test_parse_failure_propagates_so_the_caller_can_log_it(enforcer):
    """A malformed manifest must raise a PARSE error (the caller warns and returns
    False) — never be swallowed into an empty dict that reads as 'no required
    skills', and never fail because the loader itself is missing."""
    with pytest.raises(Exception) as excinfo:
        enforcer._safe_load_yaml(io.StringIO("always: [unclosed\n"))

    assert not isinstance(excinfo.value, (AttributeError, ImportError, NameError))
