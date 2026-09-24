# test_run_evals_doctor_clean.py — RED/GREEN for the doctor JSON parse seam.
#
# Bug (2026-09-25, orch-daily-regression-gate rc=1): the doctor's MCP-server
# probes (loop-governance, M6) emit `[mcp-server] DEBUG: HTTPError 401 ...`
# lines to STDERR, while run-evals._run() returns stdout+stderr combined.
# json.loads() on the combined text fails on the noise → doctor_clean always
# FAILs → daily error alert from a healthy fleet.
#
# Fix contract: a parse helper that recovers the FIRST complete JSON object
# from combined output, ignoring noise on either side.

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "run_evals", REPO / "ops" / "scripts" / "manage" / "run-evals.py"
)
assert _SPEC is not None and _SPEC.loader is not None, "spec load failed"
mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mod)

NOISE = "[mcp-server] DEBUG: HTTPError 401 for Bearer auth — trying Basic fallback\n"

GOOD = json.dumps({"summary": {"pass": 379, "warn": 2, "fail": 0}})


def test_parses_json_with_stderr_noise_after():
    out = GOOD + "\n" + NOISE * 3
    report = mod._parse_doctor_json(out)
    assert report["summary"]["fail"] == 0
    assert report["summary"]["pass"] == 379


def test_parses_json_with_stderr_noise_before():
    out = NOISE * 3 + NOISE.strip() + "\n" + GOOD
    report = mod._parse_doctor_json(out)
    assert report["summary"]["fail"] == 0


def test_no_json_raises_valueerror():
    try:
        mod._parse_doctor_json("Traceback (most recent call last): boom\n")
    except ValueError:
        return
    raise AssertionError("expected ValueError when output has no JSON object")


def test_truncated_json_raises():
    try:
        mod._parse_doctor_json('{"summary": {"pass": 379, ')
    except (ValueError, json.JSONDecodeError):
        return
    raise AssertionError("expected an error when the JSON object is truncated")


def test_non_summary_json_still_fails_later_guard():
    # Parse succeeds on any JSON object; the fail-count guard stays in
    # _doctor_clean. Simulate a doctor report with failures>0:
    bad = json.dumps({"summary": {"pass": 10, "warn": 0, "fail": 2}}) + NOISE
    report = mod._parse_doctor_json(bad)
    assert report["summary"]["fail"] == 2  # parse only; gate logic checks fail>0
