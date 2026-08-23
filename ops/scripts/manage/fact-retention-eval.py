#!/usr/bin/env python3
"""O7-S2 fact-retention probe — "never silent truncation" verification.

Deterministic eval against the REAL ContextCompressor.compress() mechanics
(no API calls; summarizer LLM is stubbed).  Verifies the guarantees that
matter for the O7 party slice:

  1. HEAD protection  — facts in the protected head region survive verbatim.
  2. TAIL protection  — facts in the protected tail region survive verbatim.
  3. USER-TURN protection — the last actionable user turn survives verbatim
     (min_tail_user_messages guarantee).
  4. SUMMARY marker   — compaction inserts a visible [CONTEXT SUMMARY] row
     instead of silently deleting the middle (never silent truncation).
  5. MIDDLE lossy by design — facts in the summarized middle are NOT
     guaranteed verbatim (that is what the summary is for); the eval asserts
     the summary row exists and reports middle retention as informational.

Run with the hermes-agent venv python (compressor import path):
    ~/.hermes/hermes-agent/venv/bin/python3 ops/scripts/manage/fact-retention-eval.py

Exit 0 + JSON detail on pass; exit 1 on any failed guarantee.

Wire-in: registered as grader `fact_retention` in run-evals.py (shells out to
the venv python — the daily gate's system python3 cannot import the
compressor), task in evals/regression-golden.yaml.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

HOME = Path.home()
AGENT_ROOT = HOME / ".hermes" / "hermes-agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from agent.context_compressor import (  # noqa: E402
    SUMMARY_PREFIX,
    ContextCompressor,
)

# ── Synthetic conversation with planted facts ─────────────────────────────

HEAD_FACTS = [
    "HEAD-FACT-1: project codename is OPALINE",
    "HEAD-FACT-2: launch date locked to 2026-11-03",
]
TAIL_FACTS = [
    "TAIL-FACT-1: budget ceiling is $47,250",
    "TAIL-FACT-2: vendor contact is maria@example.com",
    "TAIL-FACT-3: server region is ap-northeast-2",
]
USER_FACTS = [
    "USER-FACT-1: user insists on FSC-certified packaging",
    "USER-FACT-2: user deadline is end of Q3",
]
MIDDLE_FACTS = [
    "MIDDLE-FACT-1: sample batch lot number is B-8821",
    "MIDDLE-FACT-2: prototype weight is 214 grams",
]


def build_conversation() -> list[dict]:
    """~46 messages: system + 2 head facts, ~28 middle, ~12 tail, user turns.

    Sized so the middle region exceeds the compressor's tail token budget and
    a real compress window opens (legacy tail_mode: 0.20*threshold tokens).
    """
    msgs: list[dict] = [{"role": "system", "content": "You are a test agent."}]

    # Head region (protected first_n beyond system)
    msgs.append({"role": "user", "content": f"Start. {HEAD_FACTS[0]}"})
    msgs.append({"role": "assistant", "content": f"Acknowledged. {HEAD_FACTS[1]}"})

    # Middle region (will be summarized) — ~28 turns
    for i in range(28):
        if i == 0:
            content = f"Work item {i}: {MIDDLE_FACTS[0]}"
        elif i == 1:
            content = f"Work item {i}: {MIDDLE_FACTS[1]}"
        else:
            content = f"Work item {i}: routine progress, no new facts."
        msgs.append({"role": "user", "content": content})
        msgs.append(
            {
                "role": "assistant",
                "content": (
                    f"Processed item {i}. Status nominal. "
                    f"Token padding token padding token padding token padding "
                    f"token padding token padding token padding token padding."
                ),
            }
        )

    # Tail region (protected by token-budget tail + protect_last_n)
    msgs.append({"role": "user", "content": f"Now finalizing. {TAIL_FACTS[0]}"})
    msgs.append({"role": "assistant", "content": f"Noted. {TAIL_FACTS[1]}"})
    msgs.append({"role": "user", "content": f"Also: {TAIL_FACTS[2]}"})
    msgs.append({"role": "assistant", "content": "Region locked."})

    # Last actionable user turn (min_tail_user_messages guarantee)
    msgs.append({"role": "user", "content": f"Requirement: {USER_FACTS[0]}"})
    msgs.append({"role": "assistant", "content": "Packaging requirement recorded."})
    msgs.append({"role": "user", "content": f"Timeline: {USER_FACTS[1]}"})
    msgs.append({"role": "assistant", "content": "Deadline noted; plan adjusted."})

    return msgs


def make_compressor() -> ContextCompressor:
    with patch(
        "agent.context_compressor.get_model_context_length", return_value=100_000
    ):
        return ContextCompressor(
            model="test/model",
            threshold_percent=0.50,   # 50K threshold
            protect_first_n=3,
            protect_last_n=20,
            summary_target_ratio=0.20,  # 10K tail budget
            quiet_mode=True,
            tail_mode="legacy",
        )


def stub_summarizer(content: str) -> MagicMock:
    """Return a fake call_llm response carrying the given summary text."""
    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = content
    return mock_response


def region_text(msgs: list[dict]) -> str:
    parts = []
    for m in msgs:
        c = m.get("content") or ""
        if isinstance(c, str):
            parts.append(c)
    return "\n".join(parts)


def main() -> int:
    messages = build_conversation()
    all_facts = HEAD_FACTS + MIDDLE_FACTS + TAIL_FACTS + USER_FACTS

    # Summarizer stub: lossy on middle facts — models a summarizer that drops
    # detail. The eval must still find head/tail/user facts verbatim in the
    # compressed transcript.
    summary_text = (
        "[CONTEXT SUMMARY]\n"
        "Goal: verify fact retention across compaction.\n"
        "Progress: middle work items processed; details condensed.\n"
        "Decisions: keep protected regions verbatim.\n"
    )
    compressor = make_compressor()

    with patch(
        "agent.context_compressor.call_llm", return_value=stub_summarizer(summary_text)
    ):
        try:
            compressed = compressor.compress(messages, current_tokens=90_000)
        except Exception as exc:  # pragma: no cover - failure path
            print(
                json.dumps(
                    {
                        "passed": False,
                        "detail": f"compress() raised: {type(exc).__name__}: {exc}",
                        "guarantees": {},
                        "retention": {},
                    }
                )
            )
            return 1

    full_text = region_text(compressed)

    # ── Guarantee 1: head facts survive verbatim ──────────────────────────
    head_ok = all(f in full_text for f in HEAD_FACTS)

    # ── Guarantee 2: tail facts survive verbatim ──────────────────────────
    tail_ok = all(f in full_text for f in TAIL_FACTS)

    # ── Guarantee 3: last actionable user turns survive verbatim ──────────
    user_ok = all(f in full_text for f in USER_FACTS)

    # ── Guarantee 4: summary marker inserted (never silent deletion) ───────
    summary_ok = any(
        m.get("role") == "assistant"
        and isinstance(m.get("content"), str)
        and SUMMARY_PREFIX in m["content"]
        for m in compressed
    ) or SUMMARY_PREFIX in full_text

    # ── Informational: middle retention (lossy by design) ─────────────────
    middle_retained = sum(1 for f in MIDDLE_FACTS if f in full_text)

    guarantees = {
        "head_verbatim": head_ok,
        "tail_verbatim": tail_ok,
        "user_turn_verbatim": user_ok,
        "summary_marker_present": summary_ok,
    }
    retention = {
        "head": f"{sum(1 for f in HEAD_FACTS if f in full_text)}/{len(HEAD_FACTS)}",
        "middle": f"{middle_retained}/{len(MIDDLE_FACTS)} (informational)",
        "tail": f"{sum(1 for f in TAIL_FACTS if f in full_text)}/{len(TAIL_FACTS)}",
        "user": f"{sum(1 for f in USER_FACTS if f in full_text)}/{len(USER_FACTS)}",
        "total": f"{sum(1 for f in all_facts if f in full_text)}/{len(all_facts)}",
    }

    passed = all(guarantees.values())
    print(
        json.dumps(
            {
                "passed": passed,
                "detail": (
                    "compressed {} msgs → {} msgs; guarantees: {}".format(
                        len(messages), len(compressed), guarantees
                    )
                ),
                "guarantees": guarantees,
                "retention": retention,
                "compressed_msg_count": len(compressed),
                "summary_prefix": SUMMARY_PREFIX,
            }
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
