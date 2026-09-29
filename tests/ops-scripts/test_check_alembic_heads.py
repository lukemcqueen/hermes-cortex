"""check-alembic-heads.py — static migration-head integrity contract tests.

Runs the real script (subprocess) against tmp_path Alembic versions dirs
(preferring migration files as Alembic actually emits them: `revision: str = ...`
typed annotations and multiline `down_revision` tuples).
"""
import subprocess
import sys
from pathlib import Path

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "ops" / "scripts" / "project-run-scripts" / "scripts" / "check-alembic-heads.py"
)


def _run(versions_dir):
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(versions_dir)],
        capture_output=True, text=True, timeout=30,
    )


def _write(dirpath, name, body):
    f = dirpath / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(body, encoding="utf-8")


# ── single head ──────────────────────────────────────────────
def test_single_head_passes(tmp_path):
    _write(tmp_path, "rev1.py",
           "revision: str = 'aaaa0001'\ndown_revision: Union[str, None] = None\n")
    r = _run(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "single head: aaaa0001" in r.stdout


def test_untyped_classic_single_head_passes(tmp_path):
    # The classic (pre-typed) form must keep working too.
    _write(tmp_path, "rev1.py",
           "revision = 'aaaa0001'\ndown_revision = None\n")
    r = _run(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "single head: aaaa0001" in r.stdout


# ── multiple heads ───────────────────────────────────────────
def test_multiple_heads_fails(tmp_path):
    _write(tmp_path, "rev1.py", "revision: str = 'aaaa0001'\ndown_revision = None\n")
    _write(tmp_path, "rev2.py",
           "revision: str = 'bbbb0002'\ndown_revision = 'aaaa0001'\n")
    _write(tmp_path, "rev3.py",
           "revision: str = 'cccc0003'\ndown_revision = 'aaaa0001'\n")
    r = _run(tmp_path)
    assert r.returncode == 1
    assert "2 Alembic heads" in r.stdout
    assert "cccc0003" in r.stdout and "bbbb0002" in r.stdout


# ── multiline down_revision tuple ────────────────────────────
def test_multiline_merge_tuple_parses_as_single_head(tmp_path):
    # A merge revision whose down_revision tuple spans multiple lines must
    # be parsed (re.DOTALL) — both parents end up consumed by the merge head.
    _write(tmp_path, "rev1.py", "revision: str = 'aaaa0001'\ndown_revision = None\n")
    _write(tmp_path, "rev2.py",
           "revision: str = 'bbbb0002'\ndown_revision = 'aaaa0001'\n")
    _write(tmp_path, "rev3.py",
           "revision: str = 'cccc0003'\ndown_revision = (\n"
           "    'aaaa0001',\n    'bbbb0002',\n)\n")
    r = _run(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "single head: cccc0003" in r.stdout


# ── revision id length ───────────────────────────────────────
def test_overlong_revision_id_fails(tmp_path):
    _write(tmp_path, "rev1.py",
           "revision: str = 'x' * 40  # would be 40 chars, but as a literal:\n")
    # Rewrite with an actually-over-long literal id.
    _write(tmp_path, "rev1.py",
           "revision: str = 'this-revision-id-is-way-too-long-over-32-chars'\n"
           "down_revision = None\n")
    r = _run(tmp_path)
    assert r.returncode == 1
    assert "is 46 chars (max 32)" in r.stdout


# ── missing / empty dir ──────────────────────────────────────
def test_missing_dir_fails(tmp_path):
    r = _run(tmp_path / "does-not-exist")
    assert r.returncode == 1
    assert "Versions dir not found" in r.stdout


def test_empty_dir_fails(tmp_path):
    (tmp_path / "versions").mkdir()
    r = _run(tmp_path / "versions")
    assert r.returncode == 1
    assert "No migration files found" in r.stdout
