#!/usr/bin/env python3
"""Does a review receipt authorise THIS range? Print 1 (yes) or 0 (no).

Single implementation shared by the pre-push gate and its test, so the test
cannot pass against logic that differs from what actually gates a push.

Usage: review-receipt-check.py <receipt.json> <tip_sha> <base_sha>

Fail-closed by construction: any missing file, unparseable JSON, wrong verdict,
or mismatched tip/base prints 0. A receipt is bound to the RANGE it reviewed —
tip AND base — so one earned for range A can never authorise range B. Anything
that is not an explicit, matching CLEAN is a no.
"""
import json
import sys


def authorises(receipt, tip, base):
    if not isinstance(receipt, dict):
        return False
    if str(receipt.get("verdict") or "").upper() != "CLEAN":
        return False
    if str(receipt.get("tip_sha") or "") != str(tip or ""):
        return False
    if str(receipt.get("base_sha") or "") != str(base or ""):
        return False
    return True


def main(argv):
    if len(argv) != 4:
        print(0)
        return 0
    path, tip, base = argv[1], argv[2], argv[3]
    try:
        with open(path) as fh:
            receipt = json.load(fh)
    except (OSError, ValueError):
        print(0)          # missing/unreadable/unparseable is NOT clean
        return 0
    print(1 if authorises(receipt, tip, base) else 0)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
