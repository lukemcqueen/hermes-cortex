#!/usr/bin/env python3
"""Coverage means JUDGED AND NOTHING OUTSTANDING — and what must stay uncovered still does.

Found by draining the unpushed range (2026-10-18): a blob judged with SIX `info` findings read as
"0 blocking findings" to the close and as "carries no review verdict" to the receipt at the same
time, so it could never be covered and the range could never close. Coverage demanded a bare CLEAN
verdict while the close's own gate refused only on BLOCKING findings — a contradiction, not
strictness, and the reason the drain looked infinite.

The two sets answer different questions and must NOT be merged:
  * BLOCKING — unchanged; a blocking finding still refuses the close.
  * COVERED  — "was this content read, and does anything need fixing?"

DEPENDENCY POINTER (so the reviewer does not have to take this file's word for it): the helper this
file exercises, ``_blobs_with_covered_verdict``, and the blocking classifier it asserts the boundary
of, ``_blocking_findings``, live in ``mcp-servers/loop-gov-mcp.py``, added by commit ``d7175073`` on
this push range. That file is a SIBLING blob of this range and is reviewed in its own window; this
file is test-side proof that the semantics hold, not a copy of them.

Asserted here — A and B are the fix, C to E are the protection that must not move:
  A. a CLEAN verdict is covered;
  B. a FINDINGS verdict whose findings are all below blocking is covered, and is therefore NOT
     re-reviewed and NOT reported as outstanding;
  C. a BLOCKING finding is NOT covered;
  D. an UNJUDGED blob is NOT covered (a receipt may never name a file nobody read);
  E. ambiguity fails CLOSED — a missing row, unparseable findings_json, or a FINDINGS verdict with
     an EMPTY findings list is NOT covered ("silence is never CLEAN").

The store is injected, so this needs no git, no network and no live database.
"""
import importlib.util
import json
import logging as _logging
import sqlite3
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("loop_gov_coverage", REPO / "mcp-servers" / "loop-gov-mcp.py")
mcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mcp)

_gate_log = _logging.getLogger("loop-governance")
_gate_log.setLevel(_logging.CRITICAL + 1)

DDL = """CREATE TABLE IF NOT EXISTS blob_reviews (
    blob_sha TEXT PRIMARY KEY, verdict TEXT, findings_json TEXT, summary TEXT,
    reviewer_id TEXT, reviewer_model TEXT, ts TEXT)"""

FINDING = {
    "finding_id": "ADV-1-1", "technique": "unverified-claim", "target": "f:1",
    "evidence": "e", "recommendation": "r",
}


def _store(rows):
    conn = sqlite3.connect(":memory:")
    conn.execute(DDL)
    for sha, verdict, findings in rows:
        conn.execute("INSERT OR REPLACE INTO blob_reviews (blob_sha, verdict, findings_json, ts) "
                     "VALUES (?,?,?,?)", (sha, verdict, findings, "2026-10-18T00:00:00Z"))
    conn.commit()
    return conn


def _sha(ch):
    return ch * 40


def test_00_preconditions():
    assert hasattr(mcp, "_blobs_with_covered_verdict"), "the coverage helper is missing"
    assert hasattr(mcp, "_blocking_findings"), "the blocking classifier is missing"
    # The classifier must rate the severities this test relies on the way the test assumes.
    for sev, expect_blocking in (("high", True), ("critical", True), ("info", False), ("low", False)):
        raw = json.dumps([dict(FINDING, severity=sev)])
        blocked = bool(mcp._blocking_findings(raw)[0])
        assert blocked == expect_blocking, (
            f"_blocking_findings rates {sev} as blocking={blocked}, but this test assumes "
            f"{expect_blocking} — the coverage rule's boundary moved")


def test_clean_is_covered():
    blobs = {"a.py": _sha("a")}
    assert mcp._blobs_with_covered_verdict(blobs, conn=_store([(_sha("a"), "CLEAN", "[]")])) \
        == {_sha("a")}


