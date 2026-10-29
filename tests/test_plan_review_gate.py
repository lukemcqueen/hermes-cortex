"""Hermetic tests for the plan-review-before-slice gate (hc-plan-review-check).

Drives the DETECTOR with controlled inputs in both directions — never a live
ambient session/DB state (change-checklist: a regression test must exercise the
detector, not ambient state). Creates a scratch git repo for the staged-set
probe and a temp loop-governance DB for the cycle/review probes.
"""
import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "ops" / "scripts" / "hc-plan-review-check.py"
_spec = importlib.util.spec_from_file_location("hc_plan_review_check", SCRIPT)
assert _spec and _spec.loader, "could not resolve hc-plan-review-check.py"
p = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(p)


def _make_repo(tmp_path, files):
    repo = tmp_path / "repo"
    repo.mkdir()
    for name, body in files.items():
        (repo / name).write_text(body)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    return repo


def _seed_db(path, reviewed):
    """Build a minimal loop-governance DB with one cycle + optional review."""
    c = __import__("sqlite3").connect(str(path))
    c.executescript(
        """
        CREATE TABLE loop_cycles(id INTEGER PRIMARY KEY, timestamp TEXT NOT NULL,
          task_id TEXT NOT NULL, cycle_num INTEGER NOT NULL, spec_hash TEXT,
          code_hash TEXT, test_output_hash TEXT, completeness REAL NOT NULL,
          quality REAL NOT NULL, progress REAL NOT NULL, composite REAL NOT NULL,
          no_progress INTEGER NOT NULL DEFAULT 0, decision TEXT NOT NULL,
          user_overrode INTEGER, outcome_note TEXT, schema_version INTEGER,
          model_name TEXT, session_id TEXT, unscored_reason TEXT);
        CREATE TABLE adversarial_reviews(review_id TEXT PRIMARY KEY,
          cycle_id INTEGER NOT NULL, reviewer_id TEXT NOT NULL,
          reviewer_model TEXT NOT NULL, verdict TEXT NOT NULL,
          findings_json TEXT NOT NULL, summary TEXT, ts TEXT NOT NULL,
          fingerprint TEXT);
        """
    )
    c.execute(
        "INSERT INTO loop_cycles(id,timestamp,task_id,cycle_num,completeness,"
        "quality,progress,composite,decision,session_id) "
        "VALUES(101,'2026-10-29','t',1,0,0,0,0,'PENDING','SESS-1')"
    )
    if reviewed:
        c.execute(
            "INSERT INTO adversarial_reviews(review_id,cycle_id,reviewer_id,"
            "reviewer_model,verdict,findings_json,summary,ts) "
            "VALUES('r',101,'adv','deepseek/deepseek-v4-pro','CLEAN','[]',"
            "'reviewed','2026-10-29T00:00:00Z')"
        )
    c.commit()
    c.close()


def _run(db, reviewed, repo, session="SESS-1"):
    _seed_db(db, reviewed)
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--session", session,
         "--repo-root", str(repo), "--db", str(db)],
        capture_output=True, text=True, cwd=repo)


# ── staged_slice (the "is this a slice?" detector) ─────────────────────────

def test_single_small_source_file_is_not_a_slice(tmp_path):
    repo = _make_repo(tmp_path, {"mod.py": "a = 1\n"})
    is_slice, _ = p.staged_slice(str(repo))
    assert is_slice is False


def test_multi_source_file_is_a_slice(tmp_path):
    repo = _make_repo(tmp_path, {"mod.py": "a = 1\n", "mod2.py": "b = 2\n"})
    is_slice, _ = p.staged_slice(str(repo))
    assert is_slice is True


def test_large_single_source_file_is_a_slice(tmp_path):
    repo = _make_repo(tmp_path, {"mod.py": "x = 1\n" * 51})
    is_slice, _ = p.staged_slice(str(repo))
    assert is_slice is True


def test_docs_only_is_not_a_slice(tmp_path):
    repo = _make_repo(tmp_path, {"README.md": "# hi\n", "notes.md": "n\n"})
    is_slice, _ = p.staged_slice(str(repo))
    assert is_slice is False


# ── cycle / review resolution against the temp store ───────────────────────

def test_unreviewed_slice_refused(tmp_path):
    db = tmp_path / "lg.db"
    repo = _make_repo(tmp_path, {"mod.py": "a = 1\n", "mod2.py": "b = 2\n"})
    r = _run(db, reviewed=False, repo=repo)
    assert r.returncode == 1
    assert "PLAN-REVIEW REQUIRED" in r.stderr


def test_reviewed_slice_passes(tmp_path):
    db = tmp_path / "lg.db"
    repo = _make_repo(tmp_path, {"mod.py": "a = 1\n", "mod2.py": "b = 2\n"})
    r = _run(db, reviewed=True, repo=repo)
    assert r.returncode == 0
    assert "reviewed plan" in r.stdout


def test_trivial_passes_even_when_db_missing(tmp_path):
    # A trivial change returns PASS before any DB read — no store dependency.
    db = tmp_path / "does-not-exist.db"
    repo = _make_repo(tmp_path, {"mod.py": "a = 1\n"})
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--session", "SESS-1",
         "--repo-root", str(repo), "--db", str(db)],
        capture_output=True, text=True, cwd=repo)
    assert r.returncode == 0


def test_missing_db_fails_closed_on_slice(tmp_path):
    db = tmp_path / "does-not-exist.db"
    repo = _make_repo(tmp_path, {"mod.py": "a = 1\n", "mod2.py": "b = 2\n"})
    r = _run_slice_missing_db(db, repo)
    assert r.returncode == 3


def _run_slice_missing_db(db, repo):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--session", "SESS-1",
         "--repo-root", str(repo), "--db", str(db)],
        capture_output=True, text=True, cwd=repo)


def test_active_cycle_id(tmp_path):
    db = tmp_path / "lg.db"
    _seed_db(db, reviewed=False)
    assert p.active_cycle_id(db, "SESS-1") == 101
    assert p.active_cycle_id(db, "NO-SUCH-SESSION") is None


def test_cycle_reviewed(tmp_path):
    db = tmp_path / "lg.db"
    _seed_db(db, reviewed=True)
    assert p.cycle_reviewed(db, 101) is True
    _seed_db(tmp_path / "nr.db", reviewed=False)
    assert p.cycle_reviewed(tmp_path / "nr.db", 101) is False
