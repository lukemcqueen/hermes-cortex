#!/usr/bin/env python3
"""No fleet launcher may bare-exec the fleet venv — the class, not the incident.

Kustos's loop-governance MCP died as bash's "line 11: No such file or directory". That was
one launcher; the wall is the same for every launcher, so the remedy has to be a rule rather
than a one-off patch. This sweep fails when:

  * a tracked file exec's the fleet venv WITHOUT going through the shared guard
    (scripts/lib/require-fleet-venv.sh), which names the missing piece and how to fix it;
  * a launcher hardcodes an absolute home, which breaks on every host whose user differs.

Adding a new launcher is fine — it must source the guard, like loop-gov-mcp.sh does.

Run: python3 tests/test_fleet_venv_launchers.py
"""
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
GUARD = "ops/scripts/lib/require-fleet-venv.sh"
GUARD_MARKERS = ("require-fleet-venv.sh", "require_fleet_venv")
#: Files allowed to mention the venv in an exec line. Each needs a reason, not a shrug.
ALLOW = {
    GUARD,  # the guard itself is the one that MUST name the path
}
VENV_REF = re.compile(r"hermes-cortex/venv|fleet_venv_python|FLEET_VENV_DIR")
EXEC_LINE = re.compile(r"\bexec\b")
ABS_HOME = re.compile(r"/home/[a-z][a-z0-9_-]*/")
SKIP_SUFFIX = (".md", ".txt", ".json", ".yaml", ".yml", ".plist", ".raw")


def _tracked():
    out = subprocess.run(["git", "ls-files"], cwd=REPO, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return [REPO / p for p in out.stdout.split() if p]


def _code_lines(path):
    for line in path.read_text(errors="replace").splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            yield stripped


def test_no_launcher_execs_the_fleet_venv_without_the_guard():
    offenders = []
    for path in _tracked():
        rel = path.relative_to(REPO).as_posix()
        if rel in ALLOW or rel.endswith(SKIP_SUFFIX) or not path.is_file():
            continue
        body = path.read_text(errors="replace")
        if not VENV_REF.search(body):
            continue
        if not any(EXEC_LINE.search(line) and VENV_REF.search(line) for line in _code_lines(path)):
            continue          # mentions the venv but does not exec it
        if any(marker in body for marker in GUARD_MARKERS):
            continue          # goes through the guard
        offenders.append(rel)
    assert not offenders, (
        "these launchers exec the fleet venv without the shared guard "
        f"(source {GUARD} and call require_fleet_venv): {offenders}"
    )
    print("  every launcher that execs the fleet venv goes through the guard ✓")


def test_the_known_launcher_is_guarded():
    """Control: the sweep must be looking at something, not passing vacuously."""
    wrapper = REPO / "ops/scripts/manage/loop-gov-mcp.sh"
    body = wrapper.read_text()
    assert "require-fleet-venv.sh" in body, "loop-gov-mcp.sh must source the guard"
    assert "require_fleet_venv" in body, "and call it"
    print("  loop-gov-mcp.sh sources and calls the guard ✓")


def test_the_sweep_would_catch_a_bare_exec():
    """Prove the detector fires, so a green sweep means something."""
    sample = 'set -u\nexec "$HOME/.hermes-cortex/venv/bin/python3" "$HOME/.hermes-cortex/tools/x.py" "$@"\n'
    assert VENV_REF.search(sample) and any(
        EXEC_LINE.search(line) and VENV_REF.search(line) for line in sample.splitlines())
    assert not any(m in sample for m in GUARD_MARKERS), "a bare exec is exactly what it must flag"
    print("  a bare exec is detected as an offender ✓")


def test_no_absolute_home_in_launcher_code():
    """$HOME-resolved, always: an absolute path breaks on every other fleet host."""
    offenders = []
    for rel in ("ops/scripts/manage/loop-gov-mcp.sh", GUARD):
        for line in _code_lines(REPO / rel):
            if ABS_HOME.search(line):
                offenders.append(f"{rel}: {line}")
    assert not offenders, f"absolute home paths break other hosts: {offenders}"
    print("  no absolute home in launcher/guard code ✓")


def _main():
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
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