def test_non_blocking_findings_are_covered():
    blobs = {"b.py": _sha("b")}
    conn = _store([(_sha("b"), "FINDINGS", json.dumps([dict(FINDING, severity="info")]))])
    assert mcp._blobs_with_covered_verdict(blobs, conn=conn) == {_sha("b")}, (
        "a blob judged with only non-blocking findings must be COVERED, or it can never be "
        "covered at all (the close reports 0 blocking findings for it)")


def test_blocking_findings_are_not_covered():
    blobs = {"c.py": _sha("c")}
    conn = _store([(_sha("c"), "FINDINGS", json.dumps([dict(FINDING, severity="high")]))])
    assert mcp._blobs_with_covered_verdict(blobs, conn=conn) == set(), (
        "a blocking finding must NOT be covered — this is the protection that must not move")


def test_unjudged_is_not_covered():
    blobs = {"d.py": _sha("d")}
    assert mcp._blobs_with_covered_verdict(blobs, conn=_store([])) == set(), (
        "an unjudged blob must never be covered: a receipt may not name a file nobody read")


def test_ambiguity_fails_closed():
    rows = [(_sha("e"), "FINDINGS", ""),                       # no findings recorded
            (_sha("f"), "FINDINGS", "not json"),               # unparseable
            (_sha("g"), "FINDINGS", "[]")]                     # empty list = silence
    blobs = {"e.py": _sha("e"), "f.py": _sha("f"), "g.py": _sha("g")}
    got = mcp._blobs_with_covered_verdict(blobs, conn=_store(rows))
    assert got == set(), f"ambiguity must fail CLOSED (covered nothing), got {got}"


def test_covered_blob_is_not_re_reviewed_and_not_outstanding():
    """The integration benefit: a covered blob costs no call and is not reported as outstanding."""
    seen = []

    def reviewer(sha, path, material):
        seen.append(path)
        return '{"verdict": "CLEAN", "findings": []}'

    blobs = {"a/covered.py": _sha("a"), "z/pending.py": _sha("z")}
    conn = _store([(_sha("a"), "FINDINGS", json.dumps([dict(FINDING, severity="info")]))])
    out = mcp._review_uncovered_blobs(blobs, reviewer=reviewer,
                                      material_for=lambda sha, path: "m",
                                      cap=1, budget_s=240.0, conn=conn)
    assert "a/covered.py" not in seen, f"a covered blob must not be re-reviewed: {seen}"
    assert _sha("a") not in out["remaining"], (
        "a covered blob must not be reported as carrying no verdict: " + str(out["remaining"]))
    assert "z/pending.py" in seen, "the cap must go to the blob that is genuinely outstanding"


def test_receipt_names_only_covered_blobs():
    """ADV-0-6: a receipt may name only blobs that were JUDGED and need no fix."""
    saved = (mcp._range_blobs, mcp._blobs_with_covered_verdict, mcp._push_base_is_root_fallback)
    mcp._range_blobs = lambda repo, base, head: {"a.py": _sha("a"), "b.py": _sha("b")}
    mcp._blobs_with_covered_verdict = lambda blobs, conn=None: {_sha("a")}
    # A resolvable range is what this test is about; the unresolvable case has its own test.
    mcp._push_base_is_root_fallback = lambda repo: False
    try:
        got = mcp._receipt_blobs(Path("/tmp"), "base", "head")
    finally:
        (mcp._range_blobs, mcp._blobs_with_covered_verdict,
         mcp._push_base_is_root_fallback) = saved
    assert got == {"a.py": _sha("a")}, f"the receipt must omit anything not covered: {got}"


