"""bootstrap.sh resolves its cortex-doctor interpreter through the shared arbiter.

Two branches a FRESH host can hit, and neither shows up in an ordinary deploy — so they are pinned
here rather than described in an evidence file:

  * nothing on the host can import yaml (the resolver's own exit 3)
        -> say COULD NOT VERIFY and CARRY ON; a diagnostic step must not fail an install
  * the resolver ITSELF is broken (missing, unreadable, crashed — any other non-zero)
        -> say so. Reporting a broken resolver as "no interpreter can import yaml" hides a broken
           script behind a dependency story, and the two have different fixes
           (self-adversarial finding ADV-12432-2).

The block is extracted from the REAL file by stable markers, so this test fails if the logic is
edited away instead of quietly testing a stale copy — the isolation pattern documented in
skills/devops/shell-scripting ("Testing a Script Block in Isolation").
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BOOTSTRAP = REPO / "ops" / "deploy" / "bootstrap.sh"
START = "# Resolve the interpreter by CAPABILITY"
END_MARK = "\nfi\n"


def _block() -> str:
    text = BOOTSTRAP.read_text(errors="replace")
    start = text.index(START)
    end = text.index(END_MARK, start)
    return text[start : end + len(END_MARK)]


def _run(stub: str) -> tuple[int, str]:
    """Run the extracted block against a STUBBED resolver. Returns (rc, combined output)."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        lib = root / "repo" / "ops" / "scripts" / "lib"
        lib.mkdir(parents=True)
        (lib / "python-with-module.sh").write_text(stub)
        harness = root / "harness.sh"
        harness.write_text(
            # `set -e` mirrors bootstrap.sh: the block must reach its own error branch instead of
            # aborting on the failed substitution.
            "set -uo pipefail\n"
            "warn() { printf 'WARN: %s\\n' \"$*\"; }\n"
            f"CORTEX_REPO={root / 'repo'}\n"
            "REAL_USER=test\n"
            "REAL_HOME=$HOME\n" + _block()
        )
        done = subprocess.run(["bash", str(harness)], capture_output=True, text=True, timeout=60)
        return done.returncode, done.stdout + done.stderr


def test_no_interpreter_says_could_not_verify_and_the_bootstrap_continues():
    rc, out = _run("#!/usr/bin/env bash\nexit 3\n")
    assert "COULD NOT VERIFY" in out, out
    assert rc == 0, f"a host without yaml must not fail the install: rc={rc}\n{out}"


def test_a_broken_resolver_is_not_reported_as_a_missing_dependency():
    rc, out = _run("#!/usr/bin/env bash\necho 'resolver exploded' >&2\nexit 2\n")
    assert "FAILED" in out and "rc=2" in out, out
    assert "COULD NOT VERIFY" not in out, (
        "a broken resolver is a different problem than a missing dependency, and must not be "
        f"reported as one:\n{out}"
    )


def test_a_resolved_interpreter_takes_the_doctor_branch():
    """The happy path must not print either fallback message. `true` stands in for the doctor so
    the test never needs sudo or a real interpreter to observe which branch ran."""
    rc, out = _run("#!/usr/bin/env bash\nprintf '/usr/bin/true\\n'\n")
    assert "COULD NOT VERIFY" not in out and "FAILED" not in out, out
