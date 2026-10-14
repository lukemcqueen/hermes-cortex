"""Importing the purge script must be INERT; running it must still purge.

`purge-stale-governance-locks.py` is registered in cortex-update.sh and run as a no_agent cron,
but it also calls `purge()` at module level, so loading it (by a test, a probe, a doctor check)
executed the purge against the LIVE state directory — and an importer cannot protect itself,
because repointing STATE_DIR after the import is too late. That was observed for real: a probe
importing this file removed 780 abandoned lock files before it could repoint anything.

Every check below runs against a throwaway HOME (or a throwaway STATE_DIR), so this suite can
never touch the host's real locks. Both directions are proven: importing does nothing, and both
the function and the CLI still remove a stale lock.
"""
import ast
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "ops" / "scripts" / "manage" / "purge-stale-governance-locks.py"


def _stale_lock(state_dir: Path, name=".governance-stale-probe.json") -> Path:
    """A stale lock that CAN be swept: its cycle is already resolved (MOVE_ON).

    The sweep keeps a stale lock when its task's PENDING cycle cannot be resolved (#125) — that
    guard is proven in tests/test_purge_resolves_orphaned_cycles.py; here the point is the
    entrypoint, so the store is set up to let the removal proceed and the check stays focused.
    """
    import sqlite3
    state_dir.mkdir(parents=True, exist_ok=True)
    data = state_dir.parent / "data"
    data.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(data / "loop-governance.db"))
    try:
        conn.execute("CREATE TABLE IF NOT EXISTS loop_cycles (id INTEGER PRIMARY KEY, task_id TEXT,"
                     " decision TEXT, user_overrode INTEGER, unscored_reason TEXT,"
                     " outcome_note TEXT, timestamp TEXT)")
        conn.execute("INSERT INTO loop_cycles (task_id, decision) VALUES (?,?)",
                     ("stale-probe-task", "MOVE_ON"))
        conn.commit()
    finally:
        conn.close()
    old = (datetime.now(timezone.utc) - timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
    p = state_dir / name
    p.write_text(json.dumps({
        "session_id": "stale-probe", "task_id": "stale-probe-task", "status": "executing",
        "heartbeat_at": old, "started_at": old, "ttl_seconds": 3600,
    }))
    return p


def _import_with_home(home: Path):
    """Import the script as if HOME were `home` — the only way to reach its live-path constants."""
    spec = importlib.util.spec_from_file_location("purge_probe_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    with mock.patch.object(Path, "home", staticmethod(lambda: home)):
        spec.loader.exec_module(mod)
    return mod


def test_importing_the_module_purges_nothing():
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        state = home / ".hermes-cortex" / "state"
        stale = _stale_lock(state)
        _import_with_home(home)
        assert stale.exists(), (
            "importing the purge script removed a stale lock: its entrypoint runs at module "
            "level, so any importer silently purges the live state directory"
        )


def test_the_state_dir_defaults_to_the_importers_home():
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        mod = _import_with_home(home)
        assert mod.STATE_DIR == home / ".hermes-cortex" / "state", (
            "STATE_DIR must derive from Path.home() at import — the test above only proves "
            "something if the module really aimed at that HOME"
        )


def test_purge_still_removes_a_stale_lock_when_called():
    """The guard must not have neutered the function: the same file the import spared is removed
    when purge() is actually invoked."""
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        stale = _stale_lock(home / ".hermes-cortex" / "state")
        mod = _import_with_home(home)
        assert stale.exists(), "precondition: import left the stale lock alone"
        removed = mod.purge()
        assert removed == 1, f"purge() removed {removed} file(s), expected the one stale lock"
        assert not stale.exists(), "purge() no longer removes a stale lock"


def test_running_it_as_a_script_still_purges():
    """The real cron path: the file is EXECUTED, not imported. HOME is redirected so the run
    cannot reach the host's own locks."""
    with tempfile.TemporaryDirectory() as tmp:
        home = Path(tmp)
        stale = _stale_lock(home / ".hermes-cortex" / "state")
        env = {**os.environ, "HOME": str(home)}
        proc = subprocess.run([sys.executable, str(SCRIPT)], capture_output=True, text=True,
                              env=env, timeout=120)
        assert proc.returncode == 0, f"rc={proc.returncode} stderr={proc.stderr[-300:]}"
        assert "Purged 1 stale governance lock" in proc.stdout, (
            f"the CLI no longer reports the purge: stdout={proc.stdout!r}"
        )
        assert not stale.exists(), "the CLI ran but removed nothing"


def test_no_module_level_executable_statements_beyond_the_guard():
    """Source-level belt-and-braces: the module body is definitions, constants and the __main__
    guard — nothing that runs a purge at import, now or after a future edit."""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    allowed = (ast.Import, ast.ImportFrom, ast.FunctionDef, ast.ClassDef, ast.Assign,
               ast.AnnAssign, ast.Expr)
    offenders = []
    for node in tree.body:
        if isinstance(node, ast.If):
            # the only permissible top-level `if` is the __main__ guard
            guard = ast.dump(node.test)
            assert "__main__" in guard, f"a module-level if runs on import: {ast.dump(node.test)}"
            continue
        if isinstance(node, ast.ClassDef):
            # A class definition is inert, but its DECORATOR executes at import — so only a
            # side-effect-free one is acceptable here (dataclass just rewrites the class).
            for deco in node.decorator_list:
                name = ast.dump(deco)
                assert "dataclass" in name or "field" in name, (
                    f"a module-level decorator runs at import: {name[:60]}"
                )
            continue
        if isinstance(node, allowed):
            # a bare docstring/constant is fine; any CALL is not
            if isinstance(node, ast.Expr) and not isinstance(node.value, ast.Constant):
                offenders.append(ast.dump(node.value)[:80])
            continue
        offenders.append(type(node).__name__)
    assert not offenders, (
        f"these module-level statements execute on import and can have side effects: {offenders}"
    )
