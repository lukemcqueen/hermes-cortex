#!/usr/bin/env python3
"""The skill-parity check must FAIL on the pre-sync revision, not merely pass.

A guard only ever run against the healthy state is a happy path with a name.
This drives ops/scripts/manage/check-skill-drift-parity.py against the revision
before the deployed->repo skill sync (where the skills were still stranded) and
against the working tree, using a throwaway git worktree whose mtimes are aged:
the check decides direction by mtime, so a fresh checkout would otherwise look
like "repo newer" and hide the drift.
"""
import importlib.util
import os
import subprocess
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_CHECKER = _REPO / "ops" / "scripts" / "manage" / "check-skill-drift-parity.py"
# The commit immediately before the deployed->repo skill sync.
_PRE_SYNC_SHA = "8c0212ec"
_AGED = 1_000_000_000  # 2001 — unambiguously older than any deployed copy
_KNOWN_STRANDED = "devops/governance-closeout/SKILL.md"


def _load():
    spec = importlib.util.spec_from_file_location("skill_drift_parity", _CHECKER)
    assert spec is not None and spec.loader is not None, f"cannot load {_CHECKER}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_parity_check_discriminates(tmp_path, monkeypatch):
    mod = _load()
    worktree = tmp_path / "wt"
    subprocess.run(
        ["git", "-C", str(_REPO), "worktree", "add", "-q", "--detach",
         str(worktree), _PRE_SYNC_SHA],
        check=True,
    )
    try:
        for path in (worktree / "skills").rglob("*"):
            if path.is_file():
                os.utime(path, (_AGED, _AGED))
        monkeypatch.setattr(mod, "REPO_SKILLS", worktree / "skills")
        stranded, _, _ = mod.survey()
        assert _KNOWN_STRANDED in stranded, (
            f"pre-sync revision should report {_KNOWN_STRANDED} as stranded; "
            f"got {stranded}"
        )
    finally:
        subprocess.run(
            ["git", "-C", str(_REPO), "worktree", "remove", "--force", str(worktree)],
            check=False,
        )

    monkeypatch.setattr(mod, "REPO_SKILLS", _REPO / "skills")
    stranded_now, _, _ = mod.survey()
    assert stranded_now == [], f"working tree still stranded: {stranded_now}"
