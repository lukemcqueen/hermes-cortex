#!/usr/bin/env python3
"""The deploy's fleet-venv check, exercised with the venv ABSENT and present.

The claim is about a branch nobody can see on a healthy host: it fires only when
~/.hermes-cortex/venv is missing. Waiting for a broken host is not a test, and running the
whole deploy with the venv renamed is destructive — so the block is EXTRACTED by stable
comment markers and run against a stubbed HOME, the pattern this repo already uses for hook
guards:

  A. venv absent            -> error names it, prints how to create+fill, DEFERS a failure
                               (a host that cannot run its MCP servers is not "clean");
  B. venv present, modules missing -> the fallback probe reports it and DEFERS;
  C. venv present and importable   -> DEFERS NOTHING (control: no false alarm).

Run: python3 tests/test_fleet_venv_check_block.py
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DEPLOY = REPO / "ops" / "scripts" / "cortex-update.sh"
START = "# ── The fleet venv must EXIST"
END = "# ── Ensure tasks MCP server registered"

PREAMBLE = """#!/usr/bin/env bash
set -uo pipefail
_DEFERRED_FAILURES=()
error() { echo "ERROR: $*"; }
info()  { echo "INFO:  $*"; }
warn()  { echo "WARN:  $*"; }
CORTEX_DEPLOY_HOME="${CORTEX_DEPLOY_HOME:-$HOME/.hermes-cortex}"
"""
EPILOGUE = 'echo "DEFERRED=${#_DEFERRED_FAILURES[@]}"\n'


def extract_block():
    """By stable markers, never line numbers — they shift on every edit above."""
    text = DEPLOY.read_text()
    assert START in text, f"marker gone: {START!r} — this test must be updated, not silenced"
    assert END in text, f"marker gone: {END!r}"
    i = text.index(START)
    j = text.index(END, i)
    block = text[i:j]
    assert "_DEFERRED_FAILURES" in block, "the extracted block is not the venv check"
    return block


def _stub_venv(home, rc):
    py = Path(home) / ".hermes-cortex" / "venv" / "bin" / "python3"
    py.parent.mkdir(parents=True, exist_ok=True)
    py.write_text(f'#!/usr/bin/env bash\nexit {rc}\n')
    py.chmod(0o755)
    return py


def _run_block(home, deploy_home):
    with tempfile.TemporaryDirectory() as td:
        script = Path(td) / "block.sh"
        script.write_text(PREAMBLE + extract_block() + EPILOGUE)
        return subprocess.run(
            ["bash", str(script)], capture_output=True, text=True,
            env={**os.environ, "HOME": str(home), "CORTEX_DEPLOY_HOME": str(deploy_home)},
        )


def test_an_absent_venv_is_reported_and_runs_properly():
    """THE case kustos hit: the venv was never created, and the old check said nothing."""
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as dep:
        r = _run_block(home, dep)
        out = r.stdout + r.stderr
        assert "MISSING" in out, f"an absent venv must be reported: {out}"
        assert "python3 -m venv" in out, "it must show how to create it"
        assert "fix-cortex-venv.py" in out, "it must show how to fill it"
        assert "DEFERRED=1" in out, f"it must be deferred so the update is not called clean: {out}"
        print("  A: absent venv -> named, create+fill shown, deferred ✓")


def test_a_partial_venv_without_the_fixer_still_defers():
    """The fallback path, for a checkout that has not yet deployed the fixer."""
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as dep:
        _stub_venv(home, rc=1)          # every import fails
        r = _run_block(home, dep)
        out = r.stdout + r.stderr
        assert "cannot import" in out, f"a partial venv must be reported: {out}"
        assert "DEFERRED=1" in out, f"and deferred: {out}"
        print("  B: venv present, imports fail -> reported and deferred ✓")


def test_a_healthy_venv_defers_nothing():
    """Control: the check must not raise a false alarm on a working host."""
    with tempfile.TemporaryDirectory() as home, tempfile.TemporaryDirectory() as dep:
        _stub_venv(home, rc=0)          # every import succeeds
        r = _run_block(home, dep)
        out = r.stdout + r.stderr
        assert "DEFERRED=0" in out, f"a healthy venv must defer nothing: {out}"
        print("  C: healthy venv -> no false alarm ✓")


def _main():
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    if not tests:
        print("NO TESTS RAN — this file executed nothing")
        return 1
    assert DEPLOY.is_file(), f"missing {DEPLOY}"
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
