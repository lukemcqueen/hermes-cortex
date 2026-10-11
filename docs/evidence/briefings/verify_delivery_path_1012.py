#!/usr/bin/env python3
"""Verify the required deliverables exist at ~/.hermes/cron/output/ and are
byte-identical to the committed repo copies.

Answers ADV-12176-2: the repo diff cannot show files outside the repository,
so the claim "deliverables exist at the required path" was not verifiable
from the review material. This script turns it into a committed, re-runnable
check whose output is also committed.

Exit 0 = all three deliverables present at the delivery path AND byte-identical
to docs/evidence/briefings/ copies.
"""
from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

DATE = "2026-10-12"
DELIVERY = Path.home() / ".hermes" / "cron" / "output"
REPO = Path.home() / "hermes-cortex" / "docs" / "evidence" / "briefings"
EXTS = ("md", "docx", "pdf")


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    fail = 0
    home = str(Path.home())
    print("delivery path: %s" % str(DELIVERY).replace(home + "/", "~/"))
    print("repo evidence: %s" % str(REPO).replace(home + "/", "~/"))
    print()
    print("%-6s %-9s %-18s %s" % ("ext", "bytes", "sha256[:16]", "state"))
    print("-" * 68)
    for ext in EXTS:
        name = "sustainability-briefing-%s.%s" % (DATE, ext)
        d = DELIVERY / name
        r = REPO / name
        if not d.is_file():
            print("%-6s %-9s %-18s %s" % (ext, "-", "-", "MISSING AT DELIVERY PATH"))
            fail = 1
            continue
        dh = sha256(d)
        size = d.stat().st_size
        if not r.is_file():
            print("%-6s %-9d %-18s %s" % (ext, size, dh[:16], "no repo copy"))
            fail = 1
            continue
        same = dh == sha256(r)
        print("%-6s %-9d %-18s %s" % (
            ext, size, dh[:16],
            "byte-identical to repo copy" if same else "DIFFERS FROM REPO COPY"))
        if not same:
            fail = 1
    print()
    print("RESULT: %s" % ("ALL DELIVERABLES VERIFIED" if fail == 0
                          else "FAILURES PRESENT"))
    return fail


if __name__ == "__main__":
    sys.exit(main())
