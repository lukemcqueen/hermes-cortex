"""The cortex venv must be repairable by ANY agent on ANY host.

The resolver fix only reaches a host that updates, and it can only pick a capable
interpreter if one exists — so a host whose cortex venv is empty stays broken until someone
with this repo's knowledge repairs it. These tests pin the remedy:

* the dependency set is DECLARED in the repo (not knowable only by grepping imports);
* the fixer installs only what is MISSING and decides by importing, not by exit codes;
* `--check` reports and changes nothing (the shape a doctor/deploy check runs);
* a broken or absent venv produces the exact command to fix it, never a traceback.

Run: python3 -m pytest tests/test_fix_cortex_venv.py -q
"""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import venv
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
FIXER = REPO / "ops" / "scripts" / "manage" / "fix-cortex-venv.py"
REQS = REPO / "ops" / "install" / "requirements.txt"


def _load():
    spec = importlib.util.spec_from_file_location("fix_cortex_venv", FIXER)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def fixer():
    return _load()


def _make_venv(path):
    venv.create(path, with_pip=False)
    return path / "bin" / "python3"


# --- the dependency truth lives in the repo ------------------------------------------

def test_the_requirements_file_is_the_declared_set():
    """A host must be able to learn what 'fixed' means without reading the source."""
    assert REQS.is_file(), "the declared dependency set is missing"
    body = REQS.read_text()
    for name in ("mcp", "PyYAML", "fastapi", "uvicorn", "psycopg", "pytest"):
        assert name in body, f"{name} is used by the repo but not declared"


def test_requirements_are_parsed_without_comments(fixer):
    reqs = fixer.parse_requirements(
        "# a comment\n\nmcp>=1.0\nPyYAML>=6.0   # trailing\npsycopg[binary]>=3.1\n"
    )
    assert reqs == ["mcp>=1.0", "PyYAML>=6.0", "psycopg[binary]>=3.1"]


# --- deciding by IMPORT, not by a package name ---------------------------------------

def test_a_distribution_name_maps_to_the_module_it_imports(fixer):
    """Installing 'PyYAML' and importing 'PyYAML' are different things."""
    assert fixer.module_for("PyYAML>=6.0") == "yaml"
    assert fixer.module_for("psycopg[binary]>=3.1") == "psycopg"
    assert fixer.module_for("mcp>=1.0") == "mcp"
    assert fixer.module_for("pytest>=7.0") == "pytest"


def test_missing_is_decided_by_import_not_by_metadata(fixer, tmp_path):
    """A venv with no site-packages must report every requirement as missing."""
    py = _make_venv(tmp_path / "empty")
    assert py.exists()
    state = fixer.venv_state(py, ["mcp>=1.0", "PyYAML>=6.0"])
    assert [name for name, ok in state.items() if not ok] == ["mcp>=1.0", "PyYAML>=6.0"]


def test_a_present_module_reports_present():
    """Control: the checker must not report everything missing."""
    fixer = _load()
    state = fixer.venv_state(Path(sys.executable), ["PyYAML>=6.0"])
    assert state.get("PyYAML>=6.0") is True, "this interpreter has yaml; the check must see it"


# --- check mode is a REPORT: it must change nothing ----------------------------------

def test_check_mode_reports_gaps_and_exits_3(tmp_path):
    py = _make_venv(tmp_path / "empty")
    r = subprocess.run(
        [sys.executable, str(FIXER), "--check", "--venv", str(py.parent.parent)],
        capture_output=True, text=True,
    )
    assert r.returncode == 3, f"gaps must be rc=3 (not a pass, not a crash): {r.stdout}{r.stderr}"
    assert "missing" in (r.stdout + r.stderr).lower()
    assert "fix-cortex-venv.py" in (r.stdout + r.stderr), \
        "the report must name the command that fixes it"


def test_check_mode_changes_nothing(tmp_path):
    """The gap that made this cycle necessary: a check that quietly installs."""
    root = tmp_path / "v"
    py = _make_venv(root)
    before = sorted(p.name for p in (root / "lib").glob("python*/site-packages"))
    subprocess.run([sys.executable, str(FIXER), "--check", "--venv", str(root)],
                   capture_output=True, text=True)
    after = sorted(p.name for p in (root / "lib").glob("python*/site-packages"))
    assert after == before, f"check mode touched the venv: {before} -> {after}"


def test_an_absent_venv_names_how_to_create_it(tmp_path):
    r = subprocess.run(
        [sys.executable, str(FIXER), "--check", "--venv", str(tmp_path / "nope")],
        capture_output=True, text=True,
    )
    assert r.returncode == 3
    out = r.stdout + r.stderr
    assert "absent" in out.lower(), f"the report must say the venv is missing: {out}"
    assert "python3 -m venv" in out, f"the report must show how to create it: {out}"
    assert "Traceback" not in out


# --- the machine-readable shape a doctor/deploy hook consumes ------------------------

def test_requirements_are_found_in_both_layouts(fixer, tmp_path):
    """The deployed layout is scripts/ + install/; the repo layout is ops/scripts/ + ops/install/.
    A fixed number of `..` serves one and breaks the other."""
    repo_like = tmp_path / "r" / "ops" / "install"
    repo_like.mkdir(parents=True)
    (repo_like / "requirements.txt").write_text("mcp\n")
    script = tmp_path / "r" / "ops" / "scripts" / "manage" / "fix-cortex-venv.py"
    script.parent.mkdir(parents=True)
    script.write_text("")
    assert fixer.find_requirements(script) == repo_like / "requirements.txt"

    dep_like = tmp_path / "d" / "install"
    dep_like.mkdir(parents=True)
    (dep_like / "requirements.txt").write_text("mcp\n")
    dscript = tmp_path / "d" / "scripts" / "fix-cortex-venv.py"
    dscript.parent.mkdir(parents=True)
    dscript.write_text("")
    assert fixer.find_requirements(dscript) == dep_like / "requirements.txt"


