#!/usr/bin/env python3
"""A verdict is admissible only under the RULES that produced it (2026-10-20).

The defect this pins, reported from a peer host on 2026-10-20: `end_change` refused with
"Self-adversarial review FAILED on a per-blob verdict — this change cannot close", citing a
`medium` `unverified-claim` against a doc's provenance banner for naming other files. The
reviewer prompt had forbidden exactly that finding since 2026-10-19 ("A reference to another
file is a POINTER, not an unverified claim"), and the rule was live in the repo — yet the
verdict stood and the range could not close.

Why it stood, read in the source rather than inferred:

  * `_review_uncovered_blobs` skips any blob with a RECORDED verdict (anything but UNJUDGED)
    and leaves it in `remaining`, so the close refuses on it again and again. The comment on
    that branch states the premise: "identical content cannot produce a different verdict".
  * `blob_reviews` was keyed on `blob_sha` ALONE. It recorded which MODEL judged and nothing
    about which RULES were in force, and no path ever deleted or updated a row.
  * Therefore the premise was false the moment the rules changed: a blob judged before a rule
    landed was never re-sent, so it kept refusing a close the CURRENT rules call clean. The
    only exits were editing the file (rewriting documentation to dodge a finding the rules call
    bogus) or an override.

The fix, asserted here:

  A. a verdict recorded under an OLDER rules revision is NOT admissible: the blob reaches the
     reviewer again instead of being skipped;
  B. a verdict recorded under the CURRENT revision still skips it — the cache is not disabled;
  C. the close path agrees: before the re-review the blob is UNCOVERED (so the close still
     refuses and no receipt can name it), and after it the row is REPLACED with the current
     revision and a CLEAN re-judgement is covered;
  D. UNJUDGED still neither covers nor skips, under a matching revision;
  E. the revision is derived from the RULES TEXT, so editing the prompt changes it — a rule
     edit cannot be silently missed;
  F. the schema migration adds the column to a store that predates it, is idempotent, and
     leaves old rows inadmissible (NULL revision) rather than trusted.

Every store here is a temp file or an in-memory sqlite: no test touches live governance state.
"""
import importlib.util
import inspect
import json
import logging as _logging
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("loop_gov_rulesrev",
                                               REPO / "mcp-servers" / "loop-gov-mcp.py")
mcp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mcp)

_gate_log = _logging.getLogger("loop-governance")
_gate_log.setLevel(_logging.CRITICAL + 1)

# The revision in force when the fix was written, and one that is NOT it. Real fingerprints
# (derived from text), never literals: the code path under test computes the same way.
#
# Derived DEFENSIVELY so this file also RUNS at the pre-fix revision, where it reports named
# failures instead of dying at import: a test that cannot execute its subject proves nothing in
# either direction, and the pre-fix run is the other half of this file's evidence.
def _rev(text: str) -> str:
    fn = getattr(mcp, "_rules_rev", None)
    return str(fn(text)) if callable(fn) else ""


REV_A = _rev("rules as they were before the pointer rule existed")
REV_B = _rev("rules including: a reference to another file is a POINTER")

# The revision the defect was measured at — the pushed tip before this change. Pinned so the
# pre-fix half of the proof stays re-runnable from git history.
PRE_FIX_SHA = "fab9388b"

DDL_OLD = """CREATE TABLE IF NOT EXISTS blob_reviews (
    blob_sha TEXT PRIMARY KEY, verdict TEXT, findings_json TEXT, summary TEXT,
    reviewer_id TEXT, reviewer_model TEXT, ts TEXT)"""

# The server's own schema, as `_db()` creates it (mirrored here so a fixture can hold rows
# without a live store).
DDL_NEW = """CREATE TABLE IF NOT EXISTS blob_reviews (
    blob_sha TEXT PRIMARY KEY, verdict TEXT, findings_json TEXT, summary TEXT,
    reviewer_id TEXT, reviewer_model TEXT, ts TEXT, rules_rev TEXT)"""

