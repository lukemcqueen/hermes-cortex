#!/usr/bin/env python3
"""Show the DEFECTS this change removes are present in a PRE-FIX revision.

Point it at the module extracted from git history and it asserts the three defects are
really there — the other half of the discrimination, so a reader can re-run BOTH sides:

    git show <base>:mcp-servers/loop-gov-mcp.py > /tmp/pre-fix.py
    python3 docs/evidence/release-closes-cycle-prefix-check.py /tmp/pre-fix.py

Exit 0 = the source carries all three defects (so the change is a real change);
exit 1 = it does not look pre-fix (a mistyped revision, or the fix is already in it).
"""
import ast
import sys
from pathlib import Path

DEFECTS = (
    "no shared cycle closer (_close_cycle_unscored is absent)",
    "the findings refusal releases the lock without closing its cycle",
    "the metadata refusal releases by a possibly-None (process-scoped) session id",
)


def fn_source(src, name):
    for node in ast.parse(src).body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(src, node) or ""
    return ""


def main():
    if len(sys.argv) < 2:
        print("usage: release-closes-cycle-prefix-check.py <pre-fix-module.py>")
        return 2
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"FAIL: no such file: {path}")
        return 1
    src = path.read_text()
    print(f"pre-fix source: {path}")

    findings = fn_source(src, "_release_after_refusal")
    meta = fn_source(src, "_release_lock_after_metadata_refusal")
    present = [
        "def _close_cycle_unscored(" not in src,
        "_close_cycle_unscored(" not in findings and '_release_lock({"session_id"' in findings,
        '_release_lock({"session_id": sid} if sid else None)' in meta,
    ]
    for name, ok in zip(DEFECTS, present):
        print(f"{'PRESENT' if ok else 'ABSENT ':7} {name}")

    missing = [n for n, ok in zip(DEFECTS, present) if not ok]
    if missing:
        print(f"\nNOT a pre-fix revision — missing defect(s): {missing}")
        return 1
    print("\nall three defects present: this revision is pre-fix")
    return 0


if __name__ == "__main__":
    sys.exit(main())
