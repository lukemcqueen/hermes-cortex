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


def _report_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("refusal_log", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fixture_records():
    # 10 records: 5 challenged (2 overridden, 3 upheld), 5 not challenged
    recs = []
    for _ in range(2):
        recs.append({"challenged": True, "override_outcome": "overridden"})
    for _ in range(3):
        recs.append({"challenged": True, "override_outcome": "upheld"})
    for _ in range(5):
        recs.append({"challenged": False, "override_outcome": "none"})
    return recs


def test_report_hand_computed_numbers():
    mod = _report_module()
    d = mod.report(_fixture_records())
    assert d["refusal_rate"] == pytest.approx(0.5)
    assert d["false_refusal_rate"] == pytest.approx(0.4)
    assert d["override_rate"] == pytest.approx(0.2)


def test_report_subcommand_prints_three_lines(tmp_path):
    p = tmp_path / "refusals.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in _fixture_records()))
    r = subprocess.run(
        [sys.executable, str(_SCRIPT), "report", "--path", str(p)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    out = r.stdout
    assert "refusal_rate: 0.5000" in out
    assert "false_refusal_rate: 0.4000" in out
    assert "override_rate: 0.2000" in out


def test_report_empty_log_is_zero(tmp_path):
    p = tmp_path / "empty.jsonl"
    p.write_text("")
    r = subprocess.run(
        [sys.executable, str(_SCRIPT), "report", "--path", str(p)],
        capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    assert "refusal_rate: 0.0000" in r.stdout
    assert "false_refusal_rate: 0.0000" in r.stdout
    assert "override_rate: 0.0000" in r.stdout
