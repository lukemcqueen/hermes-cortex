#!/usr/bin/env python3
"""Judgment client for Hermes Cortex — typed AI decisions via the System One
wire format (Jev today, von or an in-house model tomorrow).

Design: steadfaste docs/design/judgment-abstraction.md.

Contract (POST {base_url}/v1/systemone):
    {"model": ..., "state": ..., "questions": {id: {type: noul|choice|score,
     instructions, criteria?}}}  ->  {"answers": {id: {type, ...value}},
     "usage": {...}}

Guarantees:
- Code stays in control: this module returns typed answers; thresholds and
  actions belong to the caller.
- Hot-swap: providers are config; consumers never know which model served.
- Tier gating: a provider may serve a decision class only if its measured
  accuracy tier meets the class's min_tier. Ineligible providers are skipped.
- Shadow mode is PROBATION-GATED (only classes with `shadow:` configured),
  fire-and-forget, never affects the served answer, and has a global
  kill switch (JUDGMENT_SHADOW=off).
- Fail-closed: if no eligible provider answers, status="unavailable" and the
  caller escalates (LLM session / human). No silent defaults.
- Every call (primary + shadow pair) is appended to a JSONL corpus log —
  the training data for a future in-house model.

Stdlib only. Cron scripts: set JUDGMENT_CONFIG_PATH (default:
judgment-providers.yaml next to this file) and JUDGMENT_LOG_PATH.
"""
from __future__ import annotations

import json
import os
import random
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "2026-09.v1"
SHADOW_TIMEOUT_S = 3.0
PRIMARY_TIMEOUT_S = 20.0
NOUL_DIVERGENCE_THRESHOLD = 0.25
_CONFIG_CACHE: dict | None = None


# ---------------------------------------------------------------- config

def config_path(env: dict | None = None) -> Path:
    env = env if env is not None else dict(os.environ)
    p = env.get("JUDGMENT_CONFIG_PATH")
    if p:
        return Path(p)
    return Path(__file__).resolve().parent / "judgment-providers.yaml"


def load_config(env: dict | None = None, reload: bool = False) -> dict:
    """Load provider/routing config. Missing/unreadable file -> disabled client."""
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None and not reload:
        return _CONFIG_CACHE
    path = config_path(env)
    try:
        import yaml  # PyYAML is a fleet system dep; absence fails closed
        with open(path) as fh:
            cfg = yaml.safe_load(fh) or {}
    except Exception as exc:  # noqa: BLE001 — degrade to disabled, but SAY so
        print(f"judgment: config unavailable ({path}): {exc} — client disabled", flush=True)
        cfg = {}
    cfg.setdefault("providers", {})
    cfg.setdefault("routing", {}).setdefault("decision_classes", {})
    cfg.setdefault("tiers", {})
    _CONFIG_CACHE = cfg
    return cfg


# ---------------------------------------------------------------- tiers

def tier_rank(tier: str, config: dict) -> int:
    """Rank a tier name; unknown tiers rank -1 (never eligible)."""
    return config.get("tiers", {}).get(tier, -1)


def provider_eligible(provider_id: str, class_cfg: dict, config: dict) -> bool:
    """A provider is eligible if its accuracy tier meets the class min_tier."""
    prof = config.get("providers", {}).get(provider_id, {}).get("profile", {})
    rank = tier_rank(prof.get("accuracy_tier", ""), config)
    if rank < 0:
        return False
    min_tier = class_cfg.get("min_tier")
    if min_tier is None:
        return True
    return rank >= tier_rank(min_tier, config)


# ---------------------------------------------------------------- shadow

def answer_confidence(ans: dict | None) -> float | None:
    """Best-effort confidence of one typed answer (0..1), or None if unknown.

    - explicit 'confidence' field wins
    - noul: max(p, 1-p) — distance from the 0.5 flip point
    - choice: max of the probability distribution
    - score: unknown without level probabilities -> None (treated as uncertain)
    """
    if not ans:
        return None
    if isinstance(ans.get("confidence"), (int, float)):
        return float(ans["confidence"])
    t = ans.get("type")
    if t == "noul":
        p = float(ans.get("noul", 0.5))
        return max(p, 1.0 - p)
    if t == "choice":
        probs = [float(v) for v in (ans.get("probabilities") or {}).values()]
        return max(probs) if probs else None
    return None


