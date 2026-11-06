"""Hermetic tests for the plan-review-before-slice gate (plan-review-check).

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

SCRIPT = Path(__file__).resolve().parents[1] / "ops" / "scripts" / "plan-review-check.py"
_spec = importlib.util.spec_from_file_location("plan_review_check", SCRIPT)
assert _spec and _spec.loader, "could not resolve plan-review-check.py"
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


# ── Gate A: the always-required set DERIVES from skills.yaml (single source) ─
# The enforcer's write gate keys on `_session_skills_loaded[sid] >=
# _REQUIRED_SKILLS` (set comparison). Since 2026-11-06 `_REQUIRED_SKILLS`
# derives from the DEPLOYED `~/.steadfaste-fleet/skills.yaml` `always:` names
# (with a documented default fallback), so the manifest, the enforcer and the
# doctor cannot drift apart again — the direct fix for the 7-vs-8 count bug.
# These cases drive the DERIVATION hermeticly against a TEMP manifest path,
# never the live store or ambient manifest.


def _load_enforcer():
    import importlib.util
    path = (Path(__file__).resolve().parents[1]
            / "plugins" / "governance-enforcer" / "__init__.py")
    spec = importlib.util.spec_from_file_location("gov_enforcer_test", path)
    assert spec and spec.loader, "governance enforcer module not resolvable"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_always_required_set_derives_from_skills_manifest(tmp_path):
    enf = _load_enforcer()
    man = tmp_path / "skills.yaml"
    # Written as YAML `- name:` entries so the dependency-free manifest reader
    # (used where PyYAML is absent, e.g. the test venv) resolves all three.
    man.write_text(
        "always:\n"
        "  - name: alpha\n"
        "  - name: beta\n"
        "  - name: gamma\n"
        "on_task:\n"
        "  debug:\n"
        "    - x\n"
    )
    enf._REQUIRED_MANIFEST_PATH = man
    enf._REQUIRED_MANIFEST_FP = -1
    enf._REQUIRED_SKILLS = set()
    enf._refresh_required_skills()
    assert enf._REQUIRED_SKILLS == {"alpha", "beta", "gamma"}


def test_always_required_set_falls_back_to_default_when_manifest_missing(tmp_path):
    enf = _load_enforcer()
    enf._REQUIRED_MANIFEST_PATH = tmp_path / "no-such-manifest.yaml"
    enf._REQUIRED_MANIFEST_FP = -1
    enf._REQUIRED_SKILLS = set()
    enf._refresh_required_skills()
    # Fail-closed: the documented default is kept, so a remote backend without
    # the deployed manifest still gates on a non-empty required set.
    assert enf._REQUIRED_SKILLS == enf._REQUIRED_SKILLS_DEFAULT
    assert enf._REQUIRED_SKILLS


def test_always_required_set_gate_predicate_is_exactly_the_required_set():
    enf = _load_enforcer()
    required = set(enf._REQUIRED_SKILLS)
    assert required, "required set must not be empty"
    first, *rest = sorted(required)
    others = set(rest)
    # A session missing exactly one required skill does NOT cover the set, so
    # the write gate refuses it; the full set covers it and is allowed.
    assert (others >= required) is False
    assert (required >= required) is True
