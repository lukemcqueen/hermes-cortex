#!/usr/bin/env python3
"""Does a review receipt authorise THIS range? Print 1 (yes) or 0 (no).

Single implementation shared by the pre-push gate, verify-landed.py and the tests,
so a test cannot pass against logic that differs from what actually gates a push.

Usage: review-receipt-check.py <receipt.json> <tip_sha> <base_sha> [--repo DIR]

Two ways to authorise, in order:

  1. EXACT (always honoured): the receipt's tip_sha and base_sha equal the query's.
  2. CONTENT COVERAGE (2026-10-09): the receipt's ``reviewed_blobs`` cover every
     blob the queried range changes. This is what survives a REBASE: another
     session rebasing the shared branch rewrites the tip (observed on esther:
     a commit became 120758c2 -> 09d27193 with byte-identical content), which used
     to invalidate a tip-bound receipt and block a push whose content had in fact
     been reviewed. Coverage, not equality — a range that GAINED a file the
     receipt does not cover still refuses (fail-closed), and a receipt with no
     ``reviewed_blobs`` is only ever accepted by rule 1.

Fail-closed by construction: any missing file, unparseable JSON, wrong verdict,
missing value, unresolvable revision, or uncovered blob prints 0. Anything that is
not an explicit, matching CLEAN is a no.
"""
import json
import subprocess
import sys

# Both sides of the comparison use this convention for a path that no longer
# exists at the tip, so a deletion can never read as "covered by an empty value".
DELETED = "deleted"


def range_blobs(repo, base, tip):
    """{path: blob-sha at tip} for every path the range base..tip changes.

    Returns None when the range cannot be resolved (bad revision, git missing),
    so the caller treats it as "could not verify" rather than "nothing changed".
    """
    try:
        diff = subprocess.run(["git", "-C", str(repo), "diff", "--name-only", f"{base}..{tip}"],
                              capture_output=True, text=True, timeout=30)
        if diff.returncode != 0:
            return None
        out = {}
        for path in [ln.strip() for ln in diff.stdout.splitlines() if ln.strip()]:
            rev = subprocess.run(["git", "-C", str(repo), "rev-parse", "--verify", "--quiet",
                                  f"{tip}:{path}"],
                                 capture_output=True, text=True, timeout=30)
            sha = (rev.stdout or "").strip()
            out[path] = sha if sha else DELETED
        return out
    except (OSError, subprocess.SubprocessError):
        return None


def _covered(reviewed, queried):
    """Every queried (path, sha) present with the same sha in the receipt."""
    if not isinstance(reviewed, dict) or not queried:
        return False
    for path, sha in queried.items():
        if reviewed.get(path) != sha:
            return False
    return True


def authorises(receipt, tip, base, queried_blobs=None):
    if not isinstance(receipt, dict):
        return False
    if str(receipt.get("verdict") or "").upper() != "CLEAN":
        return False
    tip = str(tip or "")
    base = str(base or "")
    # An EMPTY sha is not a match, it is a missing value. Without this, a receipt
    # whose base_sha is "" validated against a query whose base is also "" —
    # i.e. it authorised an unbounded, unreviewed range. Only ever compare
    # concrete revisions.
    if not tip or not base:
        return False
    if str(receipt.get("tip_sha") or "") == tip and str(receipt.get("base_sha") or "") == base:
        return True
    # Content coverage — only when the caller could resolve the range's blobs.
    if queried_blobs is None:
        return False
    return _covered(receipt.get("reviewed_blobs"), queried_blobs)


def _split_args(argv):
    """Positionals + optional --repo DIR. Returns (args, repo)."""
    args, repo, i = [], None, 1
    while i < len(argv):
        if argv[i] == "--repo" and i + 1 < len(argv):
            repo = argv[i + 1]
            i += 2
            continue
        args.append(argv[i])
        i += 1
    return args, repo


def main(argv):
    args, repo = _split_args(argv)
    if len(args) != 3:
        print(0)
        return 0
    path, tip, base = args[0], args[1], args[2]
    try:
        with open(path) as fh:
            receipt = json.load(fh)
    except (OSError, ValueError):
        print(0)          # missing/unreadable/unparseable is NOT clean
        return 0
    queried = range_blobs(repo, base, tip) if repo else None
    print(1 if authorises(receipt, tip, base, queried) else 0)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