def test_push_base_candidates_handle_a_master_default_and_another_remote():
    """ADV-0-2: hardcoding origin/main made a master-default repo fall back to ALL history."""
    saved = (mcp._git_capture, mcp._env_value)
    mcp._env_value = lambda name, default="": "upstream" if name == "CORTEX_PUSH_REMOTE" else ""
    mcp._git_capture = (lambda repo, *a, **k:
                        "origin/develop" if a and a[0] == "symbolic-ref" else "")
    try:
        got = mcp._push_base_candidates(Path("/tmp"))
    finally:
        mcp._git_capture, mcp._env_value = saved
    assert got[0] == "origin/develop", f"the remote's own default branch must win: {got}"
    assert "upstream/main" in got and "upstream/master" in got, (
        f"a differently named remote must still be tried: {got}")


def test_layout_hints_are_configurable():
    """ADV-0-4: the layout list was correct only for this repo."""
    saved = mcp._env_value
    mcp._env_value = (lambda name, default="":
                      "src/,lib/" if name == "CORTEX_REVIEW_LAYOUT_PREFIXES" else "")
    try:
        prefixes = mcp._layout_prefixes()
        pats = mcp._preflight_patterns()
    finally:
        mcp._env_value = saved
    assert prefixes == ("src/", "lib/"), prefixes
    assert any(p.search("touches src/thing.py") for p, _ in pats), (
        "the configured layout must compile into a pattern")


def test_db_connection_is_wal_with_a_busy_timeout():
    """The multi-session claim, asserted rather than asserted-in-a-comment.

    `_blobs_with_covered_verdict`'s docstring rests on the connection factory setting WAL and a
    busy_timeout, so a concurrent writer blocks instead of failing. This is the runnable proof.
    """
    conn = mcp._db()
    try:
        journal = conn.execute("PRAGMA journal_mode").fetchone()[0]
        timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    finally:
        conn.close()
    assert str(journal).lower() == "wal", f"_db() journal_mode is {journal!r}, not WAL"
    assert int(timeout) > 0, f"_db() busy_timeout is {timeout!r}; a concurrent writer would fail"


def test_coverage_is_recomputed_per_call_not_cached():
    """A peer's newly recorded verdict must be picked up on the NEXT call, not after a restart."""
    conn = _store([])
    blobs = {"a.py": _sha("a")}
    assert mcp._blobs_with_covered_verdict(blobs, conn=conn) == set(), (
        "an unjudged blob must start uncovered")
    conn.execute("INSERT OR REPLACE INTO blob_reviews (blob_sha, verdict, findings_json, ts) "
                 "VALUES (?,?,?,?)", (_sha("a"), "CLEAN", "[]", "2026-10-18T00:00:00Z"))
    conn.commit()
    assert mcp._blobs_with_covered_verdict(blobs, conn=conn) == {_sha("a")}, (
        "a verdict recorded by another session between two calls must be seen by the second call — "
        "the coverage path must not cache")


def test_unresolvable_range_yields_no_blobs_and_generic_guidance():
    """Operator rule (event #159): no repo data to work with means GENERIC feedback, never a
    per-file demand list over the entire history."""
    saved = (mcp._git_capture, mcp._push_base, mcp._push_base_is_root_fallback, mcp._unreviewed_paths)
    mcp._push_base_is_root_fallback = lambda repo: True
    mcp._push_base = lambda repo: "root-sha"
    mcp._git_capture = lambda repo, *a, **k: "head-sha"
    mcp._unreviewed_paths = lambda repo: []
    try:
        blobs = mcp._push_range_blobs(Path("/tmp"))
        note = mcp._review_scope_note(Path("/tmp"))
    finally:
        (mcp._git_capture, mcp._push_base, mcp._push_base_is_root_fallback,
         mcp._unreviewed_paths) = saved
    assert blobs == {}, (
        "an unresolvable range must yield NO blobs — otherwise every file in the whole history is "
        "demanded a verdict, which is the failure this resolves")
    assert "NO RESOLVABLE PUSH RANGE" in note, f"generic guidance expected instead: {note!r}"
    assert "GENERIC checks" in note, f"the note must say the review degrades to generic: {note!r}"
    assert mcp.REVIEW_EXPECTATIONS[0] in note, (
        f"the generic expectations must still be given: {note!r}")
    assert "- " not in note.split("NO RESOLVABLE")[1], (
        "there is no range, so there must be no per-file list: " + note)


