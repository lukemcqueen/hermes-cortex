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
import subprocess
import sys
import tempfile
from pathlib import Path

SERVER_PATH = Path(
    os.environ.get("LOOP_GOV_MCP", "~/hermes-cortex/mcp-servers/loop-gov-mcp.py")
).expanduser()


def _run_server_with_home(home_dir: Path) -> subprocess.CompletedProcess:
    """Start the real deployed server under a fake HOME (no symlinks, no
    hermes_models.py) and feed it EOF so it exits promptly."""
    env = {**os.environ, "HOME": str(home_dir)}
    return subprocess.run(
        [sys.executable, str(SERVER_PATH)],
        input="", capture_output=True, text=True, timeout=15,
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
        # Degrade-not-crash: the fallback warning must be present
        assert "hermes_models.py not importable" in proc.stderr
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
