"""Startup-resilience tests for loop-gov-mcp.py.

Regression: 2026-08-25 (Titus) — the deployed loop-governance MCP server
crashed at module import with "subprocess 'loop-governance' has exited",
locking the agent out of write tools (no begin_change possible).

Root cause: module-level `from hermes_models import get_model` resolves ONLY
via the ~/.hermes/scripts -> ~/.hermes-cortex/scripts symlink. On hosts where
that symlink is missing (macOS Titus), the import raises ModuleNotFoundError
at line ~80 and the entire MCP server dies before serving any tool.

The server must start even when the auxiliary hermes_models helper is not
importable — it is a model-name lookup with a documented default, not an
enforcement gate. Missing it should degrade to the default, never crash.
"""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SERVER_PATH = Path(
    os.environ.get("LOOP_GOV_MCP", "~/hermes-cortex/mcp-servers/loop-gov-mcp.py")
).expanduser()


def _server_python() -> str:
    """The interpreter that can actually RUN this server.

    The server imports the `mcp` package at startup. Using whatever `python3`
    invoked this test is a PROBE BUG: with an interpreter that lacks `mcp` the
    server exits with "the MCP SDK is not installed" before it can initialize, and
    the assertion then blames the server for the harness's choice of interpreter.
    This test passed or failed purely on which python ran it, which is not a test
    (found 2026-10-08).

    Candidates, most authoritative first: the interpreter the fleet REGISTERS for
    this server (`mcp_servers.<name>.command` in ~/.hermes/config.yaml — the one
    actually in use), the Hermes venv, then sys.executable. If none can import
    `mcp`, FAIL LOUDLY rather than assert against a server that was never allowed
    to start.
    """
    cands = []
    try:
        cfg_text = (Path.home() / ".hermes" / "config.yaml").read_text(errors="ignore")
    except OSError:
        cfg_text = ""
    if cfg_text:
        block = re.search(r"^[ \t]*loop-governance:[ \t]*$(.*?)(?=^\S|\Z)",
                          cfg_text, re.M | re.S)
        if block:
            cmd = re.search(r"^[ \t]*command:[ \t]*(\S+)[ \t]*$", block.group(1), re.M)
            if cmd:
                cands.append(cmd.group(1).strip("'\""))
    cands.append(str(Path.home() / ".hermes" / "hermes-agent" / "venv" / "bin" / "python3"))
    cands.append(sys.executable)

    tried = []
    for cand in cands:
        if not cand or cand in tried or not Path(cand).exists():
            continue
        tried.append(cand)
        try:
            probe = subprocess.run([cand, "-c", "import mcp"],
                                   capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError):
            continue
        if probe.returncode == 0:
            return cand
    raise AssertionError(
        "no interpreter with the 'mcp' package is available, so this server cannot "
        "be started at all. Checked: " + ", ".join(tried or ["(none found)"]))


def _run_server_with_home(home_dir: Path) -> subprocess.CompletedProcess:
    """Start the real deployed server under a fake HOME (no symlinks, no
    hermes_models.py) and feed it EOF so it exits promptly."""
    env = {**os.environ, "HOME": str(home_dir)}
    return subprocess.run(
        [_server_python(), str(SERVER_PATH)],
        input="", capture_output=True, text=True, timeout=60,
        env=env,
    )


def test_server_starts_without_hermes_models_symlink():
    """Titus regression: HOME without ~/.hermes/scripts symlink must NOT kill
    the MCP server at import. It should start (and exit cleanly on EOF)."""
    with tempfile.TemporaryDirectory(prefix="loop-gov-fakehome-") as tmp:
        home = Path(tmp)
        # Sanity: the fake HOME must NOT accidentally contain the real scripts
        assert not (home / ".hermes" / "scripts").exists()
        assert not (home / ".hermes-cortex" / "scripts").exists()

        proc = _run_server_with_home(home)

        # The import crash we're fixing — server must REACH the stdio loop,
        # not die at module import. The warning (with the error class in its
        # text) is expected and healthy; the crash is not.
        assert "Initializing server 'loop-governance'" in proc.stderr, (
            f"server never reached initialization under fake HOME.\n"
            f"stderr:\n{proc.stderr[:2000]}"
        )
        assert "Traceback (most recent call last)" not in proc.stderr, (
            f"server crashed with a traceback under fake HOME.\n"
            f"stderr:\n{proc.stderr[:2000]}"
        )
        # Degrade-not-crash: the fallback warning is expected ONLY when the module is
        # genuinely unavailable. Since the cortex_lib bootstrap now also puts the REPO's
        # ops/scripts on sys.path, hermes_models.py IS importable from the repo tree
        # (it lives there), so the fallback is correctly not taken. Asserting the
        # warning unconditionally would now be asserting the module is missing, which
        # is the opposite of what this file wants.
        #
        # The crash-prevention invariant below is what actually guards the regression,
        # and it is asserted in both directions.
        importable = (Path(__file__).resolve().parent.parent
                      / "ops" / "scripts" / "hermes_models.py").is_file()
        if not importable:
            assert "hermes_models.py not importable" in proc.stderr, (
                "hermes_models is absent, so the fail-soft warning must be present")
        else:
            assert "hermes_models.py not importable" not in proc.stderr, (
                "hermes_models is present on the repo path, so the fail-soft warning "
                "must NOT fire — a spurious warning here would mean the path search "
                "is wrong")
        # Server should reach the stdio loop (EOF exit 0, or clean handled exit)
        assert proc.returncode == 0, (
            f"server exited {proc.returncode} under fake HOME.\n"
            f"stderr:\n{proc.stderr[:2000]}"
        )


def test_server_starts_with_real_home():
    """Sanity: with the real HOME (symlink + hermes_models.py present) the
    server must still start — the fallback must not break the happy path."""
    proc = _run_server_with_home(Path.home())
    assert "ModuleNotFoundError" not in proc.stderr
    assert proc.returncode == 0, (
        f"server exited {proc.returncode} under real HOME.\n"
        f"stderr:\n{proc.stderr[:2000]}"
    )


if __name__ == "__main__":
    # pytest is not installed on this host and tests/run_loop_gov_regression.py runs
    # each file as `python3 <file>`: without this runner the file exited 0 having
    # executed NOTHING, so every committed artifact recorded a vacuous PASS
    # (found 2026-10-08, cycle 10916).
    test_server_starts_without_hermes_models_symlink()
    test_server_starts_with_real_home()
    print("ALL PASS — MCP server starts under both HOME shapes")
