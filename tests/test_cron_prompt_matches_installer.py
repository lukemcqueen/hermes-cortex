#!/usr/bin/env python3
"""The live cron prompt must match the prompt the installer would create.

`create_cron` skips a job that already exists, so editing the installer does NOT
propagate: a live job keeps its old prompt until it is updated via the cronjob tool.
After any prompt change BOTH must be updated, and this is the check that says whether
they agree.

The parser is the unit under test: it is driven with fixtures in both directions (a
well-formed block extracts exactly; a malformed one returns None rather than a wrong
answer). The live comparison is then an operational assertion — it SKIPS when the job
is not installed on this host, because a check that fails on a host where the job
legitimately does not exist would be noise, not a finding.

Run: python3 -m pytest tests/test_cron_prompt_matches_installer.py -q
"""

import json
import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_INSTALLER = _REPO / "ops" / "scripts" / "install" / "install-orch-crons.sh"
_JOBS = Path.home() / ".hermes" / "cron" / "jobs.json"
_JOB_NAME = "orch-task-morning-pass"


def extract_prompt(text: str, name: str):
    """The prompt argument of ``create_cron "<name>"`` in an installer, or None.

    Line-based on purpose: the block is a multi-line quoted argument, and a regex over
    it has to escape the shell line-continuations, which is where an earlier version of
    this probe silently mis-offset and reported a 7-char "difference" that was its own
    bug. Returns None (never a partial answer) when the block cannot be found.
    """
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if l.startswith(f'create_cron "{name}"')), None)
    if start is None:
        return None
    # Skip the empty script field ('  "" \') that precedes the prompt argument.
    j = start + 1
    while j < len(lines) and lines[j].strip() != '"" \\':
        j += 1
    if j >= len(lines) or not lines[j + 1].startswith('  "'):
        return None
    body = [lines[j + 1][3:]]  # strip the opening '  "'
    j += 2
    while j < len(lines):
        line = lines[j]
        if line.rstrip().endswith('" \\'):
            body.append(line.rstrip()[:-3].rstrip())
            return "\n".join(body)
        body.append(line)
        j += 1
    return None  # unterminated argument: refuse rather than return a truncated prompt


_WELL_FORMED = '''\
create_cron "orch-task-morning-pass" "0 7 * * *" \\
  "" \\
  "First line.

Second paragraph with a  two-space indent.

1. one
2. two" \\
  "" \\
  "terminal,web,file" \\
  "telegram:123" \\
  "" \\
  "false"
'''

_MALFORMED = '''\
create_cron "orch-task-morning-pass" "0 7 * * *" \\
  "" \\
  "never terminated
'''


def test_the_parser_extracts_the_prompt_exactly():
    got = extract_prompt(_WELL_FORMED, _JOB_NAME)
    assert got is not None, "a well-formed block must extract"
    assert got.startswith("First line."), got
    assert got.endswith("2. two"), repr(got[-20:])
    assert "\n\nSecond paragraph" in got, got
    assert '" \\' not in got, "the shell continuation must not leak into the prompt"
    print("  a well-formed create_cron block extracts exactly ✓")


def test_the_parser_refuses_a_malformed_block():
    assert extract_prompt(_MALFORMED, _JOB_NAME) is None, "a truncated block must not return a partial prompt"
    assert extract_prompt("nothing here", _JOB_NAME) is None
    print("  a malformed/absent block returns None, never a partial prompt ✓")


def test_the_parser_skips_the_script_field_not_just_the_first_quote():
    """The bug this pins: starting the capture at the FIRST '  "' lands inside the empty
    script field ('  "" \\') and yields a prompt offset by the field's own characters."""
    got = extract_prompt(_WELL_FORMED, _JOB_NAME)
    assert got is not None and not got.lstrip().startswith('" \\'), got
    print("  the empty script field is skipped, not captured into the prompt ✓")


def test_the_live_prompt_matches_the_installer():
    if not _JOBS.exists() or not _INSTALLER.exists():
        print("  SKIP: no cron store or installer on this host")
        return
    jobs = json.loads(_JOBS.read_text())
    jobs = jobs.get("jobs", jobs) if isinstance(jobs, dict) else jobs
    live = next((j.get("prompt", "") for j in jobs
                 if isinstance(j, dict) and j.get("name") == _JOB_NAME), None)
    if live is None:
        print(f"  SKIP: job {_JOB_NAME} is not installed on this host")
        return
    committed = extract_prompt(_INSTALLER.read_text(), _JOB_NAME)
    assert committed, "the installer block must parse"
    assert live.strip() == committed.strip(), (
        "the live cron prompt differs from the installer's — update the live job with "
        f"cronjob action='update' (live {len(live)} chars, installer {len(committed)} chars)"
    )
    assert re.search(r"NOT created_at", live), "the verified-schema block must be in the live prompt"
    print(f"  live prompt == installer paste ({len(live)} chars) ✓")


if __name__ == "__main__":
    sys.exit(__import__("pytest").main([__file__, "-q"]))
