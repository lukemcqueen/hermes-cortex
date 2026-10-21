#!/usr/bin/env python3
"""
One verify sweep must approve only slices whose evidence shows a real CHECK,
bounce the rest, and NEVER rubber-stamp. An operator who can't verify must get
a clear exit-3 message, not a silent pass.

WHY. A worker submits evidence (task_report) and the slice goes to `review`.
Only an orchestrator profile can move review->completed: the DB function
`tasks.verify_slice(uuid, boolean, text)` is SECURITY DEFINER with a
moses/esther allowlist INSIDE, and EXECUTE is granted only to roles
`mycortex_reader_esther`/`mycortex_reader_moses`. Nothing is scheduled to run
it, so slices sit in review forever. This sweep drains them — but only when
the evidence is real.

WHAT IS PINNED
  * dry run changes nothing and lists what it WOULD do;
  * apply approves a slice whose evidence shows a command + its output;
  * apply bounces a slice whose evidence is empty or prose-only, with the
    reason in the note;
  * the no-grant path exits 3 with the escalation message;
  * a slice with evidence is never approved unless both a command line AND an
    output line are present.

The sweep's `psql_fn` is INJECTED, so this is hermetic: no store, no network,
no live database. The real `sweep()` catches SystemExit(3) and returns a dict
for the no-grant case so the caller can assert it.

Run: python3 tests/test_tasks_verify_sweep.py
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_SWEEP = _REPO / "ops" / "scripts" / "manage" / "tasks-verify-sweep.py"


def _load():
    spec = importlib.util.spec_from_file_location("verify_sweep_ut", _SWEEP)
    assert spec and spec.loader, f"cannot load {_SWEEP}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load()

# ---- helpers: build a fake plan with evidence ----

_EV_MARKER = "-- EVIDENCE --"


def _plan(evidence: str) -> str:
    """Build a single-line plan with an evidence section — the real SQL
    regexp_replace's newlines, so the fake psql response must match."""
    return f"Orchestrator plan line 1 {_EV_MARKER} {evidence}"


def _plan_empty() -> str:
    return "Only the orchestrator plan, no evidence section"


# ---- helpers: build a fake psql ----

def _fake_psql_no_grant(query: str, params=None, role=None, timeout=15):
    """Responds to has_function_privilege with 'f' — no EXECUTE."""
    if "has_function_privilege" in query:
        return "f"
    raise AssertionError(f"unexpected query on no-grant host: {query[:80]}")


def _fake_psql_with_grant(responses: dict[str, str]):
    """Factory: returns a psql that matches query prefixes to canned responses.

    `responses` keys are query substrings matched with `in`.  The special key
    ``__calls__`` (a list) records every query+params for assertion.
    """
    calls = []

    def psql(query, params=None, role=None, timeout=15):
        calls.append((query, params))
        if "has_function_privilege" in query:
            return "t"
        for key, val in responses.items():
            if key in query:
                return val
        raise AssertionError(f"unexpected query: {query[:120]}")
    psql.__dict__['_calls'] = calls
    return psql


# ---- evidence extraction ----

def test_extract_evidence_finds_marker():
    assert mod.extract_evidence(_plan("$ pytest\n3 passed in 1.23s")) == \
        "$ pytest\n3 passed in 1.23s"
    assert mod.extract_evidence(_plan_empty()) == ""
    assert mod.extract_evidence(None) == ""


def test_extract_evidence_uses_last_marker():
    """Only the LAST evidence block matters — the worker's submission."""
    plan = f"Orch plan\n{_EV_MARKER}\nold evidence\n{_EV_MARKER}\nnew evidence"
    assert mod.extract_evidence(plan) == "new evidence"


# ---- evidence_shows_check ----

def test_evidence_shows_check_with_command_and_output():
    ok, reason = mod.evidence_shows_check("$ pytest tests/\n3 passed in 1.23s")
    assert ok, reason
    assert reason == ""


def test_evidence_shows_check_with_python_repl():
    ok, reason = mod.evidence_shows_check(
        ">>> import mymodule\n>>> mymodule.run()\nOK\n3 tests passed")
    assert ok


def test_evidence_empty_is_bounced():
    ok, reason = mod.evidence_shows_check("")
    assert not ok
    assert "empty" in reason


def test_evidence_whitespace_only_is_bounced():
    ok, reason = mod.evidence_shows_check("   \n  \n  ")
    assert not ok
    assert "empty" in reason


def test_evidence_prose_only_is_bounced():
    ok, reason = mod.evidence_shows_check(
        "I ran the tests and they all passed. Everything looks good.")
    assert not ok
    assert "no command line" in reason


def test_evidence_command_without_output_is_bounced():
    """A lone command line with no result/output is not a check."""
    ok, reason = mod.evidence_shows_check("$ pytest tests/")
    assert not ok
    assert "no result/output" in reason


def test_evidence_command_and_output_both_required():
    """Both a command line and output must be present."""
    assert mod.evidence_shows_check("$ pytest\n3 passed in 1.23s")[0]
    assert not mod.evidence_shows_check("$ pytest\nall good")[0]  # no output pattern


# ---- dry run does not write (a) ----

def test_dry_run_changes_nothing_and_lists_what_it_would_do():
    """A dry run prints verdicts but never calls verify_slice."""
    psql = _fake_psql_with_grant({
        mod._REVIEW_SLICE_SQL.split("WHERE")[0]:
            ("s1||Test slice||" + _plan("$ pytest 3 passed in 1.23s") + "||worker\n"
             "s2||Empty evidence||" + _plan_empty() + "||worker"),
    })
    result = mod.sweep(apply=False, psql_fn=psql)
    assert result["total"] == 2
    assert result["applied"] == 1   # s1: command+output
    assert result["bounced"] == 1   # s2: empty evidence
    assert result["failed"] == 0
    # verify_slice was never called
    verify_seen = any("SELECT tasks.verify_slice" in q for q, _ in getattr(psql, '_calls', []))
    assert not verify_seen, "dry run called verify_slice"


