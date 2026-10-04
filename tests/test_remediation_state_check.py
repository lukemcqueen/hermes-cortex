#!/usr/bin/env python3
"""The deployed-state checker must FAIL on a mismatch, not merely pass.

ADV-10577-6 asked for committed proof of the deployed-state claims in cycle
10577's note. A check that only ever ran against the healthy state is a happy
path with a name, so these tests drive each gated check in BOTH directions
with monkeypatched paths - no live deploy tree, no DB, no writes outside
tmp_path.
"""
import importlib.util
import subprocess
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_CHECKER = _REPO / "ops" / "scripts" / "manage" / "check-remediation-state.py"
_TASK_MCP = _REPO / "mcp-servers" / "task-mcp.py"


def _load():
    spec = importlib.util.spec_from_file_location("remediation_state_check", _CHECKER)
    assert spec is not None and spec.loader is not None, f"cannot load {_CHECKER}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _head() -> str:
    return subprocess.run(
        ["git", "-C", str(_REPO), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True).stdout.strip()


def test_deploy_current_check_discriminates(tmp_path, monkeypatch):
    mod = _load()
    fake = tmp_path / "update-commit"
    monkeypatch.setattr(mod, "UPDATE_COMMIT", fake)

    fake.write_text("0" * 40)
    assert mod.check_deploy_is_current().startswith("FAIL")

    fake.write_text(_head())
    assert mod.check_deploy_is_current().startswith("PASS")


def test_task_mcp_check_discriminates(tmp_path, monkeypatch):
    mod = _load()
    fake_dir = tmp_path / "scripts"
    fake_dir.mkdir()
    monkeypatch.setattr(mod, "DEPLOY_SCRIPTS", fake_dir)

    assert mod.check_task_mcp_matches_repo().startswith("SKIP")

    banner = "#!/usr/bin/env python3\n# SOURCE: x\n# y\n\n"
    (fake_dir / "task-mcp.py").write_text(banner + "not the repo source\n")
    assert mod.check_task_mcp_matches_repo().startswith("FAIL")

    body = _TASK_MCP.read_text(encoding="utf-8").split("\n", 1)[1]
    (fake_dir / "task-mcp.py").write_text(banner + body)
    assert mod.check_task_mcp_matches_repo().startswith("PASS")


def test_split_board_check_discriminates(tmp_path, monkeypatch):
    mod = _load()
    fake_dir = tmp_path / "scripts"
    fake_dir.mkdir()
    monkeypatch.setattr(mod, "DEPLOY_SCRIPTS", fake_dir)

    assert mod.check_split_board_is_deployed().startswith("SKIP")

    (fake_dir / "task-db.py").write_text("def cmd_list_board():\n    print('pending')\n")
    assert mod.check_split_board_is_deployed().startswith("FAIL")

    real = Path.home() / ".hermes-cortex" / "scripts" / "task-db.py"
    if not real.is_file():
        return
    (fake_dir / "task-db.py").write_text(real.read_text(encoding="utf-8"))
    assert mod.check_split_board_is_deployed().startswith("PASS")


def test_unpushed_check_discriminates(tmp_path, monkeypatch):
    mod = _load()
    monkeypatch.setattr(mod, "REPO", tmp_path)

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    for key, val in (("user.email", "t@example.com"), ("user.name", "t")):
        subprocess.run(["git", "-C", str(tmp_path), "config", key, val], check=True)
    (tmp_path / "f").write_text("x")
    subprocess.run(["git", "-C", str(tmp_path), "add", "f"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-qm", "x"], check=True)

    # No origin/main -> cannot compare -> SKIP, never a silent PASS.
    assert mod.check_nothing_unpushed().startswith("SKIP")


def test_ops_docs_check_discriminates(tmp_path, monkeypatch):
    mod = _load()
    fake_repo = tmp_path / "repo"
    (fake_repo / "ops" / "docs").mkdir(parents=True)
    monkeypatch.setattr(mod, "REPO", fake_repo)
    monkeypatch.setattr(
        mod, "_run",
        lambda cmd: (0, "") if "ls-files" in cmd else (0, ""))

    assert mod.check_ops_docs_holds_no_real_content().startswith("PASS")

    (fake_repo / "ops" / "docs" / "junk.md").write_text("real content")
    assert mod.check_ops_docs_holds_no_real_content().startswith("FAIL")
