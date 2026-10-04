#!/usr/bin/env python3
"""The acceptance-evidence script must be able to FAIL.

An evidence generator that always prints PASS is worse than none: it launders a
self-report into an artefact. These tests cover the part that broke first time —
the schema-version parse — and prove the script reports FAIL when an invariant is
violated.

The bug, kept as the reason this file exists: the parser matched only `current=N`
and also passed `--dry-run`, which task-db.py does not accept. On a healthy host the
runner emits the NO-OP shape instead, so the check read "unreadable" and the script
reported FAIL for a system that was fine. A check that cannot parse its own input is
not a check.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
SCRIPT = _REPO / "ops" / "scripts" / "manage" / "task-queue-evidence.py"
RUNNER = _REPO / "ops" / "scripts" / "manage" / "run-task-queue-evidence.sh"


def _load():
    spec = importlib.util.spec_from_file_location("tq_evidence", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ev = _load()


# ── the parse must handle the read-only query result ────────────────────────

def test_parses_a_bare_version_from_the_query():
    assert ev.parse_db_version("12\n") == 12
    assert ev.parse_db_version(" 3 \n") == 3


def test_parses_a_multiline_psql_result():
    assert ev.parse_db_version("12\n\n") == 12
    assert ev.parse_db_version("11\n12\n") == 11, "MAX() returns one row; take the first"


def test_returning_none_is_how_unparseable_is_signalled():
    """None is the contract: main() turns it into a visible FAIL, never a silent PASS."""
    assert ev.parse_db_version("") is None
    assert ev.parse_db_version("<unreadable: RuntimeError>") is None
    assert ev.parse_db_version("some unrelated output") is None


def test_the_evidence_never_mutates_what_it_measures():
    """An evidence script must not repair the system it is inspecting.

    The first version ran `task-db.py --apply-schema`, which APPLIES migrations. So
    a DB that was behind would be fixed by the act of measuring it, and the check
    could never report the drift it exists to detect. The version is now read with
    a SELECT.
    """
    src = SCRIPT.read_text()
    # Match the INVOCATION (a quoted argv element), not a mention in prose: the
    # docstring deliberately names the old command to explain why it was wrong.
    assert '"--apply-schema"' not in src and "'--apply-schema'" not in src, (
        "the evidence applies migrations — it must be read-only, or it hides the "
        "drift it is meant to detect")
    assert "FROM tasks.schema_version" in src, (
        "the schema version must come from a read-only query")


# ── the artefact is real, and wired to a runner ─────────────────────────────

def test_the_runner_exists_and_locates_the_repo_root():
    """The runner derived its repo root as ../.. and pointed at ops/ops/... — it
    wrote its report to a stray ops/docs/ path before this was caught."""
    text = RUNNER.read_text()
    assert "/../../.." in text, (
        "the runner is at ops/scripts/manage/, so the repo root is three levels up")
    assert "docs/evidence/task-queue-remediation.md" in text
    assert "$?" in text, "the runner must capture the status before anything else reads it"


def test_the_script_reports_failures_rather_than_always_passing():
    """Structural: main() must return non-zero on a failed check, and print FAIL."""
    src = SCRIPT.read_text()
    assert "failures.append" in src, "no failure collection — PASS would be unconditional"
    assert "return 0 if not failures else 1" in src, (
        "main() must exit non-zero when a check fails, or it cannot gate anything")
    assert "**FAIL**" in src, "a failed check must be visibly marked in the report"


def test_the_checks_cover_the_invariants_this_remediation_established():
    """Presence check — if a check is deleted the report silently gets weaker."""
    src = SCRIPT.read_text()
    for invariant in ("assigned-and-unstarted", "two views", "parked",
                      "transition_allowed", "registered for deploy",
                      "deployed tree", "schema version"):
        assert invariant in src, f"the evidence no longer checks: {invariant}"
