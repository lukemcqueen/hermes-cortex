#!/usr/bin/env python3
"""ensure-pytest.sh — the CREATE step the harness's resolution depends on.

WHY THIS FILE EXISTS (ADV-13116-1, then ADV-13253-1): tests/run_loop_gov_regression.py can only
JUDGE a pytest-style file with an interpreter that imports pytest. Resolving one that already
exists is half the job — nothing in this repo CREATED one, so on a fresh host every pytest-style
file reported NOT RUN while the summary still printed a pass. The other half is one committed,
idempotent command that creates the venv through the repo's own declared set
(`ops/install/requirements.txt`) and the repo's own supply-chain age gate.

This drives that command against a FABRICATED repo tree — a copy of the real script, a stub age
checker and a stub venv repairer — so every branch is CONSTRUCTED rather than waited for:
the age gate refusing, a repair that leaves pytest unimportable, and a missing prerequisite
(COULD NOT VERIFY). No branch is exercised only on a healthy host.

Run: python3 tests/test_ensure_pytest.py
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "ops" / "scripts" / "lib" / "ensure-pytest.sh"

AGE_STUB = '''#!/usr/bin/env python3
import os, sys
sys.exit(0 if os.environ.get("AGE_OK") == "1" else 1)
'''

# Creates the venv interpreter only when REPAIR_WORKS=1. Always logs that it RAN, so "did the age
# gate stop us before we installed anything?" is answerable rather than inferred.
REPAIR_STUB = '''#!/usr/bin/env python3
import os, sys
marker_dir = os.environ.get("MARKER_DIR", ".")
with open(os.path.join(marker_dir, "repair.log"), "a") as fh:
    fh.write("ran\\n")
if os.environ.get("REPAIR_WORKS") == "1":
    d = os.path.join(os.environ["HOME"], ".hermes-cortex", "venv", "bin")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "python3")
    with open(p, "w") as fh:
        fh.write("#!/bin/sh\\nexit 0\\n")
    os.chmod(p, 0o755)
sys.exit(0)
'''


def _tree(tmp: Path) -> Path:
    """A fabricated repo that mirrors the paths the script resolves from its own location."""
    for rel in ("ops/scripts/lib", "ops/scripts/health", "ops/scripts/manage", "ops/install"):
        (tmp / rel).mkdir(parents=True, exist_ok=True)
    shutil.copy2(SCRIPT, tmp / "ops" / "scripts" / "lib" / "ensure-pytest.sh")
    (tmp / "ops" / "scripts" / "health" / "check-package-age.py").write_text(AGE_STUB)
    (tmp / "ops" / "scripts" / "manage" / "fix-cortex-venv.py").write_text(REPAIR_STUB)
    (tmp / "ops" / "install" / "requirements.txt").write_text("pytest>=7.0\n")
    return tmp


def _run(tmp: Path, home: Path, marker: Path, **env):
    cmd = ["bash", str(tmp / "ops" / "scripts" / "lib" / "ensure-pytest.sh")]
    if env.pop("check_only", False):
        cmd.append("--check")
    full = {**os.environ, "HOME": str(home), "MARKER_DIR": str(marker), **{k: str(v) for k, v in env.items()}}
    return subprocess.run(cmd, capture_output=True, text=True, env=full)


def _repairs(marker: Path) -> int:
    log = marker / "repair.log"
    return len(log.read_text().splitlines()) if log.exists() else 0


def _newborn():
    tmp = Path(tempfile.mkdtemp(prefix="ensure-pytest-"))
    home = tmp / "home"
    home.mkdir()
    marker = tmp / "marker"
    marker.mkdir()
    return _tree(tmp), home, marker


def test_the_age_gate_stops_the_install_before_it_happens():
    """The gate must run BEFORE the repair, or a too-new package is installed and the check is a
    post-mortem. Asserted by the repairer's own log, not by reading the source order."""
    tmp, home, marker = _newborn()
    r = _run(tmp, home, marker, AGE_OK="0", REPAIR_WORKS="1")
    assert r.returncode == 1, (r.returncode, r.stdout, r.stderr)
    assert _repairs(marker) == 0, "the age gate must refuse BEFORE anything is installed"
    assert "AGE GATE REFUSED" in r.stderr, r.stderr
    assert "pytest" in r.stderr, r.stderr
    print("  age gate refuses -> rc=1, repair never invoked ✓")


