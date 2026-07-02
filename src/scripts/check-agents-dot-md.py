#!/usr/bin/env python3
"""Check that a repo's AGENTS.md has the core requirements for agent governance.

Exit codes:
  0 = AGENTS.md present and meets requirements
  1 = AGENTS.md missing
  2 = AGENTS.md exists but missing required sections

Run from a repo root:
  python3 check-agents-dot-md.py
  python3 check-agents-dot-md.py /path/to/repo

The pre-commit hook calls this on every commit. Required sections are
defined in REQUIRED_SECTIONS below — agents need these to understand
the execution contract, scoring, and governance rules.
"""

import os
import re
import sys
from pathlib import Path

REQUIRED_SECTIONS = {
    "agent-execution-contract": (
        "Agent Execution Contract",
        r"(?i)agent\s+execution\s+contract"
    ),
    "non-negotiable-rules": (
        "Non-Negotiable Rules (Rule #10 / Score Every Change)",
        r"(?i)(rule\s*#?10|score\s+every\s+change|non-negotiable)"
    ),
    "score-every-change": (
        "Score Every Change (loop governance)",
        r"(?i)(loop.?governance|score.?cycle|begin_change|end_change|mcp_loop_governance)"
    ),
    "real-execution": (
        "Real execution, no simulation",
        r"(?i)real\s+execution[,\s:]+no\s+simulation"
    ),
}

# Sections that are recommended but not enforced
RECOMMENDED_SECTIONS = {
    "architecture-principles": (
        "Architecture Principles",
        r"(?i)architecture\s+princi"
    ),
    "what-repo-does": (
        "What This Repo Does",
        r"(?i)what\s+this\s+repo\s+does"
    ),
}


def check_agents_md(repo_root: Path) -> int:
    agents_md = repo_root / "AGENTS.md"
    if not agents_md.exists():
        print(f"❌  AGENTS.md not found in {repo_root}")
        print(f"    Create one at {agents_md}")
        print(f"    See ~/hermes-cortex/AGENTS.md as a template")
        return 1

    content = agents_md.read_text(encoding="utf-8", errors="replace")

    missing_required = []
    missing_recommended = []

    for key, (display, pattern) in REQUIRED_SECTIONS.items():
        if re.search(pattern, content):
            print(f"  ✅  {display}")
        else:
            print(f"  ❌  {display} — MISSING")
            missing_required.append(key)

    for key, (display, pattern) in RECOMMENDED_SECTIONS.items():
        if re.search(pattern, content):
            print(f"  📋  {display}")
        else:
            print(f"  ⚠️   {display} — recommended but not found")
            missing_recommended.append(key)

    if missing_required:
        print(f"\n❌  FAILED: {len(missing_required)} required section(s) missing in {agents_md.name}")
        print(f"    Add these sections (see ~/hermes-cortex/AGENTS.md as reference)")
        for key in missing_required:
            print(f"    - {REQUIRED_SECTIONS[key][0]} ({key})")
        return 2

    if missing_recommended:
        print(f"\n⚠️   Passed required checks. {len(missing_recommended)} recommended section(s) missing.")
    else:
        print(f"\n✅  All checks passed.")

    return 0


def main():
    if len(sys.argv) > 1:
        repo_root = Path(sys.argv[1]).resolve()
    else:
        # Detect git root
        result = os.popen("git rev-parse --show-toplevel 2>/dev/null").read().strip()
        if result:
            repo_root = Path(result)
        else:
            repo_root = Path.cwd()

    if not repo_root.is_dir():
        print(f"❌  Not a directory: {repo_root}")
        sys.exit(1)

    print(f"🔍  Checking AGENTS.md in {repo_root}")
    sys.exit(check_agents_md(repo_root))


if __name__ == "__main__":
    main()
