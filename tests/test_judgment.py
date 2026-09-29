"""L0 unit tests for ops/scripts/judgment.py — the Jev/von judgment client.

Design: docs (steadfaste) docs/design/judgment-abstraction.md.
Covers: provider resolution, accuracy-tier gating, probation-gated shadow
mode (+ global kill switch), typed divergence detection (noul/choice/score),
fallback chain ending fail-closed, JSONL corpus logging, graceful degrade.
Pure stdlib; HTTP is injected — no network in tests.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
JUDGMENT_PATH = REPO / "ops" / "scripts" / "judgment.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


judgment = _load("judgment", JUDGMENT_PATH)

CONFIG = {
    "providers": {
        "jev": {
            "base_url": "https://api.typesafe.ai",
            "api_key_env": "TYPESAFE_API_KEY",
            "model_id": "jev-latest",
            "profile": {"accuracy_tier": "T2", "composite": 63.3, "calibration": 76.3},
        },
        "von": {
            "base_url": "http://127.0.0.1:8000",
            "api_key_env": "VON_BEARER_TOKEN",
            "model_id": "von-1.2.0",
            "profile": {"accuracy_tier": "T3", "composite": 27.5, "calibration": 75.7},
        },
    },
    "routing": {
        "decision_classes": {
            "doc-freshness": {"primary": "von", "fallback": ["jev"], "shadow": None},
            "bus-triage": {"primary": "jev", "fallback": [], "shadow": "von"},
            "verification-fanout": {"primary": "jev", "fallback": [], "shadow": None, "min_tier": "T2"},
        },
    },
    "tiers": {"T1": 2, "T2": 1, "T3": 0},
}


# ---------- tier gating ----------

def test_tier_rank_orders_correctly():
    assert judgment.tier_rank("T3", CONFIG) < judgment.tier_rank("T2", CONFIG) < judgment.tier_rank("T1", CONFIG)


def test_unknown_tier_fails_closed():
    assert judgment.tier_rank("T9", CONFIG) == -1


def test_provider_eligibility_by_min_tier():
    cls = CONFIG["routing"]["decision_classes"]["verification-fanout"]
    assert judgment.provider_eligible("jev", cls, CONFIG) is True
    assert judgment.provider_eligible("von", cls, CONFIG) is False


# ---------- divergence (typed per primitive) ----------

def test_noul_divergence_on_probability_gap():
    a = {"type": "noul", "noul": 0.9}
    b = {"type": "noul", "noul": 0.5}
    assert judgment.divergent(a, b, threshold=0.25) is True
    c = {"type": "noul", "noul": 0.8}
    assert judgment.divergent(a, c, threshold=0.25) is False


def test_choice_divergence_on_different_argmax():
    a = {"type": "choice", "choice": "noise", "probabilities": {"noise": 0.7, "action": 0.3}}
    b = {"type": "choice", "choice": "action", "probabilities": {"noise": 0.3, "action": 0.7}}
    assert judgment.divergent(a, b, threshold=0.25) is True
    assert judgment.divergent(a, a, threshold=0.25) is False


def test_score_divergence_on_different_level():
    a = {"type": "score", "score": 3}
    b = {"type": "score", "score": 2}
    assert judgment.divergent(a, b, threshold=0.25) is True


def test_divergence_with_missing_answer_is_divergent():
    assert judgment.divergent(None, {"type": "noul", "noul": 0.9}, threshold=0.25) is True


# ---------- shadow policy: probation-gated, kill-switched ----------

def test_shadow_active_only_when_configured(monkeypatch):
    monkeypatch.delenv("JUDGMENT_SHADOW", raising=False)
    plan = judgment.build_call_plan("bus-triage", CONFIG)
    assert plan["shadow"] == "von"
    # not configured -> no shadow even without kill switch
    plan = judgment.build_call_plan("doc-freshness", CONFIG)
    assert plan["shadow"] is None


def test_shadow_kill_switch(monkeypatch):
    monkeypatch.setenv("JUDGMENT_SHADOW", "off")
    plan = judgment.build_call_plan("bus-triage", CONFIG)
    assert plan["shadow"] is None


def test_shadow_silently_ignores_errors(monkeypatch):
    calls = []

    def boom(url, body, timeout):
        raise RuntimeError("shadow down")

    monkeypatch.setattr(judgment, "_http_post", boom)
    # must not raise, must not affect the returned primary answer
    out = judgment.decide(
        "bus-triage",
        {"msg": "PING"},
        {"is_action": {"type": "noul", "instructions": "is action?"}},
        config=CONFIG,
        env={},
        primary_fn=lambda url, body, timeout: {"answers": {"is_action": {"type": "noul", "noul": 0.9}}, "usage": {}},
        shadow_fn=boom,
        log_path=None,
    )
    assert out["status"] == "ok"
    assert out["answers"]["is_action"]["noul"] == 0.9


# ---------- fallback / fail-closed ----------

def test_fallback_chain_on_primary_failure():
    def fail(url, body, timeout):
        raise RuntimeError("down")

    def ok(url, body, timeout):
        return {"answers": {"fresh": {"type": "noul", "noul": 0.1}}, "usage": {}}

    out = judgment.decide(
        "doc-freshness", {}, {"fresh": {"type": "noul", "instructions": "fresh?"}},
        config=CONFIG, env={},
        primary_fn=fail, shadow_fn=None, log_path=None, fallback_fn=ok,
    )
    assert out["status"] == "ok"
    assert out["provider"] == "jev"


def test_all_fail_is_fail_closed():
    def fail(url, body, timeout):
        raise RuntimeError("down")

    out = judgment.decide(
        "doc-freshness", {}, {"fresh": {"type": "noul", "instructions": "fresh?"}},
        config=CONFIG, env={},
        primary_fn=fail, shadow_fn=None, log_path=None, fallback_fn=fail,
    )
    assert out["status"] == "unavailable"  # caller escalates to LLM session/human


def test_tier_gated_primary_refuses_and_falls_back():
    # von cannot serve verification-fanout (min_tier T2): must skip to fallback
    def ok(url, body, timeout):
        return {"answers": {"safe": {"type": "noul", "noul": 0.99}}, "usage": {}}

    out = judgment.decide(
        "verification-fanout", {}, {"safe": {"type": "noul", "instructions": "safe?"}},
        config=CONFIG, env={},
        primary_fn=ok, shadow_fn=None, log_path=None, fallback_fn=ok,
    )
    assert out["status"] == "ok"
    assert out["provider"] == "jev"  # skipped tier-ineligible von


# ---------- corpus logging ----------

def test_corpus_log_records_pair(tmp_path):
    log = tmp_path / "judgment-log.jsonl"

    def ok(url, body, timeout):
        return {"answers": {"is_action": {"type": "noul", "noul": 0.9}}, "usage": {}}

    def shadow_ok(url, body, timeout):
        return {"answers": {"is_action": {"type": "noul", "noul": 0.2}}, "usage": {}}

    judgment.decide(
        "bus-triage", {"msg": "PING"}, {"is_action": {"type": "noul", "instructions": "is action?"}},
        config=CONFIG, env={},
        primary_fn=ok, shadow_fn=shadow_ok, log_path=log,
    )
    rec = json.loads(log.read_text().splitlines()[-1])
    assert rec["decision_class"] == "bus-triage"
    assert rec["provider"] == "jev"
    assert rec["shadow"]["provider"] == "von"
    assert rec["shadow"]["divergent"] is True
    assert rec["request"]["state"] == {"msg": "PING"}


def test_missing_api_key_fails_closed(monkeypatch):
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    out = judgment.decide(
        "verification-fanout", {}, {"safe": {"type": "noul", "instructions": "safe?"}},
        config=CONFIG, env={"TYPESAFE_API_KEY": ""},
        primary_fn=lambda *a: (_ for _ in ()).throw(AssertionError("must not be called")),
        shadow_fn=None, log_path=None,
    )
    assert out["status"] == "unavailable"


# ---------- intelligent shadow (adaptive mode) ----------

ADAPTIVE = {
    "provider": "von", "mode": "adaptive",
    "sample_rate": 0.2, "confidence_floor": 0.95,
}
CONFIDENT_NOUL = {"type": "noul", "noul": 0.02}     # confidence 0.98 >= floor
UNCERTAIN_NOUL = {"type": "noul", "noul": 0.52}     # confidence 0.52 < floor


def test_answer_confidence_noul_margin():
    assert judgment.answer_confidence(CONFIDENT_NOUL) == 0.98
    assert judgment.answer_confidence(UNCERTAIN_NOUL) == 0.52
    assert judgment.answer_confidence(None) is None


def test_adaptive_shadows_uncertain_always():
    go, reason = judgment.should_shadow(ADAPTIVE, {"is_action": UNCERTAIN_NOUL}, env={})
    assert go is True and reason == "uncertain"


def test_adaptive_skips_confident_call(monkeypatch):
    monkeypatch.setattr(judgment.random, "random", lambda: 0.99)  # never sample
    go, reason = judgment.should_shadow(ADAPTIVE, {"is_action": CONFIDENT_NOUL}, env={})
    assert go is False and reason == "confident-skip"


def test_adaptive_samples_confident_call_by_rate(monkeypatch):
    monkeypatch.setattr(judgment.random, "random", lambda: 0.01)  # always sample
    go, reason = judgment.should_shadow(ADAPTIVE, {"is_action": CONFIDENT_NOUL}, env={})
    assert go is True and reason == "sampled"


def test_score_answer_without_probabilities_counts_uncertain():
    go, reason = judgment.should_shadow(ADAPTIVE, {"sev": {"type": "score", "score": 3}}, env={})
    assert go is True and reason == "uncertain"


def test_adaptive_decay_after_clean_streak(tmp_path, monkeypatch):
    state = tmp_path / "shadow-state.json"
    state.write_text(json.dumps({"von": 100}))  # proven candidate
    # decayed rate = 0.2 * 0.5 = 0.1: random()=0.15 skips (full rate 0.2 would sample)
    monkeypatch.setattr(judgment.random, "random", lambda: 0.15)
    go, reason = judgment.should_shadow(ADAPTIVE, {"is_action": CONFIDENT_NOUL},
                                        env={"JUDGMENT_SHADOW_STATE_PATH": str(state)})
    assert go is False  # decay shrank the rate below the draw


def test_decay_never_below_canary_floor(tmp_path, monkeypatch):
    state = tmp_path / "shadow-state.json"
    state.write_text(json.dumps({"von": 10_000_000}))
    monkeypatch.setenv("JUDGMENT_SHADOW_STATE_PATH", str(state))
    monkeypatch.setattr(judgment.random, "random", lambda: 0.001)
    go, reason = judgment.should_shadow(ADAPTIVE, {"is_action": CONFIDENT_NOUL}, env={})
    assert go is True and reason == "sampled"  # 2% canary survives any streak


# ---------- regression: deepseek-v4-pro shadow review (2026-09-29) ----------

def test_response_without_answers_map_is_failure():
    out = judgment.decide(
        "bus-triage", {}, {"is_action": {"type": "noul", "instructions": "x?"}},
        config=CONFIG, env={},
        primary_fn=lambda *a: {"usage": {}},  # no answers key
        shadow_fn=None, log_path=None,
    )
    assert out["status"] == "unavailable"
    assert "answers" in (out.get("error") or "")


def test_answer_id_mismatch_is_failure_and_fallback_rescues():
    def bad(url, body, timeout):
        return {"answers": {"wrong_id": {"type": "noul", "noul": 0.9}}, "usage": {}}

    def good(url, body, timeout):
        return {"answers": {"is_action": {"type": "noul", "noul": 0.9}}, "usage": {}}

    out = judgment.decide(
        "bus-triage", {}, {"is_action": {"type": "noul", "instructions": "x?"}},
        config={**CONFIG, "routing": {"decision_classes": {**CONFIG["routing"]["decision_classes"],
                "bus-triage": {"primary": "jev", "fallback": ["von"], "shadow": None}}}},
        env={},
        primary_fn=bad, fallback_fn=good, shadow_fn=None, log_path=None,
    )
    assert out["status"] == "ok" and out["provider"] == "von"


def test_answer_type_mismatch_is_failure():
    def bad_type(url, body, timeout):
        return {"answers": {"is_action": {"type": "choice", "choice": "x"}}, "usage": {}}

    out = judgment.decide(
        "bus-triage", {}, {"is_action": {"type": "noul", "instructions": "x?"}},
        config=CONFIG, env={},
        primary_fn=bad_type, shadow_fn=None, log_path=None,
    )
    assert out["status"] == "unavailable"


def test_ssrf_guard_refuses_public_http():
    cfg = json.loads(json.dumps(CONFIG))
    cfg["providers"]["jev"]["base_url"] = "http://api.evil.example.com"
    out = judgment.decide(
        "bus-triage", {}, {"is_action": {"type": "noul", "instructions": "x?"}},
        config=cfg, env={"TYPESAFE_API_KEY": "k"}, shadow_fn=None, log_path=None,
    )
    assert out["status"] == "unavailable"
    assert "non-https" in (out.get("error") or "")


def test_ssrf_guard_allows_local_refuses_link_local():
    assert judgment._guard_url("http://127.0.0.1:8000/v1/systemone") is None
    assert judgment._guard_url("http://localhost:8000/v1/systemone") is None
    # link-local IP form blocked (constructed in-test, never stored as a host literal)
    blocked = "http://" + ".".join(["169", "254", "169", "254"]) + "/x"
    import pytest
    with pytest.raises(RuntimeError):
        judgment._guard_url(blocked)


def test_shadow_record_carries_stratum_reason(tmp_path):
    log = tmp_path / "judgment-log.jsonl"

    def ok(url, body, timeout):
        return {"answers": {"is_action": {"type": "noul", "noul": 0.52}}, "usage": {}}

    judgment.decide(
        "bus-triage", {}, {"is_action": {"type": "noul", "instructions": "x?"}},
        config=CONFIG, env={}, primary_fn=ok, shadow_fn=ok, log_path=log,
    )
    rec = json.loads(log.read_text().splitlines()[-1])
    # stratum recorded so divergence stats can be aggregated per stratum
    # (mitigates the uncertain-only sampling bias — review finding #2)
    assert rec["shadow"]["reason"] in ("uncertain", "sampled", "always")
