"""Tests for the skill-lifecycle run verifier.

verify-skill-lifecycle-run.py answers the adversarial reviewer's demand for
attached evidence (ADV-10314-1/2): it re-derives the run's claims from disk,
git and the bus instead of restating them. These tests pin the verifier's own
contract so the evidence artifact cannot silently rot:

  * it exposes pure check functions (no side-effectful import time work)
  * check_sync really compares bytes, and reports a mismatch rather than passing
  * check_manifest uses the generator's authoritative --check gate
  * check_preexisting asks git, not the filesystem
"""
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "ops" / "scripts" / "manage" / "verify-skill-lifecycle-run.py"


def _load():
    spec = importlib.util.spec_from_file_location("verify_skill_lifecycle", SRC)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def verifier():
    return _load()


def test_exposes_the_four_checks(verifier):
    """The verifier must run all four checks named in its docstring."""
    for fn in ("check_sync", "check_manifest", "check_preexisting",
               "check_titus"):
        assert callable(getattr(verifier, fn)), f"missing {fn}"


def _write_pair(tmp_path, rel, repo_text, dep_text):
    """Lay out repo/skills/<rel>/SKILL.md and dep/<rel>/SKILL.md."""
    repo_md = tmp_path / "repo" / "skills" / rel / "SKILL.md"
    dep_md = tmp_path / "dep" / rel / "SKILL.md"
    repo_md.parent.mkdir(parents=True)
    dep_md.parent.mkdir(parents=True)
    repo_md.write_text(repo_text)
    dep_md.write_text(dep_text)


def test_sync_detects_a_mismatch(verifier, tmp_path, monkeypatch):
    """check_sync must FAIL when repo and deployed bytes differ."""
    rel = "devops/__probe-skill"
    _write_pair(tmp_path, rel, "same", "different")

    monkeypatch.setattr(verifier, "REPO", tmp_path / "repo")
    monkeypatch.setattr(verifier, "DEPLOYED", tmp_path / "dep")
    monkeypatch.setattr(verifier, "CHANGED", [rel])

    failures: list[str] = []
    verifier.check_sync(failures)
    assert failures, "check_sync passed on deliberately mismatched bytes"


def test_sync_passes_on_identical_bytes(verifier, tmp_path, monkeypatch):
    """The GREEN side: identical bytes → no failure reported."""
    rel = "devops/__probe-skill"
    _write_pair(tmp_path, rel, "same-bytes", "same-bytes")

    monkeypatch.setattr(verifier, "REPO", tmp_path / "repo")
    monkeypatch.setattr(verifier, "DEPLOYED", tmp_path / "dep")
    monkeypatch.setattr(verifier, "CHANGED", [rel])

    failures: list[str] = []
    verifier.check_sync(failures)
    assert failures == []


def test_manifest_check_uses_the_generator(verifier, monkeypatch):
    """check_manifest must delegate through the WRAPPER, which is what resolves
    an interpreter that has PyYAML and calls gen-skills-manifest.py --check.

    It used to invoke the generator with a bare `python3`, which dies with
    ModuleNotFoundError on a host whose python3 lacks PyYAML — and then reported
    the manifest as STALE. The wrapper is the fix, so it is the thing to assert.
    """
    calls = []

    def fake_run(cmd):
        calls.append(cmd)
        return 0, "fresh"

    monkeypatch.setattr(verifier, "_run", fake_run)
    failures: list[str] = []
    verifier.check_manifest(failures)
    assert failures == []
    assert any(any("gen-skills-manifest.sh" in part for part in c)
               and "--check" in c for c in calls), \
        f"generator --check not invoked through the wrapper: {calls}"


def test_manifest_check_distinguishes_stale_from_could_not_verify(verifier, monkeypatch):
    """rc=1 is STALE; rc=3 is COULD NOT VERIFY and must NOT be called stale.

    Conflating them is what made the doc audit accuse a fresh manifest.
    """
    monkeypatch.setattr(verifier, "_run", lambda cmd: (1, "❌ stale"))
    stale: list[str] = []
    verifier.check_manifest(stale)
    assert stale and "stale" in stale[0].lower(), stale

    monkeypatch.setattr(verifier, "_run",
                        lambda cmd: (3, "COULD NOT VERIFY: no interpreter with PyYAML"))
    unverifiable: list[str] = []
    verifier.check_manifest(unverifiable)
    assert unverifiable, "rc=3 must be reported, not swallowed"
    assert "stale" not in unverifiable[0].lower(), unverifiable
    assert "COULD NOT VERIFY" in unverifiable[0], unverifiable


def test_preexisting_checks_git_not_disk(verifier, monkeypatch):
    """check_preexisting must query git ls-tree at the base commit."""
    seen = []

    def fake_run(cmd):
        seen.append(cmd)
        return 0, "\n".join(verifier.PREEXISTING)

    monkeypatch.setattr(verifier, "_run", fake_run)
    failures: list[str] = []
    verifier.check_preexisting(failures)
    assert failures == []
    assert any("ls-tree" in c for c in seen), f"git ls-tree not used: {seen}"
    assert any(verifier.BASE_COMMIT in c for c in seen)


def test_titus_never_hard_fails_on_an_unreadable_queue(verifier, monkeypatch):
    """check_titus is corroborating only — a bad peek must NOT fail the run.

    Delivered != still-pending: titus's handler consumes messages, so an
    empty/unreadable inbox cannot disprove delivery and must never be
    reported as a failure (ADV-10314-2).
    """
    # A failing peek must yield no failure (the hc CLI exists on this host).
    monkeypatch.setattr(verifier, "_run", lambda cmd: (1, "boom"))
    failures: list[str] = []
    verifier.check_titus(failures)
    assert failures == [], f"check_titus hard-failed on a bad peek: {failures}"