def test_the_json_report_has_the_fields_a_hook_needs(tmp_path):
    py = _make_venv(tmp_path / "empty")
    r = subprocess.run(
        [sys.executable, str(FIXER), "--check", "--json", "--venv", str(py.parent.parent)],
        capture_output=True, text=True,
    )
    assert r.returncode == 3
    data = json.loads(r.stdout.strip().split("\n")[-1])
    assert data["venv_ok"] is True
    assert set(data["missing"]) == {"mcp>=2.0", "PyYAML>=6.0", "fastapi>=0.100",
                                    "uvicorn>=0.23", "psycopg[binary]>=3.1", "pytest>=7.0"}
    assert any(a.endswith("fix-cortex-venv.py") for a in data["fix_argv"]), \
        f"the report must name the command that fixes it: {data['fix_argv']}"
    assert str(py.parent.parent) in data["fix_argv"], "the report must name the venv it measured"


# --- an IMPORTABLE module can still be UNUSABLE ---------------------------------------
#
# THE GAP THIS CLOSES (gisu, 2026-10-20): this checker decided by IMPORT, and an mcp SDK
# that imports perfectly well can still be too old for the call sites that use it — the
# fleet's MCP servers construct `Server(name, on_list_tools=..., on_call_tool=...)`, the
# 2.0 constructor API. On such a host `--check` printed
#     ok: <python> imports all 6 declared requirements
# while the governance CLI exited 3 on every write gate, and cortex-update.sh — which
# gates its install on exactly this check (line ~3235) — therefore silently left the venv
# alone. Importability is necessary and NOT sufficient, so a declared requirement may
# carry a CAPABILITY probe too.

def _stub_sdk(root: Path, accepts_constructor_handlers: bool) -> Path:
    """A stub `mcp` package: importable either way; the flag picks the API generation.
    Only `mcp.server.Server` is needed — the capability probe imports exactly that, and
    keeping the stub this small is the point: it proves the probe, nothing else."""
    (root / "mcp" / "server").mkdir(parents=True, exist_ok=True)
    (root / "mcp" / "__init__.py").write_text("")
    if accepts_constructor_handlers:
        body = ("class Server:\n"
                "    def __init__(self, name, *, on_list_tools=None,\n"
                "                 on_call_tool=None, **kw):\n"
                "        self.name = name\n")
    else:
        body = ("class Server:\n"          # the decorator-era signature: kwargs rejected
                "    def __init__(self, name):\n"
                "        self.name = name\n")
    (root / "mcp" / "server" / "__init__.py").write_text(body)
    return root


def _venv_pointing_at(tmp_path: Path, sdk_root: Path) -> Path:
    """A venv-shaped dir whose bin/python3 WRAPS the real interpreter with the stub on
    PYTHONPATH. The fixer strips PYTHONPATH from the target's environment ON PURPOSE (an
    inherited path must not be able to make a healthy venv look broken, or vice versa),
    so the stub is injected by the interpreter wrapper itself — which is what a real
    venv's site-packages supplies."""
    root = tmp_path / "stubvenv"
    (root / "bin").mkdir(parents=True)
    py = root / "bin" / "python3"
    py.write_text(f'#!/bin/sh\nPYTHONPATH="{sdk_root}" exec "{sys.executable}" "$@"\n')
    py.chmod(0o755)
    return root


def _run_check(venv_root: Path, requirements: Path):
    return subprocess.run(
        [sys.executable, str(FIXER), "--check", "--venv", str(venv_root),
         "--requirements", str(requirements)],
        capture_output=True, text=True,
    )


def _mcp_requirements(tmp_path: Path) -> Path:
    reqs = tmp_path / "requirements.txt"
    reqs.write_text("mcp>=2.0\n")
    return reqs


def test_check_flags_an_importable_but_incompatible_sdk(tmp_path):
    """A too-old-but-importable SDK must be reported as a GAP (rc=3), not as ok — this is
    the check cortex-update.sh gates its repair on."""
    sdk = _stub_sdk(tmp_path / "old-sdk", accepts_constructor_handlers=False)
    venv_root = _venv_pointing_at(tmp_path, sdk)

    r = _run_check(venv_root, _mcp_requirements(tmp_path))
    out = r.stdout + r.stderr

    assert r.returncode == 3, (
        f"an incompatible SDK must be a gap (rc=3), got rc={r.returncode}:\n{out}")
    assert "incompatible" in out.lower(), (
        f"the report must name the real cause, not 'missing':\n{out}")
    assert "mcp>=2.0" in out, f"the report must name the requirement:\n{out}"
    assert "fix-cortex-venv.py" in out, f"the report must name the fix command:\n{out}"
    assert "Traceback" not in out, f"a gap is not a crash:\n{out}"


def test_check_passes_when_the_sdk_accepts_the_constructor_handlers(tmp_path):
    """Control: the capability probe must NOT flag a usable SDK, or the check becomes a
    permanent false repairee and every deploy reinstalls the venv."""
    sdk = _stub_sdk(tmp_path / "new-sdk", accepts_constructor_handlers=True)
    venv_root = _venv_pointing_at(tmp_path, sdk)

    r = _run_check(venv_root, _mcp_requirements(tmp_path))
    out = r.stdout + r.stderr

    assert r.returncode == 0, (
        f"a usable SDK must pass the check, got rc={r.returncode}:\n{out}")
    assert "incompatible" not in out.lower(), (
        f"a usable SDK was reported incompatible:\n{out}")
