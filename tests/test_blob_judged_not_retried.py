#!/usr/bin/env python3
"""A blob already JUDGED must not be judged again, or it starves the whole range.

The failure this pins, and how to reproduce it without a transcript: with a per-close cap of ONE
blob, run consecutive ``end_change`` calls over a push range containing a blob whose verdict is
FINDINGS. Each close then reports ``reviewed this pass : 1 blob(s)`` while the count of blobs that
"carry no review verdict" does NOT fall — the same content was judged again — and no blob sorted
after the first non-clean one is ever reached. Verdicts are keyed by blob CONTENT, so re-reviewing
identical bytes cannot produce a different answer: the call is pure waste.

The fix is a skip, not a pass (no enforcement is weakened):
  * a blob with a RECORDED verdict that is not CLEAN is still REPORTED in ``remaining``, so the
    close still refuses and the receipt still names it uncovered — the operator must FIX the file
    and commit (which is a new blob) rather than close in a loop;
  * it is simply not sent to the reviewer a second time for identical content, so the per-close
    cap is spent on blobs that have never been judged.

Asserted here:
  A. a blob carrying a non-clean verdict is not handed to the reviewer, and is named in
     ``already_judged`` AND in ``remaining`` — two lists answering two different questions, so a
     blob belonging to BOTH is expected, not contradictory: ``already_judged`` = "why was this
     content not sent again", ``remaining`` = "is it COVERED for the receipt" (it is not, or the
     receipt would claim a file nobody vouched for);
  B. an unjudged blob IS reviewed in the same pass, i.e. the cap is not spent on the
     already-judged blob;
  C. a CLEAN blob is still skipped as before (no regression to the existing cache path);
  D. PRECONDITIONS: the module loads, the collaborator exists with the signature this file calls,
     and the module logs to the very logger this test silences.

The store is injected, so this test needs no git, no network and no live database.
"""
import importlib.util
import inspect
import logging as _logging
import sqlite3
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MODULE = REPO / "mcp-servers" / "loop-gov-mcp.py"

# ── preconditions, checked BEFORE any assertion runs ────────────────────────────────────────────
# An adversarial finding was right that importing this module and calling into it without checking
# anything makes a renamed or removed collaborator look like a test bug: the failure would surface
# as an AttributeError or TypeError, not as a statement about the behaviour under test. These raise
# an explicit PRECONDITION FAILED instead.
_spec = importlib.util.spec_from_file_location("loop_gov_mcp_judged", MODULE)
if _spec is None or _spec.loader is None:                        # pragma: no cover - defensive
    raise SystemExit(f"PRECONDITION FAILED: cannot load the module under test at {MODULE}")
mcp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mcp)

# The preconditions are a TEST, not import-time code (finding: checks that run at import raise
# SystemExit, which kills the runner before any test can report, so a renamed collaborator reads as
# a crashed file rather than a named failure). The runner below sorts test names, so `test_00_`
# runs first and a broken precondition is attributed to it.
REQUIRED_PARAMS = ("blobs", "reviewer", "material_for", "cap", "budget_s", "conn")

# The gate's logger is where the production audit trail goes, so a test must not write to it. That
# silence is only real if the module logs to THIS logger — asserted in test D, not assumed, because
# silencing an unrelated logger would be decorative while the trail still got polluted.
GATE_LOGGER_NAME = "loop-governance"
_gate_log = _logging.getLogger(GATE_LOGGER_NAME)
_gate_log.setLevel(_logging.CRITICAL + 1)

# The stored verdict is admissible only under the rules revision that produced it (2026-10-20),
# so the fixtures stamp one fixed revision and inject it: this file is about the SKIP-vs-retry
# semantics at one revision (revision matching itself is tests/test_blob_rules_rev.py).
REV = mcp._rules_rev("fixed rules for the skip fixtures")


def _pass(blobs, **kw):
    kw.setdefault("rules_rev", REV)
    return mcp._review_uncovered_blobs(blobs, **kw)


DDL = """CREATE TABLE IF NOT EXISTS blob_reviews (
    blob_sha TEXT PRIMARY KEY, verdict TEXT, findings_json TEXT, summary TEXT,
    reviewer_id TEXT, reviewer_model TEXT, ts TEXT, rules_rev TEXT)"""


def _store(rows):
    conn = sqlite3.connect(":memory:")
    conn.execute(DDL)
    for sha, verdict in rows:
        conn.execute("INSERT OR REPLACE INTO blob_reviews"
                     " (blob_sha, verdict, ts, rules_rev) VALUES (?,?,?,?)",
                     (sha, verdict, "2026-10-18T00:00:00Z", REV))
    conn.commit()
    return conn


def _run(blobs, conn):
    seen = []

    def reviewer(sha, path, material):
        seen.append((path, sha))
        return '{"verdict": "CLEAN", "findings": []}'

    out = _pass(
        blobs, reviewer=reviewer,
        material_for=lambda sha, path: f"material for {path}",
        cap=1, budget_s=240.0, conn=conn)
    return out, seen


def test_00_preconditions():
    """D. Everything this file calls must exist — and the module must log to the logger we silence.

    Runs FIRST (the runner sorts by name). Asserted rather than raised so a renamed collaborator
    fails as THIS test's named assertion instead of an AttributeError from the first behavioural
    test, or a SystemExit that kills the runner with no test attributed.
    """
    fn = getattr(mcp, "_review_uncovered_blobs", None)
    assert fn is not None, (
        "mcp._review_uncovered_blobs is missing, so the behaviour this file pins is not present")
    sig = inspect.signature(fn)
    missing = [p for p in REQUIRED_PARAMS if p not in sig.parameters]
    assert not missing, (
        f"_review_uncovered_blobs has no {missing} parameter(s); its signature is {sig}")

    # Silencing the gate logger only silences the production audit trail if the module logs to THAT
    # logger: a rename would otherwise make the suppression decorative and let test noise through.
    mod_logger = getattr(mcp, "log", None)
    assert mod_logger is not None, (
        "the module exposes no module-level logger, so this test cannot silence its output and its "
        "noise would land in the production audit trail")
    assert mod_logger.name == GATE_LOGGER_NAME, (
        f"the module logs to {mod_logger.name!r} while this test silences {GATE_LOGGER_NAME!r}: the "
        "suppression is decorative and test output reaches the live audit trail")


def test_judged_blob_is_not_reviewed_again_and_still_blocks():
    judge_me, already = "b" * 40, "a" * 40
    blobs = {"a/one.txt": already, "z/two.txt": judge_me}
    conn = _store([(already, "FINDINGS")])
    out, seen = _run(blobs, conn)

    assert already not in [s for _, s in seen], (
        "a blob that already carries a verdict must not be re-sent: identical content "
        f"cannot produce a different verdict. reviewer saw {seen}")
    assert already in out["already_judged"], (
        "the already-judged blob must be REPORTED (as already_judged) so the close can name it: "
        f"{out}")
    assert already in out["remaining"], (
        "a non-clean verdict is NOT coverage: the blob must still count as uncovered "
        f"so the receipt cannot claim it: {out}")
    assert judge_me in [s for _, s in seen], (
        "the cap must be spent on a blob nobody has judged: " + str(seen))


def test_clean_blob_is_still_skipped():
    clean, unjudged = "c" * 40, "d" * 40
    blobs = {"a/clean.txt": clean, "z/new.txt": unjudged}
    out, seen = _run(blobs, _store([(clean, "CLEAN")]))
    assert clean not in [s for _, s in seen]
    assert out["verdicts"].get(clean) == "CLEAN"
    assert unjudged in [s for _, s in seen]


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