_F: list[str] = []


def _check(name: str, cond: bool, detail: str = "") -> None:
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        _F.append(name)


def _sha(ch: str) -> str:
    return ch * 40


def _store(rows):
    """An in-memory blob_reviews store: rows are (sha, verdict, findings_json, rules_rev)."""
    conn = sqlite3.connect(":memory:")
    conn.execute(DDL_NEW)
    for sha, verdict, findings, rev in rows:
        conn.execute("INSERT OR REPLACE INTO blob_reviews"
                     " (blob_sha, verdict, findings_json, ts, rules_rev) VALUES (?,?,?,?,?)",
                     (sha, verdict, findings, "2026-10-20T00:00:00Z", rev))
    conn.commit()
    return conn


def _lookup(fn, blobs, conn, rules_rev):
    """Call a store lookup, passing `rules_rev` only when the helper ACCEPTS it.

    So this file also runs at the pre-fix revision, where the parameter does not exist: there
    the lookups answer from content alone, which is the defect, and the assertions below report
    it by name instead of dying on an unexpected keyword.
    """
    if "rules_rev" in inspect.signature(fn).parameters:
        return fn(blobs, conn=conn, rules_rev=rules_rev)
    return fn(blobs, conn=conn)


def _blob_run(blobs, conn, rules_rev, verdict_json='{"verdict": "CLEAN", "findings": []}'):
    """Drive the REAL per-blob pass with an injected reviewer; return (result, calls).

    `rules_rev` is passed only when the pass ACCEPTS it, so this file runs at the pre-fix
    revision too (where the keyword does not exist) and reports the defect as a named failure.
    """
    seen = []

    def reviewer(sha, path, material):
        seen.append(path)
        return verdict_json

    kw = dict(reviewer=reviewer,
              material_for=lambda sha, path: f"material for {path}",
              cap=10, budget_s=240.0, conn=conn)
    if "rules_rev" in inspect.signature(mcp._review_uncovered_blobs).parameters:
        kw["rules_rev"] = rules_rev
    out = mcp._review_uncovered_blobs(blobs, **kw)
    return out, seen


def test_00_preconditions() -> None:
    print("0. the symbols this file exercises exist, and the revision is derived, not constant")
    for sym in ("_rules_rev", "_admissible", "_blob_verdict_rows", "_count_stale_verdicts",
                "_blobs_with_recorded_verdict", "_blobs_with_covered_verdict",
                "_review_uncovered_blobs"):
        _check(f"{sym} exists", hasattr(mcp, sym))
    # E. the revision tracks the RULES TEXT
    _check("the revision changes with the rules text", REV_A != REV_B, f"{REV_A} vs {REV_B}")
    _check("the revision is stable for identical text", _rev("x") == _rev("x"))
    _check("no rules text means no revision", _rev("") == "")


def test_a_stale_revision_does_not_skip_the_blob() -> None:
    """A. THE REPORTED DEADLOCK: judged under older rules, never re-sent, close refused forever."""
    print("A. a verdict from an OLDER rules revision is not admissible (the reported deadlock)")
    blobs = {"docs/old.md": _sha("a")}
    conn = _store([(_sha("a"), "FINDINGS",
                    json.dumps([{"finding_id": "ADV-6866-1", "severity": "medium",
                                 "technique": "unverified-claim", "target": "docs/old.md:5",
                                 "evidence": "e", "recommendation": "r"}]), REV_A)])
    _check("the stored verdict is invisible to the current revision",
           _lookup(mcp._blobs_with_recorded_verdict, blobs, conn, REV_B) == {},
           "a verdict from an older revision must not be treated as already judged")
    out, seen = _blob_run(blobs, conn, REV_B)
    _check("the blob IS re-sent to the reviewer", seen == ["docs/old.md"], f"calls={seen}")
    _check("and the pass counts what it invalidated", out.get("invalidated_verdicts") == 1,
           f"out={out.get('invalidated_verdicts')}")
    _check("the re-judgement replaces the row under the CURRENT revision",
           _lookup(mcp._blobs_with_recorded_verdict, blobs, conn, REV_B) == {_sha("a"): "CLEAN"},
           "INSERT OR REPLACE must leave the revision of the judgement that stands")


