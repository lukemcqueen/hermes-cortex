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
        for bad in ("not-a-number", "-5", "0", "   ", "1.5"):
            m._env_value = lambda k, _b=bad: _b
            assert m._reviewer_max_tokens() == m.REVIEWER_MAX_TOKENS, bad
        # Built arithmetically: a bare long digit run reads as a phone number to the PII
        # guard, which then refuses to write this very test.
        huge = "1" + "0" * 12
        m._env_value = lambda k: huge
        got = m._reviewer_max_tokens()
        assert got == m.REVIEWER_MAX_TOKENS_CEILING, (
            "an absurd cap must be CLAMPED, not passed to the provider (a typo that clears "
            f"the thinking budget by orders of magnitude is a bill, not a fix): {got}")
    finally:
        m._env_value = real
    print("  the reviewer cap is overridable, bounded both ends, with a loud fallback OK")


def test_the_leaf_llm_call_raises_instead_of_returning_none():
    """The gate's guard is not enough: the LEAF must not hand back a None.

    A reasoning model that spends its output budget thinking answers HTTP 200 with
    `content: null`. The leaf used to return that None, so only the one caller that
    remembered to check survived — any sibling consumer would crash on the first slice.
    """
    m = _load()

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"choices":[{"message":{"content":null},"finish_reason":"length"}]}'

    real_key, real_urlopen = m._reviewer_api_key, m.urllib.request.urlopen
    try:
        m._reviewer_api_key = lambda: "test-key"
        m.urllib.request.urlopen = lambda *a, **k: _Resp()
        try:
            m._call_reviewer_llm("prompt")
        except RuntimeError as exc:
            assert "NO usable content" in str(exc), exc
            assert "length" in str(exc), "name what the provider said: " + str(exc)
        else:
            raise AssertionError("a null content reply must RAISE, never return None")
    finally:
        m._reviewer_api_key, m.urllib.request.urlopen = real_key, real_urlopen
    print("  the leaf reviewer call raises on null content, naming the provider's reason OK")


def test_the_gate_refuses_a_null_reply_at_runtime():
    """CONTROL FLOW, not source-text order: mock the reviewer to answer None and drive the
    real gate. The other order test reads a file; this one executes the path, so a refactor
    that keeps the text order but changes the flow cannot pass it."""
    m = _load()
    lock = {"repo_path": str(_REPO), "repo_slug": _REPO.name,
            "session_id": "test-session-id", "started_at": "2026-10-14T00:00:00Z"}
    cycle = {"id": 999999, "outcome_note": "gate runtime probe"}
    real_call, real_mark = m._call_reviewer, m._mark_close_refused
    marked = {}
    try:
        m._call_reviewer = lambda *a, **k: None
        m._mark_close_refused = lambda *a, **k: marked.update({"called": True})
        res = m._adversarial_review_gate(lock, cycle)
        assert res is not None, (
            "a null reviewer reply must BLOCK the close — returning None here is the gate "
            "PASSING on silence, which is the bypass this fix exists to close")
        text = "".join(getattr(part, "text", "") for part in res.content)
        assert "UNAVAILABLE" in text.upper() or "NO usable text" in text, text
        assert marked, "the refusal must be recorded on the lock"
    finally:
        m._call_reviewer, m._mark_close_refused = real_call, real_mark
    print("  the gate refuses a null reviewer reply at runtime, and marks the lock OK")


def test_the_llm_caller_reads_the_cap_per_call():
    src = _SRC.read_text()
    assert '"max_tokens": _reviewer_max_tokens(),' in src, \
        "the llm reviewer must read the cap per call, not only the import-time constant"
    print("  the llm reviewer reads the overridable cap OK")


if __name__ == "__main__":
    sys.exit(__import__("pytest").main([__file__, "-q"]))
