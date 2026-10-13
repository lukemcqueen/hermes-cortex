#!/usr/bin/env python3
"""A caller's environment must not decide whether the fleet venv looks healthy.

Measured on esther 2026-10-13: the agent runtime exports

    PYTHONPATH=$HOME/.hermes/installs/<id>/environments/<id>/venv/lib/python3.14/site-packages

which lands AHEAD of the fleet venv's own site-packages. `import mcp` inside
~/.hermes-cortex/venv then loaded a python3.14 copy under a 3.12 interpreter and died
on ModuleNotFoundError: No module named 'pydantic_core._pydantic_core'. The venv was
healthy; the PROBE was contaminated. The fixer reported "still cannot import" about a
venv that imports fine, and the deploy inherited the same false failure.

These cases pin the fix: probe and install run with PYTHONPATH/PYTHONHOME removed, and
the tool SAYS what it ignored instead of letting the venv take the blame.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIXER = REPO / "ops" / "scripts" / "manage" / "fix-cortex-venv.py"
VENV = Path.home() / ".hermes-cortex" / "venv"


def _fixer_module():
    spec = importlib.util.spec_from_file_location("fixer_under_test", FIXER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["fixer_under_test"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_target_env_drops_the_inherited_python_paths(monkeypatch):
    mod = _fixer_module()
    monkeypatch.setenv("PYTHONPATH", "/tmp/somewhere/else")
    monkeypatch.setenv("PYTHONHOME", "/tmp/other")
    mod._STRIPPED_ENV.clear()

    env = mod.target_env()

    assert "PYTHONPATH" not in env and "PYTHONHOME" not in env, "the probe env must be clean"
    assert sorted(mod._STRIPPED_ENV) == ["PYTHONHOME", "PYTHONPATH"], (
        "and it must RECORD what it ignored, so the tooling can say so")


def test_a_shadowing_pythonpath_cannot_make_the_venv_look_broken():
    """The real case: a bogus PYTHONPATH holding a package named mcp that RAISES. If the
    probe honoured it, the venv would read as missing mcp; the fix is that it cannot."""
    if not (VENV / "bin" / "python3").exists():
        print("  (skipped: no fleet venv on this host)")
        return
    with tempfile.TemporaryDirectory() as td:
        poison = Path(td) / "mcp"
        poison.mkdir()
        (poison / "__init__.py").write_text(
            "raise ImportError('pydantic_core._pydantic_core (ABI mismatch)')")
        env = dict(os.environ)
        env["PYTHONPATH"] = td

        proc = subprocess.run([str(VENV / "bin" / "python3"), str(FIXER), "--check"],
                              capture_output=True, text=True, timeout=300, env=env)

    assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)
    assert "imports all" in proc.stdout, proc.stdout
    assert "ignored inherited PYTHONPATH" in proc.stdout, (
        "the tool must SAY it ignored an inherited path rather than blame the venv: "
        + proc.stdout)


def test_no_capability_probe_inherits_the_callers_environment():
    """Class sweep: a `python -c 'import <module>'` that DECIDES something must not inherit
    PYTHONPATH/PYTHONHOME. This defect reached five call sites in one day (the resolver, the
    venv fixer, the deploy's fallback probe, the manifest generator, the installer), and each
    one silently judged the wrong packages.

    Version probes are excluded (an inherited path cannot change what version an interpreter
    reports), and so are STDLIB imports (`json`, `ipaddress`): the hazard is a foreign
    site-packages shadowing the target's own THIRD-PARTY packages, which is where a real
    install lives. Informational probes that print a status line and decide nothing are
    allowlisted by path with the reason.
    """
    import re
    import sys

    stdlib = set(getattr(sys, "stdlib_module_names", ()))
    decisions = re.compile(r"""-c\s+(['"])\s*import\s+(?!sys\b)([A-Za-z_][A-Za-z0-9_]*)""")
    # Prints a tick, decides nothing: no branch depends on its exit status.
    informational = set()

    offenders = []
    for path in sorted(REPO.rglob("*.sh")):
        rel = str(path.relative_to(REPO))
        if rel.startswith(("docs/", ".git/")) or rel in informational:
            continue
        for n, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue                     # a probe named in a comment decides nothing
            m = decisions.search(line)
            if not m or "env -u PYTHONPATH" in line:
                continue
            if m.group(2) in stdlib:
                continue
            offenders.append(f"{rel}:{n}: {line.strip()[:120]}")

    assert not offenders, (
        "these probes decide from a contaminated environment (a foreign site-packages can "
        "shadow the target's own — probe with `env -u PYTHONPATH -u PYTHONHOME`):\n"
        + "\n".join(offenders))


def test_the_fixer_probe_uses_the_clean_environment():
    src = FIXER.read_text()
    install_call = src[src.index("install = subprocess.run("):]
    install_call = install_call[:install_call.index("\n\n")]
    assert "env=target_env()" in install_call, (
        "installing with a contaminated env can resolve the wrong site-packages too")


def test_a_failed_import_is_diagnosed_instead_of_just_announced():
    """'still cannot import' names no cause. The diagnosis must name the exception."""
    mod = _fixer_module()
    lines = mod._import_diagnosis(VENV / "bin" / "python3" if VENV.exists() else Path(sys.executable),
                                  ["definitely-not-a-real-distribution>=1"])
    joined = " ".join(lines)
    assert "ModuleNotFoundError" in joined or "failed" in joined, joined