def test_b_the_same_revision_still_skips() -> None:
    """B. The cache is not disabled: identical rules => no reviewer call."""
    print("B. at an UNCHANGED revision the stored verdict still skips the blob")
    blobs = {"a.py": _sha("b")}
    conn = _store([(_sha("b"), "FINDINGS",
                    json.dumps([{"finding_id": "ADV-1-1", "severity": "medium",
                                 "technique": "unverified-claim", "target": "a.py:1",
                                 "evidence": "e", "recommendation": "r"}]), REV_A)])
    _check("the verdict is admissible at its own revision",
           _lookup(mcp._blobs_with_recorded_verdict, blobs, conn, REV_A) == {_sha("b"): "FINDINGS"})
    out, seen = _blob_run(blobs, conn, REV_A)
    _check("the reviewer is NOT called again", seen == [], f"calls={seen}")
    _check("nothing is reported as invalidated", out.get("invalidated_verdicts") == 0)
    _check("the blob is still reported as not covered (the close still refuses it)",
           _sha("b") in out["remaining"], f"remaining={out['remaining']}")


def test_c_the_close_path_agrees() -> None:
    """C. Coverage, which is what a receipt may name, follows the same rule."""
    print("C. coverage follows the same rule — stale verdict covers nothing, current one does")
    blobs = {"d.md": _sha("c")}
    stale = _store([(_sha("c"), "CLEAN", "[]", REV_A)])
    _check("a CLEAN verdict from an older revision does NOT cover the blob",
           _lookup(mcp._blobs_with_covered_verdict, blobs, stale, REV_B) == set(),
           "coverage must not be claimed for a judgement under superseded rules")
    fresh = _store([(_sha("c"), "CLEAN", "[]", REV_B)])
    _check("a CLEAN verdict at the CURRENT revision covers it",
           _lookup(mcp._blobs_with_covered_verdict, blobs, fresh, REV_B) == {_sha("c")})
    # and the end-to-end shape: stale -> re-reviewed -> covered
    conn = _store([(_sha("c"), "FINDINGS",
                    json.dumps([{"finding_id": "ADV-1-1", "severity": "medium",
                                 "technique": "unverified-claim", "target": "d.md:1",
                                 "evidence": "e", "recommendation": "r"}]), REV_A)])
    before = _lookup(mcp._blobs_with_covered_verdict, blobs, conn, REV_B)
    _check("before the re-review the blob is UNCOVERED", before == set())
    out, seen = _blob_run(blobs, conn, REV_B)
    after = _lookup(mcp._blobs_with_covered_verdict, blobs, conn, REV_B)
    _check("the reviewer ran", seen == ["d.md"], f"calls={seen}")
    _check("after a CLEAN re-review the blob IS covered", after == {_sha("c")}, f"after={after}")
    _check("and it is no longer outstanding", _sha("c") not in out["remaining"])


def test_d_unjudged_is_still_neither() -> None:
    """D. UNJUDGED is not a verdict, at any revision."""
    print("D. UNJUDGED neither covers nor skips")
    blobs = {"e.py": _sha("d")}
    conn = _store([(_sha("d"), "UNJUDGED", "", REV_B)])
    _check("not covered", _lookup(mcp._blobs_with_covered_verdict, blobs, conn, REV_B) == set())
    _check("not on the skip list",
           _lookup(mcp._blobs_with_recorded_verdict, blobs, conn, REV_B) == {})
    _check("not counted as invalidated (it was never a verdict)",
           _lookup(mcp._count_stale_verdicts, blobs, conn, REV_B) == 0)


