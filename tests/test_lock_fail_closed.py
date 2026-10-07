#!/usr/bin/env python3
"""Fail-closed lock check (AC-5) - runnable WITHOUT pytest.

pytest is not installed on every fleet host, which left the core safety
property unverified on this one. This is a plain script: exit 0 = pass,
1 = fail. Run it directly:

    python3 tests/test_lock_fail_closed.py

It imports the DEPLOYED enforcer (the code that actually runs) rather than a
repo copy, so a deploy that failed to propagate is caught here.
"""
import importlib.util, json, shutil, sys, tempfile
from pathlib import Path

DEPLOY = Path.home() / ".hermes/plugins/governance-enforcer/__init__.py"
STATE = Path.home() / ".hermes-cortex/state"
REPO = Path(__file__).resolve().parents[1]  # repo root under test

failures = []


def check(name, got, want):
    ok = got == want
    print(f"{'PASS' if ok else 'FAIL'}  {name}: got={got} want={want}")
    if not ok:
        failures.append(name)


def load():
    spec = importlib.util.spec_from_file_location("enf_under_test", str(DEPLOY))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    if not DEPLOY.exists():
        print(f"FAIL  deployed enforcer missing at {DEPLOY}")
        return 1
    m = load()
    fn = m._has_governance_lock

    # 1. THE property: no lock -> refuse. A regression here means writes proceed
    #    ungated, which is the one outcome the whole mechanism exists to prevent.
    check("missing lock refuses (fail-closed)", fn("no-such-session-xyz"), False)

    # 2. an exact session-id lock is honoured (Phase 1, the normal path)
    locks = sorted(STATE.glob(".governance-*.json"))
    if not locks:
        print("FAIL  no live lock present to exercise the positive case")
        failures.append("positive-case")
    else:
        sid = locks[-1].name[len(".governance-"):-len(".json")]
        check("exact session id honoured", fn(sid), True)
        # 3. a foreign/partial id must NOT be honoured (no cross-session bleed)
        check("foreign id refused", fn(sid.split("_")[-1]), False)

    # 4. Phase 2 OR: a lock whose repo_path IS the target repo is honoured even
    #    when its slug disagrees - the false block this cycle set out to fix.
    tmp = Path(tempfile.mkdtemp(prefix="lockfc-"))
    try:
        # Clone a REAL lock and mutate it: the purge pass treats a lock missing
        # ttl_seconds / started_at as stale, so an invented fixture is deleted
        # before Phase 2 ever sees it (a probe bug, not a code bug - it cost me
        # three attempts to notice).
        seed = json.loads(sorted(STATE.glob(".governance-*.json"))[0].read_text())
        seed.update({
            "session_id": "20260101_000000_deadbeef",
            "repo_slug": "slug-that-does-not-match",
            "repo_path": str(REPO),
            "heartbeat_at": "2099-01-01T00:00:00Z",
        })
        (tmp / ".governance-20260101_000000_deadbeef.json").write_text(json.dumps(seed))
        m.GOVERNANCE_STATE_DIR = tmp
        # Use an UNRELATED session id so Phase 1 (exact filename) cannot match
        # and Phase 2 is genuinely exercised. Passing the lock's own id here
        # would pass Phase 1 and test nothing about the OR.
        # MEASURED, and it corrected an earlier claim of mine: with session ids
        # present on BOTH sides and different, the cross-session guard refuses
        # FIRST, so the repo_path OR is never reached. The OR is therefore NOT
        # the fix for a same-session slug mismatch - Phase 1 (exact session-id
        # filename) already covers that case. The OR's only reachable benefit is
        # legacy locks that carry NO session_id - which is exactly what the
        # docstring calls "backward compat with old MCP locks".
        check("Phase 2 refuses a different session in the same repo (guard holds)",
              fn("unrelated-session-id", str(REPO)), False)

        seed.pop("session_id", None)          # legacy lock: no session identity
        (tmp / ".governance-20260101_000000_deadbeef.json").write_text(json.dumps(seed))
        check("Phase 2 OR grants a session-less legacy lock on repo_path match",
              fn("unrelated-session-id", str(REPO)), True)
        check("Phase 2 OR still refuses a different repo",
              fn("unrelated-session-id", str(tmp)), False)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if failures:
        print(f"RESULT: FAIL ({len(failures)}): {failures}")
        return 1
    print("RESULT: ALL PASS - the lock check fails closed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
