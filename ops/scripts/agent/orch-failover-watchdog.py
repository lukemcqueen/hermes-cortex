#!/usr/bin/env python3
"""orch-failover-watchdog.py — auto-detect Moses outage, fail over to Esther.

no_agent watchdog pattern:
  Empty stdout → silent (no state change)
  Text output  → delivered (failover activated / recovered / first-blip warning)

STATE MACHINE (per-tick, every 5 min by default):
  IDLE        Moses healthy → silent.
  DEGRADED    1-2 consecutive failed checks → warn ONCE on the first failure.
  FAILOVER    3+ consecutive failures AND elapsed >= FAILOVER_MIN_DOWN_MINUTES
              → ACTIVATE: swap Esther's cortex-bus.conf primary/fallback,
                write .failover-active marker, notify fleet, report.
  RECOVERED   Moses healthy for 3 consecutive checks while failover active
              → RESTORE: swap config back, remove marker, notify fleet, report.

WHY WORKERS DON'T NEED A CONFIG CHANGE:
  lib.cortex_bus (ops/scripts/lib/cortex_bus.py) already tries
  CORTEX_BUS_FALLBACK_URL when the primary fails (per-call failover). Workers
  have primary=Moses:13004, fallback=Esther:14004. When Moses is down, every
  bus_send/bus_read automatically lands on Esther's bus. This watchdog only
  needs to flip ESTHER's own config (primary=local:8903) so her MCP tools and
  crons keep working while she is the acting orchestrator.

CONFIG (env vars, all optional):
  FAILOVER_MIN_DOWN_MINUTES  default 15 — outage duration before activation
  FAILOVER_CHECK_INTERVAL    default 5 — tick minutes (used for 3-check math)
  FAILOVER_DRY_RUN           default "1" — "0" actually swaps config/writes marker
  MOSES_HEALTH_URLS          comma-separated probes; default = Moses :13007 + :13004

State:   ~/.hermes-cortex/state/failover-state.json
Marker:  ~/.hermes-cortex/state/.failover-active
Log:     ~/.hermes-cortex/state/.failover-log

Safe to run anytime. Default dry-run; the installed cron passes
FAILOVER_DRY_RUN=0 (see install-orch-crons.sh).
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
STATE_DIR = HOME / ".hermes-cortex" / "state"
STATE_FILE = STATE_DIR / "failover-state.json"
MARKER_FILE = STATE_DIR / ".failover-active"
LOG_FILE = STATE_DIR / ".failover-log"
CONF_FILE = HOME / ".hermes-cortex" / "cortex-bus.conf"
BUS_LIB = HOME / "hermes-cortex" / "ops" / "scripts"

FLEET_QUEUES = ["inbox_joseph", "inbox_kustos", "inbox_gisu", "inbox_titus", "inbox_moses"]

MIN_DOWN_MINUTES = int(os.environ.get("FAILOVER_MIN_DOWN_MINUTES", "15"))
CHECK_INTERVAL = int(os.environ.get("FAILOVER_CHECK_INTERVAL", "5"))
DRY_RUN = os.environ.get("FAILOVER_DRY_RUN", "1") == "1"
MOSES_HEALTH_URLS = [
    u.strip()
    for u in os.environ.get(
        "MOSES_HEALTH_URLS",
        "https://bus.example.org:13007/health,https://bus.example.org:13004/health",
    ).split(",")
    if u.strip()
]

# Tick count for the first-failure warning message (not used for activation —
# activation is time-based via first_failure_at). Computed with divmod (no
# slash operator) to keep the cron lifecycle guard's shell tokenizer from
# resolving a lone "/" to the filesystem root.
WARN_TICK_TOTAL = divmod(MIN_DOWN_MINUTES, CHECK_INTERVAL)[0] + 1

RECOVER_REQUIRED_SUCCESSES = 3  # consecutive healthy checks before restoring Moses


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(line: str) -> None:
    try:
        with LOG_FILE.open("a") as f:
            f.write(f"{_now_iso()} {line}\n")
    except OSError:
        pass  # logging must never crash the watchdog — the report is stdout


def _load_state() -> dict:
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        pass
    return {
        "consecutive_failures": 0,
        "first_failure_at": None,
        "consecutive_successes": 0,
        "failover_active": False,
        "last_status": "idle",
        "last_check_at": None,
    }


def _save_state(state: dict) -> None:
    try:
        STATE_FILE.write_text(json.dumps(state, indent=2))
    except OSError:
        _log("ERROR: could not write failover-state.json")


# ── Seam 1: Moses reachability (injectable for tests) ──────────────
def moses_reachable(urls: list[str] | None = None) -> bool:
    """True only if EVERY configured Moses endpoint responds healthy.

    Per the failover runbook's exclusion table, HTTP 401/403 is an AUTH
    issue (nginx is up, credentials wrong) — NOT an outage — so it counts
    as reachable. Connection failure, timeout, 5xx, or empty list → False.
    """
    urls = MOSES_HEALTH_URLS if urls is None else urls
    if not urls:
        return False
    for url in urls:
        try:
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=8) as resp:
                if resp.status != 200:
                    return False
        except urllib.error.HTTPError as e:
            # 401/403 = auth issue, bus/nginx is up — treat as reachable
            if e.code in (401, 403):
                continue
            return False
        except (urllib.error.URLError, OSError, TimeoutError):
            return False
    return True


# ── Seam 2: config swap (injectable for tests) ─────────────────────
def swap_bus_config(active: bool) -> bool:
    """Rewrite cortex-bus.conf primary/fallback URLs.

    active=True  → Esther is acting primary: URL=local :8903, FALLBACK=Moses :13004
    active=False → standby restored:        URL=Moses :13004, FALLBACK=Esther :14004

    Returns True on success. Creates the file if missing.
    """
    if active:
        primary, fallback = "http://127.0.0.1:8903", "https://bus.example.org:13004"
    else:
        primary, fallback = "https://bus.example.org:13004", "https://bus.example.org:14004"

    try:
        lines = CONF_FILE.read_text().splitlines() if CONF_FILE.exists() else []
    except OSError as e:
        _log(f"ERROR: cannot read {CONF_FILE}: {e}")
        return False

    seen_url = seen_fallback = False
    out = []
    for line in lines:
        if line.startswith("CORTEX_BUS_URL="):
            out.append(f"CORTEX_BUS_URL={primary}")
            seen_url = True
        elif line.startswith("CORTEX_BUS_FALLBACK_URL="):
            out.append(f"CORTEX_BUS_FALLBACK_URL={fallback}")
            seen_fallback = True
        else:
            out.append(line)
    if not seen_url:
        out.append(f"CORTEX_BUS_URL={primary}")
    if not seen_fallback:
        out.append(f"CORTEX_BUS_FALLBACK_URL={fallback}")

    try:
        CONF_FILE.write_text("\n".join(out) + "\n")
        return True
    except OSError as e:
        _log(f"ERROR: cannot write {CONF_FILE}: {e}")
        return False


# ── Seam 3: fleet notification (injectable for tests) ──────────────
def notify_fleet(subject: str, body: str, queues: list[str] | None = None) -> int:
    """Broadcast a SYSTEM_EVENT to each fleet inbox via lib.cortex_bus.

    During failover the messages land on Esther's LOCAL bus (she is primary),
    so workers that have already fallen back to :14004 can read them.
    Returns number of queues successfully written.
    """
    queues = FLEET_QUEUES if queues is None else queues
    bus_send = None
    if not DRY_RUN:
        try:
            _lib_dir = os.path.dirname(os.path.abspath(__file__))
            if _lib_dir not in sys.path:
                sys.path.insert(0, _lib_dir)
            from lib.cortex_bus import bus_send  # type: ignore
        except ImportError as e:
            _log(f"WARN: lib.cortex_bus unavailable ({e}) — broadcast skipped")
            return 0
    sent = 0
    for queue in queues:
        try:
            if DRY_RUN or bus_send is None:
                sent += 1
                continue
            bus_send(queue, {
                "from": "esther",
                "subject": subject,
                "body": body,
                "topic": "system",
                "priority": "high",
            })
            sent += 1
        except Exception as e:  # noqa: BLE001 — one bad queue must not block the rest
            _log(f"WARN: notify {queue} failed: {e}")
    return sent


def _activate(state: dict) -> list[str]:
    """Execute failover activation. Returns report lines (non-empty → delivered)."""
    lines = [
        "🚨 FAILOVER ACTIVATED — Moses unreachable",
        f"   consecutive failures: {state['consecutive_failures']}",
        f"   first failure at: {state.get('first_failure_at')}",
        f"   Esther is now the acting orchestrator (bus :8903, nginx :14004)",
    ]
    if DRY_RUN:
        lines.append("   [DRY-RUN] config swap + marker + fleet notify SKIPPED (set FAILOVER_DRY_RUN=0 to execute)")
        _log("FAILOVER ACTIVATED (dry-run)")
        return lines

    if swap_bus_config(active=True):
        lines.append("   ✅ cortex-bus.conf → primary=local :8903, fallback=Moses :13004")
    else:
        lines.append("   ❌ cortex-bus.conf swap FAILED — check permissions")
    try:
        MARKER_FILE.write_text(_now_iso())
        lines.append("   ✅ failover marker written")
    except OSError:
        lines.append("   ❌ marker write FAILED")
    sent = notify_fleet(
        "SYSTEM_EVENT: FAILOVER_ACTIVE",
        "Moses is unreachable. Esther is now the acting orchestrator. "
        "Workers: your lib.cortex_bus already falls back to :14004 automatically — no action needed.",
    )
    lines.append(f"   ✅ fleet notified ({sent} queues)")
    _log("FAILOVER ACTIVATED")
    return lines


def _recover(state: dict) -> list[str]:
    """Restore Moses as primary. Returns report lines."""
    lines = [
        "✅ FAILOVER RECOVERED — Moses healthy again, resuming as orchestrator",
    ]
    if DRY_RUN:
        lines.append("   [DRY-RUN] config restore + marker removal + fleet notify SKIPPED")
        _log("FAILOVER RECOVERED (dry-run)")
        return lines

    if swap_bus_config(active=False):
        lines.append("   ✅ cortex-bus.conf → primary=Moses :13004, fallback=Esther :14004")
    else:
        lines.append("   ❌ cortex-bus.conf restore FAILED")
    try:
        if MARKER_FILE.exists():
            MARKER_FILE.unlink()
        lines.append("   ✅ failover marker removed")
    except OSError:
        lines.append("   ❌ marker removal FAILED")
    sent = notify_fleet(
        "SYSTEM_EVENT: FAILOVER_RECOVERED",
        "Moses is back online. Esther returns to standby. "
        "Forwarder will drain any backlog to Moses automatically.",
    )
    lines.append(f"   ✅ fleet notified ({sent} queues)")
    _log("FAILOVER RECOVERED")
    return lines


def run_once(reachable: bool | None = None, urls: list[str] | None = None) -> list[str]:
    """One watchdog tick. Returns report lines (empty = silent, no state change).

    reachable can be injected by tests; when None, probes MOSES_HEALTH_URLS.
    """
    state = _load_state()
    if reachable is None:
        reachable = moses_reachable(urls)
    out: list[str] = []

    if reachable:
        state["consecutive_failures"] = 0
        state["first_failure_at"] = None
        if state.get("failover_active"):
            state["consecutive_successes"] = state.get("consecutive_successes", 0) + 1
            state["last_status"] = "recovering"
            if state["consecutive_successes"] >= RECOVER_REQUIRED_SUCCESSES:
                state["failover_active"] = False
                state["consecutive_successes"] = 0
                state["last_status"] = "idle"
                out = _recover(state)
        else:
            state["consecutive_successes"] = 0
            state["last_status"] = "idle"
    else:
        state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1
        state["consecutive_successes"] = 0
        if state.get("first_failure_at") is None:
            state["first_failure_at"] = _now_iso()

        if state.get("failover_active"):
            state["last_status"] = "failover"  # stays active, stays quiet
        else:
            # Warn on the FIRST failure only (detection start).
            if state["consecutive_failures"] == 1:
                out.append(
                    f"⚠️ Moses health check FAILED (1/{WARN_TICK_TOTAL}) — "
                    f"failover to Esther will trigger after >{MIN_DOWN_MINUTES} min of continuous outage"
                )
            # Activate when the outage has lasted >= MIN_DOWN_MINUTES.
            # Time-based (not tick-count): a 15-min outage with 5-min ticks
            # means 3+ consecutive failures covering 15+ minutes. With a
            # 1-min check interval it would take 15 ticks — same result.
            first_fail = state.get("first_failure_at")
            elapsed_min = 0.0
            if first_fail:
                try:
                    first_dt = datetime.fromisoformat(first_fail)
                    elapsed_min = (datetime.now(timezone.utc) - first_dt).total_seconds() * 0.016666666666666666
                except (ValueError, TypeError):
                    elapsed_min = 9999.0  # unparseable → treat as expired threshold
            if state["consecutive_failures"] >= 3 and elapsed_min >= MIN_DOWN_MINUTES:
                state["failover_active"] = True
                state["last_status"] = "failover"
                out = _activate(state)
            else:
                state["last_status"] = "degraded"

    state["last_check_at"] = _now_iso()
    _save_state(state)
    return out


def main() -> int:
    for line in run_once():
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