def test_reply_that_judged_nothing_is_unjudged_not_findings():
    """An unparseable or silent reply is UNJUDGED, never FINDINGS with an empty list.

    FINDINGS/[] was not a pass (coverage already excludes an empty findings list) but it was a WEDGE:
    the per-blob pass recorded it, `_blobs_with_recorded_verdict` then skipped that content on every
    later close, and the blob stayed in `remaining` forever — a range that can never close.
    """
    for text in (None, "", "   ", 42, "the material looks fine to me, no issues found"):
        assert mcp._extract_verdict(text)[0] == "UNJUDGED", f"{text!r} must be UNJUDGED"


def test_json_without_a_verdict_is_unjudged_not_clean():
    """A reply that asserts NOTHING must not credit the blob.

    `obj.get("verdict", "FINDINGS" if findings else "CLEAN")` returned CLEAN for any JSON object with
    no verdict key, so `{"summary": "all good"}` was a PASS for material nobody had judged.
    """
    assert mcp._extract_verdict('{"summary": "all good"}')[0] == "UNJUDGED"
    assert mcp._extract_verdict('{"verdict": "CLEAN", "findings": []}')[0] == "CLEAN"
    assert mcp._extract_verdict(
        '{"verdict": "FINDINGS", "findings": [{"severity": "high"}]}')[0] == "FINDINGS"
    # Findings but no verdict key is still an assertion of something to look at.
    assert mcp._extract_verdict('{"findings": [{"severity": "low"}]}')[0] == "FINDINGS"


def test_a_stored_unjudged_row_neither_covers_nor_skips():
    """Defence in depth: even if an UNJUDGED row exists, it credits nothing and skips nothing."""
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE blob_reviews (blob_sha TEXT PRIMARY KEY, verdict TEXT, findings_json TEXT)")
    sha = _sha("unjudged")
    conn.execute("INSERT INTO blob_reviews VALUES (?,?,?)", (sha, "UNJUDGED", "[]"))
    blobs = {"x.py": sha}
    assert mcp._blobs_with_covered_verdict(blobs, conn=conn) == set(), "UNJUDGED is not coverage"
    assert mcp._blobs_with_recorded_verdict(blobs, conn=conn) == {}, (
        "UNJUDGED must not put content on the already-judged skip list, or it is never retried")


def test_silent_reply_leaves_no_verdict_and_keeps_the_blob_retryable():
    """End to end on the pass: an unusable reply records NOTHING and reports the blob unjudged, so the
    next close sends the same content again instead of wedging the range."""
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE blob_reviews (blob_sha TEXT PRIMARY KEY, verdict TEXT, findings_json TEXT)")
    sha = _sha("retry")
    out = mcp._review_uncovered_blobs(
        {"y.py": sha},
        reviewer=lambda s, p, m: "no json here at all",
        material_for=lambda s, p: "material",
        conn=conn)
    assert out["verdicts"] == {}, f"nothing may be recorded as judged: {out}"
    assert sha in out["remaining"], f"it must be reported unjudged: {out}"
    assert sha in out["failed"], (
        f"it must take the FAILURE path (so consecutive failures still signal an outage): {out}")
    assert conn.execute("SELECT COUNT(*) FROM blob_reviews").fetchone()[0] == 0, (
        "an unusable reply must leave no verdict row, or the content could never be re-sent")