def should_shadow(shadow_cfg, answers: dict | None, env: dict | None = None,
                  state: dict | None = None) -> tuple[bool, str]:
    """Intelligent shadow gate. Returns (shadow_now, reason).

    shadow_cfg forms:
      "provider-id"                                   -> always (probation)
      {"provider": id, "mode": "adaptive",
       "sample_rate": 0.2, "confidence_floor": 0.95}  -> intelligent
    Adaptive rule: shadow UNCERTAIN calls always (low margin = decision
    relevance is highest exactly there); confident calls are sampled at
    sample_rate — a standing low-rate sample keeps candidate-drift visible.
    JUDGMENT_SHADOW=off (kill switch) is handled upstream in build_call_plan.
    """
    env = env if env is not None else dict(os.environ)
    if not shadow_cfg:
        return False, "no-shadow"
    if isinstance(shadow_cfg, str):
        return True, "always"
    cfg = shadow_cfg if isinstance(shadow_cfg, dict) else {}
    if cfg.get("mode") != "adaptive":
        return True, "always"
    floor = float(cfg.get("confidence_floor", 0.95))
    answers = answers or {}
    if not answers:
        return True, "no-answers"
    confs = [answer_confidence(a) for a in answers.values()]
    if any(c is None or c < floor for c in confs):
        return True, "uncertain"
    rate = float(cfg.get("sample_rate", 0.0))
    # decay: consecutive clean results shrink the sample rate (state file)
    rate = max(rate * _decay_factor(cfg, env), 0.02)  # 2% drift canary floor
    if random.random() < rate:
        return True, "sampled"
    return False, "confident-skip"


_DECAY_STATE: dict | None = None

def _decay_factor(cfg: dict, env: dict) -> float:
    """<1 shrinks shadow sampling as the candidate proves itself.

    State: {class/provider key: consecutive non-divergent count}.
    clean_streak >= threshold (default 50) -> 0.5; resets to 1.0 on any
    divergence (written by the corpus-log consumer, not here).
    """
    global _DECAY_STATE
    path = env.get("JUDGMENT_SHADOW_STATE_PATH")
    if not path:
        return 1.0
    try:
        if _DECAY_STATE is None:
            with open(path) as fh:
                _DECAY_STATE = json.load(fh)
        streak = float(_DECAY_STATE.get(cfg.get("provider", ""), 0))
        threshold = float(cfg.get("decay_after_clean", 50))
        return 0.5 if streak >= threshold else 1.0
    except Exception:
        return 1.0  # no/unreadable state -> full sampling (fail towards more data)


def build_call_plan(decision_class: str, config: dict, env: dict | None = None) -> dict:
    """Resolve primary + shadow for a decision class.

    Shadow rules:
    - Active ONLY for classes configured with `shadow:` (probation list) —
      never a standing default. When a provider is added or its profile
      changes, its candidate classes enter probation by gaining a `shadow:`.
    - `JUDGMENT_SHADOW=off` is a global kill switch.
    """
    env = env if env is not None else dict(os.environ)
    cls = config["routing"]["decision_classes"].get(decision_class, {})
    shadow = cls.get("shadow")
    if env.get("JUDGMENT_SHADOW", "").lower() in ("off", "0", "false"):
        shadow = None
    return {"primary": cls.get("primary"), "shadow": shadow,
            "fallback": cls.get("fallback") or []}


# ---------------------------------------------------------------- divergence

def divergent(a: dict | None, b: dict | None,
              threshold: float = NOUL_DIVERGENCE_THRESHOLD) -> bool:
    """Typed divergence: decision-level, not raw-value level.

    noul:  probability gap > threshold (a flip in effect)
    choice: different argmax
    score: different ordinal level
    Missing/invalid answers count as divergent (never paper over).
    """
    if a is None or b is None:
        return True
    if a.get("type") != b.get("type"):
        return True
    t = a.get("type")
    if t == "noul":
        return abs(float(a.get("noul", 0.5)) - float(b.get("noul", 0.5))) > threshold
    if t == "choice":
        return a.get("choice") != b.get("choice")
    if t == "score":
        return a.get("score") != b.get("score")
    return True  # unknown primitive: fail noisy


# ---------------------------------------------------------------- http

def _http_post(base_url: str, body: dict, timeout: float, api_key: str = "") -> dict:
    url = base_url.rstrip("/") + "/v1/systemone"
    data = json.dumps(body).encode()
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def _invoke(provider_cfg: dict, body: dict, env: dict, fn=None) -> dict:
    """Call one provider. fn is the injectable transport (tests). Raises on failure."""
    key = (env.get(provider_cfg.get("api_key_env", "")) or "").strip()
    if fn is None and not key:
        raise RuntimeError(f"judgment: missing API key env {provider_cfg.get('api_key_env', '')}")
    payload = dict(body)
    payload["model"] = provider_cfg.get("model_id", "jev-latest")
    if fn is not None:
        return fn(provider_cfg["base_url"], payload, PRIMARY_TIMEOUT_S)
    return _http_post(provider_cfg["base_url"], payload, PRIMARY_TIMEOUT_S, api_key=key)


