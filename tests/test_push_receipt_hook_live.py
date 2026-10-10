#!/usr/bin/env python3
"""The REAL pre-push hook against the REAL unpushed range — both directions.

    python3 tests/test_push_receipt_hook_live.py                 # refusal case
    PUSH_RECEIPT_E2E=1 python3 tests/test_push_receipt_hook_live.py   # + allow case

Why this exists: the carve-out is only reachable for a NON-EMPTY unpushed range in
$HOME/hermes-cortex — the hook gates nothing else — so a rule-level test alone
cannot show the gate actually yields. This drives the shipped hook itself with a
THROWAWAY state dir (GOVERNANCE_STATE_DIR), so nothing here can authorise a live
push: an empty dir can only refuse harder.

  A) no lock, NO receipt          → rc≠0 with "no active governance lock"
  B) no lock, a receipt covering the range → the lock gate yields (rc=0)

Case B is OPT-IN because passing the lock gate lets the hook run on into its
doctor gate and the MANDATORY DOGFOOD, which re-deploys this host (minutes, and a
real side effect). Asserting only case A by default keeps the suite hermetic and
fast; the allow direction is proved at rule level in
tests/test_push_receipt_authorises.py and end to end with PUSH_RECEIPT_E2E=1.

SKIP (reported, never silent) when HEAD is level with origin/main: there is no
range, so the carve-out is unreachable by construction.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / "ops/scripts/pre-push-pull"
CHECK = REPO / "ops/scripts/lib/review-receipt-check.py"

failures = []


def check(name, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got={got!r} want={want!r}")
    if not ok:
        failures.append(name)


def git(*args):
    return subprocess.run(["git", "-C", str(REPO), *args],
                          capture_output=True, text=True).stdout.strip()


def run_hook(state_dir):
    env = dict(os.environ)
    env["GOVERNANCE_STATE_DIR"] = str(state_dir)
    r = subprocess.run(["bash", str(HOOK)], cwd=REPO, env=env, input="",
                       capture_output=True, text=True, timeout=900)
    return r.returncode, r.stdout + r.stderr


def main():
    spec = importlib.util.spec_from_file_location("rrc_live", CHECK)
    rrc = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rrc)

    tip = git("rev-parse", "HEAD")
    base = git("merge-base", "origin/main", "HEAD") or git("rev-list", "--max-parents=0", "HEAD")
    if not tip or not base or tip == base:
        print(f"SKIP  live hook: nothing unpushed (HEAD {tip[:8]} is level with origin/main) "
              f"— the carve-out is unreachable by construction")
        return 0
    blobs = rrc.range_blobs(REPO, base, tip)
    if not blobs:
        print(f"SKIP  live hook: range {base[:8]}..{tip[:8]} lists no files")
        return 0
    print(f"      live range {base[:8]}..{tip[:8]}, {len(blobs)} file(s)")

    tmp = Path(tempfile.mkdtemp(prefix="hook-live-"))
    try:
        empty = tmp / "no-receipt"
        empty.mkdir()
        rc_a, out_a = run_hook(empty)
        check("A) no lock and no receipt → refused",
              rc_a != 0 and "no active governance lock" in out_a, True)

        if os.environ.get("PUSH_RECEIPT_E2E") != "1":
            print("SKIP  B) the allow case (set PUSH_RECEIPT_E2E=1; it runs the mandatory "
                  "dogfood, i.e. a real deploy) — proved at rule level in "
                  "tests/test_push_receipt_authorises.py")
        else:
            covering = tmp / "covering"
            covering.mkdir()
            (covering / f".reviewed-{REPO.name}-{tip}.json").write_text(json.dumps(
                {"verdict": "CLEAN", "repo_slug": REPO.name, "tip_sha": tip,
                 "base_sha": base, "reviewed_blobs": blobs}))
            rc_b, out_b = run_hook(covering)
            check("B) no lock, covering receipt → the lock gate yields and the push path runs",
                  rc_b == 0 and "no active governance lock" not in out_b, True)
            check("B) and the hook says WHY it was allowed",
                  "CLEAN review receipt covers this range" in out_b, True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if failures:
        print(f"RESULT: FAIL ({len(failures)}): {failures}")
        return 1
    print("RESULT: ALL PASS — the shipped hook refuses without a receipt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
