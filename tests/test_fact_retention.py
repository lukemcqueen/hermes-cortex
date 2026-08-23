#!/usr/bin/env python3
"""Tests for fact-retention-eval.py — compaction "never silent truncation" (O7-S2).

Run: python3 tests/test_fact_retention.py
     (or: python3 -m pytest tests/test_fact_retention.py -v)

Verifies:
  1. The probe builds a compressible conversation (middle region exists)
  2. Real ContextCompressor.compress() shrinks the transcript
  3. HEAD facts survive verbatim (protect_first_n guarantee)
  4. TAIL facts survive verbatim (protect_last_n token-budget guarantee)
  5. Last actionable USER turns survive verbatim (min_tail_user_messages)
  6. A compaction summary marker is inserted (never silent deletion)
  7. Probe exits 0 with parseable JSON when all guarantees hold

The probe runs the REAL compressor mechanics (boundary math, token budgets,
tail protection) with the summarizer LLM stubbed — deterministic, no API.
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_PROBE = _REPO / "ops" / "scripts" / "manage" / "fact-retention-eval.py"
_VENV_PY = Path.home() / ".hermes" / "hermes-agent" / "venv" / "bin" / "python3"

_spec = importlib.util.spec_from_file_location("fre", str(_PROBE))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


def test_conversation_has_all_regions():
    msgs = _mod.build_conversation()
    # system + head + middle + tail + user turns
    assert msgs[0]["role"] == "system"
    assert len(msgs) > 40, f"conversation too small: {len(msgs)}"
    texts = "\n".join(str(m.get("content") or "") for m in msgs)
    for f in _mod.HEAD_FACTS + _mod.MIDDLE_FACTS + _mod.TAIL_FACTS + _mod.USER_FACTS:
        assert f in texts, f"fact not planted: {f}"


def test_compressor_opens_compress_window():
    messages = _mod.build_conversation()
    compressor = _mod.make_compressor()
    head_size = compressor._protect_head_size(messages)
    compress_start = compressor._align_boundary_forward(messages, head_size)
    compress_end = compressor._find_tail_cut_by_tokens(messages, compress_start)
    assert compress_start < compress_end, (
        f"no compressible window: start={compress_start} end={compress_end} "
        f"tail_budget={compressor.tail_token_budget}"
    )


def test_compress_shrinks_transcript():
    messages = _mod.build_conversation()
    compressor = _mod.make_compressor()
    from unittest.mock import MagicMock, patch

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = "test summary"
    with patch(
        "agent.context_compressor.call_llm", return_value=mock_response
    ):
        compressed = compressor.compress(messages, current_tokens=90_000)
    assert len(compressed) < len(messages), (
        f"compression did not shrink: {len(messages)} -> {len(compressed)}"
    )


def test_head_tail_user_facts_survive_verbatim():
    """The hard guarantee: protected regions are never silently truncated."""
    messages = _mod.build_conversation()
    compressor = _mod.make_compressor()
    from unittest.mock import MagicMock, patch

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = (
        "[CONTEXT SUMMARY]\nGoal: test.\nProgress: condensed.\n"
    )
    with patch(
        "agent.context_compressor.call_llm", return_value=mock_response
    ):
        compressed = compressor.compress(messages, current_tokens=90_000)

    full_text = _mod.region_text(compressed)
    for f in _mod.HEAD_FACTS:
        assert f in full_text, f"HEAD fact lost: {f}"
    for f in _mod.TAIL_FACTS:
        assert f in full_text, f"TAIL fact lost: {f}"
    for f in _mod.USER_FACTS:
        assert f in full_text, f"USER fact lost: {f}"


def test_summary_marker_inserted():
    """Compaction inserts a visible summary row — never silent deletion."""
    messages = _mod.build_conversation()
    compressor = _mod.make_compressor()
    from unittest.mock import MagicMock, patch

    mock_response = MagicMock()
    mock_response.choices = [MagicMock()]
    mock_response.choices[0].message.content = (
        "[CONTEXT SUMMARY]\nGoal: test.\nProgress: condensed.\n"
    )
    with patch(
        "agent.context_compressor.call_llm", return_value=mock_response
    ):
        compressed = compressor.compress(messages, current_tokens=90_000)

    assert any(
        isinstance(m.get("content"), str)
        and _mod.SUMMARY_PREFIX in m["content"]
        for m in compressed
    ), "no compaction summary marker in compressed transcript"


def test_probe_exit_zero_with_json():
    """End-to-end: the probe script itself passes and emits parseable JSON."""
    if not _VENV_PY.exists():
        import pytest

        pytest.skip("hermes-agent venv not present on this host")
    r = subprocess.run(
        [str(_VENV_PY), str(_PROBE)],
        capture_output=True, text=True, timeout=90,
    )
    assert r.returncode == 0, f"probe rc={r.returncode}: {r.stdout[-300:]} {r.stderr[-300:]}"
    report = None
    for line in reversed(r.stdout.strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            report = json.loads(line)
            break
    assert report is not None, f"no JSON in probe stdout: {r.stdout[-300:]}"
    assert report["passed"] is True, f"probe reports failed: {report}"
    for g in ("head_verbatim", "tail_verbatim", "user_turn_verbatim", "summary_marker_present"):
        assert report["guarantees"][g] is True, f"guarantee {g} not met"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS {name}")
            except Exception as e:  # noqa: BLE001
                failures += 1
                print(f"  FAIL {name}: {type(e).__name__}: {e}")
    sys.exit(1 if failures else 0)