# ---------------------------------------------------------------- decide

def decide(decision_class: str, state, questions: dict, config: dict | None = None,
           env: dict | None = None, primary_fn=None, shadow_fn=None,
           fallback_fn=None, log_path=None) -> dict:
    """Ask one decision class. Returns {status, provider, answers, ...}.

    status "ok"           — an eligible provider answered; answers present
    status "unavailable"  — none answered: caller escalates (fail-closed)
    Shadow, when active, never influences the primary answer or status.
    """
    env = env if env is not None else dict(os.environ)
    config = config if config is not None else load_config(env)
    plan = build_call_plan(decision_class, config, env)
    class_cfg = config["routing"]["decision_classes"].get(decision_class, {})
    body = {"state": state, "questions": questions}

    primary_result, primary_err = None, None
    primary_id = plan["primary"]
    if primary_id and provider_eligible(primary_id, class_cfg, config):
        try:
            primary_result = _invoke(config["providers"][primary_id], body, env, primary_fn)
        except Exception as exc:  # noqa: BLE001 — fail-closed on ANY provider error
            primary_err = str(exc)

    if primary_result is None:
        for fb_id in plan["fallback"]:
            if not provider_eligible(fb_id, class_cfg, config):
                continue
            try:
                primary_result = _invoke(config["providers"][fb_id], body, env,
                                         fallback_fn or primary_fn)
                primary_id, primary_err = fb_id, None
                break
            except Exception as exc:  # noqa: BLE001
                primary_err = str(exc)

    # shadow: intelligent gate (uncertain -> always; confident -> sampled),
    # fire-and-forget, best-effort, corpus only
    shadow_rec = None
    do_shadow, shadow_reason = should_shadow(plan["shadow"], (primary_result or {}).get("answers"), env)
    if do_shadow and primary_result is not None:
        s_id = plan["shadow"].get("provider") if isinstance(plan["shadow"], dict) else plan["shadow"]
        try:
            if not s_id:
                raise RuntimeError("shadow config missing 'provider'")
            s_body = dict(body)
            s_ans = _invoke(config["providers"][s_id], s_body, env,
                            shadow_fn or primary_fn).get("answers")
            diffs = {q: divergent(primary_result["answers"].get(q), s_ans.get(q))
                     for q in questions if q in (s_ans or {})}
            shadow_rec = {"provider": s_id, "reason": shadow_reason, "answers": s_ans,
                          "divergent": any(diffs.values()),
                          "divergent_questions": diffs}
        except Exception as exc:  # noqa: BLE001 — shadow failures are never fatal, but logged
            print(f"judgment: shadow provider {s_id} failed: {exc}", flush=True)
            shadow_rec = {"provider": s_id, "reason": shadow_reason, "answers": None,
                          "divergent": None, "divergent_questions": {}}

    rec = {"ts": datetime.now(timezone.utc).isoformat(), "decision_class": decision_class,
           "provider": primary_id, "schema_version": SCHEMA_VERSION,
           "request": {"state": state, "questions": questions},
           "answers": (primary_result or {}).get("answers"),
           "status": "ok" if primary_result else "unavailable"}
    if primary_err:
        rec["error"] = primary_err
    if shadow_rec is not None:
        rec["shadow"] = shadow_rec

    if log_path is None:
        log_path = env.get("JUDGMENT_LOG_PATH")
    if log_path:
        try:
            with open(log_path, "a") as fh:
                fh.write(json.dumps(rec) + "\n")
        except OSError as exc:
            print(f"judgment: corpus log write failed ({log_path}): {exc}", flush=True)

    if primary_result is None:
        return {"status": "unavailable", "provider": primary_id,
                "answers": None, "error": primary_err}
    return {"status": "ok", "provider": primary_id,
            "answers": primary_result["answers"],
            "usage": primary_result.get("usage"), "shadow": shadow_rec}


if __name__ == "__main__":  # smoke: config load + plan resolution
    cfg = load_config(reload=True)
    print(json.dumps({"providers": sorted(cfg["providers"]),
                      "classes": sorted(cfg["routing"]["decision_classes"])}))
