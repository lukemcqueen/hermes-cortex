"""Skill credit survives a no-op redeploy; invalidation is per-skill (2026-09-23).

Root cause of the fleet's "7/7 loaded ✅ but still blocked" complaint:
`_skills_fingerprint()` hashed skill-file **mtimes**, so a `cortex-update.sh`
deploy that rewrote BYTE-IDENTICAL skill files moved the fingerprint, discarded
the per-session credit journal, and invalidated the 7/7 marker mid-task.

Live proof (moses, 2026-09-23): after a deploy, the plugin reported
test-driven-development as NOT loaded in a session that had loaded it, while
`diff` showed the deployed and repo copies of that SKILL.md were identical and
only the deployed mtime had moved (15:42 → 15:56). Nothing the agent did was
wrong; the fingerprint counted mtime as a content change.

Contract pinned here:
  - the fingerprint is CONTENT-based: mtime-only moves never invalidate
  - a real content change still invalidates, and is named (per skill)
  - credit is dropped PER SKILL, not all-or-nothing, so a weak model reloads
    the one skill that changed instead of the whole always-set
"""

import importlib.util
import json
import os
import tempfile
from pathlib import Path

import pytest

_ENFORCER_PATH = (
    Path(__file__).resolve().parents[2] / "plugins" / "governance-enforcer" / "__init__.py"
)
_spec = importlib.util.spec_from_file_location("governance_enforcer_fp", _ENFORCER_PATH)
enforcer = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(enforcer)

_REQUIRED = sorted(enforcer._REQUIRED_SKILLS)


@pytest.fixture
def skills_tree(monkeypatch):
    """Temp skills root holding one SKILL.md per required skill."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "skills"
        for name in _REQUIRED:
            d = root / name
            d.mkdir(parents=True)
            (d / "SKILL.md").write_text(f"# {name}\nbody-v1\n")
        monkeypatch.setattr(enforcer, "_skills_dir", lambda: root)
        yield root


@pytest.fixture
def state_dir(monkeypatch, skills_tree):
    """Temp governance state dir (credit journal + markers)."""
    with tempfile.TemporaryDirectory() as tmp:
        original = enforcer.GOVERNANCE_STATE_DIR
        enforcer.GOVERNANCE_STATE_DIR = Path(tmp)
        enforcer._session_skills_loaded.clear()
        yield Path(tmp)
        enforcer.GOVERNANCE_STATE_DIR = original
        enforcer._session_skills_loaded.clear()


def _bump_mtime(path: Path, seconds: float = 10.0) -> None:
    """Same bytes, new mtime — exactly what a redeploy of a skill does."""
    st = path.stat()
    os.utime(path, (st.st_atime + seconds, st.st_mtime + seconds))


def _load(sid: str, *skills: str) -> None:
    enforcer._session_skills_loaded.setdefault(sid, set()).update(skills)
    enforcer._persist_session_skills(sid)


# ── fingerprint: content, not mtime ───────────────────────────────────────

def test_fingerprint_ignores_mtime_only_change(skills_tree):
    before = enforcer._skills_fingerprint()
    for name in _REQUIRED:
        _bump_mtime(skills_tree / name / "SKILL.md")
    assert enforcer._skills_fingerprint() == before, (
        "a redeploy of IDENTICAL skill bytes must not change the fingerprint"
    )


def test_fingerprint_changes_on_content_change(skills_tree):
    before = enforcer._skills_fingerprint()
    (skills_tree / "test-driven-development" / "SKILL.md").write_text("# tdd v2\n")
    assert enforcer._skills_fingerprint() != before, (
        "a real skill content change must invalidate the fingerprint"
    )


def test_fingerprint_changes_on_same_size_content_change(skills_tree):
    """Same byte length, different bytes — the mtime-keyed hash cache must miss."""
    before = enforcer._skills_fingerprint()
    (skills_tree / "task-start" / "SKILL.md").write_text("# task-start\nbody-v2\n")
    assert enforcer._skills_fingerprint() != before


# ── credit: per-skill invalidation ────────────────────────────────────────

def test_credit_survives_noop_redeploy(state_dir, skills_tree):
    _load("sess_noop", "test-driven-development", "codebase-design")
    enforcer._session_skills_loaded.clear()          # plugin reload after deploy
    for name in _REQUIRED:
        _bump_mtime(skills_tree / name / "SKILL.md")
    assert enforcer._session_skills("sess_noop") == {
        "test-driven-development", "codebase-design",
    }, "credit must survive a deploy that changed no skill CONTENT"


def test_credit_revoked_only_for_changed_skill(state_dir, skills_tree):
    _load("sess_partial", "test-driven-development", "codebase-design")
    enforcer._session_skills_loaded.clear()
    (skills_tree / "test-driven-development" / "SKILL.md").write_text("# tdd v2\n")
    assert enforcer._session_skills("sess_partial") == {"codebase-design"}, (
        "only the skill whose content changed may lose credit"
    )


def test_stale_skills_names_only_the_changed_one(state_dir, skills_tree):
    _load("sess_stale", *_REQUIRED)
    enforcer._session_skills_loaded.clear()
    (skills_tree / "task-start" / "SKILL.md").write_text("# task-start v2\n")
    assert enforcer._stale_skills("sess_stale") == ["task-start"], (
        "the block message must name exactly which skills to reload"
    )


def test_stale_skills_empty_after_noop_redeploy(state_dir, skills_tree):
    _load("sess_stale_noop", *_REQUIRED)
    enforcer._session_skills_loaded.clear()
    for name in _REQUIRED:
        _bump_mtime(skills_tree / name / "SKILL.md")
    assert enforcer._stale_skills("sess_stale_noop") == []


def test_journal_records_content_hashes(state_dir, skills_tree):
    _load("sess_hashes", "test-driven-development")
    data = json.loads(
        (state_dir / "skills-credit" / "sess_hashes.json").read_text()
    )
    assert data["hashes"]["test-driven-development"] == (
        enforcer._skill_content_hash(
            skills_tree / "test-driven-development" / "SKILL.md"
        )
    )