def test_the_old_findings_with_no_findings_row_is_what_wedged_the_range():
    """Proof the wedge was REAL, not asserted: the old parse recorded FINDINGS with an EMPTY findings
    list for silence, and `_blobs_with_recorded_verdict` skips that content on every later close —
    so the blob sat in `remaining` forever and the range could never close. UNJUDGED is the row that
    is NOT skipped, which is what keeps the content retryable.

    DEPENDENCY, stated because this blob cannot demonstrate it alone: both functions under test live in
    mcp-servers/loop-gov-mcp.py, a sibling blob of this same push range. This test is the EVIDENCE for
    that sibling's claim that UNJUDGED removes the wedge; it passes only when the production code
    carries the UNJUDGED filter, and it fails immediately if that filter is removed.
    """
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE blob_reviews (blob_sha TEXT PRIMARY KEY, verdict TEXT, findings_json TEXT)")
    old, new = _sha("old-wedge"), _sha("new-unjudged")
    conn.execute("INSERT INTO blob_reviews VALUES (?,?,?)", (old, "FINDINGS", "[]"))
    conn.execute("INSERT INTO blob_reviews VALUES (?,?,?)", (new, "UNJUDGED", "[]"))
    blobs = {"old.py": old, "new.py": new}
    assert mcp._blobs_with_recorded_verdict(blobs, conn=conn) == {old: "FINDINGS"}, (
        "the record the OLD parse wrote IS skipped — that is precisely the wedge removed here")
    assert new not in mcp._blobs_with_recorded_verdict(blobs, conn=conn), "UNJUDGED stays retryable"
    assert mcp._blobs_with_covered_verdict(blobs, conn=conn) == set(), (
        "neither row is coverage: an empty findings list and an unjudged row both credit nothing")


def test_leaf_raises_on_empty_content_so_silence_is_a_failure():
    """`_extract_verdict`'s docstring claims `_call_reviewer_llm` raises AT THE LEAF on empty content,
    i.e. a starved reply becomes a FAILURE before any recorder sees it. The claim is load-bearing for
    the UNJUDGED backstop, so it is exercised here with the HTTP layer stubbed (no network, no key)."""
    import json as _json
    import os
    import urllib.request

    class _Resp:
        def __init__(self, payload):
            self._b = _json.dumps(payload).encode()

        def read(self):
            return self._b

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    os.environ.setdefault("OPENROUTER_API_KEY", "test-presence-only")  # never printed

    def fake_urlopen(req, timeout=None):
        # The measured shape: a reasoning model that spent its output budget thinking.
        return _Resp({"choices": [{"message": {"content": None}, "finish_reason": "length"}],
                      "usage": {"completion_tokens_details": {"reasoning_tokens": 130836}}})

    saved = urllib.request.urlopen
    urllib.request.urlopen = fake_urlopen
    try:
        # Captured with BaseException on purpose (this file runs under its own runner, so pytest's
        # raises() is not assumed): an UNEXPECTED exception type must surface as a failure here, not
        # be swallowed by a narrow `except`.
        err = None
        try:
            mcp._call_reviewer_llm("prompt")
        except BaseException as exc:  # noqa: BLE001 — any exception is captured and asserted below
            err = exc
        assert isinstance(err, RuntimeError), (
            f"an empty reviewer reply must RAISE RuntimeError, got {type(err).__name__}: {err}")
        assert "NO usable content" in str(err), f"unexpected failure message: {err}"
    finally:
        urllib.request.urlopen = saved


def test_unparseable_reply_is_retried_on_the_next_pass_and_never_skipped():
    """Stitches the raise to the skip list: an unusable reply must leave the content sendable AGAIN."""
    import sqlite3
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE blob_reviews (blob_sha TEXT PRIMARY KEY, verdict TEXT, findings_json TEXT)")
    sha = _sha("stitched")
    blobs = {"z.py": sha}
    seen: list = []

    def reviewer(s, p, m):
        seen.append(s)
        return "I reviewed it and it looks fine"          # non-empty, but judges NOTHING

    out1 = mcp._review_uncovered_blobs(blobs, reviewer=reviewer,
                                       material_for=lambda s, p: "material", conn=conn)
    assert sha in out1["failed"] and sha in out1["remaining"], f"unjudged, not credited: {out1}"
    assert mcp._blobs_with_recorded_verdict(blobs, conn=conn) == {}, (
        "nothing may be recorded, or the skip list would hide the content from every later pass")
    out2 = mcp._review_uncovered_blobs(blobs, reviewer=reviewer,
                                       material_for=lambda s, p: "material", conn=conn)
    assert len(seen) == 2, "the SAME content must be sent again on the next pass (the retry property)"
    assert seen[0] == seen[1] == sha, (
        f"it must be the SAME blob sent twice, not two different ones: {seen}")
    assert sha in out2["remaining"], f"and still be reported unjudged: {out2}"


