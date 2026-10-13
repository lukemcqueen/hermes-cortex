#!/usr/bin/env python3
"""A `.git` DIRECTORY that holds nothing is not a repository.

Measured 2026-10-14: `~/proj/.git/` was an empty directory, so the doctor's dev-repo scan
(which only asks `find ~ -maxdepth 3 -name .git -type d`) called it a dev repo, warned that its
AGENTS.md lacked the fleet efficiency block, and printed a fix command
(`apply-repo-efficiency.py ~/proj --commit`) that CANNOT run — git answers "not a git
repository". A check must not prescribe a command against a repo that does not exist.

Run: python3 -m pytest tests/test_doctor_dev_repo_detection.py -q
"""
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO / "ops" / "scripts" / "manage") not in sys.path:
    sys.path.insert(0, str(_REPO / "ops" / "scripts" / "manage"))

from cortex_doctor import checks  # noqa: E402
from cortex_doctor.results import Results  # noqa: E402


def test_an_empty_git_dir_is_not_a_repo(tmp_path):
    empty = tmp_path / "proj"
    (empty / ".git").mkdir(parents=True)
    (empty / "AGENTS.md").write_text("# looks like a repo\n")
    assert checks._is_git_repo(empty) is False
    print("  an empty .git/ directory is not a repo ✓")


def test_a_real_repo_and_a_worktree_pointer_are_repos(tmp_path):
    real = tmp_path / "real"
    (real / ".git").mkdir(parents=True)
    (real / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    assert checks._is_git_repo(real) is True

    wt = tmp_path / "wt"
    wt.mkdir()
    (wt / ".git").write_text("gitdir: /elsewhere/.git/worktrees/wt\n")
    assert checks._is_git_repo(wt) is True
    print("  a real repo and a worktree .git FILE are repos ✓")


def test_the_dev_repo_scan_does_not_warn_about_a_non_repo(tmp_path, monkeypatch):
    """The integration half: the warning AND its unrunnable fix command must not be emitted for a
    directory that is not a repository."""
    proj = tmp_path / "proj"
    (proj / ".git").mkdir(parents=True)
    (proj / "AGENTS.md").write_text("# no efficiency block here\n")
    monkeypatch.setattr(checks, "HOME", tmp_path)
    monkeypatch.setattr(checks, "CORTEX_REPO", _REPO)

    res = Results()
    checks.check_dev_repo_agents(res)
    offenders = [c for c in res.checks
                 if "proj" in c["name"] and "efficiency" in c["name"]]
    assert not offenders, f"warned about a non-repo: {offenders}"
    print("  no efficiency warning for a directory that is not a repo ✓")


def test_a_worktree_of_the_cortex_repo_is_not_a_dev_repo(tmp_path, monkeypatch):
    """A worktree of the cortex repo carries the CORTEX repo's AGENTS.md on a session branch.
    Treating it as a dev repo warns about a block that belongs to the cortex repo (enforced by
    the repo check) and points the fix command at a session branch — measured 2026-10-14 with
    ~/hc-session2. Its `.git` FILE names the real gitdir."""
    cortex = tmp_path / "hermes-cortex"
    (cortex / ".git" / "worktrees" / "wt").mkdir(parents=True)
    (cortex / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (cortex / "AGENTS.md").write_text("# cortex\n")
    wt = tmp_path / "hc-session2"
    wt.mkdir()
    (wt / ".git").write_text(f"gitdir: {cortex}/.git/worktrees/wt\n")
    (wt / "AGENTS.md").write_text("# cortex worktree, no efficiency block\n")

    monkeypatch.setattr(checks, "HOME", tmp_path)
    monkeypatch.setattr(checks, "CORTEX_REPO", cortex)
    res = Results()
    checks.check_dev_repo_agents(res)
    offenders = [c for c in res.checks if "hc-session2" in c["name"]]
    assert not offenders, f"warned about a cortex worktree: {offenders}"
    print("  a worktree of the cortex repo is not a dev repo ✓")


def test_a_worktree_of_another_repo_is_still_a_dev_repo(tmp_path, monkeypatch):
    """The narrow rule must not swallow unrelated worktrees."""
    cortex = tmp_path / "hermes-cortex"
    (cortex / ".git").mkdir(parents=True)
    (cortex / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (cortex / "AGENTS.md").write_text("# cortex\n")
    other = tmp_path / "client-src"
    (other / ".git" / "worktrees" / "wt").mkdir(parents=True)
    wt = tmp_path / "client-wt"
    wt.mkdir()
    (wt / ".git").write_text(f"gitdir: {other}/.git/worktrees/wt\n")
    (wt / "AGENTS.md").write_text("# client worktree, no efficiency block\n")

    monkeypatch.setattr(checks, "HOME", tmp_path)
    monkeypatch.setattr(checks, "CORTEX_REPO", cortex)
    res = Results()
    checks.check_dev_repo_agents(res)
    offenders = [c for c in res.checks
                 if "client-wt" in c["name"] and "efficiency" in c["name"]]
    assert offenders, "a non-cortex worktree must still be checked as a dev repo"
    print("  an unrelated worktree is still a dev repo ✓")


def test_a_real_dev_repo_without_the_block_still_warns(tmp_path, monkeypatch):
    """The other direction — the check must still fire on the case it exists for."""
    proj = tmp_path / "client"
    proj.mkdir()
    subprocess.run(["git", "-C", str(proj), "init", "-q"], check=True, capture_output=True)
    (proj / "AGENTS.md").write_text("# client repo, no efficiency block\n")
    monkeypatch.setattr(checks, "HOME", tmp_path)
    monkeypatch.setattr(checks, "CORTEX_REPO", _REPO)

    res = Results()
    checks.check_dev_repo_agents(res)
    offenders = [c for c in res.checks
                 if "client" in c["name"] and "efficiency" in c["name"]]
    assert offenders, "a real dev repo missing the block must still warn"
    print("  a real dev repo without the block still warns ✓")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
