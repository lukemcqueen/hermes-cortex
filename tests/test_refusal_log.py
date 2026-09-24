#!/usr/bin/env python3
"""Tests for ops/scripts/manage/refusal-log.py (Story M3.1).

`record` appends a JSONL record {ts, session_id, context, challenged,
override_outcome} to the refusal log. The script is hyphenated, so it is
exercised through subprocess against a hermetic --path target.

Run: python3 -m pytest tests/test_refusal_log.py -q
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "ops" / "scripts" / "manage" / "refusal-log.py"


def _record(*args, path):
    return subprocess.run(
        [sys.executable, str(_SCRIPT), "record", *args, "--path", str(path)],
        capture_output=True, text=True,
    )


def _lines(path):
    return [json.loads(l) for l in path.read_text().strip().splitlines()]


def test_record_challenged_overridden_writes_correct_shape(tmp_path):
    p = tmp_path / "refusals.jsonl"
    r = _record("--challenged", "--outcome", "overridden", "--context", "del", "--session-id", "s1", path=p)
    assert r.returncode == 0, r.stderr
    recs = _lines(p)
    assert len(recs) == 1
    rec = recs[0]
    assert rec["challenged"] is True
    assert rec["override_outcome"] == "overridden"
    assert rec["session_id"] == "s1"
    assert rec["context"] == "del"
    assert "ts" in rec and rec["ts"]


def test_record_baseline_not_challenged_forces_none_outcome(tmp_path):
    p = tmp_path / "refusals.jsonl"
    r = _record(path=p)
    assert r.returncode == 0, r.stderr
    rec = _lines(p)[0]
    assert rec["challenged"] is False
    assert rec["override_outcome"] == "none"


def test_record_appends_not_overwrites(tmp_path):
    p = tmp_path / "refusals.jsonl"
    _record("--challenged", "--outcome", "upheld", path=p)
    _record(path=p)
    recs = _lines(p)
    assert len(recs) == 2
    assert recs[0]["override_outcome"] == "upheld"
    assert recs[1]["override_outcome"] == "none"
