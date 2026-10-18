#!/usr/bin/env python3
"""verify_preexisting_failures.sh must never call an unmeasured run a FAILURE, or agreement.

WHY THIS FILE EXISTS. The script's first version compared bare exit CODES between two revisions.
A file that could not execute at all — no interpreter, a timeout, a crash before the first test
ran — returns the SAME code on both sides, so it was reported "SAME (pre-existing)": a regression
claim manufactured from two runs that measured nothing. That is the same defect class as a
self-skipping test reading as PASS, and it is the defect that let a wrong record (#157) be written
in the first place: "four more tests fail identically at both revisions, so all are PRE-EXISTING"
was asserted by a comparison that could not tell FAILED from NEVER RAN.

WHAT IS PINNED
  * the classifier names THREE outcomes — never a pass and a failure only when a failure is NAMED
    in the output (rc=1 with an empty or unrelated log is NOT RUN, not FAILED);
  * the decisive case is driven end-to-end: with every run timing out, the script exits 3 and says
    COULD NOT VERIFY. Pre-fix that same input produced exit 0 and "SAME (pre-existing)".
  * a listed file that now PASSES is LIST DRIFT (exit 1), so the artifact's scope cannot silently
    drift away from its claim.

Run: python3 tests/test_verify_preexisting_failures_classification.py
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "tests" / "verify_preexisting_failures.sh"


class NotRun(Exception):
    """The subject could not be executed here, so nothing was verified."""


def _classify(rc: int, log_text: str):
    """Drive the script's OWN classifier — the safety property under test."""
    d = Path(tempfile.mkdtemp(prefix="vpf-classify-"))
    out = d / "run.log"
    out.write_text(log_text)
    r = subprocess.run(["bash", str(SCRIPT), "--classify-only", str(rc), str(out)],
                       capture_output=True, text=True, cwd=str(REPO))
    assert r.returncode == 0, ("--classify-only must be a clean mode:",
                               r.returncode, r.stdout, r.stderr)
    return r.stdout.strip()


def test_a_failure_must_be_NAMED_in_the_output():
    """rc=1 with a failure named is a failure. rc=1 with nothing named is the probe failing, and
    calling that a failure of the code under test is how a broken probe becomes a false record."""
    assert _classify(1, "RESULT: FAIL (1/9): ['test_x']") == "FAIL"
    assert _classify(1, "FAIL  test_x\nTraceback (most recent call last):\n  ...") == "FAIL"
    assert _classify(1, "3 FAILED: a, b, c") == "FAIL"
    # The decisive pair: same exit code, nothing named -> NOT RUN.
    assert _classify(1, "7.0.0-38-generic\n") == "NOTRUN", \
        "an exit code with no failure named is NOT a failure — it is nothing measured"
    assert _classify(1, "") == "NOTRUN"
    print("  a failure is only a failure when the output NAMES one ✓")


def test_a_run_that_cannot_execute_is_NOT_RUN():
    """Timeout and invocation errors are their own outcome: never FAIL, never PASS."""
    for rc in (124, 126, 127):
        assert _classify(rc, "") == "NOTRUN", rc
        assert _classify(rc, "RESULT: ALL PASS (9 tests)") == "NOTRUN", \
            f"rc={rc} means the process never ran the tests, whatever it printed"
    print("  timeout / cannot-invoke is NOT RUN, never FAIL and never PASS ✓")


def test_a_silent_success_is_not_a_pass():
    """A run that produced no output at all verified nothing — the measured case being a log whose
    entire content was the kernel release string."""
    assert _classify(0, "RESULT: ALL PASS (5 tests)") == "PASS"
    assert _classify(0, "") == "NOTRUN", "an empty log is not evidence of a pass"
    print("  rc=0 with an empty log is NOT RUN, not PASS ✓")


def test_the_script_reports_COULD_NOT_VERIFY_instead_of_agreement():
    """END-TO-END, and the whole point: when every run times out, the script must refuse to claim
    agreement. Pre-fix this exact input produced exit 0 and 'SAME (pre-existing)'.
    """
    assert SCRIPT.is_file(), f"missing {SCRIPT}"
    # 0.01s, not 1s: a whole second turned out to be enough for the file to COMPLETE, so the probe
    # silently measured the (passing) happy path instead of the timeout branch it names. A probe
    # that cannot reach its subject reports the wrong verdict in both directions.
    env = {**os.environ, "PER_TEST_TIMEOUT": "0.01",
           "PREEXISTING_TESTS": "tests/test_per_blob_findings_recorded.py"}
    r = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True,
                       cwd=str(REPO), env=env, timeout=600)
    both = r.stdout + r.stderr
    assert r.returncode == 3, f"expected exit 3 (could not verify), got {r.returncode}:\n{both}"
    assert "COULD NOT VERIFY" in both, both
    assert "SAME (FAIL pre-existing)" not in both, "must not claim agreement from unmeasured runs"
    print("  all runs timed out -> exit 3, COULD NOT VERIFY (never 'SAME') ✓")


def test_a_listed_file_that_now_passes_is_flagged_as_drift():
    """The artifact's scope must not silently disagree with its claim."""
    env = {**os.environ, "PER_TEST_TIMEOUT": "200",
           "PREEXISTING_TESTS": "tests/test_per_blob_findings_recorded.py"}
    r = subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True,
                       cwd=str(REPO), env=env, timeout=600)
    both = r.stdout + r.stderr
    assert r.returncode == 1, f"expected exit 1 (drift), got {r.returncode}:\n{both}"
    assert "NO LONGER FAILING" in both, both
    print("  a listed file that passes is reported as LIST DRIFT ✓")


def _main():
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    if not tests:
        print("NO TESTS RAN — this file executed nothing")
        return 1
    print("script:", SCRIPT)
    failed, not_run = [], []
    for name, fn in tests:
        try:
            fn()
        except NotRun as exc:
            not_run.append(f"{name}: {exc}")
            print(f"NOT RUN  {name}")
        except Exception:
            import traceback
            failed.append(name)
            print(f"FAIL  {name}")
            traceback.print_exc()
    if not_run:
        print(f"NOT RUN ({len(not_run)}) — ran nothing here, so not evidence either way:")
        for entry in not_run:
            print(f"  - {entry}")
    if failed:
        print(f"RESULT: FAIL ({len(failed)}/{len(tests)}): {failed}")
        return 1
    print(f"RESULT: ALL PASS ({len(tests)} tests)" + (f" ({len(not_run)} NOT RUN)" if not_run else ""))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
