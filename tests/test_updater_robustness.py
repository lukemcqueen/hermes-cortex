#!/usr/bin/env python3
"""The two updater-robustness fixes, driven by their REAL blocks with stubs.

Both changes replace a signal that fires when nothing is wrong, or fails to fire when
something is:

  * change-validate.sh §3 warned about any staged file under deploy/ or ops/scripts/
    whose basename is absent from cortex-update.sh. That is not a missed step for the
    19 of 99 manage scripts that are deliberately checkout-only, nor for
    ops/scripts/quality/evidence-*.sh — yet it warned on every edit they received.
    It now considers only NEWLY ADDED files.
  * cortex-update.sh points MCP-server registrations at ~/.hermes-cortex/venv/bin/python3
    but never checked that interpreter could import what those servers need. Measured
    2026-10-08: it existed and held only psycopg, so the daily regression gate failed
    every day on PyYAML. It now probes the modules and reports the repair.

Each block is EXTRACTED from the real script (anchored on its section comment, never on
line numbers) and run with a stub preamble, per the shell-scripting skill's
"Testing a Script Block in Isolation". A test that re-implemented either block would
prove nothing about the script that ships.

Run: python3 tests/test_updater_robustness.py
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CHANGE_VALIDATE = REPO / "ops" / "scripts" / "change-validate.sh"
CORTEX_UPDATE = REPO / "ops" / "scripts" / "cortex-update.sh"
UNREGISTERED_TOOL = "ops/scripts/manage/verify-landed.py"   # checkout-only by design

STUBS = """set -uo pipefail
warn() { echo "WARN: $*"; }
info() { echo "INFO: $*"; }
error() { echo "ERROR: $*"; }
_DEFERRED_FAILURES=()
export CORTEX_DEPLOY_HOME=/nonexistent-deploy-home
# Set by change-validate.sh before §3; relative to cwd, which is the fixture repo.
export CORTEX_UPDATE="./ops/scripts/cortex-update.sh"
"""


def _extract(path: Path, start_marker: str, stop_marker: str) -> str:
    """The block between two section markers — anchored on content, not line numbers."""
    lines = path.read_text().splitlines(keepends=True)
    out, inside = [], False
    for line in lines:
        if start_marker in line:
            inside = True
        if inside and stop_marker in line:
            break
        if inside:
            out.append(line)
    assert out, f"could not extract {start_marker!r} from {path.name}"
    return "".join(out)


def _run_block(code: str, cwd: Path, env_extra=None) -> subprocess.CompletedProcess:
    script = cwd / "_block.sh"
    script.write_text(code)
    env = {**os.environ, **(env_extra or {})}
    return subprocess.run(["bash", str(script)], cwd=str(cwd), capture_output=True,
                          text=True, env=env)


def _git(repo: Path, *args) -> None:
    subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, check=False)


def _temp_repo(tmp: Path) -> Path:
    repo = tmp / "repo"
    (repo / "ops" / "scripts" / "manage").mkdir(parents=True)
    (repo / "ops" / "scripts" / "cortex-update.sh").write_text("# no register() calls here\n")
    (repo / "ops" / "scripts" / "manage" / "verify-landed.py").write_text("v1\n")
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "base")
    return repo


def _registration_block() -> str:
    return STUBS + _extract(CHANGE_VALIDATE,
                            "── 3. Registration consistency",
                            "── 4.")


def test_an_ADDED_unregistered_file_still_warns():
    """The case the check exists for — it must not have been lost with the noise."""
    with tempfile.TemporaryDirectory() as td:
        repo = _temp_repo(Path(td))
        (repo / "ops" / "scripts" / "brand-new-tool.sh").write_text("#!/usr/bin/env bash\n")
        _git(repo, "add", "ops/scripts/brand-new-tool.sh")
        r = _run_block(_registration_block(), repo)
        assert "NEW file ops/scripts/brand-new-tool.sh" in r.stdout, r.stdout + r.stderr
        assert "not registered in cortex-update.sh" in r.stdout, r.stdout
        print("  ADDED file -> warns ✓")


def test_a_MODIFIED_checkout_only_tool_is_silent():
    """THE fix: a long-unregistered tool being edited is not a missed registration."""
    with tempfile.TemporaryDirectory() as td:
        repo = _temp_repo(Path(td))
        p = repo / UNREGISTERED_TOOL
        p.write_text("v1\n# a new line\n")
        _git(repo, "add", UNREGISTERED_TOOL)
        r = _run_block(_registration_block(), repo)
        assert "not registered" not in r.stdout, \
            f"a MODIFIED checkout-only tool must not warn; got: {r.stdout}"
        print("  MODIFIED tool -> silent ✓")


def test_the_block_reads_the_ADDED_filter_not_every_staged_file():
    """Source-level guard: reverting to a bare $STAGED loop reintroduces the noise."""
    src = CHANGE_VALIDATE.read_text()
    assert "--diff-filter=A" in src, \
        "the registration check must consider only ADDED files (--diff-filter=A)"
    block = _registration_block()
    assert "ADDED_FILES" in block, "the block must iterate the ADDED set"
    print("  block uses --diff-filter=A ✓")


def _venv_block() -> str:
    return STUBS + _extract(CORTEX_UPDATE,
                            "── The fleet venv must be able to RUN what we point at it",
                            "── Ensure tasks MCP server registered")


def test_a_venv_that_cannot_import_the_modules_is_reported():
    """A venv EXISTING proves nothing — this is the 2026-10-08 failure, constructed."""
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / "home"
        bindir = home / ".hermes-cortex" / "venv" / "bin"
        bindir.mkdir(parents=True)
        # A python that cannot import anything: exactly the shape of the real venv,
        # which existed with only psycopg while callers expected yaml and mcp.
        (bindir / "python3").write_text("#!/usr/bin/env bash\nexit 1\n")
        (bindir / "python3").chmod(0o755)
        r = _run_block(_venv_block(), Path(td), env_extra={"HOME": str(home)})
        assert "cannot import" in r.stdout, r.stdout + r.stderr
        for mod in ("yaml", "mcp", "psycopg"):
            assert mod in r.stdout, f"the message must name the missing module {mod}: {r.stdout}"
        assert "uv pip install --python" in r.stdout, "it must print the exact repair"
        print("  module-less venv -> all three named + repair printed ✓")


def test_a_capable_venv_is_silent():
    """The other direction: with the modules present, nothing is reported."""
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / "home"
        bindir = home / ".hermes-cortex" / "venv" / "bin"
        bindir.mkdir(parents=True)
        # A python that imports whatever it is asked for.
        (bindir / "python3").write_text("#!/usr/bin/env bash\nexit 0\n")
        (bindir / "python3").chmod(0o755)
        r = _run_block(_venv_block(), Path(td), env_extra={"HOME": str(home)})
        assert "cannot import" not in r.stdout, r.stdout
        assert "ERROR" not in r.stdout, r.stdout
        print("  capable venv -> silent ✓")


def test_a_missing_venv_is_not_this_check_s_business():
    """No venv at all is a different condition; this check must not invent a failure."""
    with tempfile.TemporaryDirectory() as td:
        home = Path(td) / "home"
        home.mkdir()
        r = _run_block(_venv_block(), Path(td), env_extra={"HOME": str(home)})
        assert "cannot import" not in r.stdout, r.stdout
        print("  absent venv -> silent (not this check's finding) ✓")


def _main():
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    if not tests:
        print("NO TESTS RAN — this file executed nothing")
        return 1
    print(f"running {len(tests)} case(s)")
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