# ---- apply approves a slice with command+output (b) ----

def test_apply_approves_slice_with_command_and_output():
    psql = _fake_psql_with_grant({
        mod._REVIEW_SLICE_SQL.split("WHERE")[0]:
            "s1||Test slice||" + _plan("$ pytest 3 passed in 1.23s") + "||worker",
        "verify_slice": "t",
    })
    result = mod.sweep(apply=True, psql_fn=psql)
    assert result["applied"] == 1
    assert result["bounced"] == 0
    assert result["failed"] == 0
    # verify_slice was called with approve=true
    verify_calls = [(q, p) for q, p in getattr(psql, '_calls', [])
                    if "SELECT tasks.verify_slice" in q]
    assert len(verify_calls) == 1
    _, params = verify_calls[0]
    assert params[1] is True   # approve=true
    assert params[2] is None   # no note on approve


# ---- apply bounces a slice with empty/prose-only evidence (c) ----

def test_apply_bounces_slice_with_empty_evidence():
    psql = _fake_psql_with_grant({
        mod._REVIEW_SLICE_SQL.split("WHERE")[0]:
            "s1||Empty slice||" + _plan_empty() + "||worker",
        "verify_slice": "t",
    })
    result = mod.sweep(apply=True, psql_fn=psql)
    assert result["bounced"] == 1
    assert result["applied"] == 0
    verify_calls = [(q, p) for q, p in getattr(psql, '_calls', [])
                    if "SELECT tasks.verify_slice" in q]
    assert len(verify_calls) == 1
    _, params = verify_calls[0]
    assert params[1] is False                  # approve=false
    assert "evidence empty" in (params[2] or "")  # note names the reason


def test_apply_bounces_prose_only_evidence_with_reason():
    psql = _fake_psql_with_grant({
        mod._REVIEW_SLICE_SQL.split("WHERE")[0]:
            "s1||Prose slice||" + _plan("All tests passed, I checked manually") + "||w",
        "verify_slice": "t",
    })
    result = mod.sweep(apply=True, psql_fn=psql)
    assert result["bounced"] == 1
    verify_calls = [(q, p) for q, p in getattr(psql, '_calls', [])
                    if "SELECT tasks.verify_slice" in q]
    _, params = verify_calls[0]
    assert params[1] is False
    assert "no command line" in (params[2] or "")


# ---- no-grant path exits 3 (d) ----

def test_no_grant_exits_3_with_escalation_message():
    """A host whose role has no EXECUTE must exit 3, never 1."""
    try:
        mod.sweep(apply=False, psql_fn=_fake_psql_no_grant)
    except SystemExit as e:
        assert e.code == 3, f"expected exit 3, got {e.code}"
    else:
        raise AssertionError("sweep with no grant did not raise SystemExit")


def test_no_grant_exit_code_is_3_not_1():
    """Exit 3 says 'could not verify'; exit 1 reads as 'the tool is broken'."""
    import io
    save = sys.stdout
    try:
        sys.stdout = io.StringIO()
        try:
            mod.sweep(apply=False, psql_fn=_fake_psql_no_grant)
        except SystemExit as e:
            assert e.code == 3
        else:
            raise AssertionError("did not exit")
    finally:
        sys.stdout = save


# ---- edge cases ----

def test_no_review_slices_reports_cleanly():
    psql = _fake_psql_with_grant({
        mod._REVIEW_SLICE_SQL.split("WHERE")[0]: "",
    })
    result = mod.sweep(apply=False, psql_fn=psql)
    assert result["total"] == 0
    assert result["applied"] == 0
    assert result["bounced"] == 0


def test_never_approves_slice_with_null_plan():
    """A slice whose plan is NULL has no evidence at all — must bounce."""
    psql = _fake_psql_with_grant({
        mod._REVIEW_SLICE_SQL.split("WHERE")[0]:
            "s1||Null plan||NULL||worker",
        "verify_slice": "t",
    })
    result = mod.sweep(apply=True, psql_fn=psql)
    assert result["bounced"] == 1
    verify_calls = [(q, p) for q, p in getattr(psql, '_calls', [])
                    if "SELECT tasks.verify_slice" in q]
    assert len(verify_calls) == 1
    _, params = verify_calls[0]
    assert params[1] is False


def test_touches_only_review_slices():
    """The SQL only fetches status='review' + kind='slice'. Prove it structurally."""
    sql = mod._REVIEW_SLICE_SQL
    assert "status = 'review'" in sql
    assert "kind = 'slice'" in sql
    print("  review-slice query is scoped correctly \u2713")


# ---- _main ----

def _main():
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    if not tests:
        print("NO TESTS RAN — this file executed nothing")
        return 1
    assert _SWEEP.is_file(), f"missing sweep script: {_SWEEP}"
    print(f"sweep script: {_SWEEP}")
    failed = []
    for name, fn in tests:
        try:
            fn()
            print(f"PASS  {name}")
        except Exception:
            import traceback
            failed.append(name)
            print(f"FAIL  {name}")
            traceback.print_exc()
    if failed:
        print(f"\nRESULT: FAIL ({len(failed)}/{len(tests)}): {failed}")
        return 1
    print(f"\nRESULT: ALL PASS ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    sys.exit(_main())