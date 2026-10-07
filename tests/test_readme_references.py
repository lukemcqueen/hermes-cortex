#!/usr/bin/env python3
"""Every repo path the README points at must exist (no pytest needed).

    python3 tests/test_readme_references.py     # exit 0 = pass

README rot is invisible until a reader follows a link into nothing. Cycling
through this by hand found a dead `ops/scripts/remediation/` (the scripts are
under ops/scripts/health/) that had been pointing nowhere for who knows how long.

Anchors (`file.md#section`) are checked on the FILE, not the fragment — a stale
heading anchor is a smaller problem than a missing target and is not asserted here.
"""
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
README = REPO / "README.md"
failures = []


def main():
    text = README.read_text()
    refs = set()
    for m in re.findall(r"\]\((?!https?:|#)([^)]+)\)", text):
        refs.add(m.split("#", 1)[0])
    for m in re.findall(r"`((?:ops|docs|skills|plugins|mcp-servers|core)/[A-Za-z0-9_./-]+)`", text):
        refs.add(m)
    refs = {r for r in refs if r and not r.startswith("mailto:")}

    for r in sorted(refs):
        target = REPO / r
        if target.exists():
            print(f"PASS  {r}")
        else:
            print(f"FAIL  {r}  -> does not exist")
            failures.append(r)

    print()
    if failures:
        print(f"RESULT: FAIL ({len(failures)} dead reference(s) in README.md)")
        return 1
    print(f"RESULT: ALL PASS ({len(refs)} references resolve)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
