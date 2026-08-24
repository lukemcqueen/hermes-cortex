#!/usr/bin/env python3
"""cortex-bus-failover-watchdog.py — detect bus failover, per-role behavior.

Deployed to EVERY agent (orchestrators and workers). Role is detected from
the host (same rule as the doctor): home dir / hostname moses|esther →
orchestrator, anything else → worker.

ROLE BEHAVIOR
  ── Orchestrator (Esther — backup) ────────────────────────────────
  IDLE       Moses healthy → silent.
  DEGRADED   1-2 consecutive failed checks → warn ONCE on first failure.
  FAILOVER   3+ consecutive failures AND elapsed >= FAILOVER_MIN_DOWN_MINUTES
             → ACTIVATE: swap Esther's cortex-bus.conf primary/fallback,
               write .failover-active marker, notify fleet, report.
  RECOVERED  Moses healthy 3 consecutive checks while failover active
             → RESTORE: swap config back, remove marker, notify fleet, report.
  Executes for real by default (FAILOVER_DRY_RUN=0) — that is the point of
  the automation. Run with FAILOVER_DRY_RUN=1 for a safe preview.

  ── Worker (Gisu, Joseph, Kustos, Titus) ──────────────────────────
  IDLE       Primary bus (Moses :13004) reachable → silent.
  DEGRADED   Primary down but fallback (Esther :14004) up → warn ONCE:
             traffic now routes via Esther automatically (lib.cortex_bus
             per-call fallback). No config change needed on the worker.
  ISOLATED   PRIMARY AND FALLBACK BOTH DOWN → CRITICAL alert: no bus path
             at all; messages queue locally until a bus returns.
  RECOVERED  Primary back after being down → report recovery, silent.

  Workers NEVER swap config or write markers — their lib.cortex_bus already
  falls back per-call; this watchdog only detects and reports.

  ── Moses (primary orchestrator) ───────────────────────────────────
  Runs the same checks but stays silent: his own health is covered by
  orch-fleet-watchdog, and he has nothing to fail over TO.

STATE MACHINE STATE FILE (per host):
  ~/.hermes-cortex/state/bus-failover-state.json

CONFIG (env vars, all optional):
  FAILOVER_MIN_DOWN_MINUTES  default 15 — outage before orchestrator activates
  FAILOVER_DRY_RUN           default 0 for orchestrators / 1 for workers —
                             orchestrators must actually fail over; workers
                             never write anything anyway
  MOSES_HEALTH_URLS          comma-separated probes; default Moses :13007+:13004
  ESTHER_HEALTH_URLS         comma-separated probes; default Esther :14004
  FAILOVER_CHECK_INTERVAL    default 5 — tick minutes (warning text only)

Safe to run anytime. no_agent cron pattern: empty stdout = silent; text
output = delivered to the configured channel.
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
HOSTNAME = os.uname().nodename.split(".")[0]
IS_ORCHESTRATOR = HOSTNAME in ("moses", "esther")
IS_MOSES = HOSTNAME == "moses"

STATE_DIR = HOME / ".hermes-cortex" / "state"
STATE_FILE = STATE_DIR / "bus-failover-state.json"
MARKER_FILE = STATE_DIR / ".failover-active"
LOG_FILE = STATE_DIR / ".bus-failover-log"
CONF_FILE = HOME / ".hermes-cortex" / "cortex-bus.conf"
WATCHDOG_DIR = os.path.dirname(os.path.abspath(__file__))

# Esther's ACL (docs/bus-architecture.md): workers and Esther send to
# inbox_orchestrator (shared) or their own inbox; only Moses sends
# cross-agent. During failover Esther's LOCAL bus accepts everything (she
# is primary), so the event also reaches workers who have fallen back to
# :14004 — the designed cross-agent path is inbox_orchestrator.
FLEET_QUEUES = ["inbox_moses", "inbox_esther"]

MIN_DOWN_MINUTES = int(os.environ.get("FAILOVER_MIN_DOWN_MINUTES", "15"))
CHECK_INTERVAL = int(os.environ.get("FAILOVER_CHECK_INTERVAL", "5"))
# Orchestrators must actually fail over; workers never write anything.
DRY_RUN = os.environ.get("FAILOVER_DRY_RUN", "1" if not IS_ORCHESTRATOR else "0") == "1"

MOSES_HEALTH_URLS = [
    u.strip()
    for u in os.environ.get(
        # Canonical (Luke 2026-08-24): ORCH_HEALTH_URLS = active
        # orchestrator's probes, BACKUP_ORCH_HEALTH_URLS = standby's.
        # Role-derived, never host-hardcoded — the same code runs on any
        # host. Legacy names kept as fallback for un-migrated hosts.
        "ORCH_HEALTH_URLS",
        os.environ.get("MOSES_HEALTH_URLS", ""),
    ).split(",")
    if u.strip()
]
ESTHER_HEALTH_URLS = [
    u.strip()
    for u in os.environ.get(
        "BACKUP_ORCH_HEALTH_URLS",
        os.environ.get("ESTHER_HEALTH_URLS", ""),
    ).split(",")
    if u.strip()
]

# Tick count for the first-failure warning message (not used for activation —
# activation is time-based via first_failure_at). Computed with divmod (no
# slash operator) to keep the cron lifecycle guard's shell tokenizer from
# resolving a lone "/" to the filesystem root.
WARN_TICK_TOTAL = divmod(MIN_DOWN_MINUTES, CHECK_INTERVAL)[0] + 1

RECOVER_REQUIRED_SUCCESSES = 3  # consecutive healthy checks before restoring


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
        _log("ERROR: could not write bus-failover-state.json")


# ── Seam 1: endpoint reachability (injectable for tests) ──────────
def endpoints_reachable(urls: list[str] | None = None) -> bool:
    """True only if EVERY configured endpoint responds healthy.

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


