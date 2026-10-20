#!/usr/bin/env python3
"""The gate must say what it wants BEFORE the work, not one refusal per cycle.

Operator directive (Luke, 2026-10-18): "let the agent know exactly what they need to provide
earlier". What actually happened instead is the thing this file guards against: an agent learned the
review's requirements ONE REFUSED BLOB AT A TIME — commit a runnable proof, do not lean on a sibling
the window cannot see, run the check to completion, put preconditions in a test, make the task
description cover the range — and each lesson cost a full close cycle.

So the requirements are stated once (REVIEW_EXPECTATIONS) and surfaced when a session OPENS, and the
close refusal names the PATHS that are still unreviewed rather than a bare count.

Asserted here:
  A. the scope note names the unreviewed PATHS (not the CLEAN ones) and carries every requirement;
  B. it is EMPTY when nothing is left to judge, so a solved range is not nagged about;
  C. a long list is capped and summarised ("... and N more") rather than truncated silently;
  D. SHAs reported by the pass map back to PATHS a human can act on;
  E. no repo (or an unreadable range) yields an empty scope, never an exception — opening a session
     must not be able to fail because of a review message.

The range is injected, so this test needs no git, no network and no live database.
"""
import importlib.util
import logging as _logging
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("loop_gov_guidance", REPO / "mcp-servers" / "loop-gov-mcp.py")
mcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mcp)

# The gate's real logger writes the production audit trail; a test must not add to it.
_gate_log = _logging.getLogger("loop-governance")
_gate_log.setLevel(_logging.CRITICAL + 1)

SB = "b" * 40
SA = "a" * 40
SC = "c" * 40

# A minimal review context, so _blob_material can be exercised without a session.
CTX = {"sid": "s", "author": "a", "branch": "b", "head_sha": "h", "cycle_id": 1,
       "task_id": "t", "description": "d"}


class _InjectedRange:
    """Pin the push-range lookups so the message text can be judged without a repository."""

    def __init__(self, blobs, clean=()):
        self.blobs, self.clean = dict(blobs), set(clean)

    def __enter__(self):
        self._saved = (mcp._push_range_blobs, mcp._blobs_with_covered_verdict,
                       mcp._blobs_with_recorded_verdict, mcp._git_capture,
                       mcp._push_base_is_root_fallback)
        mcp._push_range_blobs = lambda repo: dict(self.blobs)
        # Coverage is decided by _blobs_with_covered_verdict (2026-10-18): CLEAN, or findings that
        # all landed below blocking. This stub injects the COVERED set for the same reason the old
        # one injected the CLEAN set — the message text is what is under test here, and the blob
        # lookup must not need a store.
        mcp._blobs_with_covered_verdict = lambda blobs, conn=None, **kw: set(self.clean)
        # Every blob in the fake range has a recorded verdict: CLEAN when it is in `clean`, else
        # FINDINGS. The material states these so a sibling dependency is answerable with data.
        mcp._blobs_with_recorded_verdict = lambda blobs, conn=None, **kw: {
            sha: ("CLEAN" if sha in self.clean else "FINDINGS") for sha in blobs.values()}
        mcp._git_capture = lambda repo, *a: ""
        # These tests describe a RESOLVABLE range (an injected one). Without this stub the new
        # unresolvable-range branch would fire, because the fake "repo" is /tmp — which has no git.
        mcp._push_base_is_root_fallback = lambda repo: False
        return self

    def __exit__(self, *exc):
        (mcp._push_range_blobs, mcp._blobs_with_covered_verdict,
         mcp._blobs_with_recorded_verdict, mcp._git_capture,
         mcp._push_base_is_root_fallback) = self._saved
        return False


def test_00_preconditions():
    """Everything this file calls must exist, and the requirements must actually be stated."""
    for helper in ("_review_scope_note", "_unreviewed_paths", "_blob_paths_for", "_path_list"):
        assert hasattr(mcp, helper), f"missing helper {helper!r} — the guidance was not implemented"
    assert isinstance(mcp.REVIEW_EXPECTATIONS, tuple), "REVIEW_EXPECTATIONS is not a tuple"
    assert len(mcp.REVIEW_EXPECTATIONS) >= 4, (
        "fewer than four standing requirements — the ones learned the hard way have been dropped")
    assert isinstance(mcp.REVIEW_SCOPE_MAX_PATHS, int) and mcp.REVIEW_SCOPE_MAX_PATHS > 0


def test_scope_note_names_paths_and_every_requirement():
    with _InjectedRange({"z/clean.py": SA, "a/pending.py": SB}, clean={SA}):
        note = mcp._review_scope_note(Path("/tmp/does-not-matter"))
    assert "a/pending.py" in note, f"the unreviewed path must be named: {note!r}"
    assert "z/clean.py" not in note, f"a CLEAN blob is not part of the outstanding scope: {note!r}"
    missing = [e for e in mcp.REVIEW_EXPECTATIONS if e not in note]
    assert not missing, f"requirements absent from the note: {missing}"


def test_scope_note_is_empty_when_nothing_is_left():
    with _InjectedRange({"z/clean.py": SA}, clean={SA}):
        assert mcp._review_scope_note(Path("/tmp/x")) == "", (
            "a fully reviewed range must not be nagged about")


