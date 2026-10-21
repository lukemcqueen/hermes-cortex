#!/usr/bin/env python3
"""Tests for publishing cortex defaults at the agent-visible skills location (cycle 13491).

Fabricated trees only. The mechanism under test was chosen from a measured probe:
a symlinked ROOT is visible to a plain `rglob`/`os.walk` scan, a per-skill symlink
farm is NOT — so `root` mode is the default and `copy` mode the escape hatch.
"""

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO / "ops" / "scripts" / "manage" / "publish-agent-skills.py"


def _skill(root: Path, rel: str, marker="v1"):
    d = root / rel
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(f"---\nname: {d.name}\ndescription: d\n---\n{marker}\n")
    (d / "references").mkdir(exist_ok=True)
    (d / "references" / "note.md").write_text(f"note {marker}\n")
    return d


def _run(defaults, published, *extra):
    cmd = [sys.executable, str(TOOL), "--from", str(defaults), "--to", str(published), *extra]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)


def _visible(root: Path) -> int:
    """What a PLAIN scan sees — the harness's own view."""
    return len(list(root.rglob("SKILL.md"))) if root.exists() else 0


def _tree(tmp_path):
    return tmp_path / "cortex" / "skills", tmp_path / "agents" / "skills"


# ── root mode (default) ───────────────────────────────────────────────────

def test_root_mode_publishes_a_pointer_plainly_visible(tmp_path):
    defaults, published = _tree(tmp_path)
    _skill(defaults, "workflow/task-start")
    _skill(defaults, "devops/shell-scripting")
    _skill(defaults, "root-skill")

    r = _run(defaults, published)
    assert r.returncode == 0, r.stdout + r.stderr
    assert published.is_symlink()
    assert os.path.realpath(published) == os.path.realpath(defaults)
    assert _visible(published) == 3
    assert "note v1" in (published / "workflow" / "task-start" / "references" / "note.md").read_text()


def test_root_mode_propagates_updates_without_a_sync_step(tmp_path):
    defaults, published = _tree(tmp_path)
    src = _skill(defaults, "workflow/task-start")
    assert _run(defaults, published).returncode == 0

    (src / "SKILL.md").write_text("---\nname: task-start\ndescription: d\n---\nUPDATED\n")
    _skill(defaults, "brand-new/skill")
    assert "UPDATED" in (published / "workflow" / "task-start" / "SKILL.md").read_text()
    assert _visible(published) == 2, "a dynamically added skill is visible immediately"


def test_root_mode_is_idempotent(tmp_path):
    defaults, published = _tree(tmp_path)
    _skill(defaults, "workflow/task-start")
    assert _run(defaults, published).returncode == 0
    assert _run(defaults, published).returncode == 0
    assert _run(defaults, published, "--check").returncode == 0


def test_root_mode_check_reports_drift_and_creates_nothing(tmp_path):
    defaults, published = _tree(tmp_path)
    _skill(defaults, "workflow/task-start")
    r = _run(defaults, published, "--check")
    assert r.returncode == 1, r.stdout + r.stderr
    assert not published.exists(), "--check must not publish"


def test_foreign_real_tree_at_published_needs_an_explicit_decision(tmp_path):
    defaults, published = _tree(tmp_path)
    _skill(defaults, "workflow/task-start")
    _skill(published, "someone-elses-skill")

    r = _run(defaults, published)
    assert r.returncode == 4, r.stdout + r.stderr
    assert not published.is_symlink()
    assert (published / "someone-elses-skill" / "SKILL.md").exists()
    assert not list(published.parent.glob("skills.pre-publish-*"))


def test_adopt_published_preserves_the_foreign_tree_by_rename(tmp_path):
    defaults, published = _tree(tmp_path)
    _skill(defaults, "workflow/task-start")
    _skill(published, "someone-elses-skill")

    r = _run(defaults, published, "--adopt-published")
    assert r.returncode == 0, r.stdout + r.stderr
    assert published.is_symlink()
    backups = list(published.parent.glob("skills.pre-publish-*"))
    assert backups, "the foreign tree must be preserved, not deleted"
    assert (backups[0] / "someone-elses-skill" / "SKILL.md").exists()
    assert _visible(published) == 1


def test_foreign_symlink_elsewhere_needs_a_decision(tmp_path):
    defaults, published = _tree(tmp_path)
    _skill(defaults, "workflow/task-start")
    other = tmp_path / "elsewhere"
    other.mkdir(parents=True)

    published.parent.mkdir(parents=True, exist_ok=True)
    os.symlink(other, published)
    r = _run(defaults, published)
    assert r.returncode == 4, r.stdout + r.stderr
    assert os.path.realpath(published) == os.path.realpath(other)


def test_empty_published_dir_is_replaced_without_a_decision(tmp_path):
    defaults, published = _tree(tmp_path)
    _skill(defaults, "workflow/task-start")
    published.mkdir(parents=True)

    r = _run(defaults, published)
    assert r.returncode == 0, r.stdout + r.stderr
    assert published.is_symlink()


def test_missing_defaults_is_could_not_verify(tmp_path):
    defaults, published = _tree(tmp_path)
    r = _run(defaults, published, "--check")
    assert r.returncode == 3, r.stdout + r.stderr


def test_empty_defaults_is_could_not_verify(tmp_path):
    defaults, published = _tree(tmp_path)
    defaults.mkdir(parents=True)
    r = _run(defaults, published)
    assert r.returncode == 3, r.stdout + r.stderr


# ── copy mode (escape hatch) ──────────────────────────────────────────────

def test_copy_mode_materializes_real_files(tmp_path):
    defaults, published = _tree(tmp_path)
    _skill(defaults, "workflow/task-start")
    r = _run(defaults, published, "--mode", "copy")
    assert r.returncode == 0, r.stdout + r.stderr
    dst = published / "workflow" / "task-start"
    assert dst.is_dir() and not dst.is_symlink()
    assert (dst / "references" / "note.md").exists()
    assert _visible(published) == 1


def test_copy_mode_refreshes_and_check_reports_drift(tmp_path):
    defaults, published = _tree(tmp_path)
    src = _skill(defaults, "workflow/task-start")
    assert _run(defaults, published, "--mode", "copy").returncode == 0

    (src / "SKILL.md").write_text("---\nname: task-start\ndescription: d\n---\nUPDATED\n")
    assert _run(defaults, published, "--mode", "copy", "--check").returncode == 1
    assert _run(defaults, published, "--mode", "copy").returncode == 0
    assert "UPDATED" in (published / "workflow" / "task-start" / "SKILL.md").read_text()


def test_copy_mode_reports_foreign_without_deleting_it(tmp_path):
    defaults, published = _tree(tmp_path)
    _skill(defaults, "workflow/task-start")
    assert _run(defaults, published, "--mode", "copy").returncode == 0
    foreign = published / "someone-elses-skill"
    foreign.mkdir(parents=True)
    (foreign / "SKILL.md").write_text("---\nname: someone-elses-skill\ndescription: d\n---\n")

    r = _run(defaults, published, "--mode", "copy")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "FOREIGN" in r.stdout
    assert (foreign / "SKILL.md").exists()
