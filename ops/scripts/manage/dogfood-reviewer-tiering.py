#!/usr/bin/env python3
"""Dogfood for the reviewer-tiering change (commit 11e52691 / cycle 3877).

Exercises _call_reviewer routing ON THE REAL MODULE (no mocks) and prints
machine-verifiable PASS/FAIL lines. Light-but-complex changes must route to the
fast llm reviewer; heavy / always-review changes must route to the agent
backend; enforcement must hold (every branch goes through SOME reviewer).

Run (hermes venv, from repo root):
    PATH="$HOME/.hermes/hermes-agent/venv/bin:$PATH" python3 \
        ops/scripts/manage/dogfood-reviewer-tiering.py
"""
import importlib.util
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent.parent  # hermes-cortex/
MODULE = REPO / "mcp-servers" / "loop-gov-mcp.py"
_FAIL = []


def check(label: str, cond: bool, detail: str = "") -> None:
    print(f"  {'PASS' if cond else 'FAIL'}  {label}" + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        _FAIL.append(label)


def load() -> object:
    spec = importlib.util.spec_from_file_location("loop_gov_mcp", MODULE)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load loop-gov-mcp.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main() -> int:
    print("Reviewer tiering dogfood — real module, real constants, no mocks")
    m = load()
    saved = {k: os.environ.get(k) for k in
             ("ADVERSARIAL_REVIEW_BACKEND", "ADVERSARIAL_REVIEW_AGENT_NAME",
              "ADVERSARIAL_REVIEW_LIGHT_MODEL")}
    try:
        for k in saved:
            os.environ.pop(k, None)

        # Decision matrix on the real _tier() (real constants).
        check("complex-but-small -> light",
              m._tier({"lines": 60, "files": 2, "always_review": False}) == "light")
        check("always-review -> heavy",
              m._tier({"lines": 1, "files": 1, "always_review": True}) == "heavy")
        check(">=10 files -> heavy",
              m._tier({"lines": 0, "files": 10, "always_review": False}) == "heavy")
        check(">=200 lines -> heavy",
              m._tier({"lines": 200, "files": 1, "always_review": False}) == "heavy")

        # Routing on the real module. Patch ONLY the two leaf backends so we
        # prove _call_reviewer's dispatch, not the transport.
        os.environ["ADVERSARIAL_REVIEW_BACKEND"] = "agent"
        os.environ["ADVERSARIAL_REVIEW_AGENT_NAME"] = "pi"
        os.environ["ADVERSARIAL_REVIEW_LIGHT_MODEL"] = "deepseek/deepseek-v4-flash-0731"
        called = {}
        REV = '{"verdict":"CLEAN","findings":[]}'

        def fake_agent(prompt, author=None):
            called["agent"] = True
            return REV

        def fake_llm(prompt, *, model=None):
            called["light_model"] = model
            return REV

        m._call_reviewer_agent = fake_agent
        m._call_reviewer_llm = fake_llm

        m._call_reviewer("M", author="esther@x",
                         cx={"lines": 220, "files": 1, "always_review": False})
        check("heavy(220 lines) routes to the agent backend",
              called.get("agent") is True and "light_model" not in called, str(called))

        called.clear()
        m._call_reviewer("M", author="esther@x",
                         cx={"lines": 60, "files": 2, "always_review": False})
        check("light(60 lines) routes to the fast llm reviewer, NOT the agent",
              called.get("light_model") == "deepseek/deepseek-v4-flash-0731"
              and "agent" not in called, str(called))

        called.clear()
        m._call_reviewer("M", author="esther@x",
                         cx={"lines": 1, "files": 1, "always_review": True})
        check("always-review surface routes to the agent backend",
              called.get("agent") is True and "light_model" not in called, str(called))

        print()
        if _FAIL:
            print(f"{len(_FAIL)} FAILED: {', '.join(_FAIL)}")
            return 1
        print("ALL PASS — tiering routes light/ heavy / always-review correctly; enforcement held.")
        return 0
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


if __name__ == "__main__":
    sys.exit(main())
