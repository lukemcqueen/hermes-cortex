#!/usr/bin/env python3
"""The loop-gov regression harness must resolve pytest through the COMMITTED resolver.

WHY THIS FILE EXISTS (adversarial finding ADV-13116-1, 2026-10-18): the harness resolved pytest
from a hardcoded $HOME/.hermes/tools/pytest-venv path that NOTHING IN THIS REPO CREATES. Such a
path works on exactly the one host where somebody built it by hand and degrades silently
everywhere else — every pytest-style file then reports NOT RUN, which reads as a clean run to
anyone who reads only the summary line.

The fix is not "install pytest on this host". It is to resolve the interpreter by CAPABILITY
through the resolver every other deployed script already uses
(`ops/scripts/lib/python-with-module.sh`), and to name the repair that IS committed when nothing
can import pytest (`ops/scripts/manage/fix-cortex-venv.py`, which installs the declared set in
`ops/install/requirements.txt` — pytest is declared there). Those two facts, plus the third
outcome being visible in the summary, are what this file pins.

Run: python3 tests/test_run_loop_gov_regression_harness.py

The same file re-runs the discrimination from git history — point it at ANY revision of the
harness and it must fail there:

    git show <pre-fix-rev>:tests/run_loop_gov_regression.py > /tmp/harness.pre-fix.py
    HARNESS_UNDER_TEST=/tmp/harness.pre-fix.py python3 tests/test_run_loop_gov_regression_harness.py   # rc=1
    python3 tests/test_run_loop_gov_regression_harness.py                                              # rc=0
"""
import importlib.util
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HARNESS = Path(os.environ.get("HARNESS_UNDER_TEST") or (REPO / "tests" / "run_loop_gov_regression.py"))
RESOLVER = REPO / "ops" / "scripts" / "lib" / "python-with-module.sh"
VENV_FIX = REPO / "ops" / "scripts" / "manage" / "fix-cortex-venv.py"
REQUIREMENTS = REPO / "ops" / "install" / "requirements.txt"


def _harness():
    """Load the harness as a module. Safe to import: its only module-level effect is resolving the
    pytest interpreter, and `main()` sits behind `if __name__ == "__main__"`."""
    spec = importlib.util.spec_from_file_location("loop_gov_harness_under_test", HARNESS)
    assert spec is not None and spec.loader is not None, f"cannot load {HARNESS}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _find_pytest_under(env: dict):
    """Call the SHIPPED resolver-invoking path with a controlled environment, in a subprocess, so a
    constructed failure is not undone by this process's own search path."""
    code = (
        "import importlib.util, json, os, sys\n"
        "spec = importlib.util.spec_from_file_location('h', sys.argv[1])\n"
        "m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
        "os.environ.pop('PYTEST', None); os.environ['PYTEST'] = sys.argv[2]\n"
        "print(json.dumps(m._find_pytest()))\n"
    )
    r = subprocess.run([sys.executable, "-c", code, str(HARNESS), env["PYTEST"]],
                       capture_output=True, text=True, env=dict(os.environ, **env))
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    import json
    return json.loads(r.stdout.strip().splitlines()[-1])


def test_the_repair_the_harness_names_is_committed_and_declares_pytest():
    """A hint that names a repair nobody can run is the same defect one level up: the reader is
    told to fix it and given a dead end."""
    assert RESOLVER.is_file(), f"resolver missing: {RESOLVER}"
    assert VENV_FIX.is_file(), f"repair script missing: {VENV_FIX}"
    declared = [ln.strip() for ln in REQUIREMENTS.read_text().splitlines()
                if ln.strip() and not ln.strip().startswith("#")]
    assert any(re.match(r"^pytest[<>=!~]", d) for d in declared), \
        f"pytest must be DECLARED, or a repair has nothing to install: {declared}"
    print(f"  repair is committed: {VENV_FIX.name} + declared {[d for d in declared if d.startswith('pytest')]}")


def test_the_harness_names_no_interpreter_path_this_repo_does_not_create():
    """The ADV-13116-1 defect itself. `~/.hermes/tools/pytest-venv` is created by nothing in this
    repo — no installer, no requirements file, no setup step — so resolving it makes the harness
    correct on one host and quietly blind on every other.

    The probe matches the CONSTRUCT, not a bare literal: a comment that NAMES the removed path (to
    record why it went) is the explanation, not the defect."""
    src = HARNESS.read_text()
    code_lines = [ln for ln in src.splitlines() if not ln.lstrip().startswith("#")]
    offenders = [ln for ln in code_lines if "pytest-venv" in ln]
    assert not offenders, \
        f"the harness must not resolve a venv path nothing creates (ADV-13116-1): {offenders}"
    assert "python-with-module.sh" in src, "pytest must be resolved through the committed resolver"
    assert "ensure-pytest.sh" in src, "the no-pytest case must name the committed create step"
    # CONTROL — the probe must still FIRE on the construct it forbids, or "no offenders" means
    # nothing. Same predicate, a fabricated source carrying the removed resolution.
    control = '        cand = Path.home() / ".hermes" / "tools" / "pytest-venv" / "bin" / "python"\n'
    control_offenders = [ln for ln in control.splitlines()
                         if not ln.lstrip().startswith("#") and "pytest-venv" in ln]
    assert control_offenders, "the probe no longer detects the construct it exists to forbid"
    print("  no venv path in code; resolver + repair are named ✓ (probe fires on the old line)")


