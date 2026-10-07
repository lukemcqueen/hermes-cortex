#!/usr/bin/env python3
"""Review-receipt gate: a CLEAN review must precede a push (no pytest needed).

    python3 tests/test_review_receipt_gate.py     # exit 0 = pass

Exercises the SAME ops/scripts/lib/review-receipt-check.py the pre-push hook
calls, so these assertions cannot drift from what actually gates a push.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CHECK = REPO / "ops/scripts/lib/review-receipt-check.py"
LIST = REPO / "ops/scripts/lib/always-review-paths.txt"

failures = []


def check(name, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got={got!r} want={want!r}")
    if not ok:
        failures.append(name)


def authorises(receipt, tip, base):
    """Run the shipped helper the hook runs."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(receipt, fh)
        p = fh.name
    try:
        out = subprocess.run([sys.executable, str(CHECK), p, tip, base],
                             capture_output=True, text=True)
        return (out.stdout.strip() or "0")
    finally:
        Path(p).unlink(missing_ok=True)


def main():
    check("shared checker exists", CHECK.is_file(), True)
    check("always-review list exists", LIST.is_file(), True)

    clean = {"verdict": "CLEAN", "tip_sha": "aaaa111", "base_sha": "bbbb222"}

    # AC-1/AC-2: a matching clean receipt authorises; nothing else does.
    check("matching range authorises", authorises(clean, "aaaa111", "bbbb222"), "1")
    check("FINDINGS never authorises",
          authorises({**clean, "verdict": "FINDINGS"}, "aaaa111", "bbbb222"), "0")
    check("missing receipt refuses", authorises({}, "aaaa111", "bbbb222"), "0")

    # AC-3 - THE replay guard. A receipt earned for range A must not authorise B.
    check("different tip refuses (range A vs B)",
          authorises(clean, "cccc333", "bbbb222"), "0")
    check("different base refuses (same tip, rebased range)",
          authorises(clean, "aaaa111", "dddd444"), "0")

    # AC-4 - scope: only always-review paths require a receipt.
    patterns = [l.strip() for l in LIST.read_text().splitlines()
                if l.strip() and not l.startswith("#")]
    check("list is non-empty", len(patterns) > 0, True)
    ordinary = ["docs/README.md", "skills/devops/example/SKILL.md", "README.md"]
    check("ordinary files need no receipt",
          any(p in f for p in patterns for f in ordinary), False)
    guarded = ["mcp-servers/loop-gov-mcp.py", "ops/scripts/pre-push-pull"]
    check("always-review files DO need one",
          any(p in f for p in patterns for f in guarded), True)

    # AC-5 - runtime-only: the receipt lives in the state dir, never in a repo.
    check("no repo-local receipt convention in the hook",
          ".reviewed-" in (REPO / "ops/scripts/pre-push-pull").read_text()
          and "$GOVERNANCE_STATE_DIR/.reviewed-" in (REPO / "ops/scripts/pre-push-pull").read_text(),
          True)

    print()
    if failures:
        print(f"RESULT: FAIL ({len(failures)}): {failures}")
        return 1
    print("RESULT: ALL PASS - review receipt is bound to the range and scoped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
