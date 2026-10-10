#!/usr/bin/env python3
"""Does a review receipt authorise THIS range? Print 1 (yes) or 0 (no).

Single implementation shared by the pre-push gate, verify-landed.py and the tests,
so a test cannot pass against logic that differs from what actually gates a push.

Usage: review-receipt-check.py <receipt.json> <tip_sha> <base_sha> [--repo DIR]
       review-receipt-check.py --scan <state_dir> <repo_slug> <tip_sha> <base_sha> [--repo DIR]

`--scan` answers the question the PUSH GATES ask — "is there a receipt in the state
dir that authorises the range I am about to push?" — with the same rule as the
single-receipt form. It prints `1 <receipt-path>` on authorisation, or `0`. Both the
pre-push hook and the enforcer's lock carve-out call THIS, so neither can drift into
a weaker version of "covered".

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
from pathlib import Path

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
    # An EMPTY range (tip == base) is not an authorisation: there is nothing to
    # push, and a hand-written or legacy receipt naming tip==base would otherwise
    # validate by the exact-match rule below and open a lock-free push path. The
    # real writer never mints one — it refuses a range that lists no files — so
    # this only ever refuses the fabricated case (probe ADV-2026-10-10, empty
    # range: got True, want False).
    if tip == base:
        return False
    if str(receipt.get("tip_sha") or "") == tip and str(receipt.get("base_sha") or "") == base:
        return True
    # Content coverage — only when the caller could resolve the range's blobs.
    if queried_blobs is None:
        return False
    return _covered(receipt.get("reviewed_blobs"), queried_blobs)


def scan_covering(state_dir, slug, tip, base, repo=None):
    """(ok, receipt_path) for the newest receipt in state_dir that authorises tip/base.

    The hook and the enforcer both ask exactly this question, so the scan lives here
    beside the rule. Ordering mirrors the hook's original two-step: the receipt NAMED
    for this tip is tried first (it is the one this close wrote), then the rest
    newest-first — the content-coverage rule is what makes the rest usable after a
    rebase rewrote the tip.

    Fail-closed: a missing/unreadable dir, an unparseable receipt, an unresolvable
    range or an uncovered blob are all "no". Returns (False, None) for every one.
    """
    if not slug or not tip or not base:
        return False, None
    state = Path(state_dir)
    # Prefix match instead of a glob pattern: the slug comes from a repo directory
    # name, so a glob would let a name containing `*`/`?` match ANOTHER repo's
    # receipts. An explicit prefix cannot.
    prefix = f".reviewed-{slug}-"

    def _mtime(p):
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0

    try:
        candidates = sorted((p for p in state.iterdir()
                             if p.name.startswith(prefix) and p.name.endswith(".json")),
                            key=_mtime, reverse=True)
    except OSError:
        return False, None
    preferred = state / f".reviewed-{slug}-{tip}.json"
    ordered = ([preferred] if preferred.is_file() else []) + \
              [p for p in candidates if p != preferred]
    if not ordered:
        return False, None
    queried = range_blobs(repo, base, tip) if repo else None
    for path in ordered:
        try:
            with open(path) as fh:
                receipt = json.load(fh)
        except (OSError, ValueError):
            continue
        if authorises(receipt, tip, base, queried):
            return True, str(path)
    return False, None


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
    if args and args[0] == "--scan":
        rest = args[1:]
        if len(rest) != 4:
            print(0)
            return 0
        ok, path = scan_covering(rest[0], rest[1], rest[2], rest[3], repo=repo)
        print(f"1 {path}" if ok else "0")
        return 0
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