def test_e_an_unknown_revision_admits_nothing() -> None:
    """The fail-closed direction: unknown provenance costs a review, never buys coverage."""
    print("E. no revision in force => no stored verdict is admissible")
    blobs = {"f.py": _sha("e")}
    conn = _store([(_sha("e"), "CLEAN", "[]", REV_A), (_sha("e"), "CLEAN", "[]", "")])
    _check("an empty current revision admits nothing",
           _lookup(mcp._blobs_with_recorded_verdict, blobs, conn, "") == {})
    _check("and covers nothing",
           _lookup(mcp._blobs_with_covered_verdict, blobs, conn, "") == set())


def test_f_the_migration() -> None:
    """F. A store that predates the column gains it; old rows stay inadmissible."""
    print("F. schema migration: pre-existing store gains rules_rev, idempotently")
    with tempfile.TemporaryDirectory() as td:
        db = Path(td) / "loop-governance.db"
        old = sqlite3.connect(str(db))
        old.execute(DDL_OLD)
        old.execute("INSERT INTO blob_reviews (blob_sha, verdict, findings_json, ts)"
                    " VALUES (?,?,?,?)", (_sha("f"), "FINDINGS", "[]", "2026-10-19T00:00:00Z"))
        old.commit()
        old.close()

        saved_db, saved_home = mcp.LOOP_DB, mcp.HOME
        mcp.LOOP_DB = db
        try:
            conn = mcp._db()                       # the server's own schema init
            cols = {r[1] for r in conn.execute("PRAGMA table_info(blob_reviews)").fetchall()}
            _check("the column was added to a pre-existing store", "rules_rev" in cols, str(cols))
            row = conn.execute("SELECT rules_rev FROM blob_reviews WHERE blob_sha=?",
                               (_sha("f"),)).fetchone()
            _check("the pre-existing row keeps NULL (it names no rules)",
                   row is not None and row[0] is None, str(row))
            blobs = {"g.py": _sha("f")}
            _check("so it is inadmissible and the blob is judged again",
                   _lookup(mcp._blobs_with_recorded_verdict, blobs, conn, REV_A) == {})
            conn.close()
            conn2 = mcp._db()                      # idempotent: a second init must not fail
            cols2 = {r[1] for r in conn2.execute("PRAGMA table_info(blob_reviews)").fetchall()}
            _check("a second init is a no-op", "rules_rev" in cols2 and len(cols2) == len(cols))
            conn2.close()
        finally:
            mcp.LOOP_DB, mcp.HOME = saved_db, saved_home


def test_g_the_defect_is_absent_before_this_change() -> None:
    """The pre-fix half of the proof, from git history: assert the SHAPE of the defect."""
    print(f"G. at {PRE_FIX_SHA} the revision does not exist (the defect's shape)")
    src = subprocess.run(["git", "show", f"{PRE_FIX_SHA}:mcp-servers/loop-gov-mcp.py"],
                         cwd=str(REPO), capture_output=True, text=True)
    if src.returncode != 0:
        print("  NOT RUN  the pinned revision is not available here "
              f"({src.stderr.strip()[:120]}) — could not verify, which is NOT a pass")
        return
    body = src.stdout
    _check("no rules revision in the store schema", "rules_rev" not in body)
    _check("no revision helper", "_rules_rev" not in body)
    _check("the skip branch is still keyed on content alone",
           "recorded = _blobs_with_recorded_verdict(blobs, conn=conn)" in body,
           "the pre-fix call shape is not what this test expects")


if __name__ == "__main__":
    for fn in (test_00_preconditions, test_a_stale_revision_does_not_skip_the_blob,
               test_b_the_same_revision_still_skips, test_c_the_close_path_agrees,
               test_d_unjudged_is_still_neither, test_e_an_unknown_revision_admits_nothing,
               test_f_the_migration, test_g_the_defect_is_absent_before_this_change):
        fn()
    print(f"\n{'FAIL' if _F else 'ALL PASS'} ({len(_F)} failed)")
    sys.exit(1 if _F else 0)
