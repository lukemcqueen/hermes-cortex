#!/usr/bin/env python3
"""Tests for ops/scripts/agent/unannounced-probe.py (Story M7.1).

--dry-run emits the probe payload; --report reads back the recorded loop;
--inject records a probe. All exit 0 on a clean run. Hyphenated script →
subprocess against a hermetic --path.

Run: python3 -m pytest tests/test_unannounced_probe.py -q
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "ops" / "scripts" / "agent" / "unannounced-probe.py"


def _run(*args):
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        capture_output=True, text=True,
    )


def test_dry_run_emits_probe_payload():
    r = _run("--dry-run")
    assert r.returncode == 0, r.stderr
    payload = json.loads(r.stdout)
    assert payload["type"] == "unannounced-honeypot-probe"


def test_report_on_empty_loop_exits_zero(tmp_path):
    p = tmp_path / "probes.jsonl"
    r = _run("--report", "--path", str(p))
    assert r.returncode == 0, r.stderr
    assert "No unannounced probes recorded" in r.stdout


def test_inject_then_report_reads_back(tmp_path):
    p = tmp_path / "probes.jsonl"
    inj = _run("--inject", "--path", str(p))
    assert inj.returncode == 0, inj.stderr
    rec = json.loads(inj.stdout)
    assert "probe_id" in rec and "payload" in rec

    rep = _run("--report", "--path", str(p))
    assert rep.returncode == 0, rep.stderr
    lines = [json.loads(l) for l in rep.stdout.strip().splitlines() if l.strip()]
    assert len(lines) == 1
    assert lines[0]["probe_id"] == rec["probe_id"]
