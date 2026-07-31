#!/usr/bin/env python3
"""
orch-bus-fleet-rollback.py — Moses-side fleet rollback orchestrator.

Reads the last dispatch state from fleet-update-state.json and sends
ROLLBACK_REQUEST to agents that failed or didn't respond.

Usage:
    python3 orch-bus-fleet-rollback.py                          # dry-run
    python3 orch-bus-fleet-rollback.py --execute                 # send rollback requests
    python3 orch-bus-fleet-rollback.py --execute --all           # rollback ALL agents
    python3 orch-bus-fleet-rollback.py --dispatch <id>           # rollback specific dispatch
    python3 orch-bus-fleet-rollback.py --json                    # machine-readable output

Exit codes:
    0 = rollback complete or nothing to rollback
    1 = some rollbacks failed
    2 = no dispatch state found
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))    # deployed: lib/ is sibling
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo: lib/ in parent

import json
import os
import time
import uuid
from datetime import datetime, timezone

HOME = Path.home()
HERMES_STATE = HOME / ".hermes-cortex" / "state"
DISPATCH_LOG = HERMES_STATE / "fleet-update-state.json"
CORTEX_REPO = HOME / "hermes-cortex"


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def load_dispatch_state() -> dict:
    if not DISPATCH_LOG.exists():
        print(json.dumps({"error": "No dispatch state found"}))
        sys.exit(2)
    return json.loads(DISPATCH_LOG.read_text())


def send_rollback_request(agent: str, target_sha: str, reason: str, dispatch_id: str) -> bool:
    """Send ROLLBACK_REQUEST to an agent's inbox."""
    correlation_id = f"rollback-{dispatch_id[:8]}-{agent}"
    body = {
        "from": "moses",
        "to": agent,
        "topic": "fleet-update",
        "subject": "ROLLBACK_REQUEST",
        "correlation_id": correlation_id,
        "priority": "high",
        "body": {
            "target_sha": target_sha,
            "reason": reason,
            "dispatch_id": dispatch_id,
            "run_doctor": True,
            "deadline_minutes": 10,
        },
    }
    try:
        from lib.cortex_bus import bus_send
        result = bus_send(f"inbox_{agent}", body)
        ok = result is not None
        if ok:
            log(f"  ✅ Sent ROLLBACK_REQUEST to {agent} → {target_sha[:8]}")
        else:
            log(f"  ❌ Failed to send to {agent}: bus_send returned None")
        return ok
    except Exception as e:
        log(f"  ❌ Error sending to {agent}: {e}")
        return False


def read_inbox(vt: int = 30) -> dict | None:
    try:
        from lib.cortex_bus import bus_read
        return bus_read("inbox_moses", vt)
    except Exception:
        print("expected — silently handled", file=sys.stderr)
    return None


def get_previous_good_sha(dispatch_list: list, current_sha: str) -> str:
    """Find the SHA before the failed dispatch for rollback target."""
    for i, d in enumerate(dispatch_list):
        if d.get("sha") == current_sha and i > 0:
            return dispatch_list[i - 1]["sha"]
        if d.get("sha") == current_sha:
            # This was the first dispatch, nothing to revert to
            return "HEAD~1"
    return "HEAD~1"


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Fleet rollback orchestrator")
    parser.add_argument("--execute", action="store_true", help="Actually send rollback requests")
    parser.add_argument("--all", action="store_true", help="Rollback all agents (not just failed)")
    parser.add_argument("--dispatch", type=str, help="Specific dispatch ID to rollback")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    parser.add_argument("--timeout", type=int, default=120, help="Max seconds to wait for responses")
    args = parser.parse_args()

    state = load_dispatch_state()
    dispatches = state.get("dispatches", [])
    if not dispatches:
        log("No dispatch records found.")
        sys.exit(0 if args.json else 2)

    # Find the target dispatch
    if args.dispatch:
        target = None
        for d in dispatches:
            if d.get("dispatch_id", "").startswith(args.dispatch):
                target = d
                break
        if not target:
            log(f"Dispatch '{args.dispatch}' not found.")
            sys.exit(2)
    else:
        target = dispatches[-1]  # latest

    dispatch_id = target.get("dispatch_id", "unknown")
    current_sha = target.get("sha", "unknown")
    responses = target.get("responses", {})
    pending = target.get("pending", [])
    healthy = target.get("healthy", 0)
    unhealthy = target.get("unhealthy", 0)
    unreachable = target.get("unreachable", 0)

    # Determine rollback SHA
    rollback_sha = get_previous_good_sha(dispatches, current_sha)

    if not args.json:
        log(f"Fleet rollback — dispatch {dispatch_id} ({current_sha})")
        log(f"  Rollback target SHA: {rollback_sha}")
        log(f"  Mode: {'EXECUTE' if args.execute else 'DRY-RUN'}")

    agents_to_rollback = []
    for agent_key, resp in responses.items():
        if args.all or not resp.get("success", True):
            agents_to_rollback.append(agent_key)
    # Also rollback pending/unreachable agents
    agents_to_rollback.extend(pending)

    if not agents_to_rollback:
        if not args.json:
            log("  ✅ No agents need rollback.")
        sys.exit(0)

    if not args.json:
        log(f"  {len(agents_to_rollback)} agent(s) to rollback: {', '.join(agents_to_rollback)}")

    # Send requests
    results = []
    for agent in agents_to_rollback:
        reason = f"Update to {current_sha} had issues"
        if args.all:
            reason = f"Manual rollback from {current_sha}"

        if args.execute:
            ok = send_rollback_request(agent, rollback_sha, reason, dispatch_id)
        else:
            ok = True

        results.append({"agent": agent, "dispatched": ok})

    # Wait for responses
    rollback_results = {}
    if args.execute and results:
        deadline = time.time() + min(args.timeout, 300)
        pending_agents = {r["agent"]: r for r in results if r["dispatched"]}

        if not args.json:
            log(f"  Waiting for {len(pending_agents)} agent(s) to confirm rollback…")

        while pending_agents and time.time() < deadline:
            msg = read_inbox(vt=30)
            if msg:
                body = msg.get("body", {})
                agent = body.get("from", "")
                subj = body.get("subject", "")
                payload = body.get("body", {})

                if agent in pending_agents and subj == "ROLLBACK_RESULT":
                    rollback_results[agent] = payload
                    ok = payload.get("success", False)
                    sha = payload.get("sha_after", "?")
                    if not args.json:
                        log(f"  {'✅' if ok else '❌'} {agent}: reverted to {sha[:8]}")
                    del pending_agents[agent]
            else:
                time.sleep(2)

    if args.json:
        print(json.dumps({
            "action": "rollback",
            "dispatch_id": dispatch_id,
            "current_sha": current_sha,
            "rollback_sha": rollback_sha,
            "agents_targeted": agents_to_rollback,
            "results": rollback_results,
            "pending": list(pending_agents.keys()) if 'pending_agents' in dir() else [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, indent=2))
    else:
        if rollback_results:
            failed = [k for k, v in rollback_results.items() if not v.get("success")]
            if failed:
                log(f"\n  ⚠️  {len(failed)} rollback(s) failed: {', '.join(failed)}")
            else:
                log(f"\n  ✅ All rollbacks confirmed.")
        log(f"\n  Run with --execute to actually send rollback requests.")

    sys.exit(0 if rollback_results else 1)


if __name__ == "__main__":
    main()
