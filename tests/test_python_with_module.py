#!/usr/bin/env python3
"""python-with-module.sh — resolve an interpreter by CAPABILITY, and fail LOUDLY.

Why: a script that picks its python by PATH EXISTENCE and falls back to a bare
`python3` breaks twice — the file existing says nothing about the module, and the
fallback is usually the interpreter that lacks it. Measured on this host (2026-10-08),
`~/.hermes-cortex/venv/bin/python3` existed but imported neither `yaml` nor `mcp`, so
`orch-daily-regression-gate.sh`'s `if [[ ! -x $PY ]]` guard never fired and the gate
failed every day with "PyYAML is not installed".

RE-MEASURED 2026-10-13: that premise is now STALE — the cortex venv imports yaml and mcp
(pytest after installing it there), and it is the fleet venv cortex-update.sh registers
every MCP server against. So the resolver prefers the CORTEX venv and treats the Hermes
venv as the second candidate; capability still decides, the order only breaks a tie.

Each branch is exercised by CONSTRUCTING it, not by waiting for a host that has it:
the could-not-verify branch is driven with a module name that cannot exist.

Run: python3 tests/test_python_with_module.py
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HELPER = REPO / "ops" / "scripts" / "lib" / "python-with-module.sh"
# A name that cannot be importable anywhere, so the branch is reachable on ANY host.
ABSENT_MODULE = "no_such_module_zzz_for_this_test"


def _run(*args, env=None):
    return subprocess.run(["bash", str(HELPER), *args], capture_output=True, text=True,
                          env={**os.environ, **(env or {})})


def test_it_resolves_a_module_every_interpreter_has():
    r = _run("--print", "json")
    assert r.returncode == 0, r.stdout + r.stderr
    resolved = r.stdout.strip()
    assert resolved and Path(resolved).exists(), f"must print a real interpreter path: {r.stdout!r}"
    assert subprocess.run([resolved, "-c", "import json"], capture_output=True).returncode == 0
    print(f"  --print json -> {resolved} ✓")


def test_an_explicit_python_wins():
    """PYTHON= is the escape hatch an operator reaches for; it must be honoured first."""
    r = _run("--print", "json", env={"PYTHON": sys.executable})
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip() == sys.executable, \
        f"PYTHON must win; got {r.stdout.strip()!r} want {sys.executable!r}"
    print("  PYTHON=... is honoured first ✓")


def test_exec_mode_runs_the_script_with_a_capable_interpreter():
    with tempfile.TemporaryDirectory() as td:
        script = Path(td) / "probe.py"
        script.write_text("import sys, json\nprint('OK', sys.version_info[0])\n")
        r = _run("json", str(script))
        assert r.returncode == 0, r.stdout + r.stderr
        assert r.stdout.startswith("OK "), r.stdout
    print("  exec mode runs the child under a capable interpreter ✓")


def test_a_module_nobody_has_is_could_not_verify_not_a_silent_fallback():
    """THE regression: the old code fell back to a python3 that lacked the module."""
    r = _run("--print", ABSENT_MODULE)
    assert r.returncode == 3, f"must be rc=3 (COULD NOT VERIFY), got {r.returncode}\n{r.stdout}{r.stderr}"
    assert "COULD NOT VERIFY" in r.stderr, r.stderr
    assert ABSENT_MODULE in r.stderr, "the message must name the module it could not find"
    assert "Checked:" in r.stderr, "the message must list what it tried"
    # control: a silent fallback is exactly the bug — assert we did NOT print a path
    assert r.stdout.strip() == "", f"nothing may be printed as a usable interpreter: {r.stdout!r}"
    print("  absent module -> rc=3, names the module, prints no path ✓")


def test_a_missing_module_argument_is_a_usage_error():
    r = subprocess.run(["bash", str(HELPER)], capture_output=True, text=True)
    assert r.returncode == 2, f"usage error must be rc=2, got {r.returncode}"
    assert "usage" in r.stderr.lower(), r.stderr
    print("  no module argument -> rc=2 usage ✓")


def _can_import(py, module):
    return subprocess.run([str(py), "-c", f"import {module}"], capture_output=True).returncode == 0


def test_the_cortex_venv_is_preferred_over_the_hermes_venv():
    """Two capable candidates: the CORTEX venv wins (2026-10-13).

    The order only breaks a tie — a module only the Hermes venv has still resolves — but when
    both can import it, fleet tooling must not run under the tree we are migrating away from.
    Guarded rather than constructed: the comparison needs BOTH venvs, so it skips on a host
    that has one.
    """
    cortex = Path.home() / ".hermes-cortex" / "venv" / "bin" / "python3"
    hermes = Path.home() / ".hermes" / "hermes-agent" / "venv" / "bin" / "python3"
    if not (cortex.exists() and hermes.exists()):
        print("  skip: needs both venvs to compare them (this host has one) — not a failure")
        return
    module = next((m for m in ("yaml", "mcp", "json")
                   if _can_import(cortex, m) and _can_import(hermes, m)), None)
    assert module, "both venvs exist but share no importable module — re-measure this host"
    # PYTHON= and HERMES_VENV= are the explicit-choice escape hatches; empty them so this
    # measures the DEFAULT order rather than an operator's override.
    r = _run("--print", module, env={"PYTHON": "", "HERMES_VENV": ""})
    assert r.returncode == 0, r.stdout + r.stderr
    assert r.stdout.strip() == str(cortex), \
        f"the cortex venv must win a tie; got {r.stdout.strip()!r}"
    print(f"  {module}: the cortex venv beats the Hermes venv ✓")


def _main():
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    if not tests:
        print("NO TESTS RAN — this file executed nothing")
        return 1
    print("helper:", HELPER)
    assert HELPER.is_file(), f"missing helper: {HELPER}"
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
