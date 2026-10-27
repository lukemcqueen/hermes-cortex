#!/usr/bin/env python3
"""A close whose per-blob pass did NO work must say so — it must not report blob work.

THE DEFECT THIS PINS. `_complete_push_range_blobs` hands the blob pass whatever is LEFT of one
240s window after the whole-range review has run, and a range call measures 180-220s. So the pass
can receive a remainder that no single blob call can fit inside. Every call it issues is then cut
at the deadline, `calls` stays 0, and each blob is appended to `remaining` — which the refusal
prints as "N blob(s) of the push range still carry no review verdict", i.e. as WORK STILL QUEUED.
The agent is told to close again, closing again repeats it, and nothing in the output names the
engine's own limit. Measured cost: four identical refusals on one change.

Two states also shared one name. `calls == 0` means either
  (a) nothing was ATTEMPTED (the window was already spent) — an engine condition, or
  (b) nothing was ELIGIBLE (every outstanding blob already carries a not-clean verdict for its
      exact content) — where the only remedy is to change the content.
They print identically today, so an agent cannot tell which one it is looking at.

WHAT IS PINNED HERE
  A. below the minimum-call floor the close STARTS NO WAVE and refuses as an ENGINE condition
     (`REVIEW_WINDOW_SPENT`), naming that zero calls were attempted — and it does not present the
     blobs as queued work;
  B. with room to work, an all-already-judged outcome refuses as `REVIEW_PENDING` and names the
     CONTENT change as the only remedy (that message is correct and must not regress);
  C. a pass that judged something still reports progress and lists what is left;
  D. no path is printed under BOTH lists: `remaining - already_judged` and `already_judged` are
     presented as disjoint sets;
  E. `CLEAN in the range` asks the coverage question with the CURRENT rules revision, so it can
     report a non-zero count instead of a structural 0.

`_complete_push_range_blobs` is driven with injected collaborators (the store, git, the reviewer
and the pass itself are all replaced), so this is hermetic: no live lock, no live DB, no network.

Run: python3 tests/test_perblob_zero_work_is_engine_condition.py
"""
import importlib.util
import logging as _logging
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SERVER = Path(os.environ.get("SERVER_UNDER_TEST") or (REPO / "mcp-servers" / "loop-gov-mcp.py"))

_gate_log = _logging.getLogger("loop-governance")
_gate_log.setLevel(_logging.CRITICAL + 1)

FLOOR = 180.0          # BLOB_REVIEW_MIN_CALL_S: the low end of the measured 180-220s call band
SHA_JUDGED = "a" * 40
SHA_LEFT = "b" * 40


def _mod():
    spec = importlib.util.spec_from_file_location("loop_gov_zero_work_under_test", SERVER)
    assert spec is not None and spec.loader is not None, f"cannot load {SERVER}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _harness(mod, pb, covered=()):
    """Stub everything `_complete_push_range_blobs` reaches outside itself.

    Returns (refusals, forwarded, seen_coverage_rev) so the assertions can read what the close
    actually did rather than re-deriving it.
    """
    refusals: list = []
    forwarded: list = []
    seen_coverage_rev: list = []

    mod._lock_repo = lambda lock: Path("/tmp/repo")
    mod._range_touches_always_review = lambda repo: True
    mod._review_template_text = lambda repo: mod.REVIEW_MARKER + "\n"
    mod._agent_author = lambda repo: "the-agent"
    mod._git_capture = lambda *a, **k: ""
    mod._complexity = lambda *a, **k: {"lines": 10, "files": 1, "is_complex": True}
    mod._reviewer_label = lambda cx: "test/judge"
    mod._mark_close_refused = lambda cycle_id, verdict, findings, lock: refusals.append(verdict)
    mod._push_range_blobs = lambda repo: {"cap.rs": SHA_JUDGED, "lib.rs": SHA_LEFT}
    mod._blob_paths_for = lambda repo, shas: sorted(
        p for p, s in {"cap.rs": SHA_JUDGED, "lib.rs": SHA_LEFT}.items() if s in set(shas or ()))

    def _coverage(blobs, conn=None, *, rules_rev=""):
        seen_coverage_rev.append(rules_rev)
        return set(covered)

    mod._blobs_with_covered_verdict = _coverage

    def _fake_pass(repo, template, ctx, run_reviewer, **kw):
        forwarded.append(kw)
        return dict(pb, blocking=pb.get("blocking") or [])

    mod._complete_blob_reviews = _fake_pass
    return refusals, forwarded, seen_coverage_rev


def _close(mod, budget_s, pb, covered=()):
    refusals, forwarded, rev = _harness(mod, pb, covered)
    res = mod._complete_push_range_blobs(
        {"session_id": "s", "task_id": "t", "description": "d", "repo_path": "/tmp/repo"},
        {"id": 7}, require_full=True, cap=4, budget_s=budget_s)
    return res, refusals, forwarded, rev


def _text(res):
    assert res is not None, "the close was PERMITTED — the blob pass must refuse here"
    return "\n".join(c.text for c in res.content if getattr(c, "text", None))


