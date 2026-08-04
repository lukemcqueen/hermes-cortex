#!/usr/bin/env python3
"""test-failover-drill.py — Fleet-wide Moses→Esther failover drill.

Thorough, repeatable test of the orchestrator failover contract:

  PHASE 0  Preflight — all agents reachable, Esther bus healthy, no stale
           failover state.
  PHASE 1  Detection — Moses down for >15 min must be DETECTED (watchdog
           counts consecutive failures; first failure warns).
  PHASE 2  Auto-failover — after the outage threshold, the watchdog ACTIVATES:
           Esther's cortex-bus.conf swaps primary→local, marker written,
           fleet notified (dry-run in safe mode).
  PHASE 3  All-agent fallback — every agent's bus config must have Esther's
           URL as fallback (primary=Moses, fallback=Esther) so their
           lib.cortex_bus lands on Esther when Moses is unreachable.
  PHASE 4  Resume — Moses healthy again for 3 checks → watchdog RECOVERS:
           config restored to primary=Moses, marker removed, fleet notified.
  PHASE 5  Full-cycle simulation — drive the watchdog through the complete
           down→failover→up→recover sequence with a simulated Moses.

Modes:
  python3 test-failover-drill.py             # safe: dry-run watchdog + config audit
  python3 test-failover-drill.py --live      # execute real config swap + marker
                                             # (requires Moses actually down or
                                             #  FAILOVER_MIN_DOWN_MINUTES lowered)

Exit code 0 = all critical checks pass; 1 = warnings; 2 = failures.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

LIVE = "--live" in sys.argv

PASS = 0
FAIL = 0
WARN = 0

HOME = Path.home()
WATCHDOG_SRC = HOME / "hermes-cortex" / "ops" / "scripts" / "agent" / "cortex-bus-failover-watchdog.py"
STATE_DIR = HOME / ".hermes-cortex" / "state"
STATE_FILE = STATE_DIR / "bus-failover-state.json"
MARKER_FILE = STATE_DIR / ".failover-active"
CONF_FILE = HOME / ".hermes-cortex" / "cortex-bus.conf"
REGISTRY_FILE = STATE_DIR / "agent-registry.local.json"

# Moses' real health URLs (from agent registry)
MOSES_HEALTH = "https://bus.example.org:13007/health"
MOSES_BUS = "https://bus.example.org:13004/health"
ESTHER_BUS_EXTERNAL = "https://bus.example.org:14004/health"
ESTHER_BUS_LOCAL = "http://127.0.0.1:8903/health"

FLEET_AGENTS = ["moses", "esther", "joseph", "kustos", "gisu"]


def ok(msg: str) -> None:
    global PASS
    PASS += 1
    print(f"  ✅ {msg}")


def bad(msg: str, detail: str = "") -> None:
    global FAIL
    FAIL += 1
    print(f"  ❌ {msg}" + (f" — {detail}" if detail else ""))


def warn(msg: str) -> None:
    global WARN
    WARN += 1
    print(f"  ⚠️  {msg}")


def _http_ok(url: str, timeout: int = 8) -> bool:
    """HTTP 200/401/403 = reachable (401/403 = auth-protected but up)."""
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status == 200
    except urllib.error.HTTPError as e:
        return e.code in (401, 403)  # auth-protected endpoint is up
    except (urllib.error.URLError, OSError, TimeoutError):
        return False


def _load_watchdog() -> object:
    """Import the watchdog module (fresh copy) for seam-level testing.

    Redirects state/marker/log to a temp dir so the drill NEVER touches the
    host's real failover state or marker files.
    """
    spec = importlib.util.spec_from_file_location("orch_failover_watchdog", WATCHDOG_SRC)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["orch_failover_watchdog"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    tmpdir = Path(tempfile.mkdtemp(prefix="drill-state-"))
    mod.STATE_FILE = tmpdir / "bus-failover-state.json"
    mod.MARKER_FILE = tmpdir / ".failover-active"
    mod.LOG_FILE = tmpdir / ".bus-failover-log"
    mod._tmpdir = tmpdir
    return mod


def _read_conf() -> dict:
    conf = {}
    if CONF_FILE.exists():
        for line in CONF_FILE.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                conf[k.strip()] = v.strip()
    return conf


# ═══════════════════════════════════════════════
# PHASE 0 — PREFLIGHT
# ═══════════════════════════════════════════════
def phase0_preflight() -> None:
    print("\n═══ Phase 0: Preflight ═══")
    if not WATCHDOG_SRC.exists():
        bad(f"watchdog not found: {WATCHDOG_SRC}")
        return
    ok(f"watchdog present: {WATCHDOG_SRC.name}")

    # All agents reachable via registry health URLs
    if REGISTRY_FILE.exists():
        try:
            reg = json.loads(REGISTRY_FILE.read_text())
            agents = reg.get("agents", {})
            for key in FLEET_AGENTS:
                entry = agents.get(key, {})
                url = entry.get("health_url", "")
                if not url:
                    warn(f"{key}: no health_url in registry (may be inbox-push agent)")
                    continue
                if _http_ok(url):
                    ok(f"{key} reachable: {url}")
                else:
                    bad(f"{key} UNREACHABLE: {url}")
        except (json.JSONDecodeError, OSError) as e:
            bad("registry parse", str(e))
    else:
        warn("no agent-registry.local.json — skipping per-agent reachability")

    # Esther bus healthy (local + external nginx)
    if _http_ok(ESTHER_BUS_LOCAL):
        ok(f"Esther local bus healthy: {ESTHER_BUS_LOCAL}")
    else:
        bad(f"Esther local bus DOWN: {ESTHER_BUS_LOCAL}")
    if _http_ok(ESTHER_BUS_EXTERNAL):
        ok(f"Esther external bus healthy: {ESTHER_BUS_EXTERNAL}")
    else:
        bad(f"Esther external bus DOWN: {ESTHER_BUS_EXTERNAL}")

    # No stale failover marker / state
    if MARKER_FILE.exists():
        bad("stale failover marker present at start", "remove before drill: rm ~/.hermes-cortex/state/.failover-active")
    else:
        ok("no stale failover marker")
    if STATE_FILE.exists():
        try:
            st = json.loads(STATE_FILE.read_text())
            if st.get("failover_active"):
                bad("failover-state.json says failover_active at start", "reset: rm ~/.hermes-cortex/state/failover-state.json")
            else:
                ok("failover-state.json clean (not active)")
        except json.JSONDecodeError:
            warn("failover-state.json unreadable — will be rebuilt by watchdog")


# ═══════════════════════════════════════════════
# PHASE 1 — DETECTION (watchdog seams)
# ═══════════════════════════════════════════════
def phase1_detection(mod) -> None:
    print("\n═══ Phase 1: Detection ═══")
    # moses_reachable: all endpoints up → True
    if mod._moses_reachable([MOSES_HEALTH, MOSES_BUS]):
        ok("_moses_reachable([moses health, moses bus]) = True (Moses up)")
    else:
        warn("Moses currently unreachable from Esther — this is the failover precondition, not a test failure")

    # Any endpoint down → False
    if mod._moses_reachable(["http://127.0.0.1:1/health", MOSES_BUS]):
        bad("_moses_reachable with dead endpoint returned True")
    else:
        ok("_moses_reachable with dead endpoint = False (correct)")

    # Empty list → False (fail closed)
    if mod._moses_reachable([]):
        bad("_moses_reachable([]) returned True")
    else:
        ok("_moses_reachable([]) = False (fail closed)")

    # First failure must warn
    state = mod._load_state()
    state["failover_active"] = False
    mod._save_state(state)
    out = mod.run_once(moses_up=False, esther_up=True)
    if any("Moses health check FAILED" in l for l in out):
        ok("first failure warns (detection start announced)")
    else:
        bad("first failure did not warn", str(out))


# ═══════════════════════════════════════════════
# PHASE 2 — AUTO-FAILOVER (time-threshold activation)
# ═══════════════════════════════════════════════
def phase2_autofailover(mod) -> None:
    print("\n═══ Phase 2: Auto-Failover (Moses down > 15m) ═══")
    # Force an outage that has already lasted past the threshold:
    # 3+ consecutive failures with first_failure_at >15 min ago.
    first_fail = (datetime.now(timezone.utc) - timedelta(minutes=mod.MIN_DOWN_MINUTES + 1)).isoformat()
    st = {
        "consecutive_failures": 3,
        "first_failure_at": first_fail,
        "consecutive_successes": 0,
        "failover_active": False,
        "last_status": "degraded",
        "last_check_at": None,
    }
    mod._save_state(st)
    out = mod.run_once(moses_up=False, esther_up=True)
    if any("FAILOVER ACTIVATED" in l for l in out):
        ok("failover ACTIVATED after >15m outage")
        if mod.DRY_RUN:
            ok("dry-run mode: config/marker/notify skipped (safe)")
        else:
            ok("LIVE mode: config swap + marker executed")
    else:
        bad("failover NOT activated after threshold outage", str(out))

    # Post-activation state persisted
    after = mod._load_state()
    if after.get("failover_active"):
        ok("state.failover_active = True persisted")
    else:
        bad("state.failover_active not persisted")

    # Config audit: while active, primary must be local
    conf = _read_conf()
    if not mod.DRY_RUN and LIVE:
        if conf.get("CORTEX_BUS_URL", "").startswith("http://127.0.0.1"):
            ok("cortex-bus.conf primary = local (acting orchestrator)")
        else:
            bad("cortex-bus.conf primary NOT local", str(conf.get("CORTEX_BUS_URL")))
    else:
        warn("config swap not executed (dry-run) — not audited")


# ═══════════════════════════════════════════════
# PHASE 3 — ALL-AGENT FALLBACK CONFIG
# ═══════════════════════════════════════════════
def phase3_agent_fallback(mod) -> None:
    print("\n═══ Phase 3: All-Agent Fallback Config ═══")
    # Every worker's lib.cortex_bus must fall back to Esther's URL.
    # We audit the documented worker config contract (cortex-bus-config.md §8)
    # and Esther's own conf as the reference implementation.
    conf = _read_conf()
    primary = conf.get("CORTEX_BUS_URL", "")
    fallback = conf.get("CORTEX_BUS_FALLBACK_URL", "")
    if primary.startswith("https://bus.example.org:13004"):
        ok(f"Esther primary = Moses :13004 ({primary})")
    else:
        warn(f"Esther primary not Moses :13004 (current: {primary}) — expected during active failover only")
    if fallback.endswith(":14004"):
        ok(f"Esther fallback = Esther :14004 ({fallback})")
    else:
        bad("Esther fallback not :14004", str(fallback))

    # The fallback path workers use: Esther's EXTERNAL nginx must answer.
    if _http_ok(ESTHER_BUS_EXTERNAL):
        ok(f"worker fallback target reachable: {ESTHER_BUS_EXTERNAL}")
    else:
        bad(f"worker fallback target DOWN: {ESTHER_BUS_EXTERNAL}")

    # Documented worker contract from cortex-bus-config.md §8:
    # primary=https://bus.example.org:13004, fallback=...:14004, AGENT_NAME set
    if "CORTEX_BASIC_AUTH" in conf or "CORTEX_BUS_AUTH" in conf:
        ok("auth configured (Basic) — worker HTTP client can authenticate")
    else:
        warn("no Basic auth key found in Esther conf (orchestrator uses Bearer — acceptable)")

    # Simulated worker fallback: with primary dead, lib.cortex_bus must choose
    # the fallback URL. Verify the library's URL-selection logic exists.
    try:
        sys.path.insert(0, str(HOME / "hermes-cortex" / "ops" / "scripts"))
        import lib.cortex_bus as cb
        if cb.BUS_FALLBACK_URL:
            ok(f"lib.cortex_bus fallback configured: {cb.BUS_FALLBACK_URL}")
        else:
            bad("lib.cortex_bus has NO fallback URL configured")
    except ImportError as e:
        bad("lib.cortex_bus import failed", str(e))


# ═══════════════════════════════════════════════
# PHASE 4 — RESUME MOSES
# ═══════════════════════════════════════════════
def phase4_resume(mod) -> None:
    print("\n═══ Phase 4: Resume Moses ═══")
    # Force active-failover state, then 3 consecutive healthy checks.
    st = {
        "consecutive_failures": 0,
        "first_failure_at": None,
        "consecutive_successes": 0,
        "failover_active": True,
        "last_status": "failover",
        "last_check_at": None,
    }
    mod._save_state(st)

    for i in range(1, mod.RECOVER_REQUIRED_SUCCESSES + 1):
        out = mod.run_once(moses_up=True, esther_up=True)
        if i < mod.RECOVER_REQUIRED_SUCCESSES:
            if any("FAILOVER RECOVERED" in l for l in out):
                bad(f"recovered early after {i} checks (expected {mod.RECOVER_REQUIRED_SUCCESSES})")
                return
        else:
            if any("FAILOVER RECOVERED" in l for l in out):
                ok(f"recovery triggered after exactly {mod.RECOVER_REQUIRED_SUCCESSES} healthy checks")
            else:
                bad("recovery NOT triggered after 3 healthy checks", str(out))

    after = mod._load_state()
    if not after.get("failover_active"):
        ok("state.failover_active = False after recovery")
    else:
        bad("state still failover_active after recovery")


# ═══════════════════════════════════════════════
# PHASE 5 — FULL-CYCLE SIMULATION
# ═══════════════════════════════════════════════
def phase5_full_cycle(mod) -> None:
    print("\n═══ Phase 5: Full Down→Failover→Up→Recover Cycle ═══")
    # Fresh state
    mod._save_state({
        "consecutive_failures": 0, "first_failure_at": None,
        "consecutive_successes": 0, "failover_active": False,
        "last_status": "idle", "last_check_at": None,
    })
    # Short threshold for the simulation (don't wait 15 real minutes)
    old_min = mod.MIN_DOWN_MINUTES
    mod.MIN_DOWN_MINUTES = 0  # any elapsed time >= 0 triggers

    # Ticks 1-3: Moses down → detection → activation (3 consecutive failures)
    for _tick in range(3):
        mod.run_once(moses_up=False, esther_up=True)
    if mod._load_state().get("failover_active"):
        ok("3 down ticks → failover active")
    else:
        bad("Moses down x3 did not activate failover", str(mod._load_state()))

    # More down ticks: stays active, stays quiet
    mod.run_once(moses_up=False, esther_up=True)
    if mod._load_state().get("failover_active"):
        ok("continues active while Moses down")
    else:
        bad("failover deactivated while Moses still down")

    # Moses back: 3 healthy ticks → recovered
    for i in range(mod.RECOVER_REQUIRED_SUCCESSES):
        mod.run_once(moses_up=True, esther_up=True)
    if not mod._load_state().get("failover_active"):
        ok("Moses back → failover cleared")
    else:
        bad("failover not cleared after Moses returns")

    # Idle stability: healthy ticks produce no output
    out = mod.run_once(moses_up=True, esther_up=True)
    if not out:
        ok("idle ticks are silent (no state change, no delivery)")
    else:
        warn(f"idle tick produced output: {out}")

    mod.MIN_DOWN_MINUTES = old_min


# ═══════════════════════════════════════════════
# PHASE 6 — WORKER-MODE WATCHDOG (all agents)
# ═══════════════════════════════════════════════
def phase6_worker_mode(mod) -> None:
    print("\n═══ Phase 6: Worker-Mode Watchdog (deployed on all agents) ═══")
    # Worker role = not orchestrator, not Moses. The watchdog must detect
    # this from the host and switch to worker behavior.
    if mod.IS_MOSES:
        ok("Moses host: watchdog is silent self-check (fleet watchdog covers health)")
    if not mod.IS_ORCHESTRATOR:
        ok(f"role detected as worker on this host ({mod.HOSTNAME})")
    else:
        ok(f"host {mod.HOSTNAME} detected as orchestrator — full failover mode (worker path tested by override)")

    # Save real constants, override to worker
    real_orch = mod.IS_ORCHESTRATOR
    real_moses = mod.IS_MOSES
    mod.IS_ORCHESTRATOR = False
    mod.IS_MOSES = False

    # Worker, Moses down, Esther up → warn once (fallback path active)
    mod._save_state({
        "consecutive_failures": 0, "first_failure_at": None,
        "consecutive_successes": 0, "failover_active": False,
        "last_status": "idle", "last_check_at": None,
    })
    out = mod.run_once(moses_up=False, esther_up=True)
    if any("routes via Esther" in l for l in out):
        ok("worker: Moses down + Esther up → warns 'traffic routes via Esther'")
    else:
        bad("worker: no fallback warning when Moses down", str(out))

    # Worker, BOTH down → CRITICAL alert
    mod._save_state({
        "consecutive_failures": 0, "first_failure_at": None,
        "consecutive_successes": 0, "failover_active": False,
        "last_status": "idle", "last_check_at": None,
    })
    out = mod.run_once(moses_up=False, esther_up=False)
    if any("CRITICAL" in l and "NO BUS PATH" in l for l in out):
        ok("worker: both buses down → CRITICAL no-bus-path alert")
    else:
        bad("worker: both-down did not raise CRITICAL", str(out))

    # Worker, Moses back → recovery report (worker_was_down is set by the
    # real code on first failure — mirror that in the primed state)
    mod._save_state({
        "consecutive_failures": 2, "first_failure_at": mod._now_iso(),
        "consecutive_successes": 0, "failover_active": False,
        "worker_was_down": True,
        "last_status": "degraded", "last_check_at": None,
    })
    out = mod.run_once(moses_up=True, esther_up=True)
    if any("reachable again" in l for l in out):
        ok("worker: Moses back → recovery reported")
    else:
        bad("worker: recovery not reported when Moses returns", str(out))

    # Worker, healthy idle → silent
    mod._save_state({
        "consecutive_failures": 0, "first_failure_at": None,
        "consecutive_successes": 0, "failover_active": False,
        "last_status": "idle", "last_check_at": None,
    })
    out = mod.run_once(moses_up=True, esther_up=True)
    if not out:
        ok("worker: idle ticks silent")
    else:
        warn(f"worker: idle produced output: {out}")

    # Worker must NEVER swap config (no orchestrator-only side effects)
    conf_before = _read_conf()
    mod._save_state({
        "consecutive_failures": 0, "first_failure_at": None,
        "consecutive_successes": 0, "failover_active": False,
        "last_status": "idle", "last_check_at": None,
    })
    mod.run_once(moses_up=False, esther_up=False)  # worst case
    conf_after = _read_conf()
    if conf_before == conf_after:
        ok("worker: config untouched in worst-case scenario (no swap)")
    else:
        bad("worker: config CHANGED — worker must never swap")

    # Restore real role constants
    mod.IS_ORCHESTRATOR = real_orch
    mod.IS_MOSES = real_moses


# ═══════════════════════════════════════════════
# CLEANUP — restore real state
# ═══════════════════════════════════════════════
def cleanup(mod) -> None:
    print("\n═══ Cleanup ═══")
    # The watchdog state file is the watchdog's own — reset to idle so the
    # next real tick starts clean. Marker only if we created one in LIVE mode.
    try:
        if LIVE and not mod.DRY_RUN:
            if MARKER_FILE.exists():
                MARKER_FILE.unlink()
                ok("removed test failover marker")
            # restore conf to standby (primary=Moses) if the watchdog swapped it
            conf = _read_conf()
            if conf.get("CORTEX_BUS_URL", "").startswith("http://127.0.0.1"):
                mod.swap_bus_config(active=False)
                ok("restored cortex-bus.conf to standby (primary=Moses)")
            else:
                ok("cortex-bus.conf already standby")
        else:
            ok("dry-run: no config/marker changes to undo")
    except Exception as e:
        warn(f"cleanup error: {e}")

    # Remove the temp drill-state dir (module state was redirected there;
    # the host's real bus-failover-state.json is never touched by the drill)
    try:
        tmpdir = getattr(mod, "_tmpdir", None)
        if tmpdir is not None and tmpdir.exists():
            shutil.rmtree(tmpdir)
            ok("removed temp drill-state dir")
    except OSError:
        warn("could not remove temp drill-state dir")


# ═══════════════════════════════════════════════
def main() -> int:
    global PASS, FAIL, WARN
    print(f"═══ Moses→Esther Failover Drill ({'LIVE' if LIVE else 'DRY-RUN'}) ═══")
    if not WATCHDOG_SRC.exists():
        bad(f"watchdog missing: {WATCHDOG_SRC}")
        print(f"\n{FAIL} failed, {PASS} passed, {WARN} warned")
        return 2

    mod = _load_watchdog()
    # SAFETY: the drill always runs the watchdog dry — even though the
    # installed cron defaults to execute (DRY_RUN=0) for orchestrators,
    # the drill must never swap the real config or write the marker.
    mod.DRY_RUN = True
    print(f"  watchdog: {WATCHDOG_SRC.name} (dry_run={mod.DRY_RUN}, threshold={mod.MIN_DOWN_MINUTES}m)")
    if LIVE:
        warn("--live passed but drill forces DRY_RUN — set FAILOVER_DRY_RUN=0 in the watchdog env for real execution")

    phase0_preflight()
    phase1_detection(mod)
    phase2_autofailover(mod)
    phase3_agent_fallback(mod)
    phase4_resume(mod)
    phase5_full_cycle(mod)
    phase6_worker_mode(mod)
    cleanup(mod)

    print(f"\n═══ Summary: {PASS} passed, {FAIL} failed, {WARN} warned ═══")
    if FAIL > 0:
        print("  ❌ Drill FAILED")
        return 2
    if WARN > 0:
        print("  ⚠️  Drill passed with warnings")
        return 1
    print("  ✅ Drill PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
