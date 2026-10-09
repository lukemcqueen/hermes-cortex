"""Tests for the bus-overnight evidence artifact + its generator.

These pin the contract the self-adversarial reviewer requires of the committed
overnight evidence (docs/evidence/bus-overnight-2026-10-09.txt):

  * the artifact's ``inspector_last_commit`` line MATCHES the inspector
    module's actual last-touching commit (ADV-11906-1/ADV-11910-1) — the
    artifact must not carry a free-floating, unverifiable revision string.
  * the artifact records the source fingerprints the run note relies on:
    ``issues_exit=0`` (the canonical no-action condition) and a probe SUMMARY
    with ``stuck(retry>=max)=0`` and ``dlq_backlog=0``.
  * the generator fails CLOSED on an unresolved/empty revision — it must not
    swallow git's stderr and write an artifact anyway (ADV-11910-2).

No network. The revision check shells out to ``git`` in the repo and skips
only when git/the repo is genuinely unavailable (e.g. a source tarball export).
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ARTIFACT = REPO / "docs" / "evidence" / "bus-overnight-2026-10-09.txt"
GENERATOR = REPO / "ops" / "evidence" / "bus-overnight-2026-10-09.sh"
INSPECTOR_REL = "ops/scripts/orch-bus/bus-inbox-inspect.py"


def _artifact_text() -> str:
    assert ARTIFACT.is_file(), f"missing committed artifact {ARTIFACT}"
    return ARTIFACT.read_text()


def _inspector_last_commit() -> str | None:
    if not shutil.which("git"):
        return None
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO), "log", "-1", "--format=%h", "--", INSPECTOR_REL],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except (subprocess.CalledProcessError, OSError):
        return None
    return out or None


def test_artifact_inspector_revision_matches_git():
    """inspector_last_commit must equal the inspector's real last-touching commit."""
    expected = _inspector_last_commit()
    if expected is None:
        return  # git/repo unavailable (e.g. exported tree) — not this test's target
    m = re.search(r"^# inspector_last_commit: (\S+)$", _artifact_text(), re.M)
    assert m, "artifact is missing the '# inspector_last_commit: <rev>' line"
    assert m.group(1) == expected, (
        f"artifact inspector_last_commit={m.group(1)!r} != git {expected!r}")


def test_artifact_records_no_action_and_clean_probe():
    text = _artifact_text()
    assert "issues_exit=0" in text, "artifact must record issues_exit=0"
    assert "probe_exit=0" in text, "artifact must record probe_exit=0"
    summary = re.search(r"^SUMMARY pending_peeked=(\d+) stuck\(retry>=max\)=(\d+) "
                        r"dlq_backlog=(\d+)$", text, re.M)
    assert summary, "artifact is missing the probe SUMMARY line"
    assert summary.group(2) == "0", "artifact records stuck messages (retry>=max != 0)"
    assert summary.group(3) == "0", "artifact records a DLQ backlog (!= 0)"


def test_generator_fails_closed_on_unresolved_revision():
    gen = GENERATOR.read_text()
    # The revision resolution must not swallow git's stderr.
    assert "rev-parse --short HEAD" not in gen, "generator still records self-referential HEAD"
    assert "log -1 --format=%h" in gen, "generator must derive the inspector revision from git log"
    assert "2>/dev/null" not in gen.split("OUT_ISSUES")[0], (
        "generator suppresses git stderr while resolving the revision")
    # Both fail-closed guards must be present.
    assert "inspector revision empty" in gen, "missing empty-revision guard"
    assert "git log failed resolving the inspector revision" in gen, (
        "missing git-failure guard")
