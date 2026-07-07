#!/usr/bin/env python3
"""
agents-md-prune-scan.py — Daily scan for AGENTS.md pruning candidates.

Runs the agents-doc-audit --prune analysis and outputs the JSON report
ONLY when candidates are found. Silent when AGENTS.md is lean.

Designed as a no_agent cron companion: exit 0 + no stdout = nothing to report.
Exit 0 + JSON report = candidates available for LLM review.
"""
import json
import subprocess
import sys
from pathlib import Path

REPO = Path.home() / "hermes-cortex"
AUDIT_SCRIPT = (
    Path.home() / ".hermes-cortex" / "scripts" / "agents-doc-audit.py"
)


def main():
    if not AUDIT_SCRIPT.exists():
        # Fallback to repo path
        fallback = REPO / "src" / "scripts" / "agent" / "agents-doc-audit.py"
        if not fallback.exists():
            print(f"agents-doc-audit.py not found at {AUDIT_SCRIPT} or {fallback}", file=sys.stderr)
            sys.exit(1)
        script = str(fallback)
    else:
        script = str(AUDIT_SCRIPT)

    result = subprocess.run(
        [sys.executable, script, "--repo", str(REPO), "--prune", "--json"],
        capture_output=True,
        text=True,
        timeout=60,
    )

    if result.returncode not in (0, 2):
        # Non-zero in unexpected way — report error
        print(f"ERROR: audit script failed (exit {result.returncode}):", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

    # Parse the JSON report
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        print(f"ERROR: could not parse audit output", file=sys.stderr)
        sys.exit(1)

    # Silent when clean
    if report.get("candidate_count", 0) == 0:
        sys.exit(0)

    # Print the full JSON report for the LLM downstream cron
    print(result.stdout)


if __name__ == "__main__":
    main()
