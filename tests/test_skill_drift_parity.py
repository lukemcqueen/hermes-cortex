#!/usr/bin/env python3
"""The skill-parity check must FAIL on the pre-sync revision, not merely pass.

A guard only ever run against the healthy state is a happy path with a name.
This drives ops/scripts/manage/check-skill-drift-parity.py against the revision
before the deployed->repo skill sync (where the skills were still stranded) and
against the working tree, using a throwaway git worktree.

The worktree's files carry FRESH mtimes from the checkout, and the check still
reports the drift — direction is decided by content, not mtime, so a clone or
checkout cannot hide stranded content.
"""
import importlib.util
import subprocess
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_CHECKER = _REPO / "ops" / "scripts" / "manage" / "check-skill-drift-parity.py"
# The commit immediately before the deployed->repo skill sync.
_PRE_SYNC_SHA = "8c0212ec"
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

    # POSITIVE CONTROLS, hermetic. The live tree is deliberately NOT asserted: deployed-vs-
    # repo drift is a ROUTINE pipeline condition (a lesson written on the deployed copy is
    # synced back by the lifecycle run — see orch-skill-lifecycle, "Deployed-vs-repo skill
    # drift is now the MOST COMMON Phase 3 action"), so asserting a clean live tree would
    # make this REGRESSION gate flap on normal operation. What must hold is that the checker
    # discriminates — in both directions — and that is testable without the live tree.
    with tempfile.TemporaryDirectory() as td:
        dep = Path(td) / "deployed"
        src = Path(td) / "repo" / "skills"
        for root in (dep, src):
            (root / "cat" / "demo").mkdir(parents=True)
        (dep / "cat" / "demo" / "SKILL.md").write_text("synced body\n")
        (src / "cat" / "demo" / "SKILL.md").write_text("synced body\n")
        monkeypatch.setattr(mod, "DEPLOY_SKILLS", dep)
        monkeypatch.setattr(mod, "REPO_SKILLS", src)
        monkeypatch.setattr(mod, "ARTIFACT", Path(td) / "artifact.txt")

        clean, in_sync, _ = mod.survey()
        assert clean == [], f"a SYNCED tree must report nothing; got {clean}"
        assert in_sync == 1, f"the synced file must count as in sync; got {in_sync}"

        (dep / "cat" / "demo" / "SKILL.md").write_text("deployed-only body\n")
        drifted, _, _ = mod.survey()
        assert drifted == ["cat/demo/SKILL.md"], \
            f"deployed-ONLY content must be reported as stranded; got {drifted}"
        print("  discriminates: synced -> nothing, deployed-only -> reported ✓")


class _Monkeypatch:
    """Minimal stand-in for pytest's monkeypatch — setattr, with undo.

    This file must run under plain `python3` (the regression harness requires a
    __main__ runner, and pytest is not on every host), so the two fixtures the case
    asks for are supplied here.
    """

    def __init__(self):
        self._undo = []

    def setattr(self, target, name, value):
        self._undo.append((target, name, target.__dict__.get(name)))
        setattr(target, name, value)

    def undo(self):
        for target, name, old in reversed(self._undo):
            if old is None:
                delattr(target, name)
            else:
                setattr(target, name, old)


def _main():
    """Standalone runner — without this the file imports, runs nothing, exits 0."""
    print("running 1 case(s)")
    monkey = _Monkeypatch()
    try:
        with tempfile.TemporaryDirectory() as td:
            test_parity_check_discriminates(Path(td), monkey)
    finally:
        monkey.undo()
    print("[PASS] test_parity_check_discriminates")
    print("RESULT: ALL PASS (1 tests)")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