def test_00_preconditions():
    assert hasattr(mod_global, "_complete_push_range_blobs"), "subject missing"
    assert hasattr(mod_global, "BLOB_REVIEW_MIN_CALL_S"), (
        "BLOB_REVIEW_MIN_CALL_S is missing: the close has no floor for starting a blob call")


def test_a_starved_close_is_an_engine_condition():
    """A. The window is spent: zero calls were ATTEMPTED, and the message must say that."""
    mod = _mod()
    pb = {"verdicts": {}, "remaining": [SHA_JUDGED], "calls": 0,
          "already_judged": [], "failed": []}
    res, refusals, forwarded, _ = _close(mod, budget_s=30.0, pb=pb)

    assert forwarded == [], (
        "a close with 30s left must NOT start a blob wave (a call measures "
        f"{int(FLOOR)}-220s): the pass was called with {forwarded}")
    assert refusals == ["REVIEW_WINDOW_SPENT"], (
        f"expected the engine-condition marker, got {refusals}")
    text = _text(res)
    low = text.lower()
    assert "window" in low, f"the refusal must name the close's window as the cause:\n{text}"
    assert "blob calls attempted" in low, (
        f"the refusal must state how many blob calls were attempted:\n{text}")
    assert "nothing was attempted" in low or "never ran" in low, (
        f"the refusal must say the pass never ran — that is the engine condition:\n{text}")
    assert "still carry no review verdict" not in low, (
        "the starved close must not present its blobs as work still queued — that is the "
        f"one-way gate this pins:\n{text}")


def test_all_already_judged_names_the_content_change():
    """B. Nothing eligible is a different state with a different remedy."""
    mod = _mod()
    pb = {"verdicts": {}, "remaining": [SHA_JUDGED], "calls": 0,
          "already_judged": [SHA_JUDGED], "failed": []}
    res, refusals, forwarded, _ = _close(mod, budget_s=240.0, pb=pb)

    assert forwarded, "with a full window the pass must still be driven"
    assert refusals == ["REVIEW_PENDING"], (
        f"an all-already-judged close is PENDING work, not a spent window: {refusals}")
    text = _text(res)
    assert "content" in text.lower(), (
        f"the only remedy for an already-judged blob is a CONTENT change:\n{text}")
    assert "REVIEW_WINDOW_SPENT" not in text and "window" not in text.lower(), (
        f"this is not an engine condition and must not be described as one:\n{text}")


def test_a_pass_that_judged_something_still_reports_progress():
    """C. No regression to the ordinary path."""
    mod = _mod()
    pb = {"verdicts": {SHA_JUDGED: "CLEAN"}, "remaining": [SHA_LEFT], "calls": 1,
          "already_judged": [], "failed": []}
    res, refusals, _, _ = _close(mod, budget_s=240.0, pb=pb)

    assert refusals == ["REVIEW_PENDING"], f"{refusals}"
    text = _text(res)
    assert "reviewed this pass : 1" in text, f"progress must be reported:\n{text}"


def test_one_path_is_never_printed_in_both_lists():
    """D. `already_judged` is a subset of `remaining`; the MESSAGE must show them disjoint."""
    mod = _mod()
    pb = {"verdicts": {}, "remaining": [SHA_JUDGED, SHA_LEFT], "calls": 0,
          "already_judged": [SHA_JUDGED], "failed": []}
    res, _, _, _ = _close(mod, budget_s=240.0, pb=pb)
    text = _text(res)

    assert text.count("- cap.rs") == 1, (
        "cap.rs is judged-and-not-clean, so it must appear under ONE heading only "
        f"(it is in both `remaining` and `already_judged`):\n{text}")
    assert "- lib.rs" in text, f"lib.rs has no verdict at all and must be listed:\n{text}"
    # The two headings must be telling the reader different things.
    assert "never judged" in text.lower() or "no verdict" in text.lower(), (
        f"the never-judged set needs a heading of its own:\n{text}")


def test_clean_count_asks_with_the_current_rules_revision():
    """E. `CLEAN in the range` must be able to report a real count, not a structural 0."""
    mod = _mod()
    pb = {"verdicts": {}, "remaining": [SHA_LEFT], "calls": 1,
          "already_judged": [], "failed": []}
    res, _, _, seen_rev = _close(mod, budget_s=240.0, pb=pb, covered={SHA_JUDGED})
    text = _text(res)

    assert seen_rev and all(seen_rev), (
        "the coverage question was asked with an EMPTY rules revision, which `_admissible` "
        f"answers False for — the count is a structural 0: {seen_rev}")
    assert f"CLEAN in the range : 1" in text, (
        f"a stored CLEAN blob under the current rules must count:\n{text}")


mod_global = _mod()

if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS {name}")
            except AssertionError as exc:
                fails += 1
                print(f"  FAIL {name}: {exc}")
    print(f"\n{'FAILED' if fails else 'OK'} — {fails} failure(s)")
    sys.exit(1 if fails else 0)
