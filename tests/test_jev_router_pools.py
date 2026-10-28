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
    named = set(doc.get("candidates") or {}) | set(doc.get("rejected") or {})
    assert orphans <= named, \
        f"priced but neither routed nor named as candidates/rejected: {sorted(orphans)}"
    # and every head the policy leans on carries its arithmetic in the file
    heads = doc["derivation"]["heads"]
    assert heads and all("x baseline" in v for v in heads.values()), heads


def _config():
    import json as _json
    return _json.loads((Path(__file__).resolve().parents[1] / "config"
                        / "jev-router-models.json").read_text())


def _bl(doc, model):
    x = doc["prices"][model]
    return x["in"] + x["out"]


def test_every_non_hard_pool_head_is_cheaper_than_the_baseline():
    """Luke's rule: always cheaper, except very complex work. The HEAD is what first fit
    takes, so a head at or above the baseline is the rule broken."""
    doc = _config()
    base = _bl(doc, doc["baseline"])
    offenders = []
    for tier, specs in doc["tiers"].items():
        if tier == "hard":
            continue
        for spec, models in specs.items():
            if _bl(doc, models[0]) >= base:
                offenders.append(f"{tier}/{spec} -> {models[0]}")
    assert not offenders, f"heads not cheaper than the baseline: {offenders}"


def test_every_model_in_a_simple_pool_is_cheaper_than_the_baseline():
    """'ALWAYS cheaper' is a claim about the whole simple pool, not only its head."""
    doc = _config()
    base = _bl(doc, doc["baseline"])
    offenders = [f"simple/{spec} -> {m}" for spec, models in doc["tiers"]["simple"].items()
                 for m in models if _bl(doc, m) >= base]
    assert not offenders, f"simple pools contain models at/above baseline: {offenders}"


def test_a_rejected_model_is_never_also_a_candidate():
    """ADV-13902-3: 'rejected' and 'promotable by a one-file edit' cannot both be true."""
    doc = _config()
    rejected = set(doc.get("rejected") or {})
    candidates = set(doc.get("candidates") or {})
    assert not (rejected & candidates), f"both rejected and a candidate: {sorted(rejected & candidates)}"
    assert doc["rejected"]["openrouter:moonshotai/kimi-k2.7-code"]["price_usd_per_m"] > _bl(doc, doc["baseline"])


def test_the_derivation_covers_every_pool_head():
    """ADV-13902-5: two heads computed and the rest implicit is how an unverified claim
    survives. Every head must carry its arithmetic."""
    doc = _config()
    expected = {f"{tier}/{spec}" for tier, specs in doc["tiers"].items() for spec in specs}
    assert expected <= set(doc["derivation"]["heads"]), \
        f"heads without derivation: {sorted(expected - set(doc['derivation']['heads']))}"


def test_simple_pools_respect_their_own_ceiling():
    """ADV-13902-1/2: the file said 0.5x and a simple pool carried a 0.62x model. A
    stated ceiling the contents violate is a promise nobody can trust."""
    doc = _config()
    base = _bl(doc, doc["baseline"])
    ceiling = float(doc["policy"]["simple"]["max_multiple_of_baseline"])
    offenders = [f"simple/{spec} -> {m} (${_bl(doc, m):.3f}/M = {_bl(doc, m)/base:.2f}x)"
                 for spec, models in doc["tiers"]["simple"].items() for m in models
                 if _bl(doc, m) > base * ceiling]
    assert not offenders, f"above the simple ceiling ({ceiling:g}x): {offenders}"


def test_hard_routes_only_whitelisted_models():
    """Luke 2026-10-28: the hard tier is the exception for complex work, not a licence to
    spend 28x. Only models that fit the budget may be routed there."""
    doc = _config()
    assert doc["policy"]["hard"]["whitelist_only"] is True
    wl = set(doc["hard_whitelist"])
    assert wl, "the whitelist is the control; it cannot be empty"
    offenders = [f"hard/{spec} -> {m}" for spec, models in doc["tiers"]["hard"].items()
                 for m in models if m not in wl]
    assert not offenders, f"hard routes models off the whitelist: {offenders}"


def test_no_model_dearer_than_the_hard_cap_is_even_listed():
    """'Keep the ridiculously expensive models out of our list completely.' The cap is an
    absolute $/M so a cheaper baseline cannot move it. `rejected` is exempt: it records why
    a dear model is NOT routed, price and all."""
    doc = _config()
    cap = float(doc["policy"]["hard"]["max_price_usd_per_m"])
    rejected = set(doc.get("rejected") or {})
    offenders = [f"{m} ${_bl(doc, m):.3f}/M" for m in doc["prices"]
                 if m not in rejected and _bl(doc, m) > cap]
    assert not offenders, f"above the ${cap:.2f}/M hard cap but still in the file: {offenders}"


def test_the_whitelist_head_is_deepseek_v4_pro_and_stays_affordable():
    """Luke's pick, and the reason it qualifies: cheapest pro seat, 1048k ctx."""
    doc = _config()
    base = _bl(doc, doc["baseline"])
    head = doc["tiers"]["hard"]["coding"][0]
    assert head == "openrouter:deepseek/deepseek-v4-pro-0813"
    cap = float(doc["policy"]["hard"]["max_price_usd_per_m"])
    assert _bl(doc, head) <= cap, f"{head} is ${_bl(doc, head):.3f}/M - over the ${cap:.2f}/M cap"
    assert doc["hard_whitelist"][head]["ctx"] >= 200000


def test_the_baseline_is_the_model_the_host_actually_runs():
    """Luke 2026-10-28: the default model is deepseek-v4-flash-0731. The multipliers and the
    doctor's cost guard are anchored to the baseline, so a baseline that is not the model we
    run makes every 'x cheaper' claim compare against the wrong thing."""
    doc = _config()
    assert doc["baseline"] == "openrouter:deepseek/deepseek-v4-flash-0731"
    assert doc["prices"][doc["baseline"]]["in"] + doc["prices"][doc["baseline"]]["out"] < 0.560


def test_every_model_in_a_medium_pool_is_within_the_medium_ceiling():
    """The medium ceiling is 1x: the fallback is allowed to BE the baseline, but nothing
    dearer may sit in the pool. Caught for real when the baseline got cheaper and left the
    old, dearer baseline stranded above the new ceiling."""
    doc = _config()
    base = _bl(doc, doc["baseline"])
    ceiling = float(doc["policy"]["medium"]["max_multiple_of_baseline"])
    offenders = [f"medium/{spec} -> {m} (${_bl(doc, m):.3f}/M = {_bl(doc, m)/base:.2f}x)"
                 for spec, models in doc["tiers"]["medium"].items() for m in models
                 if _bl(doc, m) > base * ceiling]
    assert not offenders, f"above the medium ceiling ({ceiling:g}x): {offenders}"
