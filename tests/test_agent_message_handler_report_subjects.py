#!/usr/bin/env python3
"""agent-message-handler report subjects — regression for the "Unknown subject" drop.

Bug (observed on moses, 2026-10-01):

    ⚠️ [moses] Unknown subject 'PROPOSAL' from esther, responded with error

Cause: a contradiction between two lists in the same file.
  * `TASK_CREATING_SUBJECTS` includes PROPOSAL / ISSUES / IMPROVEMENTS, so the
    task lifecycle records them, and `normalize_tracked_subject()` maps the
    documented "PROPOSAL: <what>" form to exactly "PROPOSAL".
  * They have NO handler in the command registry (commands.py), so
    `cmd_dispatch()` returns None.
  * The report branch that exists to catch them matched PREFIX forms only
    ("PROPOSAL:", "📝 PROPOSAL:", ...) — so a BARE "PROPOSAL" (which is what
    normalization produces and what a plain `hc send --subject PROPOSAL`
    sends) matched nothing and fell through to the fatal fallback, which
    archives the message and replies with an error.

Net effect: a legitimate fleet report was silently dropped and the sender got
an error reply.

Fix: the report branch also accepts the bare tracked forms.

Run: python3 -m pytest tests/test_agent_message_handler_report_subjects.py -q
"""

import importlib.util
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
_HANDLER_SRC = (REPO_ROOT / "ops" / "scripts" / "agent" / "agent-message-handler.py").read_text()
_COMMANDS_SRC = (REPO_ROOT / "ops" / "scripts" / "agent" / "commands.py").read_text()


def _bare_report_subjects() -> tuple:
    """The bare report subjects the handler's report branch accepts."""
    m = re.search(r"_bare_report_subjects\s*=\s*\(([^)]*)\)", _HANDLER_SRC)
    assert m, "the report branch no longer declares _bare_report_subjects"
    return tuple(re.findall(r'"([^"]+)"', m.group(1)))


def _registered_commands() -> set:
    """Subjects the command registry dispatches (decorator + register_custom)."""
    subjects = set()
    # @command("<RESULT>", ...) on handle_<name> -> <NAME>_REQUEST
    for result_subject, fn_name in re.findall(
            r'@command\(\s*"([^"]+)"[^)]*\)\s*\ndef\s+(handle_\w+)', _COMMANDS_SRC):
        subjects.add(fn_name[len("handle_"):].upper() + "_REQUEST")
    # register_custom("<SUBJECT>", ...)
    subjects.update(re.findall(r'register_custom\(\s*"([^"]+)"', _COMMANDS_SRC))
    return subjects


@pytest.fixture()
def handler_module(monkeypatch):
    """Load agent-message-handler.py by file path (hyphenated name)."""
    monkeypatch.setenv("AGENT_NAME", "test-agent")
    monkeypatch.setenv("CORTEX_BUS_NO_OUTBOX", "1")
    src = REPO_ROOT / "ops" / "scripts" / "agent" / "agent-message-handler.py"
    spec = importlib.util.spec_from_file_location("agent_message_handler", src)
    amh = importlib.util.module_from_spec(spec)
    backup = list(sys.path)
    sys.path.insert(0, str(Path.home() / ".hermes-cortex" / "scripts"))
    spec.loader.exec_module(amh)
    sys.path[:] = backup
    return amh


# ── The exact bug ─────────────────────────────────────────────

def test_bare_proposal_is_accepted_as_a_report():
    assert "PROPOSAL" in _bare_report_subjects(), (
        "a bare 'PROPOSAL' subject must be accepted by the report branch")


def test_report_branch_checks_both_prefix_and_bare_forms(handler_module):
    """Both forms must be recognised — now through ONE named predicate.

    This used to assert the literal `subject.startswith(_issue_prefixes) or
    subject in _bare_report_subjects` text. The early-archive guard needs the
    same decision (2026-10-27), and a second copy of a predicate is a second
    rule, so the condition moved into `_is_report_subject()` and this pins the
    PREDICATE's behaviour instead of the sentence it is written in.
    """
    assert handler_module._is_report_subject("PROPOSAL") is True, "bare form"
    assert handler_module._is_report_subject("PROPOSAL: add a doc") is True, "prefix form"


def test_issues_and_improvements_are_also_accepted():
    bare = _bare_report_subjects()
    assert "ISSUES" in bare and "IMPROVEMENTS" in bare, (
        f"all tracked report subjects must be accepted, got {bare}")


# ── Real behaviour: normalization produces the bare form ──────

def test_normalized_prefix_form_is_a_handled_subject(handler_module):
    """`normalize_tracked_subject("PROPOSAL: x")` yields "PROPOSAL" — a handled one."""
    norm = handler_module.normalize_tracked_subject("PROPOSAL: add a gateway doc")
    assert norm == "PROPOSAL", f"unexpected normalization: {norm}"
    assert norm in _bare_report_subjects(), (
        "the normalized subject must be accepted by the report branch")


@pytest.mark.parametrize("subject", ["PROPOSAL", "ISSUES", "IMPROVEMENTS"])
def test_every_tracked_report_subject_is_normalization_stable(handler_module, subject):
    """A bare tracked subject must normalize to itself and stay handled."""
    assert handler_module.normalize_tracked_subject(subject) == subject
    assert subject in _bare_report_subjects()


