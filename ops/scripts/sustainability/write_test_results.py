#!/usr/bin/env python3
"""Run the briefing suites and commit their verbatim output as evidence.

The self-adversarial reviewer repeatedly noted it cannot see test execution.
This writes docs/evidence/briefings/test-results-<date>.txt containing the
real, unedited stdout/stderr of each suite under warnings-as-errors, plus the
exit codes — so the claim "N tests pass" is backed by an inspectable file.

Usage: python3 ops/scripts/sustainability/write_test_results.py 2026-10-10
"""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
EVID = REPO / "docs" / "evidence" / "briefings"
SUITES = (
    "tests/test_gen_briefing.py",
    "tests/test_capture_evidence.py",
    "tests/test_write_cycle_evidence.py",
    "tests/test_verify_briefing.py",
)


def python_exe() -> str:
    venv = Path.home() / ".hermes/cron/output/.venv-brief/bin/python"
    if venv.exists():
        return str(venv)
    return sys.executable


def main(date_str: str) -> int:
    py = python_exe()
    lines: list[str] = []
    lines.append(f"# Briefing test results — {date_str}")
    lines.append("")
    lines.append(f"Captured: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"Interpreter: {py}")
    lines.append("Flag set: -W error::ResourceWarning (a leaked handle fails)")
    lines.append("")
    lines.append("Regenerate with:")
    lines.append("    python3 ops/scripts/sustainability/write_test_results.py "
                 f"{date_str}")
    lines.append("")
    lines.append("=" * 72)
    lines.append("")

    total_pass = 0
    failed = 0
    for suite in SUITES:
        path = REPO / suite
        lines.append(f"$ {py} -W error::ResourceWarning {suite}")
        lines.append("")
        if not path.exists():
            lines.append("  (suite not present)")
            lines.append("")
            continue
        r = subprocess.run([py, "-W", "error::ResourceWarning", suite],
                           cwd=REPO, capture_output=True, text=True)
        combined = (r.stdout + r.stderr).rstrip()
        lines.append(combined)
        lines.append("")
        lines.append(f"exit_code={r.returncode}")
        lines.append("")
        lines.append("-" * 72)
        lines.append("")
        m = [ln for ln in combined.splitlines() if ln.startswith("Ran ")]
        if m:
            total_pass += int(m[-1].split()[1])
        if r.returncode != 0:
            failed += 1

    lines.append(f"SUMMARY: {total_pass} tests across "
                 f"{len(SUITES)} suites; failing suites: {failed}")
    lines.append("")

    dest = EVID / f"test-results-{date_str}.txt"
    dest.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {dest} ({dest.stat().st_size} bytes)")
    print(f"SUMMARY: {total_pass} tests; failing suites: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "2026-10-10"))
