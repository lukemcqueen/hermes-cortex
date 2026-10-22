"""Tests for the doctor's interpreter resolution (ops/scripts/manage/cortex-doctor.py).

Why this exists: the doctor is documented as `python3 cortex-doctor.py`, and on a
fleet host `python3` is whatever the agent's session has on PATH. Measured
2026-10-22 on esther, that is the Hermes runtime venv, which cannot import yaml —
so every yaml-dependent check ran weaker than it reported and nothing said so. The
wrapper now re-execs once under a capable interpreter.

The DECISION is a pure function with injected probes, so both directions are
pinned here without needing a second python on the box; the live re-exec is
evidenced separately (docs/evidence/doctor-interpreter-2026-10-22.txt).

Run: bash tests/run-tests.sh tests/test_doctor_interpreter.py -q
"""

import importlib.util
import sys
from pathlib import Path

import pytest

WRAPPER = Path(__file__).resolve().parents[1] / "ops" / "scripts" / "manage" / "cortex-doctor.py"


@pytest.fixture(scope="module")
def doctor():
    """Load the wrapper as a module. It must be INERT on import (tested below)."""
    spec = importlib.util.spec_from_file_location("cortex_doctor_wrapper", WRAPPER)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_module_import_is_inert(doctor):
    """Importing the wrapper must not import the package or re-exec.

    The heavy `from cortex_doctor.cli import main` sits inside the __main__ guard
    precisely so this holds: a module-level import would pull the whole package in
    under whatever interpreter did the importing — the very thing being fixed —
    and would make this file untestable.
    """
    assert "cortex_doctor.cli" not in sys.modules
    assert doctor.__name__ == "cortex_doctor_wrapper"


def test_can_import_here_both_ways(doctor):
    assert doctor._can_import_here("yaml") is True
    assert doctor._can_import_here("definitely_not_a_module_xyz") is False
    assert doctor._can_import_here("no.such.dotted.module") is False


def test_choose_stays_put_when_the_current_interpreter_is_capable(doctor):
    """The common case on a repaired host: no re-exec, no probe, no surprise."""
    probed = []

    def probe(p):
        probed.append(p)
        return True

    assert doctor.choose_interpreter(True, ["/x/python3"], probe) is None
    assert probed == [], "a capable interpreter must not even probe candidates"


def test_choose_returns_the_first_capable_candidate(doctor):
    seen = []

    def probe(p):
        seen.append(p)
        return p == "/second/python3"

    assert doctor.choose_interpreter(False, ["/first/python3", "/second/python3", "/third"],
                                     probe) == "/second/python3"
    assert seen == ["/first/python3", "/second/python3"], "must stop at the first hit"


def test_choose_returns_none_when_nothing_is_capable(doctor):
    """No capable interpreter is a real outcome: stay put and warn, never crash."""
    assert doctor.choose_interpreter(False, ["/a", "/b"], lambda p: False) is None
    assert doctor.choose_interpreter(False, [], lambda p: True) is None


def test_reexec_is_a_noop_when_the_flag_is_already_set(doctor, monkeypatch):
    """The flag is the loop guard: a re-exec must happen at most once."""
    monkeypatch.setenv(doctor.REEXEC_FLAG, "1")
    monkeypatch.setattr(doctor.os, "execv", lambda *a: pytest.fail("must not re-exec"))

    assert doctor.reexec_if_degraded() is None


def test_reexec_uses_the_declared_interpreter_once(doctor, monkeypatch):
    calls = []
    monkeypatch.delenv(doctor.REEXEC_FLAG, raising=False)
    monkeypatch.setattr(doctor, "_can_import_here", lambda m: False)
    monkeypatch.setattr(doctor, "candidate_interpreters", lambda: ["/declared/python3"])
    monkeypatch.setattr(doctor, "_child_imports_all", lambda p, mods=None: True)
    monkeypatch.setattr(doctor.os, "execv", lambda path, argv: calls.append((path, argv)))

    doctor.reexec_if_degraded()

    assert len(calls) == 1, "exactly one re-exec"
    assert calls[0][0] == "/declared/python3"
    assert calls[0][1][0] == "/declared/python3"
    assert calls[0][1][1].endswith("cortex-doctor.py")
    assert doctor.os.environ[doctor.REEXEC_FLAG] == "1", "the guard must be set BEFORE execv"


def test_candidates_prefer_the_declaration_and_skip_the_current_interpreter(doctor, monkeypatch, tmp_path):
    declared = tmp_path / "declared-python"
    declared.write_text("#!/bin/sh\n")
    fleet = tmp_path / "fleet-python"
    fleet.write_text("#!/bin/sh\n")

    monkeypatch.setenv("CORTEX_PYTHON", str(declared))
    monkeypatch.setattr(doctor.os.path, "expanduser", lambda p: str(tmp_path))
    monkeypatch.setattr(doctor, "os", doctor.os)  # keep os patched consistently
    # fleet venv path is <home>/.hermes-cortex/venv/bin/python3
    venv_bin = tmp_path / ".hermes-cortex" / "venv" / "bin"
    venv_bin.mkdir(parents=True)
    (venv_bin / "python3").write_text("#!/bin/sh\n")

    cands = doctor.candidate_interpreters()
    assert cands[0] == str(declared), "CORTEX_PYTHON is the host's declaration and wins"
    assert cands[1] == str(venv_bin / "python3")
    assert len(cands) == 2


def test_candidates_exclude_an_interpreter_that_is_the_current_one(doctor, monkeypatch, tmp_path):
    """Re-execing into the same interpreter would be a no-op dressed as a fix."""
    me = tmp_path / "python3"
    me.write_text("#!/bin/sh\n")
    monkeypatch.setenv("CORTEX_PYTHON", str(me))
    monkeypatch.setattr(doctor.sys, "executable", str(me))
    # Redirect ~ too, so the fleet-venv fallback resolves inside the fixture
    # instead of picking up this host's real venv.
    monkeypatch.setattr(doctor.os.path, "expanduser", lambda p: str(tmp_path))
    assert doctor.candidate_interpreters() == []