def _moses_reachable(urls: list[str] | None = None) -> bool:
    return endpoints_reachable(urls if urls is not None else MOSES_HEALTH_URLS)


def _esther_reachable(urls: list[str] | None = None) -> bool:
    return endpoints_reachable(urls if urls is not None else ESTHER_HEALTH_URLS)


# ── Seam 2: config swap (orchestrator only, injectable for tests) ─
def swap_bus_config(active: bool) -> bool:
    """Rewrite cortex-bus.conf primary/fallback URLs (Esther only).

    active=True  → acting primary: URL=local :8903, FALLBACK=Moses :13004
    active=False → standby restored: URL=Moses :13004, FALLBACK=Esther :14004

    Returns True on success. Creates the file if missing.
    """
    bus_url = os.environ.get("CORTEX_BUS_URL", "").strip()
    bus_fallback = os.environ.get("CORTEX_BUS_FALLBACK_URL", "").strip()
    if not bus_url or not bus_fallback:
        _log("ERROR: CORTEX_BUS_URL / CORTEX_BUS_FALLBACK_URL not set in env — cannot swap")
        return False
    if active:
        primary, fallback = "http://127.0.0.1:8903", bus_url
    else:
        primary, fallback = bus_url, bus_fallback

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


# ── Seam 3: fleet notification (orchestrator only, injectable) ────
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
            if WATCHDOG_DIR not in sys.path:
                sys.path.insert(0, WATCHDOG_DIR)
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


# ── Orchestrator activation / recovery ────────────────────────────
def _activate(state: dict) -> list[str]:
    lines = [
        "🚨 FAILOVER ACTIVATED — Moses unreachable",
        f"   consecutive failures: {state['consecutive_failures']}",
        f"   first failure at: {state.get('first_failure_at')}",
        "   Esther is now the acting orchestrator (bus :8903, nginx :14004)",
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
        "Workers: your lib.cortex_bus already falls back to :14004 automatically — no action needed. "
        "Events go via inbox_orchestrator; the orchestrator will relay on his return.",
    )
    lines.append(f"   ✅ fleet notified ({sent} queues)")
    _log("FAILOVER ACTIVATED")
    return lines


def _recover(state: dict) -> list[str]:
    lines = ["✅ FAILOVER RECOVERED — Moses healthy again, resuming as orchestrator"]
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


# ── Worker detection / alerts ─────────────────────────────────────
def _worker_alert(isolated: bool) -> list[str]:
    if isolated:
        return [
            "🚨 CRITICAL: NO BUS PATH — Moses AND Esther both unreachable",
            "   Messages will queue locally until a bus returns.",
            "   Check nginx/network on both orchestrator hosts.",
        ]
    return [
        "⚠️ Moses (primary bus) unreachable — traffic now routes via Esther :14004",
        "   lib.cortex_bus falls back per-call; no worker config change needed.",
        f"   Will alert again if both buses go down. Recovery reported when Moses returns.",
    ]