def test_it_creates_the_venv_then_verifies_by_import():
    tmp, home, marker = _newborn()
    r = _run(tmp, home, marker, AGE_OK="1", REPAIR_WORKS="1")
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
    printed = Path(r.stdout.strip())
    assert printed == home / ".hermes-cortex" / "venv" / "bin" / "python3", printed
    assert printed.is_file(), printed
    assert _repairs(marker) == 1, _repairs(marker)
    print(f"  created and verified: {printed} ✓")


def test_it_is_idempotent_and_never_reinstalls_what_imports():
    """Verified by IMPORT, not by metadata: a second run must not invoke the repairer again."""
    tmp, home, marker = _newborn()
    first = _run(tmp, home, marker, AGE_OK="1", REPAIR_WORKS="1")
    assert first.returncode == 0, first.stderr
    second = _run(tmp, home, marker, AGE_OK="1", REPAIR_WORKS="1")
    assert second.returncode == 0, second.stderr
    assert second.stdout.strip() == first.stdout.strip(), second.stdout
    assert _repairs(marker) == 1, f"the repairer ran {_repairs(marker)} times, must be 1"
    print("  second run is a no-op (repairer invoked once) ✓")


def test_a_repair_that_leaves_pytest_unimportable_is_NOT_a_pass():
    """The whole point of verifying by import: exit 0 from the installer is not evidence."""
    tmp, home, marker = _newborn()
    r = _run(tmp, home, marker, AGE_OK="1", REPAIR_WORKS="0")
    assert r.returncode == 1, f"an unusable venv must be rc=1, got {r.returncode}"
    assert "STILL cannot import pytest" in r.stderr, r.stderr
    assert r.stdout.strip() == "", f"nothing may be offered as an interpreter: {r.stdout!r}"
    print("  repair ran, import still fails -> rc=1, no path printed ✓")


def test_a_missing_prerequisite_is_could_not_verify_not_a_pass():
    """rc=3 is its own outcome. A caller that reads only `if ! script; then <report the bad thing>`
    would otherwise be told its artifact is stale when the tool simply could not run."""
    tmp, home, marker = _newborn()
    (tmp / "ops" / "scripts" / "health" / "check-package-age.py").unlink()
    r = _run(tmp, home, marker, AGE_OK="1", REPAIR_WORKS="1")
    assert r.returncode == 3, (r.returncode, r.stdout, r.stderr)
    assert "COULD NOT VERIFY" in r.stderr, r.stderr
    assert _repairs(marker) == 0, "nothing may be installed when a prerequisite is missing"
    print("  missing age checker -> rc=3 COULD NOT VERIFY ✓")


def test_check_mode_reports_and_never_installs():
    tmp, home, marker = _newborn()
    r = _run(tmp, home, marker, check_only=True, AGE_OK="1", REPAIR_WORKS="1")
    assert r.returncode == 1, (r.returncode, r.stdout, r.stderr)
    assert _repairs(marker) == 0, "--check must never install"
    print("  --check reports only ✓")


def test_the_harness_hint_and_the_deploy_map_name_this_script():
    """The harness must point at THIS script, and the script must actually reach a peer host."""
    harness = (REPO / "tests" / "run_loop_gov_regression.py").read_text()
    assert SCRIPT.is_file(), SCRIPT
    assert "ops/scripts/lib/ensure-pytest.sh" in harness, \
        "the no-pytest hint must name the committed create step"
    updater = (REPO / "ops" / "scripts" / "cortex-update.sh").read_text()
    assert "ensure-pytest.sh" in updater, \
        "an unregistered script never reaches a peer host — add it to the deploy map"
    print("  hint + deploy registration both name it ✓")


def _main():
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    if not tests:
        print("NO TESTS RAN — this file executed nothing")
        return 1
    print("script:", SCRIPT)
    assert SCRIPT.is_file(), f"missing script: {SCRIPT}"
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
