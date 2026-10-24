"""The detached UPDATE worker must be able to LOAD the handler it is asked to run.

Regression (2026-10-24, cycle `cost4-fleet-cost-coverage`): the worker child is a
fresh interpreter started as `python3 -c <code> <handler_path> <body> <corr>`, so
it inherits no PYTHONPATH. The worker source inserted only the HANDLER'S OWN
directory on sys.path — but `agent-message-handler.py` imports `hermes_paths`
from its PARENT directory (ops/scripts), so every detached UPDATE worker raised
ModuleNotFoundError at `exec_module` BEFORE its try/except. It wrote no result
and left its `.running` marker behind, so the requesting orchestrator waited the
full UPDATE_RESULT_TIMEOUT_S (30 min) for an update that never ran.

Measured live the same day: a self-test UPDATE_REQUEST spawned exactly such a
worker (`state/pending-update-results/<corr>.running`, no process, no `.json`),
which is why four worker hosts still ran a pre-change cron-cost-metrics.py.

These tests drive the REAL worker source (read out of the handler module) against
a throwaway stub handler that reproduces the one property that matters: it
imports a sibling module from its PARENT directory. No bus, no cortex-update, no
live state — the stub's `UPDATE_PENDING_DIR` is a temp dir.
"""

import importlib.util
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HANDLER = REPO / "ops" / "scripts" / "agent" / "agent-message-handler.py"


def _worker_code() -> str:
    """The worker source exactly as the handler spawns it."""
    os.environ.setdefault("AGENT_NAME", "worker-under-test")
    sys.path.insert(0, str(REPO / "ops" / "scripts"))
    spec = importlib.util.spec_from_file_location("amh_under_test", HANDLER)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._update_worker_code()


def _stub_handler_dir(tmp_path: Path) -> tuple[Path, Path]:
    """A scripts/agent/stub_handler.py that imports from its PARENT dir.

    This is the real handler's shape: `from hermes_paths import ...` resolves to
    ops/scripts/hermes_paths.py, one level ABOVE the handler's own directory.
    """
    scripts = tmp_path / "scripts"
    agent_dir = scripts / "agent"
    agent_dir.mkdir(parents=True)
    results = tmp_path / "results"
    results.mkdir()
    (scripts / "parent_dir_module.py").write_text("VALUE = 'loaded-from-parent'\n")
    (agent_dir / "stub_handler.py").write_text(
        textwrap.dedent(
            f"""
            from pathlib import Path
            from parent_dir_module import VALUE

            UPDATE_PENDING_DIR = Path({str(results)!r})

            def process_update_request(msg_body, corr):
                return {{"success": True, "git_sha_after": "deadbeefcafe", "value": VALUE}}
            """
        )
    )
    return agent_dir / "stub_handler.py", results


def test_worker_loads_a_handler_that_imports_from_its_parent_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_NAME", "worker-under-test")
    stub, results = _stub_handler_dir(tmp_path)

    corr = "test-worker-load"
    (results / f"{corr}.running").write_text("0")  # as the handler writes it before spawning

    r = subprocess.run(
        [sys.executable, "-c", _worker_code(), str(stub), json.dumps({"body": {}}), corr],
        capture_output=True,
        text=True,
        timeout=60,
    )

    written = results / f"{corr}.json"
    assert written.exists(), (
        "the worker wrote no result: it died while loading the handler, which costs "
        f"the requester the whole 30-minute timeout (rc={r.returncode}, stderr={r.stderr[-400:]})"
    )
    assert json.loads(written.read_text())["value"] == "loaded-from-parent", (
        "the worker must run the handler it loaded, not a silent no-op"
    )
    assert not (results / f"{corr}.running").exists(), (
        "the in-flight marker must be cleared on the loader path too"
    )


def test_an_unloadable_handler_still_yields_a_result(tmp_path, monkeypatch):
    """Silence is not an outcome.

    The load must sit INSIDE the try: a handler that cannot be imported is as
    reportable as a failed deploy, and the sweep can only send what exists.
    """
    monkeypatch.setenv("AGENT_NAME", "worker-under-test")
    agent_dir = tmp_path / "scripts" / "agent"
    agent_dir.mkdir(parents=True)
    broken = agent_dir / "broken_handler.py"
    broken.write_text("import a_module_that_does_not_exist\n")

    deploy = tmp_path / "deploy"
    pending = deploy / "state" / "pending-update-results"
    pending.mkdir(parents=True)

    corr = "test-worker-broken"
    env = {**os.environ, "CORTEX_DEPLOY_HOME": str(deploy)}
    r = subprocess.run(
        [sys.executable, "-c", _worker_code(), str(broken), json.dumps({"body": {}}), corr],
        capture_output=True,
        text=True,
        timeout=60,
        env=env,
    )

    written = pending / f"{corr}.json"
    assert written.exists(), (
        "an unloadable handler must still produce a result on the fallback path, "
        f"never silence (rc={r.returncode}, stderr={r.stderr[-300:]})"
    )
    result = json.loads(written.read_text())
    assert result["success"] is False
    assert "crashed" in result["error"]
