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


def test_report_branch_checks_both_prefix_and_bare_forms():
    """The condition must test membership, not only startswith()."""
    assert re.search(r"subject\.startswith\(_issue_prefixes\)\s+or\s+subject\s+in\s+_bare_report_subjects",
                     _HANDLER_SRC), (
        "the report branch must accept the bare tracked forms as well as prefixes")


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
