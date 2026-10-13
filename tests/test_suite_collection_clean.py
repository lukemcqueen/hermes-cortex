"""A green run that tests less than it claims is worse than a red one.

Measured on this fleet 2026-10-13 — same command, same host, ONLY the environment differing:

    caller's PYTHONPATH inherited       1817 collected, 4 collection ERRORS
    env -u PYTHONPATH -u PYTHONHOME     1845 collected, no errors

28 tests were silently absent, 4 modules did not import at all, and the runner still printed
"N passed". Every agent session inherits a PYTHONPATH, so the contaminated case is the DEFAULT case,
not an exotic one — and the pre-commit scoring path runs the suite from inside such a session.

This asserts that the environment the suite is being run in can import every test module. Through
`tests/run-tests.sh` (which cleanses the environment) it passes; run any other way from a
contaminated session it FAILS LOUDLY instead of quietly reporting a smaller suite as green.
"""

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def test_the_environment_can_collect_the_whole_suite():
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(REPO / "tests"), "--collect-only", "-q",
         "-p", "no:cacheprovider"],
        capture_output=True,
        text=True,
        cwd=str(REPO),
        timeout=600,
    )
    out = proc.stdout + proc.stderr

    errors = re.search(r"(\d+) errors? during collection", out)
    if errors:
        bad = [ln.strip() for ln in out.splitlines() if ln.startswith("E ")][:4]
        raise AssertionError(
            f"{errors.group(1)} test module(s) cannot be imported in this environment, so their "
            "tests are ABSENT from the run even though it reports a pass count:\n  "
            + "\n  ".join(bad)
            + "\n\nRun the suite through tests/run-tests.sh, which unsets PYTHONPATH/PYTHONHOME. "
            "A foreign site-packages shadowing the venv's own build raises ImportError that reads "
            "like a broken host rather than a contaminated caller."
        )

    collected = re.findall(r"(\d+) tests collected", out)
    assert collected, "pytest reported no collection summary at all:\n" + out[-1500:]
    # Deliberately NOT a repo-specific magic number. An earlier draft asserted > 1000, which is only
    # true of THIS repo's suite: in a smaller repo, or any non-cortex repo, it would fail a healthy
    # environment. What must be true anywhere is that pytest collected SOMETHING — a suite that
    # collects nothing is not a pass, and the errors check above has already ruled out silently
    # absent modules.
    assert int(collected[-1]) > 0, (
        "pytest collected no tests at all — a suite that collects nothing is not a pass:\n"
        + out[-1500:]
    )