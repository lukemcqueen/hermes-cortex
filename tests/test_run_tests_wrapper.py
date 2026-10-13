"""tests/run-tests.sh must work on macOS, in multi-repo sessions, and in repos with no cortex.

This runs the REAL wrapper in constructed environments rather than reading it and hoping. The three
things that actually differ off this host:

* **macOS** ships bash **3.2** and BSD userland. No `declare -A`, no `mapfile`, no `${var,,}`, no
  GNU-only flags (`readlink -f`, `date -d`, `sed -i` without a suffix, `grep -P`). A script that
  silently needs bash 4 breaks on Titus.
* **multi-repo sessions**: the wrapper must not assume it is in hermes-cortex, must not read another
  repo's state, and must not depend on a fleet install being present at all.
* **non-cortex repos**: no `ops/scripts/lib/python-with-module.sh`, no `~/.hermes-cortex` — the
  interpreter then has to be found by CAPABILITY on PATH, and if nothing can import pytest the
  wrapper must say so (rc=3) rather than run something that cannot test.
"""

import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WRAPPER = REPO / "tests" / "run-tests.sh"
REAL_PY = sys.executable


def _shim(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(0o755)


def _fake_repo(tmp_path: Path) -> Path:
    """A repo shaped like any OTHER repo: a tests dir, and nothing else of ours."""
    fake = tmp_path / "some-other-repo"
    (fake / "tests").mkdir(parents=True)
    _shim(fake / "tests" / "run-tests.sh", WRAPPER.read_text())
    (fake / "tests" / "test_one.py").write_text("def test_ok():\n    assert True\n")
    return fake


def _run(fake: Path, home: Path, bindir: Path, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["HOME"] = str(home)
    env["PATH"] = f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}"
    return subprocess.run(
        ["bash", str(fake / "tests" / "run-tests.sh"), *args],
        capture_output=True, text=True, cwd=str(fake), env=env, timeout=300,
    )


def test_it_works_in_a_repo_with_no_cortex_and_no_fleet_install(tmp_path):
    """No ops/scripts/lib, no ~/.hermes-cortex: resolve by capability on PATH and run."""
    fake = _fake_repo(tmp_path)
    home = tmp_path / "empty-home"
    home.mkdir()
    bindir = tmp_path / "bin"
    bindir.mkdir()
    # A PATH python3 that CAN import pytest, standing in for the host's own interpreter.
    _shim(bindir / "python3", f'#!/bin/sh\nexec "{REAL_PY}" "$@"\n')

    proc = _run(fake, home, bindir, "tests/test_one.py", "-q")
    assert proc.returncode == 0, f"wrapper failed in a non-cortex repo:\n{proc.stdout}{proc.stderr}"
    assert "1 passed" in proc.stdout, proc.stdout
    assert "using python3 from PATH, which CAN import pytest" in proc.stderr, (
        "the fallback must SAY it fell back — a silent one swaps which code decides:\n" + proc.stderr
    )


def test_it_refuses_to_run_when_nothing_can_import_pytest(tmp_path):
    """The honest failure: no interpreter means no verdict, never a green lie."""
    fake = _fake_repo(tmp_path)
    home = tmp_path / "empty-home"
    home.mkdir()
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for name in ("python3", "python"):
        _shim(bindir / name, "#!/bin/sh\nexit 1\n")  # cannot import pytest

    proc = _run(fake, home, bindir, "tests/test_one.py", "-q")
    assert proc.returncode == 3, f"expected COULD NOT VERIFY (3), got {proc.returncode}"
    assert "COULD NOT VERIFY" in proc.stderr
    assert "NOT a pass" in proc.stderr


def test_the_wrapper_is_bash_3_2_and_bsd_safe():
    """Read the source for what macOS would break on. Cheap, and decisive if it regresses."""
    src = WRAPPER.read_text()
    forbidden = {
        "declare -A": "associative arrays need bash 4",
        "mapfile": "needs bash 4",
        "readarray": "needs bash 4",
        "local -n": "nameref needs bash 4.3",
        "readlink -f": "BSD readlink has no -f",
        "date -d": "BSD date has no -d",
        "grep -P": "BSD grep has no -P",
        "sed -i ": "BSD sed -i requires a suffix argument",
        "sha256sum": "macOS ships shasum -a 256",
        "&>>": "needs bash 4",
    }
    for needle, why in forbidden.items():
        assert needle not in src, f"{needle!r} is not portable ({why})"
    for pattern, why in (
        (r"\$\{[A-Za-z_][A-Za-z0-9_]*,,", "lowercase expansion needs bash 4"),
        (r"\$\{[A-Za-z_][A-Za-z0-9_]*\^\^", "uppercase expansion needs bash 4"),
    ):
        assert not re.search(pattern, src), f"{pattern} is not portable ({why})"
    assert src.startswith("#!/usr/bin/env bash"), "must not hardcode a bash path"


def test_it_is_not_tied_to_this_repo_path():
    """Portable paths: the repo root is derived from the script's own location, never hardcoded.

    (An earlier draft asserted `"hermes-cortex" not in src` and failed — correctly. The wrapper DOES
    name the deployed cortex resolver, as its last-resort fallback by way of `$HOME`. Referring to a
    fleet install is not the same as REQUIRING one; what must never appear is an absolute path that
    only exists on one host.)
    """
    src = WRAPPER.read_text()
    assert "/home/" not in src, "an absolute home path would break on every other host"
    assert 'dirname "${BASH_SOURCE[0]}"' in src, "derive REPO from the script's own location"
    # Any reference to the fleet install must go through $HOME, so it stays host-independent.
    for i, line in enumerate(src.splitlines(), 1):
        if "hermes-cortex" in line:
            assert "$HOME" in line or "${HOME}" in line, (
                f"line {i} names the fleet install without $HOME: {line!r}"
            )
