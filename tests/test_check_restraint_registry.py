#!/usr/bin/env python3
"""Tests for ops/scripts/manage/check-restraint-registry.py (Story M1.1).

The validator must reject any class missing a non-empty `restraint` or a valid
ISO `noticed` timestamp, and accept a well-formed registry. The script is
hyphenated (not importable as a normal module), so it is loaded via importlib
and also exercised end-to-end through subprocess for the exit-code contract.

Run: python3 -m pytest tests/test_check_restraint_registry.py -q
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO / "ops" / "scripts" / "manage" / "check-restraint-registry.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_restraint_registry", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _class(restraint="doctor:check_governance", noticed="2026-07-30",
           layer="ops", tier="enforced", artifacts=None):
    return {
        "artifacts": artifacts if artifacts is not None else ["doctor:check_governance"],
        "restraint": restraint,
        "noticed": noticed,
        "layer": layer,
        "tier": tier,
    }


def test_well_formed_registry_has_no_errors():
    crr = _load_module()
    data = {"classes": {"verify-before-declare": _class()}}
    assert crr.validate_registry(data) == []


def test_empty_restraint_names_the_class():
    crr = _load_module()
    data = {"classes": {"verify-before-declare": _class(restraint="  ")}}
    errors = crr.validate_registry(data)
    assert errors, "empty restraint must be rejected"
    assert any("verify-before-declare" in e for e in errors)


def test_missing_restraint_is_rejected():
    crr = _load_module()
    data = {"classes": {"verify-before-declare": {"noticed": "2026-07-30"}}}
    errors = crr.validate_registry(data)
    assert errors, "missing restraint must be rejected"


def test_invalid_noticed_is_rejected():
    crr = _load_module()
    data = {"classes": {"verify-before-declare": _class(noticed="yesterday-ish")}}
    errors = crr.validate_registry(data)
    assert errors, "invalid noticed must be rejected"
    assert any("noticed" in e for e in errors)


def test_full_iso_datetime_noticed_accepted():
    crr = _load_module()
    data = {"classes": {"verify-before-declare": _class(noticed="2026-07-30T10:00:00+09:00")}}
    assert crr.validate_registry(data) == []


def test_missing_layer_tier_rejected():
    crr = _load_module()
    data = {"classes": {"verify-before-declare": {"restraint": "r", "noticed": "2026-07-30"}}}
    errors = crr.validate_registry(data)
    assert any("layer" in e for e in errors), errors
    assert any("tier" in e for e in errors), errors


def test_invalid_layer_value_rejected():
    crr = _load_module()
    data = {"classes": {"verify-before-declare": _class(layer="banana")}}
    errors = crr.validate_registry(data)
    assert any("layer" in e for e in errors), errors


def test_enforced_with_only_model_artifacts_rejected():
    crr = _load_module()
    data = {"classes": {
        "verify-before-declare": _class(
            tier="enforced",
            artifacts=["SOUL.md:Principle-21", "skill:reflexion-check"],
        ),
    }}
    errors = crr.validate_registry(data)
    assert errors, "enforced tier with only model-layer artifacts must be rejected"
    assert any("model-layer" in e for e in errors)


def test_enforced_with_harness_artifact_accepted():
    crr = _load_module()
    data = {"classes": {
        "bypass-attempt": _class(tier="enforced", artifacts=["hook:pre-commit-score"]),
    }}
    assert crr.validate_registry(data) == []


def test_known_gaps_validated():
    crr = _load_module()
    data = {
        "classes": {},
        "known_gaps": [
            {"class": "P0-3 end_change evidence", "restraint": "planned: allowlist", "noticed": "2026-07-31"},
        ],
    }
    assert crr.validate_registry(data) == []


def test_known_gap_empty_restraint_rejected():
    crr = _load_module()
    data = {
        "classes": {},
        "known_gaps": [
            {"class": "P0-3 end_change evidence", "restraint": "", "noticed": "2026-07-31"},
        ],
    }
    errors = crr.validate_registry(data)
    assert errors, "empty restraint in a known gap must be rejected"
    assert any("known_gaps" in e for e in errors)


def test_known_gap_missing_class_rejected():
    crr = _load_module()
    data = {
        "classes": {},
        "known_gaps": [
            {"restraint": "planned: allowlist", "noticed": "2026-07-31"},
        ],
    }
    errors = crr.validate_registry(data)
    assert errors, "missing class in a known gap must be rejected"


def test_known_gaps_not_a_list_rejected():
    crr = _load_module()
    data = {"classes": {}, "known_gaps": "not-a-list"}
    errors = crr.validate_registry(data)
    assert errors, "known_gaps must be a list"
    assert any("known_gaps" in e for e in errors)


def test_encouraged_not_enforced_report():
    crr = _load_module()
    data = {"classes": {
        "verify-before-declare": dict(_class(layer="model", tier="encouraged"), should_be_enforced=True),
    }}
    drift = crr.report_encouraged_not_enforced(data)
    assert "verify-before-declare" in drift


def test_no_should_be_enforced_no_drift():
    crr = _load_module()
    data = {"classes": {"verify-before-declare": _class(layer="model", tier="encouraged")}}
    assert crr.report_encouraged_not_enforced(data) == []


def test_script_exits_nonzero_on_encouraged_not_enforced(tmp_path):
    p = tmp_path / "drift.json"
    p.write_text(json.dumps({"classes": {
        "x": dict(_class(layer="model", tier="encouraged"), should_be_enforced=True),
    }}))
    r = subprocess.run(
        [sys.executable, str(_SCRIPT), "--registry", str(p)],
        capture_output=True, text=True,
    )
    assert r.returncode != 0
    assert "x" in r.stderr


def test_script_exit_codes(tmp_path):
    """End-to-end: exit 0 on well-formed, non-zero + names class on empty restraint."""
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"classes": {"x": _class()}}))
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"classes": {"x": _class(restraint="")}}))

    r_good = subprocess.run(
        [sys.executable, str(_SCRIPT), "--registry", str(good)],
        capture_output=True, text=True,
    )
    assert r_good.returncode == 0, r_good.stderr

    r_bad = subprocess.run(
        [sys.executable, str(_SCRIPT), "--registry", str(bad)],
        capture_output=True, text=True,
    )
    assert r_bad.returncode != 0
    assert "x" in r_bad.stderr
