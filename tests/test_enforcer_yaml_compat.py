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


# ── the case the docstring above assumed away: NO YAML LIBRARY AT ALL ─────────
#
# MEASURED 2026-10-28 on a live host: the agent runtime that runs the plugin
# (`~/.hermes/tools/python-3.14.7*/bin/python3`, the interpreter the gateway
# itself is launched with) shipped NEITHER PyYAML NOR ruamel.yaml. `_safe_load_yaml`
# therefore raised ModuleNotFoundError('ruamel'), `_bootstrap_cron_skills()`
# returned False, no skills marker was written for a cron session, and gate 1
# blocked EVERY write in every cron/bg session that had no skill tool — the
# dream write-back silently never happened while the job reported success.
# A host whose runtime DOES ship PyYAML (measured on a peer host, same tool
# version) is unaffected, so this is a per-host runtime property, not a
# per-job one — and the fix must not depend on the runtime's site-packages.

def _block_all_yaml_libraries(monkeypatch):
    """Make every `import yaml` / `from ruamel.yaml import ...` raise ImportError."""
    monkeypatch.setitem(sys.modules, "yaml", None)
    monkeypatch.setitem(sys.modules, "ruamel", None)
    monkeypatch.setitem(sys.modules, "ruamel.yaml", None)


def test_no_yaml_library_at_all_still_yields_the_always_section(enforcer, monkeypatch):
    _block_all_yaml_libraries(monkeypatch)

    manifest = enforcer._safe_load_yaml(io.StringIO(DOC))

    assert _names(manifest) == ["task-start", "agent-flow"]


def test_stdlib_reader_never_invents_an_always_section(enforcer, monkeypatch):
    """No `always:` section ⇒ nothing to report (the caller still fails closed)."""
    _block_all_yaml_libraries(monkeypatch)

    manifest = enforcer._safe_load_yaml(io.StringIO("blocking:\n  - always-task-start\n"))

    assert manifest.get("always", []) == []


def test_stdlib_reader_matches_pyyaml_on_the_real_manifest(enforcer, monkeypatch):
    """The dependency-free path must agree with a real YAML parse of the manifest
    every host actually reads — not merely avoid crashing."""
    pytest.importorskip("yaml")
    manifest_path = Path.home() / ".hermes-cortex" / "skills.yaml"
    if not manifest_path.exists():
        pytest.skip(f"no deployed manifest at {manifest_path}")

    with manifest_path.open() as handle:
        with_pyyaml = enforcer._safe_load_yaml(handle)
    _block_all_yaml_libraries(monkeypatch)
    with manifest_path.open() as handle:
        without_any_library = enforcer._safe_load_yaml(handle)

    assert _names(without_any_library) == _names(with_pyyaml)
    assert set(enforcer._REQUIRED_SKILLS).issubset(set(_names(without_any_library)))


def test_cron_bootstrap_satisfies_gate_1_without_any_yaml_library(enforcer, monkeypatch, tmp_path):
    """The whole point, end to end: a cron session on a YAML-less runtime must
    still get its skills marker when the always-skills exist on disk, so gate 1
    passes for a job whose toolset has no skill tool."""
    real_manifest = Path.home() / ".hermes-cortex" / "skills.yaml"
    if not real_manifest.exists():
        pytest.skip(f"no deployed manifest at {real_manifest}")

    home = tmp_path / "home"
    (home / ".hermes-cortex").mkdir(parents=True)
    (home / ".hermes-cortex" / "skills.yaml").write_text(real_manifest.read_text())
    for name in enforcer._REQUIRED_SKILLS:
        d = home / ".hermes" / "skills" / "devops" / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"# {name}\n")

    monkeypatch.setenv("HOME", str(home))
    # GOVERNANCE_STATE_DIR is a module constant, not HOME-derived at call time —
    # repoint it or the marker lands in the LIVE state dir (the module documents
    # this seam on _skills_marker_dir).
    monkeypatch.setattr(enforcer, "GOVERNANCE_STATE_DIR",
                        home / ".hermes-cortex" / "state")
    _block_all_yaml_libraries(monkeypatch)
    session_id = "cron_probe000000_bootstrap"

    assert enforcer._check_skills_loaded_marker(session_id) is False
    assert enforcer._bootstrap_cron_skills(session_id) is True
    assert enforcer._check_skills_loaded_marker(session_id) is True


def test_cron_bootstrap_still_fails_closed_when_a_skill_is_missing_on_disk(
        enforcer, monkeypatch, tmp_path):
    """The fallback must not widen the gate: a missing SKILL.md still blocks."""
    real_manifest = Path.home() / ".hermes-cortex" / "skills.yaml"
    if not real_manifest.exists():
        pytest.skip(f"no deployed manifest at {real_manifest}")

    home = tmp_path / "home"
    (home / ".hermes-cortex").mkdir(parents=True)
    (home / ".hermes-cortex" / "skills.yaml").write_text(real_manifest.read_text())
    for name in sorted(enforcer._REQUIRED_SKILLS)[:-1]:  # one skill absent
        d = home / ".hermes" / "skills" / "devops" / name
        d.mkdir(parents=True)
        (d / "SKILL.md").write_text(f"# {name}\n")

    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(enforcer, "GOVERNANCE_STATE_DIR",
                        home / ".hermes-cortex" / "state")
    _block_all_yaml_libraries(monkeypatch)

    assert enforcer._bootstrap_cron_skills("cron_probe000000_missing") is False
