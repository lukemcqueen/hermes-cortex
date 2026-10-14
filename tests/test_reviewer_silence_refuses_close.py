#!/usr/bin/env python3
"""A SILENT reviewer must REFUSE the close — never crash it, and never pass it.

Measured 2026-10-14 (cycle 12530): the reviewer LLM answered with a 200 whose message
content was null. `_extract_verdict` already treats that as "nothing was judged" and
returns FINDINGS with an EMPTY findings list — but the review row still sliced the RAW
reply (`reviewer_text[:2000]`), so end_change died with "'NoneType' object is not
subscriptable", leaving the lock HELD with nothing recorded. That is the worst outcome
available, and precisely what the parse guard's own comment says it was written to stop.

The same input carries a second, quieter danger: FINDINGS with an empty findings list is
the "only LOW severity" path, which ANNOTATES and lets the close through. So a reviewer
that answers with silence would have PASSED the gate the moment the crash was papered
over by defaulting the text to "".

Both halves are pinned here: the truth table of the usability guard, and the ORDER in the
gate that makes the guard effective before anything consumes the reply.

Run: python3 -m pytest tests/test_reviewer_silence_refuses_close.py -q
"""

import importlib.util
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SRC = _REPO / "mcp-servers" / "loop-gov-mcp.py"


def _load():
    spec = importlib.util.spec_from_file_location("loop_gov_silence", _SRC)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_a_silent_reviewer_reply_is_not_usable():
    """Null (a starved reasoning model), empty, and whitespace are all "nothing judged"."""
    m = _load()
    assert hasattr(m, "_reviewer_reply_is_usable"), \
        "the gate needs one predicate for 'the reviewer actually said something'"
    for bad in (None, "", "   \n\t ", 0, []):
        assert m._reviewer_reply_is_usable(bad) is False, f"{bad!r} must not be usable"
    for good in ('{"verdict": "CLEAN", "findings": []}', "### Findings\nnone"):
        assert m._reviewer_reply_is_usable(good) is True, f"{good!r} must be usable"
    print("  a null/empty/whitespace reply is not usable; real prose is OK")


def test_extract_verdict_still_fails_closed_on_a_null_reply():
    """Why the guard has to live UPSTREAM: the parse maps silence to FINDINGS with no
    findings, which the severity policy then reads as 'nothing blocking'."""
    m = _load()
    verdict, findings = m._extract_verdict(None)
    assert verdict == "FINDINGS" and findings == "[]", (verdict, findings)
    blocking, annot = m._blocking_findings(findings)
    assert not blocking, "an empty findings list has no blockers — hence the upstream guard"
    print("  silence parses to FINDINGS with no blockers, so it must never reach the policy OK")


def test_the_gate_checks_usability_before_anything_slices_the_reply():
    # Match the CODE construct, not a bare `reviewer_text[:2000]`: the docstring that
    # explains this bug quotes that literal, so a plain find() matches the EXPLANATION
    # and reports the whole file as "sliced before the guard" (observed, 2026-10-14).
    src = _SRC.read_text()
    guard_call = "_reviewer_reply_is_usable(reviewer_text)"
    slice_call = "(reviewer_text[:2000] + _ref_note)"
    guard_at = src.find(guard_call)
    slice_at = src.find(slice_call)
    assert guard_at != -1, f"the gate must consult {guard_call} on the reply itself"
    assert slice_at != -1, f"the review row still records {slice_call}"
    assert guard_at < slice_at, \
        "the guard must run BEFORE the slice — that order is what the crash was"
    between = src[guard_at:slice_at]
    assert "REVIEWER_UNAVAILABLE" in between, \
        "a silent reply must take the reviewer-unavailable REFUSAL path, not a pass"
    assert "_mark_close_refused" in between, \
        "the refusal must be recorded on the lock, or an outage looks like a live cycle"
    print("  the gate refuses a silent reply before slicing it, and marks the lock OK")


def test_the_output_cap_is_operator_overridable_at_call_time():
    """The cap that caused the silence must be turnable WITHOUT a deploy: a blocked close
    is exactly when an operator needs the knob, and a code constant needs a restart."""
    m = _load()
    assert hasattr(m, "_reviewer_max_tokens"), "the cap must be resolvable per call"
    real = m._env_value
    try:
        m._env_value = lambda k: None
        assert m._reviewer_max_tokens() == m.REVIEWER_MAX_TOKENS
        m._env_value = lambda k: " 24000 "
        assert m._reviewer_max_tokens() == 24000, "a set value must be honoured"
        for bad in ("not-a-number", "-5", "0"):
            m._env_value = lambda k, _b=bad: _b
            assert m._reviewer_max_tokens() == m.REVIEWER_MAX_TOKENS, bad
    finally:
        m._env_value = real
    print("  the reviewer cap is overridable and validated, with a loud fallback OK")


def test_the_llm_caller_reads_the_cap_per_call():
    src = _SRC.read_text()
    assert '"max_tokens": _reviewer_max_tokens(),' in src, \
        "the llm reviewer must read the cap per call, not only the import-time constant"
    print("  the llm reviewer reads the overridable cap OK")


if __name__ == "__main__":
    sys.exit(__import__("pytest").main([__file__, "-q"]))