def test_blob_material_shows_sibling_added_lines_so_evidence_is_visible():
    """The churn this fixes: a fix PROVED in a sibling blob cost an extra round trip per file, because
    the reviewer could see the sibling's path and verdict but never its content — so it demanded the
    evidence be duplicated into the file under review, or produced as committed output."""
    import pathlib
    saved = (mcp._git_capture, mcp._push_range_blobs, mcp._blobs_with_covered_verdict,
             mcp._blobs_with_recorded_verdict)

    def fake_git(repo, *args):
        return f"+++ b/{args[-1]}\n+{args[-1]}: added by this range\n"

    mcp._git_capture = fake_git
    mcp._push_range_blobs = lambda repo: {"a.py": "shaA", "tests/t.py": "shaT"}
    mcp._blobs_with_covered_verdict = lambda blobs, conn=None: set()
    mcp._blobs_with_recorded_verdict = lambda blobs, conn=None: {}
    try:
        md = mcp._blob_material(pathlib.Path("/tmp"), "base", "a.py", {"head_sha": "head"})
    finally:
        (mcp._git_capture, mcp._push_range_blobs, mcp._blobs_with_covered_verdict,
         mcp._blobs_with_recorded_verdict) = saved
    assert "sibling ADDED lines" in md, md
    assert "tests/t.py: added by this range" in md, (
        "the sibling's added line must be VISIBLE in this file's window: " + md)
    assert "do NOT ask for it to be duplicated into the file under review" in md, (
        "the material must say where to verify it: " + md)


def test_sibling_added_lines_are_bounded_per_file_and_in_total():
    """A wide range must not flood one blob's window.

    Isolation is made EXPLICIT here rather than inherited: `_sibling_added_lines` must not consult the
    store or the range lookup at all, so those three are replaced with poisoned stubs that fail if it
    touches them. (The sibling test above restores everything it patches in a `finally`, but no test
    should have to depend on another test's cleanup to be deterministic.)
    """
    import pathlib
    saved = (mcp._git_capture, mcp._push_range_blobs, mcp._blobs_with_covered_verdict,
             mcp._blobs_with_recorded_verdict)

    def fake_git(repo, *args):
        return "+++ b/x\n" + "".join(f"+sib{i}\n" for i in range(500))

    def _poison(*a, **k):
        raise AssertionError("_sibling_added_lines must not call the store/range helpers")

    mcp._git_capture = fake_git
    mcp._push_range_blobs = _poison
    mcp._blobs_with_covered_verdict = _poison
    mcp._blobs_with_recorded_verdict = _poison
    try:
        block = mcp._sibling_added_lines(pathlib.Path("/tmp"), "base",
                                         [f"s{i}.py" for i in range(20)])
    finally:
        (mcp._git_capture, mcp._push_range_blobs, mcp._blobs_with_covered_verdict,
         mcp._blobs_with_recorded_verdict) = saved
    assert block.count("+sib") <= mcp.RANGE_CONTEXT_TOTAL_LINES, (
        f"the block must respect the TOTAL cap: {block.count('+sib')} lines")
    assert block.count("(+500 added line(s)") <= mcp.RANGE_CONTEXT_SIBLINGS, (
        "and it must stop after the sibling cap")


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
