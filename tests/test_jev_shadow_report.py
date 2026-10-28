#!/usr/bin/env python3
"""The shadow monitor: does the log say routing is worth turning on?

Driven as a subprocess against a fixture log, so the assertions are about what an
operator actually reads. The decisive case is the one that stops a mistake: a log
full of `routed: false` on low confidence means the POOLS are not the lever, and a
report that just printed counts would let someone flip the switch and see nothing.
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

SCRIPT = (Path(__file__).resolve().parents[1] / "ops" / "scripts" / "manage"
          / "jev-shadow-report.py")
NOW = time.time()


def _row(**kw):
    row = {"ts": NOW - 60, "profile": "default", "kind": "route", "mode": "shadow"}
    row.update(kw)
    return row


def _log(tmp_path, rows):
    path = tmp_path / "jev-decisions.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return path


def _run(path, *args):
    return subprocess.run([sys.executable, str(SCRIPT), "--log", str(path), *args],
                          capture_output=True, text=True, timeout=60)


def test_missing_log_is_could_not_verify(tmp_path):
    result = _run(tmp_path / "nope.jsonl")

    assert result.returncode == 3, f"{result.stdout}{result.stderr}"
    assert "COULD NOT VERIFY" in result.stderr
    assert "nothing has been routed on this host yet" in result.stderr


def test_a_log_of_low_confidence_keeps_the_switch_off(tmp_path):
    """The case that matters: counts alone would mislead."""
    path = _log(tmp_path, [
        _row(routed=False, model="openrouter:deepseek/deepseek-v4.1-flash",
             reason="low confidence 0.02", confidence=0.02, tier=None),
        _row(routed=False, model="openrouter:deepseek/deepseek-v4.1-flash",
             reason="low confidence 0.05", confidence=0.05, tier=None),
    ])

    result = _run(path)

    assert result.returncode == 0
    assert "POOLS are not" in result.stdout, result.stdout
    assert "not recognising these turns as asks" in result.stdout


def test_a_routed_turn_names_what_it_would_switch_to(tmp_path):
    path = _log(tmp_path, [
        _row(routed=True, model="openrouter:qwen/qwen3.7-flash", tier="simple",
             reason="simple coding", confidence=0.91),
        _row(routed=False, model="openrouter:deepseek/deepseek-v4.1-flash",
             reason="medium coding", confidence=0.8, tier="medium"),
    ])

    result = _run(path)

    assert result.returncode == 0
    assert "1 of 2 decision(s) would have switched" in result.stdout
    assert "openrouter:qwen/qwen3.7-flash" in result.stdout
    assert "1x → " in result.stdout


def test_an_empty_window_says_so_rather_than_reporting_zeroes(tmp_path):
    path = _log(tmp_path, [_row(ts=NOW - 30 * 86400, routed=True, model="x", reason="old")])

    result = _run(path, "--days", "1")

    assert result.returncode == 0
    assert "no routing decisions logged yet" in result.stdout


def test_applied_is_counted_separately_from_routed(tmp_path):
    """Shadow must never report a switch as applied."""
    path = _log(tmp_path, [
        _row(kind="route", routed=True, model="openrouter:qwen/qwen3.7-flash",
             reason="simple coding", confidence=0.9),
        _row(kind="route_effective", applied=False, reason="simple coding"),
    ])

    result = _run(path)

    assert "would switch  : 1" in result.stdout
    assert "actually applied: 0" in result.stdout


def test_a_malformed_line_is_counted_not_hidden(tmp_path):
    path = tmp_path / "jev-decisions.jsonl"
    path.write_text(json.dumps(_row(routed=False, reason="x", confidence=0.1)) + "\n{not json\n")

    result = _run(path)

    assert result.returncode == 0
    assert "1 malformed line(s) skipped" in result.stderr


def test_json_mode_is_machine_readable(tmp_path):
    path = _log(tmp_path, [_row(routed=True, model="openrouter:qwen/qwen3.7-flash",
                               tier="simple", reason="simple coding", confidence=0.9)])

    result = _run(path, "--json")

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["route_rows"] == 1
    assert payload["routed_true"] == 1
    assert payload["would_switch_to"] == {"openrouter:qwen/qwen3.7-flash": 1}
    assert "verdict" in payload and payload["verdict"]


@pytest.mark.parametrize("value", ["--days", "--current"])
def test_the_window_and_baseline_are_operator_settable(tmp_path, value):
    path = _log(tmp_path, [_row(routed=False, reason="x", confidence=0.5)])
    extra = ["1"] if value == "--days" else ["openrouter:some/model"]

    result = _run(path, value, *extra)

    assert result.returncode == 0


def test_confidence_is_read_from_the_reason_when_the_field_is_null(tmp_path):
    """The LIVE shape: a low-confidence keep logs confidence null and puts the number
    in the reason, so reading the field alone reported "n: 0, median: None" on a log
    full of confidence values."""
    path = _log(tmp_path, [
        {"ts": NOW - 60, "kind": "route", "mode": "shadow", "routed": False,
         "model": "openrouter:deepseek/deepseek-v4.1-flash",
         "reason": "low confidence 0.02", "confidence": None},
        {"ts": NOW - 30, "kind": "route", "mode": "shadow", "routed": False,
         "model": "openrouter:deepseek/deepseek-v4.1-flash",
         "reason": "low confidence 0.40", "confidence": None},
    ])

    result = _run(path, "--json")

    payload = json.loads(result.stdout)
    assert payload["confidence"]["n"] == 2, payload["confidence"]
    assert payload["confidence"]["median"] == pytest.approx(0.21)
