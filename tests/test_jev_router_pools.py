#!/usr/bin/env python3
"""The router pricing list must actually govern the pools.

Order is what spends money (first fit wins), so the assertions are about DRIFT: a
live pool that no longer matches the list, leads with a dearer model than the list
says, or exceeds the tier's ceiling. The `hard` exemption is pinned too — escalation
there is the tier's purpose, and a check that flagged it would be noise nobody reads.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = (Path(__file__).resolve().parents[1] / "ops" / "scripts" / "manage"
          / "jev-router-pools.py")

CHEAP = "openrouter:qwen/qwen3.7-flash"          # 0.16/M
BASE = "openrouter:deepseek/deepseek-v4.1-flash"  # 0.56/M
DEAR = "openrouter:moonshotai/kimi-k2.7-code"     # 3.66/M
FRONTIER = "openrouter:openai/gpt-5.3-codex"      # 15.75/M

LIST = {
    "captured": "2026-10-28",
    "baseline": BASE,
    "policy": {"simple": {"max_multiple_of_baseline": 1.0},
               "medium": {"max_multiple_of_baseline": 1.0},
               "hard": {"max_multiple_of_baseline": None}},
    "tiers": {"simple": {"coding": [CHEAP, BASE]},
              "medium": {"coding": [BASE, CHEAP]},
              "hard": {"coding": [FRONTIER]}},
    "prices": {
        CHEAP: {"in": 0.01, "out": 0.04},
        BASE: {"in": 0.14, "out": 0.42},
        DEAR: {"in": 0.90, "out": 2.76},
        FRONTIER: {"in": 3.00, "out": 12.75},
    },
}


def _write(tmp_path, name, payload):
    path = tmp_path / name
    path.write_text(json.dumps(payload, indent=2))
    return path


def _live(**tiers):
    return {"mode": "redacted-text", "exclude": ["*:free"], "tiers": tiers}


def _run(list_path, routing_path, *args):
    return subprocess.run([sys.executable, str(SCRIPT), "--list", str(list_path),
                           "--routing", str(routing_path), *args],
                          capture_output=True, text=True, timeout=60)


def _matching(tmp_path):
    live = _live(simple={"coding": [CHEAP, BASE]}, medium={"coding": [BASE, CHEAP]},
                 hard={"coding": [FRONTIER]})
    return _write(tmp_path, "list.json", LIST), _write(tmp_path, "routing.json", live)


def test_matching_pools_report_no_findings(tmp_path):
    list_path, routing = _matching(tmp_path)

    result = _run(list_path, routing)

    assert result.returncode == 0, result.stdout
    assert "no findings" in result.stdout
    assert "$0.560/M" in result.stdout, "the baseline price is shown"


def test_a_drifted_head_is_reported_with_its_price_delta(tmp_path):
    list_path, _ = _matching(tmp_path)
    routing = _write(tmp_path, "routing.json",
                     _live(medium={"coding": [DEAR, BASE]}))

    result = _run(list_path, routing)

    assert result.returncode == 1
    assert "[order]" in result.stdout
    assert "medium/coding" in result.stdout
    assert DEAR in result.stdout and BASE in result.stdout
    assert "+" in result.stdout, "the delta must be signed and shown"


def test_a_head_above_the_tier_ceiling_is_a_finding(tmp_path):
    list_path, _ = _matching(tmp_path)
    routing = _write(tmp_path, "routing.json", _live(medium={"coding": [DEAR]}))

    result = _run(list_path, routing)

    assert result.returncode == 1
    assert "[ceiling]" in result.stdout
    assert "above the 1x baseline ceiling" in result.stdout


def test_hard_may_lead_with_a_frontier_model(tmp_path):
    """No ceiling for `hard`: a dearer head there is the POINT."""
    list_path, _ = _matching(tmp_path)
    # every pool present and matching, EXCEPT hard leads with the frontier model
    routing = _write(tmp_path, "routing.json",
                     _live(simple={"coding": [CHEAP, BASE]},
                           medium={"coding": [BASE, CHEAP]},
                           hard={"coding": [FRONTIER]}))

    result = _run(list_path, routing)

    assert "[ceiling]" not in result.stdout, result.stdout
    assert result.returncode == 0, result.stdout


def test_an_unlisted_model_is_a_finding(tmp_path):
    list_path, _ = _matching(tmp_path)
    routing = _write(tmp_path, "routing.json",
                     _live(medium={"coding": [BASE, "openrouter:who/what"]}))

    result = _run(list_path, routing)

    assert result.returncode == 1
    assert "[unlisted]" in result.stdout
    assert "openrouter:who/what" in result.stdout


def test_a_missing_pool_is_a_finding(tmp_path):
    list_path, _ = _matching(tmp_path)
    routing = _write(tmp_path, "routing.json", _live(simple={"coding": [CHEAP]}))

    result = _run(list_path, routing)

    assert result.returncode == 1
    assert "[missing]" in result.stdout
    assert "medium/coding" in result.stdout


def test_write_rebuilds_the_pools_and_preserves_everything_else(tmp_path):
    list_path, _ = _matching(tmp_path)
    routing = _write(tmp_path, "routing.json",
                     _live(simple={"coding": [BASE]}, medium={"coding": [DEAR]}))

    result = _run(list_path, routing, "--write")

    assert result.returncode == 0, result.stdout
    live = json.loads(routing.read_text())
    assert live["tiers"]["simple"]["coding"] == [CHEAP, BASE], "reordered from the list"
    assert live["tiers"]["medium"]["coding"] == [BASE, CHEAP]
    assert live["mode"] == "redacted-text" and live["exclude"] == ["*:free"], \
        "everything outside the pools is preserved"


def test_a_missing_list_is_could_not_verify(tmp_path):
    routing = _write(tmp_path, "routing.json", _live())

    result = _run(tmp_path / "nope.json", routing)

    assert result.returncode == 3
    assert "COULD NOT VERIFY" in result.stderr


def test_json_mode_lists_findings_machine_readably(tmp_path):
    list_path, _ = _matching(tmp_path)
    routing = _write(tmp_path, "routing.json", _live(medium={"coding": [DEAR]}))

    result = _run(list_path, routing, "--json")

    payload = json.loads(result.stdout)
    kinds = {f["kind"] for f in payload["findings"]}
    assert {"order", "ceiling"} <= kinds, payload


def test_every_priced_model_is_routed_or_named_as_a_candidate():
    """ADV-13902-2: a price with no tier and no explanation makes the artifact
    ambiguous about what actually governs routing."""
    import json as _json
    doc = _json.loads((Path(__file__).resolve().parents[1] / "config"
                       / "jev-router-models.json").read_text())
    routed = {m for specs in doc["tiers"].values() for models in specs.values() for m in models}
    priced = set(doc["prices"])
    orphans = priced - routed
    assert orphans <= set(doc.get("candidates") or {}), \
        f"priced but neither routed nor named as candidates: {sorted(orphans)}"
    # and the derivation the policy notes lean on must be in the file
    assert doc["derivation"]["heads"]["simple/*"].count("x baseline") == 1