# ── Class-level invariant: no tracked subject may be unhandled ─

def test_no_tracked_subject_is_left_unhandled(handler_module):
    """Every TASK_CREATING_SUBJECT must be dispatchable OR treated as a report.

    This is the invariant the bug violated: PROPOSAL was tracked (task row +
    lifecycle) but neither dispatchable nor accepted as a report, so it hit the
    fatal "Unknown subject" fallback. Any future tracked subject that is added
    without a handler must be added to the report branch, or this fails.
    """
    commands = _registered_commands()
    bare = _bare_report_subjects()
    unhandled = [s for s in handler_module.TASK_CREATING_SUBJECTS
                 if s not in commands and s not in bare]
    assert not unhandled, (
        f"tracked subject(s) {unhandled} are neither registered commands nor "
        "report subjects — they will hit the 'Unknown subject' error path")


def test_registry_actually_matched_commands():
    """Guard the parser: the registration regexes must find real commands."""
    commands = _registered_commands()
    assert "UPDATE_REQUEST" in commands and "EXEC" in commands, (
        f"command registry parse looks wrong: {sorted(commands)}")


# ── The 2026-10-27 defect: the early archive removed reports before their
#    own branch could leave them queued for the orchestrator ────────────────

_REPORT_SHAPES = ("ISSUES", "ISSUES: disk pressure on gisu", "🚨 ISSUES: x",
                  "IMPROVEMENTS", "IMPROVEMENTS: cache the venv",
                  "PROPOSAL", "PROPOSAL: add a doc",
                  "RE: your lock report", "STRANDED_SKILL_LAND")


def test_report_subject_is_not_early_archived(handler_module, monkeypatch):
    """Behaviour, not source text: the archive collaborator must NOT be called.

    Measured 2026-10-27: an ISSUES report logged "left in queue for
    orchestrator" and the queue peek then showed nothing — the early archive had
    already removed it, so the report survived only in bus.archives and the
    orchestrator's live-queue read could never see it.
    """
    calls = []
    monkeypatch.setattr(handler_module, "archive_message",
                        lambda q, m: calls.append((q, m)) or True)
    archived = handler_module._early_archive("inbox_agent", "msg-1", "ISSUES")
    assert archived is False, "a report subject must be LEFT pending"
    assert calls == [], f"the report was archived anyway: {calls}"


def test_normal_subject_is_still_early_archived(handler_module, monkeypatch):
    """The crash-safety archive must still happen for everything else."""
    calls = []
    monkeypatch.setattr(handler_module, "archive_message",
                        lambda q, m: calls.append((q, m)) or True)
    archived = handler_module._early_archive("inbox_agent", "msg-2", "UPDATE_REQUEST")
    assert archived is True
    assert calls == [("inbox_agent", "msg-2")], calls


@pytest.mark.parametrize("subject", _REPORT_SHAPES)
def test_every_report_shape_is_guarded(handler_module, monkeypatch, subject):
    calls = []
    monkeypatch.setattr(handler_module, "archive_message",
                        lambda q, m: calls.append((q, m)) or True)
    assert handler_module._early_archive("inbox_agent", "msg-3", subject) is False
    assert calls == [], f"{subject!r} was archived: {calls}"


def test_early_archive_call_site_uses_the_guard():
    """Supplement to the behaviour test: the poll path must call the guard.

    The predicate and the guard can both be right while the call site still
    archives directly — this is the only check that catches that.
    """
    assert "_early_archive(source_queue, msg_id, subject)" in _HANDLER_SRC, (
        "the early-archive call site no longer routes through the guard")


def test_duplicate_row_is_not_reported_as_a_failure(handler_module, monkeypatch):
    """A re-read of a report must not log a failure for the row it already has.

    With reports now left pending for a tick, task_create_from_message runs again
    on the re-read; the unique index (source='inbox', correlation_id) makes that
    a duplicate, and the old code logged it as "task-create failed" — an expected
    state wearing an error's clothes.
    """
    monkeypatch.setattr(handler_module, "_taskdb", lambda *a, **k: (
        1, 'ERROR: duplicate key value violates unique constraint '
           '"idx_tasks_inbox_correlation"'))
    assert handler_module.task_create_from_message("ISSUES", "corr-dup", "ISSUES: x") == "corr-dup"


def test_created_row_still_reports_its_correlation_id(handler_module, monkeypatch):
    monkeypatch.setattr(handler_module, "_taskdb", lambda *a, **k: (0, "✅ Task added: abcd1234..."))
    assert handler_module.task_create_from_message("ISSUES", "corr-new", "ISSUES: x") == "corr-new"


def test_other_taskdb_failure_is_still_none(handler_module, monkeypatch):
    """Do not widen the tolerance: a REAL failure must keep returning None."""
    monkeypatch.setattr(handler_module, "_taskdb", lambda *a, **k: (1, "could not connect to server"))
    assert handler_module.task_create_from_message("ISSUES", "corr-bad", "ISSUES: x") is None
