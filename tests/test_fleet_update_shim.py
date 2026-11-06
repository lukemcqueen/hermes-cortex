#!/usr/bin/env python3
"""P3 step-2: the fleet-update.sh forwarding shim must WORK, not just exist.

The P3 exit criterion is that a deploy runs from the NEW name
(ops/scripts/fleet-update.sh) while every legacy invocation keeps working.
The shim at ops/scripts/fleet-update.sh is the load-bearing legacy path —
live crons, documented commands and the sanctioned gate all resolve through
it for this one release. Three facts pinned here:

1. The shim exists, is executable, and execs its sibling fleet-update.sh
   (a content check: a shim that existed but pointed nowhere would pass a
   presence-only test).
2. The canonical script it forwards to exists (the executable target, not
   a claim).
3. FORWARDING WORKS: `bash ops/scripts/fleet-update.sh --status` exits 0
   and reaches the real script's own output. --status is deliberately the
   fast, non-mutating invocation — it prints "Changed files since last
   update" and returns 0; running the full deploy in a unit test would
   mutate the host.
"""
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SHIM = REPO / "ops" / "scripts" / "fleet-update.sh"
CANONICAL = REPO / "ops" / "scripts" / "fleet-update.sh"


def test_shim_exists_executable_and_forwards_to_sibling():
    assert SHIM.exists(), "the one-release shim was deleted before its release"
    assert SHIM.stat().st_mode & 0o111, "legacy direct invocations need the +x bit"
    body = SHIM.read_text()
    assert "fleet-update.sh" in body, "the shim must exec its new-name sibling"
    assert "ONE-RELEASE" in body, "the shim must self-describe as one-release"
    assert CANONICAL.exists(), "the shim forwards to a script that does not exist"


def test_shim_status_reaches_the_real_script():
    run = subprocess.run(["bash", str(SHIM), "--status"],
                         capture_output=True, text=True, timeout=120)
    assert run.returncode == 0, f"shim --status rc={run.returncode}: {run.stderr[-500:]}"
    # The banner + the status section are produced by fleet-update.sh itself —
    # reaching them proves the exec chain, not just a wrapper echo.
    assert "Changed files since last update" in run.stdout
