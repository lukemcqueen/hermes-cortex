#!/usr/bin/env python3
"""Regression test: the receipt writer must RESOLVE the lock (no pytest needed).

    python3 tests/test_review_receipt_writer.py     # exit 0 = pass

Guards the root cause of 2026-10-07: _write_review_receipt called
_read_lock(None). _read_lock resolves the session from the tool-call ARGS, so
with None it returns None, the writer bailed at its next check, and NO receipt
was ever written - leaving the pre-push receipt gate unsatisfiable while every
code path read correctly.

Uses a TEMP state dir (GOVERNANCE_STATE_DIR is monkeypatched) so running this
test cannot mint a real authorisation for a real range.
"""
import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DEPLOY = Path.home() / ".hermes-cortex/tools/loop-governance/loop-gov-mcp.py"
REPO = Path(__file__).resolve().parents[1]
failures = []


def check(name, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got={got!r} want={want!r}")
    if not ok:
        failures.append(name)


def main():
    if not DEPLOY.is_file():
        print(f"FAIL  deployed module missing at {DEPLOY}")
        return 1
    spec = importlib.util.spec_from_file_location("dep_under_test", str(DEPLOY))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    live_locks = sorted((Path.home() / ".hermes-cortex/state").glob(".governance-*.json"))
    if not live_locks:
        print("SKIP: no live lock to derive a session id from")
        return 0
    sid = live_locks[-1].name[len(".governance-"):-len(".json")]

    # 1. THE BUG: without args the lock is unresolvable.
    check("_read_lock(None) cannot resolve a session (the bug)",
          m._read_lock(None), None)
    # 2. with args it resolves - which is what the fix relies on.
    check("_read_lock(args) resolves the lock",
          bool(m._read_lock({"session_id": sid})), True)

    # 3. end to end: the writer produces a receipt when given args, into a TEMP
    #    state dir so this test cannot authorise a real range.
    tmp = Path(tempfile.mkdtemp(prefix="receipt-writer-"))
    real_state = m.GOVERNANCE_STATE_DIR
    try:
        # the lock must exist IN the temp dir, because the writer resolves it
        # from the state dir it is pointed at - an empty temp dir makes
        # _read_lock return None and the writer bail (which is how this test
        # first failed, and how the instrumentation named the reason).
        shutil.copy2(live_locks[-1], tmp / live_locks[-1].name)
        m.GOVERNANCE_STATE_DIR = tmp
        m._write_review_receipt("regression-test", {"session_id": sid})
        made = sorted(tmp.glob(".reviewed-*.json"))
        check("writer emits a receipt when given args", len(made), 1)
        if made:
            d = json.loads(made[0].read_text())
            head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO,
                                  capture_output=True, text=True).stdout.strip()
            check("receipt is bound to HEAD", d.get("tip_sha"), head)
            check("receipt records a base", bool(d.get("base_sha")), True)
            check("receipt verdict is CLEAN", d.get("verdict"), "CLEAN")
            check("receipt carries the repo slug", d.get("repo_slug"), "hermes-cortex")
    finally:
        m.GOVERNANCE_STATE_DIR = real_state
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if failures:
        print(f"RESULT: FAIL ({len(failures)}): {failures}")
        return 1
    print("RESULT: ALL PASS - the writer resolves the lock and emits a bound receipt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
