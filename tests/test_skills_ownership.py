#!/usr/bin/env python3
"""Tests for skills-tree ownership inversion (cycle 13491).

The migration tool runs against FABRICATED trees only — never the live
~/.hermes or ~/.hermes-cortex paths. Every case asserts that no tree is
DELETED: the non-winner is preserved by rename.

Exit-code contract under test:
  0  NEW (cortex real, borrower is a symlink to it) — or applied successfully
  1  OLD direction (cortex is a symlink into the borrower) — migratable
  3  COULD NOT VERIFY (a path is missing / dangling / unresolvable)
  4  BOTH REAL — needs an explicit operator decision, nothing was touched
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "ops" / "scripts" / "manage" / "migrate-skills-ownership.py"

OLD, NEW, UNVERIFIABLE, NEEDS_DECISION = 1, 0, 3, 4


def _make_tree(root: Path, names, marker="x"):
    """Create <root>/<cat>/<name>/SKILL.md trees; returns the file map."""
    made = {}
    for n in names:
        d = root / "cat" / n
        d.mkdir(parents=True, exist_ok=True)
        f = d / "SKILL.md"
        f.write_text(f"---\nname: {n}\ndescription: {marker}\n---\nbody {n}\n")
        made[n] = f
    return made


def _count(root: Path) -> int:
    return sum(1 for _ in root.rglob("SKILL.md"))


def _run(cortex: Path, borrower: Path, *extra):
    cmd = [sys.executable, str(TOOL),
           "--cortex-root", str(cortex), "--borrower-root", str(borrower), *extra]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)


@pytest.fixture()
def paths(tmp_path):
    return tmp_path / "cortex" / "skills", tmp_path / "borrower" / "skills"


# ── classification ────────────────────────────────────────────────────────

def test_old_direction_is_detected_and_not_mutated_by_check(paths):
    cortex, borrower = paths
    _make_tree(borrower, ["alpha", "beta"])
    cortex.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(borrower, cortex)                      # OLD: cortex -> borrower

    r = _run(cortex, borrower, "--check")
    assert r.returncode == OLD, r.stdout + r.stderr
    assert cortex.is_symlink()                        # --check never mutates
    assert not borrower.is_symlink()
    assert _count(borrower) == 2


def test_new_direction_is_a_noop(paths):
    cortex, borrower = paths
    _make_tree(cortex, ["alpha", "beta"])
    borrower.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(cortex, borrower)                      # NEW

    r = _run(cortex, borrower)                        # apply = no-op
    assert r.returncode == NEW, r.stdout + r.stderr
    assert not cortex.is_symlink()
    assert borrower.is_symlink()
    assert _count(borrower) == 2                      # readable through the link


def test_missing_paths_are_could_not_verify(paths):
    cortex, borrower = paths
    cortical = _run(cortex, borrower, "--check")
    assert cortical.returncode == UNVERIFIABLE, cortical.stdout + cortical.stderr


def test_dangling_cortex_symlink_is_could_not_verify(paths):
    cortex, borrower = paths
    cortex.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(borrower, cortex)                      # borrower does not exist
    r = _run(cortex, borrower, "--check")
    assert r.returncode == UNVERIFIABLE, r.stdout + r.stderr


def test_cortex_real_and_borrower_absent_is_acceptable(paths):
    """A host with no borrower installed: cortex owns the tree, no pointer needed."""
    cortex, borrower = paths
    _make_tree(cortex, ["alpha"])
    r = _run(cortex, borrower, "--check")
    assert r.returncode == NEW, r.stdout + r.stderr


# ── migration ─────────────────────────────────────────────────────────────

def test_old_to_new_preserves_content_and_count(paths):
    cortex, borrower = paths
    before = _make_tree(borrower, ["alpha", "beta", "gamma"])
    payload = {n: f.read_text() for n, f in before.items()}
    cortex.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(borrower, cortex)
    pre = _count(borrower)

    r = _run(cortex, borrower)
    assert r.returncode == NEW, r.stdout + r.stderr

    assert cortex.is_dir() and not cortex.is_symlink()          # real now
    assert borrower.is_symlink() and os.path.realpath(borrower) == os.path.realpath(cortex)
    assert _count(cortex) == pre
    assert _count(borrower) == pre                              # readable via link
    for n, text in payload.items():
        assert (cortex / "cat" / n / "SKILL.md").read_text() == text
    assert r.returncode == NEW


def test_migration_is_idempotent(paths):
    cortex, borrower = paths
    _make_tree(borrower, ["alpha"])
    cortex.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(borrower, cortex)
    assert _run(cortex, borrower).returncode == NEW
    second = _run(cortex, borrower)
    assert second.returncode == NEW, second.stdout + second.stderr
    assert _count(borrower) == 1


def test_write_through_borrower_path_lands_in_cortex_tree(paths):
    """The clobber-risk test, made re-executable (ADV-13491-3)."""
    cortex, borrower = paths
    _make_tree(borrower, ["alpha"])
    cortex.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(borrower, cortex)
    assert _run(cortex, borrower).returncode == NEW

    target = borrower / "cat" / "alpha" / "SKILL.md"
    target.write_text("rewritten through the borrower path\n")
    assert (cortex / "cat" / "alpha" / "SKILL.md").read_text() == \
        "rewritten through the borrower path\n"
    assert os.path.realpath(borrower) == os.path.realpath(cortex)


def test_write_through_borrower_does_not_replace_the_symlink(paths):
    """A write must not turn the borrower pointer into a real directory."""
    cortex, borrower = paths
    _make_tree(borrower, ["alpha"])
    cortex.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(borrower, cortex)
    assert _run(cortex, borrower).returncode == NEW

    (borrower / "new-skill").mkdir()
    (borrower / "new-skill" / "SKILL.md").write_text("---\nname: new-skill\ndescription: d\n---\n")
    assert borrower.is_symlink()
    assert (cortex / "new-skill" / "SKILL.md").exists()


# ── both-real: never guess, never delete ─────────────────────────────────

@pytest.mark.parametrize("cortex_n,borrower_n", [(1, 3), (3, 1), (2, 2)])
def test_both_real_needs_a_decision_and_touches_nothing(paths, cortex_n, borrower_n):
    cortex, borrower = paths
    _make_tree(cortex, [f"c{i}" for i in range(cortex_n)])
    _make_tree(borrower, [f"b{i}" for i in range(borrower_n)])

    r = _run(cortex, borrower, "--check")
    assert r.returncode == NEEDS_DECISION, r.stdout + r.stderr
    assert not cortex.is_symlink() and not borrower.is_symlink()
    assert _count(cortex) == cortex_n and _count(borrower) == borrower_n


def test_both_real_equal_counts_divergent_content_is_not_agreement(paths):
    cortex, borrower = paths
    f1 = _make_tree(cortex, ["alpha"], marker="cortex")
    f2 = _make_tree(borrower, ["alpha"], marker="borrower")
    assert f1["alpha"].read_text() != f2["alpha"].read_text()

    r = _run(cortex, borrower, "--check")
    assert r.returncode == NEEDS_DECISION, r.stdout + r.stderr
    assert "diverg" in (r.stdout + r.stderr).lower()


def test_both_real_adopt_hermes_preserves_the_non_winner_by_rename(paths):
    cortex, borrower = paths
    _make_tree(cortex, ["old-only"], marker="cortex")
    _make_tree(borrower, ["new-one", "new-two"], marker="borrower")

    r = _run(cortex, borrower, "--adopt-borrower")
    assert r.returncode == NEW, r.stdout + r.stderr

    assert cortex.is_dir() and not cortex.is_symlink()
    assert borrower.is_symlink()
    assert (cortex / "cat" / "new-one" / "SKILL.md").exists()
    backups = list(cortex.parent.glob("skills.pre-migration-*"))
    assert backups, "the non-winning tree must be preserved, not deleted"
    assert (backups[0] / "cat" / "old-only" / "SKILL.md").exists()


def test_both_real_keep_refuses_without_an_explicit_decision(paths):
    cortex, borrower = paths
    _make_tree(cortex, ["a"])
    _make_tree(borrower, ["b"])
    r = _run(cortex, borrower)
    assert r.returncode == NEEDS_DECISION, r.stdout + r.stderr
    assert not cortex.is_symlink() and not borrower.is_symlink()
    assert not list(cortex.parent.glob("skills.pre-migration-*"))


# ── ownership constant has ONE definition (no per-check literals) ────────

def test_owner_root_resolves_from_one_place():
    """Roots come from the tool's arguments/env — no hardcoded home path, no
    per-host literal, and exactly one definition of each default."""
    src = TOOL.read_text()
    assert "/home/" not in src, "no absolute home path in the tool"
    assert "CORTEX_HOME" in src, "the cortex root default reads the env var"
    assert src.count("default_cortex =") == 1
    assert src.count("default_borrower =") == 1
    # No check may re-derive a root locally: only the two defaults + argparse wiring.
    assert src.count("Path.home()") == 2, "root defaults are defined once each"
