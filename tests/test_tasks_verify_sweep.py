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
  * an engine that cannot be reached exits 4 with an ENGINE message — never the
    exit-3 no-grant message (pro finding ADV-0-2);
  * rows are JSON, so a worker's own text containing psql's '||' column
    separator still parses with every field intact (pro finding ADV-0-3);
  * rows the query returned but the parser cannot read STOP the sweep instead of
    being reported as an empty queue;
  * a slice with evidence is never approved unless both a command line AND an
    output line are present.

The sweep's `psql_fn` is INJECTED, so this is hermetic: no store, no network,
no live database. The no-grant path PRINTS the escalation message and raises
`SystemExit(3)` — sweep() does not return a dict for that case, so the tests
assert the exit code rather than a return value (corrected under pro finding
ADV-0-5, which caught this docstring describing a catch that does not exist).

Run: python3 tests/test_tasks_verify_sweep.py
"""

from __future__ import annotations

import importlib.util
import io
import json
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

def _row(rid: str, content: str, plan: str | None,
         created_by: str = "worker") -> str:
    """ONE line of psql output, exactly as the sweep's query now emits it.

    `SELECT json_build_object(...)::text` under `-t -A` yields one JSON object per
    line with control characters escaped INSIDE the string, so a row's own text can
    never be mistaken for a line boundary or a field boundary.
    """
    return json.dumps({"id": rid, "content": content, "plan": plan,
                       "created_by": created_by})


def _capture_exit(fn) -> tuple[int | str | None, str]:
    """Run fn() and return (exit code, everything it printed to stdout)."""
    buf, save = io.StringIO(), sys.stdout
    try:
        sys.stdout = buf
        try:
            fn()
        except SystemExit as e:
            return e.code, buf.getvalue()
        else:
            raise AssertionError("expected the sweep to exit, but it returned")
    finally:
        sys.stdout = save


def _fake_psql_no_grant(query: str, params=None, role=None, timeout=15):
    """Responds to has_function_privilege with 'f' — no EXECUTE."""
    if "has_function_privilege" in query:
        return "f"
    raise AssertionError(f"unexpected query on no-grant host: {query[:80]}")


def _fake_psql_engine_down(query: str, params=None, role=None, timeout=15):
    """An engine that cannot answer at all.

    This is the shape the real seam produces: task-db.psql() prints the error and
    calls sys.exit(1) for a missing docker/psql, a container that is down, or any SQL
    error — it never returns a value.
    """
    raise SystemExit(1)


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
            "\n".join([
                _row("s1", "Test slice", _plan("$ pytest 3 passed in 1.23s")),
                _row("s2", "Empty evidence", _plan_empty()),
            ]),
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
            _row("s1", "Test slice", _plan("$ pytest 3 passed in 1.23s")),
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
            _row("s1", "Empty slice", _plan_empty()),
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
            _row("s1", "Prose slice", _plan("All tests passed, I checked manually"), "w"),
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
    code, _out = _capture_exit(lambda: mod.sweep(apply=False, psql_fn=_fake_psql_no_grant))
    assert code == 3


# ---- engine unreachable is NOT no-grant (ADV-0-2) ----

def test_engine_unreachable_is_not_reported_as_no_grant():
    """PRO REVIEW FINDING ADV-0-2 (cycle 13536 / issue #206): the capability gate
    caught SystemExit broadly and returned False, so a host that could not reach the
    ENGINE at all was told 'This host cannot verify — no role with EXECUTE on
    tasks.verify_slice' — a cause nobody had asked the database about.

    A privilege answer arrives as DATA ('t'/'f') and never exits, so any exit means the
    question was never answered: exit 4 carrying the engine detail, never exit 3
    carrying the no-grant message.
    """
    code, out = _capture_exit(lambda: mod.sweep(apply=False, psql_fn=_fake_psql_engine_down))
    assert code == 4, f"expected exit 4 (could not verify), got {code}"
    assert "no role with EXECUTE" not in out, \
        f"an engine failure was misreported as a missing grant: {out!r}"
    assert "Could not reach" in out, out
    print("  engine-down exits 4 with the engine message, never 'no grant' \u2713")


def test_engine_unreachable_exit_differs_from_no_grant():
    """The two outcomes must stay DISTINCT — collapsing them is the bug itself."""
    engine_code, _ = _capture_exit(
        lambda: mod.sweep(apply=False, psql_fn=_fake_psql_engine_down))
    grant_code, _ = _capture_exit(
        lambda: mod.sweep(apply=False, psql_fn=_fake_psql_no_grant))
    assert engine_code != grant_code, (
        f"engine-unreachable and no-grant share exit {engine_code} — one of them is "
        "being misreported")


# ---- rows are JSON, not '||'-delimited (ADV-0-3 / ADV-13540-3) ----

def test_row_with_column_separator_in_content_still_parses():
    """PRO REVIEW FINDING ADV-0-3 (cycle 13536 / issue #208; fixed under ADV-13540-3).

    psql joins COLUMNS with '||' (task-db.py runs it with `-F '||'`), while content and
    plan are arbitrary worker-written text. A plan carrying shell evidence such as
    `pytest || true` produced extra fields, so `plan` and `created_by` shifted and the
    row was judged on the wrong text — or dropped outright.
    """
    content = "Fix the sweep || never lose a row"
    plan = _plan("$ pytest -q tests/ || true\n3 passed in 1.23s")
    row = _row("s1", content, plan, created_by="worker||x")

    parsed = mod._parse_row(row)
    assert parsed is not None, "a row containing '||' failed to parse"
    assert parsed["id"] == "s1"
    assert parsed["content"] == content
    assert parsed["plan"] == plan
    assert parsed["created_by"] == "worker||x"

    # and the row is judged on THAT text, not on a shifted field
    psql = _fake_psql_with_grant({
        mod._REVIEW_SLICE_SQL.split("WHERE")[0]: row,
        "verify_slice": "t",
    })
    result = mod.sweep(apply=True, psql_fn=psql)
    assert result["total"] == 1
    assert result["applied"] == 1, result
    verify_calls = [(q, p) for q, p in getattr(psql, "_calls", [])
                    if "SELECT tasks.verify_slice" in q]
    assert verify_calls[0][1][0] == "s1"
    print("  '||' inside content/plan parses intact; the row is judged on its own text \u2713")


def test_review_query_emits_json_rows_and_never_splits_on_separator():
    """Structural pin for ADV-0-3: the row format is JSON, and the parser does not
    split rows on the separator psql uses between COLUMNS."""
    assert "json_build_object" in mod._REVIEW_SLICE_SQL, \
        "the review query no longer emits JSON rows"
    src = _SWEEP.read_text(encoding="utf-8")
    assert 'split("' + "||" + '")' not in src, \
        "the parser splits rows on psql's column separator again"
    print("  review rows are JSON; no delimiter split \u2713")


def test_unreadable_rows_stop_the_sweep_instead_of_looking_empty():
    """A query that ANSWERED and could not be read is a could-not-verify — never
    'No slices in review', which is the silent drop ADV-0-3 warned about."""
    psql = _fake_psql_with_grant({
        mod._REVIEW_SLICE_SQL.split("WHERE")[0]: "not json at all",
    })
    code, out = _capture_exit(lambda: mod.sweep(apply=False, psql_fn=psql))
    assert code == 4, f"expected exit 4, got {code}"
    assert "No slices in review" not in out, out
    print("  unreadable rows stop the sweep; never reported as an empty queue \u2713")


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
    """A slice whose plan is NULL has no evidence at all — must bounce.

    SQL NULL arrives as JSON `null`, which _parse_row turns into plan=None.
    """
    psql = _fake_psql_with_grant({
        mod._REVIEW_SLICE_SQL.split("WHERE")[0]:
            _row("s1", "Null plan", None),
        "verify_slice": "t",
    })
    assert mod._parse_row(_row("s1", "Null plan", None))["plan"] is None
    result = mod.sweep(apply=True, psql_fn=psql)
    assert result["bounced"] == 1
    verify_calls = [(q, p) for q, p in getattr(psql, '_calls', [])
                    if "SELECT tasks.verify_slice" in q]
    assert len(verify_calls) == 1
    _, params = verify_calls[0]
    assert params[1] is False


def test_prose_mentioning_a_tool_and_a_count_bounces():
    """PRO REVIEW FINDING ADV-0-1 (cycle 13536 / issue #206): the check was SUBSTRING-based, so
    prose such as "I ran bash and got 3 passed" satisfied both the command and the output patterns
    and would have been APPROVED — the rubber-stamp this module's docstring promises not to be.

    The command pattern is now ANCHORED at the line start, so a sentence that merely MENTIONS a tool
    cannot satisfy it, while a real transcript (a prompt line, or a bare tool invocation at the start
    of a line) still does.
    """
    ok, why = mod.evidence_shows_check("I ran bash and it worked, 3 passed")
    assert not ok, f"prose must bounce, got {ok}"
    assert "command" in why, why

    ok_prompt, why_prompt = mod.evidence_shows_check("$ pytest -q tests/\n3 passed in 1.23s")
    assert ok_prompt, f"a real transcript with a prompt must still be approved: {why_prompt}"

    ok_bare, why_bare = mod.evidence_shows_check("pytest -q tests/\n3 passed in 1.23s")
    assert ok_bare, f"a bare tool invocation at line start must still count: {why_bare}"

    print("  prose mentioning a tool bounces; real transcripts still approve ✓")


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