def test_long_lists_are_capped_and_summarised():
    many = [f"f/{i:03d}.py" for i in range(mcp.REVIEW_SCOPE_MAX_PATHS + 3)]
    rendered = mcp._path_list(many)
    assert "... and 3 more" in rendered, f"the overflow must be summarised: {rendered!r}"
    assert rendered.count("- f/") == mcp.REVIEW_SCOPE_MAX_PATHS, "the cap was not applied"
    assert "f/012.py" not in rendered, "a path beyond the cap leaked into the list"


def test_material_states_each_siblings_own_verdict():
    """A sibling dependency must be answerable with DATA, not with 'I cannot see it'."""
    with _InjectedRange({"a/one.py": SA, "b/two.py": SB}, clean={SA}):
        material = mcp._blob_material(Path("/tmp"), "base", "b/two.py", CTX)
    assert "sibling review status" in material, (
        "the material must state each sibling's own recorded verdict — the per-blob reviewer "
        "otherwise files the dependency as a HIGH unverified-claim it cannot resolve")
    assert "a/one.py: CLEAN — covered" in material, (
        f"the sibling's own verdict must be named with its coverage state: {material[-500:]}")


def test_preflight_advice_names_the_evidence_the_review_will_want():
    """The advice is computed from the range's OWN added lines, at session open — not after a refusal."""
    saved = (mcp._push_base, mcp._push_range_blobs, mcp._blobs_with_covered_verdict, mcp._git_capture)
    mcp._push_base = lambda repo: "base"
    mcp._push_range_blobs = lambda repo: {"a/one.py": SA}
    mcp._blobs_with_covered_verdict = lambda blobs, conn=None, **kw: set()
    mcp._git_capture = lambda repo, *a, **k: (
        "+++ b/a/one.py\n"
        "+# measured 2026-10-18: the call took 200s\n"
        "+def test_thing():\n"
    )
    try:
        advice = mcp._preflight_advice(Path("/tmp"), limit=4)
    finally:
        (mcp._push_base, mcp._push_range_blobs,
         mcp._blobs_with_covered_verdict, mcp._git_capture) = saved
    joined = " | ".join(advice)
    assert advice, "the advice must fire for a cited measurement in the range's own diff"
    assert any("pointer" in a for a in advice), (
        f"a cited measurement must ask for a pointer to its record: {joined}")
    assert all(a.startswith("a/one.py — ") for a in advice), (
        f"every item must name the file it applies to: {joined}")


def test_preflight_does_not_call_a_non_timeout_exit_a_timeout():
    """ADV-13071-1: 127 is command-not-found, not a timeout — do not advise 'run it to completion'."""
    saved = (mcp._push_base, mcp._push_range_blobs, mcp._blobs_with_covered_verdict, mcp._git_capture)
    mcp._push_base = lambda repo: "base"
    mcp._push_range_blobs = lambda repo: {"a/one.py": SA}
    mcp._blobs_with_covered_verdict = lambda blobs, conn=None, **kw: set()
    try:
        for code in ("120", "125", "126", "127", "128"):
            mcp._git_capture = (lambda c: lambda repo, *a, **k: f"+++ b/a/one.py\n+rc={c}\n")(code)
            got = mcp._preflight_advice(Path("/tmp"), limit=2)
            assert not any("TIMEOUT" in a for a in got), (
                f"rc={code} is not a timeout, but the advice called it one: {got}")
        mcp._git_capture = lambda repo, *a, **k: "+++ b/a/one.py\n+rc=124\n"
        got = mcp._preflight_advice(Path("/tmp"), limit=2)
    finally:
        (mcp._push_base, mcp._push_range_blobs,
         mcp._blobs_with_covered_verdict, mcp._git_capture) = saved
    assert any("TIMEOUT" in a for a in got), f"rc=124 IS the timeout code: {got}"


def test_preflight_advice_is_empty_when_nothing_is_outstanding():
    saved = (mcp._push_base, mcp._push_range_blobs, mcp._blobs_with_covered_verdict)
    mcp._push_base = lambda repo: "base"
    mcp._push_range_blobs = lambda repo: {"a/one.py": SA}
    mcp._blobs_with_covered_verdict = lambda blobs, conn=None, **kw: {SA}
    try:
        assert mcp._preflight_advice(Path("/tmp")) == [], (
            "a fully covered range must produce no advice — the opener stays quiet")
    finally:
        (mcp._push_base, mcp._push_range_blobs, mcp._blobs_with_covered_verdict) = saved


def test_shas_map_back_to_paths():
    with _InjectedRange({"a/one.py": SA, "b/two.py": SB}):
        assert mcp._blob_paths_for(Path("/tmp/x"), [SB]) == ["b/two.py"]


def test_no_repo_or_unreadable_range_is_never_an_exception():
    assert mcp._review_scope_note(None) == "", "no repo must yield an empty scope, not a crash"
    assert mcp._blob_paths_for(None, [SB]) == []
    with _InjectedRange({}):
        assert mcp._review_scope_note(Path("/tmp/x")) == ""


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
    raise SystemExit(1 if fails else 0)
