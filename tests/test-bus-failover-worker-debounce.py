#!/usr/bin/env python3
"""test-bus-failover-worker-debounce.py — regression test for recurrent
false 'Moses unreachable -> reachable' flapping on worker hosts.

Root cause (Oct 2026, Luke report): worker path of
cortex-bus-failover-watchdog.py alerts on its FIRST failed probe
(consecutive_failures == 1) and recovers on the FIRST subsequent success
(worker_was_down -> immediate recovery). A single transient network blip to
Moses' health endpoint therefore emits a ⚠️ alert followed 5 min later by a
✅ recovery — the "unreachable/reachable" flapping pair seen repeatedly on
every worker. Unlike the orchestrator path (3 consecutive failures + elapsed
time before activation; 3 consecutive successes before recovery), the worker
path had NO debounce.

Fix: worker emits its alert only after WORKER_ALERT_CONSECUTIVE consecutive
failures (default 2) and reports recovery only after RECOVER_REQUIRED_SUCCESSES
(3) consecutive successes — mirroring the orchestrator. A single-tick blip now
produces zero output.

Usage:
  python3 test-bus-failover-worker-debounce.py     # exit 0 = pass

Safe: forces worker mode, injects moses_up/esther_up (no network), and
redirects the state file to a temp dir — the host's real failover state is
never touched. Dry-run irrelevant (worker never writes config).
"""
from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
from pathlib import Path

PASS = 0
FAIL = 0

HOME = Path.home()
WATCHDOG_SRC = HOME / "hermes-cortex" / "ops" / "scripts" / "agent" / "cortex-bus-failover-watchdog.py"


def ok(msg: str) -> None:
    global PASS
    PASS += 1
    print(f"  ✅ {msg}")


def bad(msg: str) -> None:
    global FAIL
    FAIL += 1
    print(f"  ❌ {msg}")


def _load_watchdog():
    """Import the watchdog with state/log redirected to a temp dir, forced
    into WORKER mode (no swap, no marker), probes injected (no network)."""
    spec = importlib.util.spec_from_file_location("wd_debounce", WATCHDOG_SRC)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["wd_debounce"] = mod
    spec.loader.exec_module(mod)
    tmpdir = Path(tempfile.mkdtemp(prefix="wd-debounce-"))
    mod.STATE_FILE = tmpdir / "bus-failover-state.json"
    mod.LOG_FILE = tmpdir / ".bus-failover-log"
    mod._tmpdir = tmpdir
    # Force worker role (host moses would otherwise short-circuit on IS_MOSES)
    mod.IS_MOSES = False
    mod.IS_ORCHESTRATOR = False
    return mod


def _fresh(mod):
    mod._save_state({
        "consecutive_failures": 0, "first_failure_at": None,
        "consecutive_successes": 0, "failover_active": False,
        "last_status": "idle", "last_check_at": None,
    })


def main() -> int:
    global PASS, FAIL
    print("═══ Worker failover watchdog debounce regression ═══")
    mod = _load_watchdog()
    mod.DRY_RUN = True
    # Non-empty probe urls so the worker config-guard doesn't stand down;
    # moses_up/esther_up are injected so no network call happens.
    urls_m = ["probe-moses"]
    urls_e = ["probe-esther"]

    # ── TEST A: single transient blip must be SILENT (the flapping fix) ──
    _fresh(mod)
    out_down = mod.run_once(moses_up=False, esther_up=True,
                            moses_urls=urls_m, esther_urls=urls_e)
    out_up = mod.run_once(moses_up=True, esther_up=True,
                          moses_urls=urls_m, esther_urls=urls_e)
    if not out_down and not out_up:
        ok("A: single-tick Moses blip → NO alert and NO recovery (silent, no flapping)")
    else:
        bad(f"A: blip produced output (flapping) — down={out_down} up={out_up}")
    st = mod._load_state()
    if st.get("worker_was_down"):
        bad("A: worker_was_down set by a single transient failure")
    else:
        ok("A: worker_was_down NOT set by a single transient failure")

    # ── TEST B: a real 2-tick outage still alerts (once) ──
    _fresh(mod)
    t1 = mod.run_once(moses_up=False, esther_up=True,
                      moses_urls=urls_m, esther_urls=urls_e)
    t2 = mod.run_once(moses_up=False, esther_up=True,
                      moses_urls=urls_m, esther_urls=urls_e)
    if any("routes via Esther" in l for l in t2):
        ok("B: persistent outage alerts after WORKER_ALERT_CONSECUTIVE failures")
    else:
        bad(f"B: no alert after 2 consecutive failures — t1={t1} t2={t2}")

    # ── TEST C: recovery is debounced to RECOVER_REQUIRED_SUCCESSES ──
    _fresh(mod)
    mod._save_state({
        "consecutive_failures": 2, "first_failure_at": mod._now_iso(),
        "consecutive_successes": 0, "failover_active": False,
        "worker_was_down": True, "last_status": "degraded", "last_check_at": None,
    })
    rec_line = []
    any_before = False
    for i in range(1, mod.RECOVER_REQUIRED_SUCCESSES + 1):
        out = mod.run_once(moses_up=True, esther_up=True,
                           moses_urls=urls_m, esther_urls=urls_e)
        if any("reachable again" in l for l in out):
            rec_line.append(i)
        if i < mod.RECOVER_REQUIRED_SUCCESSES and out:
            any_before = True
    if rec_line == [mod.RECOVER_REQUIRED_SUCCESSES] and not any_before:
        ok(f"C: recovery reported only after exactly {mod.RECOVER_REQUIRED_SUCCESSES} healthy checks")
    else:
        bad(f"C: recovery timing wrong — fired on ticks {rec_line}, early out={any_before}")

    # Cleanup temp dir
    try:
        shutil.rmtree(getattr(mod, "_tmpdir", ""), ignore_errors=True)
    except Exception:
        pass

    print(f"\n═══ Summary: {PASS} passed, {FAIL} failed ═══")
    return 0 if FAIL == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
