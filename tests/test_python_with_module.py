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
VENV = Path.home() / ".hermes-cortex" / "venv"


class NotRun(Exception):
    """The subject could not be EXECUTED on this host, so nothing was verified.

    The runner scores "no exception" as PASS, so a test that prints a skip and RETURNS reads as a
    pass while having tested nothing. NOT RUN is its own outcome: named separately, counted
    separately, never a pass and never a failure of the code under test.
    """


def test_the_declared_fleet_interpreter_is_preferred():
    """CORTEX_PYTHON is ONE name for "the fleet interpreter". Seven scripts each carried their
    own clean-env probe before it existed; a caller should read this instead."""
    py = str(VENV / "bin" / "python3")
    if not Path(py).exists():
        raise NotRun("no fleet venv on this host — nothing to resolve against")
    r = _run("--print", "yaml", env={"CORTEX_PYTHON": py})
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    assert r.stdout.strip() == py, r.stdout


def test_the_declaration_is_read_from_agent_env():
    """The declaration lives in the per-host file the deploy provisions, so it survives a
    session that exports nothing.

    NO `tmp_path`: this file is run by the standalone runner in `_main()`, which calls each test
    with no arguments, so a pytest fixture arrives as an undefined name — the test failed with a
    NameError and read as a defect in the resolver. Build the file here with `tempfile` so it runs
    under the standalone runner AND under pytest.
    """
    py = str(VENV / "bin" / "python3")
    if not Path(py).exists():
        raise NotRun("no fleet venv on this host — no declaration to read")
    d = Path(tempfile.mkdtemp(prefix="pwm-declaration-"))
    f = d / "agent.env"
    f.write_text(f"AGENT_NAME=test-host\nCORTEX_PYTHON={py}\n")
    r = _run("--print", "yaml", env={"CORTEX_PYTHON": "", "CORTEX_ENV_FILE": str(f)})
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    assert r.stdout.strip() == py, r.stdout
    print("  the declaration in agent.env was read ✓")


def test_a_declaration_that_cannot_import_is_named():
    """A declaration is a PROMISE. When the declared interpreter cannot provide the module the
    resolver must NAME it — quietly falling through to some other interpreter hides a wrong
    declaration exactly as the old PATH-pick hid a missing dependency."""
    r = _run("--print", ABSENT_MODULE, env={"CORTEX_PYTHON": "/nonexistent/python3"})
    assert r.returncode == 3, (r.returncode, r.stdout, r.stderr)
    assert "Declared CORTEX_PYTHON: /nonexistent/python3" in r.stderr, r.stderr
    assert ABSENT_MODULE in r.stderr, r.stderr


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
    not_run = []
    for name, fn in tests:
        try:
            fn()
        except NotRun as exc:
            not_run.append(f"{name}: {exc}")
            print(f"NOT RUN  {name}")
        except Exception:
            import traceback
            failed.append(name)
            print(f"FAIL  {name}")
            traceback.print_exc()
    if not_run:
        print(f"NOT RUN ({len(not_run)}) — ran nothing here, so they are not evidence either way:")
        for entry in not_run:
            print(f"  - {entry}")
    if failed:
        print(f"RESULT: FAIL ({len(failed)}/{len(tests)}): {failed}")
        return 1
    print(f"RESULT: ALL PASS ({len(tests)} tests)" + (f" ({len(not_run)} NOT RUN)" if not_run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
