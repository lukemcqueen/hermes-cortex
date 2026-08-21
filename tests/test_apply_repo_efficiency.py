#!/usr/bin/env python3
"""Tests for apply-repo-efficiency.py — fleet session-efficiency block (O7-S2).

Run: python3 tests/test_apply_repo_efficiency.py
     (or: python3 -m pytest tests/test_apply_repo_efficiency.py -v)

Verifies:
  1. Applies the block to an existing AGENTS.md (append, not overwrite)
  2. Creates AGENTS.md when missing
  3. Idempotent: second run SKIPs
  4. --commit lands the change in git history
  5. --dry-run writes nothing
"""
import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_APPLIER = _REPO / "ops" / "scripts" / "manage" / "apply-repo-efficiency.py"

_spec = importlib.util.spec_from_file_location("are", str(_APPLIER))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


def _make_repo(tmp: Path, name: str, with_agents: bool = True) -> Path:
    repo = tmp / name
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t.local"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "T"], check=True)
    if with_agents:
        (repo / "AGENTS.md").write_text("## Project Rules\n- convention\n", encoding="utf-8")
    else:
        (repo / "README.md").write_text("# Project\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "init"], check=True)
    return repo


def test_append_to_existing():
    with tempfile.TemporaryDirectory() as td:
        repo = _make_repo(Path(td), "existing")
        msg, changed = _mod.apply_to(repo, dry_run=False)
        assert changed is True
        assert "OK" in msg
        content = (repo / "AGENTS.md").read_text()
        assert "## Project Rules" in content, "original content must survive"
        assert _mod.MARKER in content, "block marker must be present"


def test_create_when_missing():
    with tempfile.TemporaryDirectory() as td:
        repo = _make_repo(Path(td), "noagents", with_agents=False)
        msg, changed = _mod.apply_to(repo, dry_run=False)
        assert changed is True
        assert (repo / "AGENTS.md").exists()
        assert _mod.MARKER in (repo / "AGENTS.md").read_text()


def test_idempotent_skip():
    with tempfile.TemporaryDirectory() as td:
        repo = _make_repo(Path(td), "idem")
        _mod.apply_to(repo, dry_run=False)
        msg, changed = _mod.apply_to(repo, dry_run=False)
        assert changed is False
        assert "SKIP" in msg


def test_commit_lands_in_history():
    with tempfile.TemporaryDirectory() as td:
        repo = _make_repo(Path(td), "commitme")
        msg, changed = _mod.apply_to(repo, dry_run=False, commit=True)
        assert changed is True
        log = subprocess.run(["git", "-C", str(repo), "log", "--oneline", "-2"],
                             capture_output=True, text=True).stdout
        assert "efficiency" in log, "commit message must be in history"
        status = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"],
                                capture_output=True, text=True).stdout
        assert status.strip() == "", "repo must be clean after --commit"


def test_dry_run_writes_nothing():
    with tempfile.TemporaryDirectory() as td:
        repo = _make_repo(Path(td), "dry")
        before = (repo / "AGENTS.md").read_text()
        msg, changed = _mod.apply_to(repo, dry_run=True)
        assert changed is False
        assert (repo / "AGENTS.md").read_text() == before, "dry-run must not write"


if __name__ == "__main__":
    import traceback
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(fns)-failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
