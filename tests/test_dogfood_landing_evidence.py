#!/usr/bin/env python3
"""Runnable verifier for docs/evidence/dogfood-fix-landing-41f1e601.txt.

Parsses the committed 3rd-dogfood transcript and asserts the claims the close
relies on (ADV-4916-1):
  - Deploy sync: a line matches HEAD (deployed commit matches HEAD)
  - Zero doctor FAILs (Overall WARNING with an explicit '0 fail' token;
    assert no other 'fail' with a nonzero count)
  - DOGFOOD_EXIT=0
  - Key deploy-mapped checksums present (content-matches lines for loop-gov.py,
    loop-gov-mcp.py, cortex-update.sh, cortex-dogfood.sh, verify-stamp-repo-tuple.py)
A later reviewer re-executes this check rather than trusting prose.
"""
from __future__ import annotations

import re
from pathlib import Path

EVIDENCE = Path(__file__).resolve().parent.parent / "docs" / "evidence" / "dogfood-fix-landing-41f1e601.txt"

REQUIRED = [
    "DOGFOOD_EXIT=0",
    "deployed commit matches HEAD",
    "Checksum: loop-gov.py",
    "Checksum: loop-gov-mcp.py",
    "Checksum: cortex-update.sh",
    "Checksum: cortex-dogfood.sh",
    "Checksum: verify-stamp-repo-tuple.py",
]


def main() -> int:
    assert EVIDENCE.exists(), f"missing {EVIDENCE}"
    text = EVIDENCE.read_text()
    for token in REQUIRED:
        assert token in text, f"missing token: {token!r} in {EVIDENCE.name}"
    # zero-fail: the doctor overall must carry an explicit '0 fail'; no 'N fail' with N big bless than 1
    fail_m = re.findall(r"(\d+)\s*fail", text)
    for n in fail_m:
        assert int(n) == 0, f"doctor report cards non-zero fail count: {n} "
    assert "0 fail" in text, "missing explicit '0 fail' doctor token"
    print("RESULT: dogfood-fix-landing evidence verified (deploy-sync=HEAD, zero-fail, EXIT=0, checksums present))\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())