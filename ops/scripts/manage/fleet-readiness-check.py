#!/usr/bin/env python3
"""
fleet-readiness-check.py — Pre-flight check before dispatching fleet update.

Verifies that the fleet is ready to receive and process an update:
1. Bus is healthy (PGMQ reachable)
2. Each agent's inbox queue exists
3. No stale dispatches in progress
4. Current git state is clean
5. Doctor passes on this machine

Usage:
    python3 fleet-readiness-check.py              # Human-readable
    python3 fleet-readiness-check.py --json       # Machine-readable

Exit codes:
    0 = ready to dispatch
    1 = issues found (read output for details)
    2 = fatal error
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
CORTEX_REPO = HOME / "hermes-cortex"
REGISTRY_PATH = HOME / ".hermes-cortex" / "state" / "agent-registry.json"
DISPATCH_LOG = HOME / ".hermes-cortex" / "state" / "fleet-update-state.json"


def check(label: str, ok: bool, detail: str = "") -> dict:
    return {"name": label, "pass": ok, "detail": detail}


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Fleet readiness check")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    args = parser.parse_args()

    checks = []

    # 1. Git state
    try:
        r = subprocess.run(
            ["git", "-C", str(CORTEX_REPO), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10
        )
        git_clean = r.stdout.strip() == ""
        git_sha = subprocess.run(
            ["git", "-C", str(CORTEX_REPO), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5
        ).stdout.strip()
        checks.append(check("Git clean", git_clean, f"on {git_sha}" if git_clean else f"uncommitted: {r.stdout.strip()[:60]}"))
    except Exception as e:
        checks.append(check("Git clean", False, str(e)))

    # 2. Registry exists and valid
    registry_ok = REGISTRY_PATH.exists()
    agent_count = 0
    if registry_ok:
        try:
            reg = json.loads(REGISTRY_PATH.read_text())
            agent_count = len(reg.get("agents", {}))
            registry_ok = agent_count > 0
        except json.JSONDecodeError:
            registry_ok = False
    checks.append(check("Registry valid", registry_ok, f"{agent_count} agents" if registry_ok else "Missing or invalid"))

    # 3. Bus is reachable (health endpoint)
    try:
        r = subprocess.run(
            ["curl", "-sf", "--max-time", "5", "http://127.0.0.1:8903/health"],
            capture_output=True, text=True, timeout=10
        )
        bus_ok = r.returncode == 0
        detail = "PGMQ healthy" if bus_ok else r.stdout[:100]
        checks.append(check("Bus reachable", bus_ok, detail or "Unreachable"))
    except Exception as e:
        checks.append(check("Bus reachable", False, str(e)))

    # 4. No stale dispatches
    stale_dispatch = False
    last_pending = 0
    if DISPATCH_LOG.exists():
        try:
            state = json.loads(DISPATCH_LOG.read_text())
            if state.get("dispatches"):
                last = state["dispatches"][-1]
                stale_dispatch = bool(last.get("pending"))
                last_pending = len(last.get("pending", []))
        except (json.JSONDecodeError, IndexError, KeyError):
            pass
    checks.append(check("No stale dispatch", not stale_dispatch,
                        f"Last dispatch has {last_pending} pending agent(s)" if stale_dispatch else "Clear"))

    # 5. Doctor passes on this machine
    try:
        r = subprocess.run(
            [sys.executable, str(CORTEX_REPO / "ops" / "scripts" / "manage" / "cortex-doctor.py"), "--json"],
            capture_output=True, text=True, timeout=30
        )
        if r.returncode == 0 and r.stdout.strip():
            # Find JSON in output
            lines = r.stdout.strip()
            start = lines.index("{")
            doctor = json.loads(lines[start:])
            doctor_healthy = doctor.get("healthy", False)
            checks.append(check("Doctor healthy", doctor_healthy, 
                                f"{doctor['summary']['pass']} pass / {doctor['summary']['warn']} warn / {doctor['summary']['fail']} fail"))
        else:
            checks.append(check("Doctor healthy", False, "Doctor failed to run"))
    except Exception as e:
        checks.append(check("Doctor healthy", False, str(e)))

    # 6. Agent inbox queues exist  
    queues_ok = False
    try:
        r = subprocess.run(
            ["docker", "exec", "gbrain-postgres", "psql", "-U", "gbrain", "-d", "gbrain",
             "-t", "-A", "-c",
             "SELECT bus.list_queues()"],
            capture_output=True, text=True, timeout=15
        )
        if r.returncode == 0 and r.stdout.strip():
            raw = json.loads(r.stdout.strip())
            queues = [q["name"] for q in raw if q.get("name", "").startswith("inbox_") and not q.get("name", "").endswith("_dlq")]
            if queues:
                queues_ok = len(queues) >= (agent_count - 1)
                checks.append(check("Agent inbox queues", queues_ok, f"{len(queues)} queue(s) found: {', '.join(queues[:6])}"))
            else:
                checks.append(check("Agent inbox queues", False, "No inbox queues found"))
        else:
            checks.append(check("Agent inbox queues", False, "Could not list queues"))
    except Exception as e:
        checks.append(check("Agent inbox queues", False, str(e)))

    # Aggregate
    passed = sum(1 for c in checks if c["pass"])
    failed = sum(1 for c in checks if not c["pass"])
    all_ok = passed > 0 and failed == 0

    if args.json:
        print(json.dumps({
            "ready": all_ok,
            "checks": checks,
            "summary": {"pass": passed, "fail": failed},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, indent=2))
    else:
        print(f"\nFleet Readiness Check\n")
        for c in checks:
            icon = "✅" if c["pass"] else "❌"
            detail = f" — {c['detail']}" if c["detail"] else ""
            print(f"  {icon} {c['name']}{detail}")
        print(f"\n  {'✅ READY' if all_ok else '❌ ISSUES FOUND'} — {passed} pass, {failed} fail\n")

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