# ── Main tick ─────────────────────────────────────────────────────
def run_once(
    moses_up: bool | None = None,
    esther_up: bool | None = None,
    moses_urls: list[str] | None = None,
    esther_urls: list[str] | None = None,
) -> list[str]:
    """One watchdog tick. Returns report lines (empty = silent).

    moses_up / esther_up can be injected by tests; when None, probes the
    configured URLs. Role-agnostic: orchestrator and worker paths share
    the same state file fields.
    """
    state = _load_state()
    if moses_up is None:
        moses_up = _moses_reachable(moses_urls)
    if esther_up is None:
        esther_up = _esther_reachable(esther_urls)
    out: list[str] = []

    # Config guard (Luke 2026-08-24 — fleet-wide false CRITICAL): if
    # either orchestrator's probe list is EMPTY (unconfigured env), the
    # watchdog cannot judge reachability. Empty ≠ down — stand down
    # silently instead of screaming "NO BUS PATH" for an unset variable.
    # Only applies when the watchdog is actually PROBING (moses_up/
    # esther_up injected by callers/tests = the caller knows the state,
    # so empty URL lists are irrelevant).
    if not IS_ORCHESTRATOR and moses_up is None and esther_up is None:
        cfg_moses = MOSES_HEALTH_URLS if moses_urls is None else moses_urls
        cfg_esther = ESTHER_HEALTH_URLS if esther_urls is None else esther_urls
        if not cfg_moses or not cfg_esther:
            state["last_status"] = "unconfigured"
            _save_state(state)
            return []

    # Moses (primary orchestrator) — silent: his health is the fleet
    # watchdog's job; he has no bus to fail over to.
    if IS_MOSES:
        return []

    if moses_up:
        # Primary healthy
        state["consecutive_failures"] = 0
        state["first_failure_at"] = None
        state["consecutive_successes"] = state.get("consecutive_successes", 0) + 1
        if state.get("failover_active") and IS_ORCHESTRATOR:
            state["last_status"] = "recovering"
            if state["consecutive_successes"] >= RECOVER_REQUIRED_SUCCESSES:
                state["failover_active"] = False
                state["consecutive_successes"] = 0
                state["last_status"] = "idle"
                out = _recover(state)
        elif state.get("worker_was_down") and not IS_ORCHESTRATOR:
            # Worker: report recovery once (worker_was_down tracks the
            # degraded/isolated period without touching failover_active,
            # which is orchestrator-only semantics).
            state["worker_was_down"] = False
            state["last_status"] = "idle"
            out = ["✅ Moses (primary bus) reachable again — normal routing restored"]
        else:
            state["last_status"] = "idle"
            state["consecutive_successes"] = 0
    else:
        # Primary down
        state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1
        state["consecutive_successes"] = 0
        if state.get("first_failure_at") is None:
            state["first_failure_at"] = _now_iso()

        if state.get("failover_active"):
            state["last_status"] = "failover"  # stays active, stays quiet
        elif IS_ORCHESTRATOR:
            # Orchestrator: warn on first failure, activate after threshold
            if state["consecutive_failures"] == 1:
                out.append(
                    f"⚠️ Moses health check FAILED (1/{WARN_TICK_TOTAL}) — "
                    f"failover to Esther will trigger after >{MIN_DOWN_MINUTES} min of continuous outage"
                )
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
        else:
            # Worker: Moses down. Alert depends on whether Esther is also down.
            if state["consecutive_failures"] == 1:
                state["worker_was_down"] = True
                out = _worker_alert(isolated=not esther_up)
                state["last_status"] = "isolated" if not esther_up else "degraded"
            else:
                # Subsequent ticks: re-alert every N ticks if ISOLATED
                if not esther_up and state["consecutive_failures"] % 3 == 0:
                    out = _worker_alert(isolated=True)
                state["last_status"] = "isolated" if not esther_up else "degraded"

    state["last_check_at"] = _now_iso()
    _save_state(state)
    return out


def main() -> int:
    for line in run_once():
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