def test_a_resolved_interpreter_is_a_python_that_can_actually_run_pytest():
    """`<interpreter> -m pytest` is the command shape, so the resolved path must be a PYTHON — hand
    back the `pytest` console script and the command silently becomes `pytest -m pytest`, which
    collects nothing and is then reported as a test defect."""
    py = _harness()._find_pytest()
    if py is None:
        print("  (no interpreter here can import pytest — NOT RUN is the correct verdict; skipping)")
        return
    assert Path(py).is_file(), py
    assert Path(py).name.startswith("python"), f"must resolve a python, not a console script: {py}"
    r = subprocess.run([py, "-m", "pytest", "--version"], capture_output=True, text=True)
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    print(f"  resolved {py} -> {r.stdout.strip()}")


def test_a_missing_pytest_is_could_not_verify_and_says_so():
    """Constructed, never waited for: an override pointing at a path that does not exist must
    resolve to NOTHING (the harness then reports NOT RUN) — never be handed back as a usable
    interpreter, which would surface the shell's own error as the test's result."""
    got = _find_pytest_under({"PYTEST": "/nonexistent/does-not-exist/python3"})
    assert got is None, f"a non-existent override must resolve to None, got {got!r}"
    mod = _harness()
    hint = getattr(mod, "NO_PYTEST_HINT", "")
    assert "ensure-pytest.sh" in hint, f"the NOT RUN message must name the create step: {hint!r}"
    assert "requirements.txt" in hint, f"the hint must name what gets installed: {hint!r}"
    print("  absent pytest -> None, and the hint names the committed create step ✓")


def test_the_three_outcomes_are_distinct_in_the_summary():
    """PASS, FAIL and NOT RUN must be readable apart in the artifact. A summary that prints only
    `RESULT: ALL PASS` while three files ran NOTHING is how five files came to be called
    "pre-existing failures" on a host where four of them never executed."""
    mod = _harness()
    block = mod._result_block([], ["tests/x.py: pytest collected no tests (rc=5)"])
    assert block[0] == "RESULT: ALL PASS", block
    assert any("NOT RUN" in ln for ln in block), f"NOT RUN must appear in the summary: {block}"
    assert any("tests/x.py" in ln for ln in block), f"and must name the file: {block}"
    fail_block = mod._result_block(["tests/y.py: rc=1"], [])
    assert "FAILURES" in fail_block[0], fail_block
    block_clean = mod._result_block([], [])
    assert not any("NOT RUN" in ln for ln in block_clean), block_clean
    print("  ALL PASS + NOT RUN are separate lines; a clean run adds neither ✓")


def test_attribution_distinguishes_reproduced_from_introduced():
    """A failure count is not an attribution: "3 failed" cannot say whether THIS range caused them,
    which is exactly the claim a reviewer has to refuse. The three outcomes must be readable apart."""
    mod = _harness()
    assert "REPRODUCED" in mod._attribution_verdict(1, 1), mod._attribution_verdict(1, 1)
    assert "DIFFERS" in mod._attribution_verdict(0, 1), mod._attribution_verdict(0, 1)
    assert "DIFFERS" in mod._attribution_verdict(1, 0), mod._attribution_verdict(1, 0)
    assert "COULD NOT VERIFY" in mod._attribution_verdict(None, 1), mod._attribution_verdict(None, 1)
    # CONTROL both ways: agreement must never read as a regression, and a difference must never
    # read as agreement.
    assert mod._attribution_verdict(1, 1) != mod._attribution_verdict(0, 1)
    print("  attribution: reproduced / differs / could-not-verify are distinct ✓")


def _main():
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    if not tests:
        print("NO TESTS RAN — this file executed nothing")
        return 1
    print("harness:", HARNESS)
    assert HARNESS.is_file(), f"missing harness: {HARNESS}"
    failed = []
    for name, fn in tests:
        try:
            fn()
        except Exception:
            import traceback
            failed.append(name)
            print(f"FAIL  {name}")
            traceback.print_exc()
    if failed:
        print(f"RESULT: FAIL ({len(failed)}/{len(tests)}): {failed}")
        return 1
    print(f"RESULT: ALL PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
