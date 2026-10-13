#!/usr/bin/env python3
"""The loop-gov wrapper must fail SPECIFICALLY, and the deploy must see an ABSENT venv.

Kustos's loop-governance MCP died as bash's "line 11: No such file or directory" — a
message that names neither the path nor the cause, for three different causes with three
different fixes. These tests construct each branch hermetically (HOME pointed at a temp
tree), so none of them needs a broken host:

  A. no interpreter  -> says so, prints HOME and the create+fill commands, rc=78;
  B. no server file  -> says so, points at the deploy, rc=78;
  C. both present    -> EXECS the server with the caller's args (the guard must not break
                        the happy path).

Run: python3 tests/test_loop_gov_wrapper_guard.py
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
WRAPPER = REPO / "ops" / "scripts" / "manage" / "loop-gov-mcp.sh"
EX_CONFIG = 78


def _run(home):
    return subprocess.run(["bash", str(WRAPPER)], capture_output=True, text=True,
                          env={**os.environ, "HOME": str(home)})


def _fake_home(tmp, with_python=False, with_server=False, calls=None):
    root = Path(tmp)
    if with_python:
        p = root / ".hermes-cortex" / "venv" / "bin" / "python3"
        p.parent.mkdir(parents=True, exist_ok=True)
        # A real file that records how it was called — the guard must exec it, with args.
        p.write_text('#!/usr/bin/env bash\nprintf "EXEC:%s\\n" "$@"\n')
        p.chmod(0o755)
    if with_server:
        s = root / ".hermes-cortex" / "tools" / "loop-governance" / "loop-gov-mcp.py"
        s.parent.mkdir(parents=True, exist_ok=True)
        s.write_text("# deployed governance server\n")
    return root


def test_missing_interpreter_is_named_with_its_home_and_the_fix():
    with tempfile.TemporaryDirectory() as td:
        home = _fake_home(td, with_server=True)      # venv absent, server present
        r = _run(home)
        assert r.returncode == EX_CONFIG, f"expected rc={EX_CONFIG}, got {r.returncode}"
        assert "NO INTERPRETER" in r.stderr, r.stderr
        assert str(home / ".hermes-cortex" / "venv" / "bin" / "python3") in r.stderr, \
            "the message must name the exact path that is missing"
        assert f"HOME={home}" in r.stderr, "the message must print the HOME it resolved"
        assert "python3 -m venv" in r.stderr, "it must show how to create the venv"
        assert "fix-cortex-venv.py" in r.stderr, "it must show how to fill it"
        assert "No such file or directory" not in r.stderr, \
            "the whole point: bash's generic message must be replaced by a specific one"
        print("  A: absent interpreter -> named path, HOME, create+fill, rc=78 ✓")


def test_missing_server_points_at_the_deploy():
    with tempfile.TemporaryDirectory() as td:
        home = _fake_home(td, with_python=True)      # venv present, server absent
        r = _run(home)
        assert r.returncode == EX_CONFIG, f"expected rc={EX_CONFIG}, got {r.returncode}"
        assert "NOT DEPLOYED" in r.stderr, r.stderr
        assert str(home / ".hermes-cortex" / "tools" / "loop-governance" / "loop-gov-mcp.py") in r.stderr
        assert "cortex-update.sh" in r.stderr, "it must name the deploy that installs it"
        print("  B: absent server -> named path, deploy command, rc=78 ✓")


def test_the_happy_path_still_execs_with_arguments():
    with tempfile.TemporaryDirectory() as td:
        home = _fake_home(td, with_python=True, with_server=True)
        r = _run(home)
        assert r.returncode == 0, f"the guard must not break the exec: {r.stderr}"
        assert r.stdout.startswith("EXEC:"), r.stdout
        assert str(home / ".hermes-cortex" / "tools" / "loop-governance" / "loop-gov-mcp.py") in r.stdout
        print("  C: both present -> execs the server ✓")


def test_the_wrapper_carries_no_absolute_home():
    """It must resolve through $HOME: a hardcoded /home/<user> is how a fleet script breaks
    on every other host (and reads as PII to the scanners)."""
    body = WRAPPER.read_text()
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or not stripped:
            continue
        assert "/home/" not in stripped, f"absolute home in code: {stripped}"
    print("  no absolute /home/ path in executable lines ✓")


def _main():
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    if not tests:
        print("NO TESTS RAN — this file executed nothing")
        return 1
    assert WRAPPER.is_file(), f"missing wrapper: {WRAPPER}"
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
