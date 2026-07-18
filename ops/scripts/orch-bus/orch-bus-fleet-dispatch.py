#!/usr/bin/env python3
"""
fleet-update-dispatch.py — Moses-side fleet update orchestrator.

Sends UPDATE_REQUEST to fleet agents, collects results via inbox,
evaluates outcomes, sends FIX_REQUEST for issues, and outputs
a fleet-wide summary.

Usage:
    python3 fleet-update-dispatch.py                    # dry-run (show what would happen)
    python3 fleet-update-dispatch.py --execute           # actually send bus messages
    python3 fleet-update-dispatch.py --execute --fix     # auto-fix issues (send FIX_REQUEST)
    python3 fleet-update-dispatch.py --json              # machine-readable output

Architecture:
    Moses → UPDATE_REQUEST → Agent inboxes
    Moses ← UPDATE_RESULT  ← Agent responses
    Moses → FIX_REQUEST    → Agent (if issues found)
    Moses ← FIX_RESULT     ← Agent (fix applied)
    Moses → Telegram         Fleet status report

Exit codes:
    0 = all agents healthy
    1 = some agents need attention
    2 = unrecoverable error
"""

import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
HERMES_STATE = HOME / ".hermes-cortex" / "state"
REGISTRY_PATH = HERMES_STATE / "agent-registry.json"
CORTEX_REPO = HOME / "hermes-cortex"
DISPATCH_LOG = HERMES_STATE / "fleet-update-state.json"

# Agents that only push — cannot receive bus work items
PUSH_ONLY_AGENTS = {"titus"}


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def load_registry() -> dict:
    """Load agent registry."""
    if not REGISTRY_PATH.exists():
        print(json.dumps({"error": f"Registry not found at {REGISTRY_PATH}"}))
        sys.exit(2)
    return json.loads(REGISTRY_PATH.read_text())


def get_current_sha() -> str:
    """Get current git SHA of this repo."""
    try:
        r = subprocess.run(
            ["git", "-C", str(CORTEX_REPO), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=10
        )
        return r.stdout.strip()
    except Exception:
        return "unknown"


def get_agents_for_update(registry: dict) -> list[dict]:
    """Filter agents that can receive updates via bus."""
    agents = []
    for key, val in registry.get("agents", {}).items():
        caps = val.get("capabilities", {})
        bus_mode = caps.get("bus_mode", "poll")
        if key in PUSH_ONLY_AGENTS:
            continue  # handled separately
        if not caps.get("has_git", False):
            log(f"  ⚠️  {key} has no git — skipping")
            continue
        agents.append({
            "key": key,
            "name": val.get("name", key),
            "inbox_user": val.get("inbox_user", key),
            "bus_mode": bus_mode,
            "capabilities": caps,
            "maintenance_window": caps.get("maintenance_window", "any"),
        })
    return agents


def send_bus_message(queue: str, body: dict, correlation_id: str = "") -> bool:
    """Send a message to PGMQ via bus.send SQL function."""
    if not correlation_id:
        correlation_id = str(uuid.uuid4())

    full_body = {
        "from": "moses",
        **body,
        "correlation_id": correlation_id,
    }
    # Escape single quotes for SQL
    body_json = json.dumps(full_body).replace("'", "''")
    try:
        r = subprocess.run(
            ["docker", "exec", "gbrain-postgres", "psql", "-U", "gbrain", "-d", "gbrain",
             "-t", "-A", "-c",
             f"SELECT bus.send('{queue}', '{body_json}'::jsonb, 0)"],
            capture_output=True, text=True, timeout=15
        )
        if r.returncode == 0 and r.stdout.strip() and "ERROR" not in r.stdout:
            log(f"  ✅ Sent UPDATE_REQUEST to {queue[6:]} (corr={correlation_id[:8]}…)")
            return True
        log(f"  ❌ Send failed to {queue[6:]}: {r.stderr[:200] or r.stdout[:200]}")
        return False
    except subprocess.TimeoutExpired:
        log(f"  ❌ Timeout sending to {queue[6:]}")
        return False
    except Exception as e:
        log(f"  ❌ Error sending to {queue[6:]}: {e}")
        return False


def read_inbox_queue(queue: str, vt: int = 60) -> dict | None:
    """Read one message from a PGMQ queue."""
    try:
        r = subprocess.run(
            ["docker", "exec", "gbrain-postgres", "psql", "-U", "gbrain", "-d", "gbrain",
             "-t", "-A", "-c",
             f"SELECT bus.read('{queue}', {vt})"],
            capture_output=True, text=True, timeout=15
        )
        if r.returncode == 0 and r.stdout.strip():
            try:
                return json.loads(r.stdout.strip())
            except json.JSONDecodeError:
                pass
        return None
    except Exception:
        return None


def read_current_state() -> dict:
    """Read previous dispatch state for idempotency."""
    if DISPATCH_LOG.exists():
        try:
            return json.loads(DISPATCH_LOG.read_text())
        except json.JSONDecodeError:
            pass
    return {"dispatches": [], "agents": {}}


def save_current_state(state: dict):
    """Save dispatch state."""
    DISPATCH_LOG.parent.mkdir(parents=True, exist_ok=True)
    DISPATCH_LOG.write_text(json.dumps(state, indent=2))


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Fleet update orchestrator")
    parser.add_argument("--execute", action="store_true", help="Actually send bus messages")
    parser.add_argument("--fix", action="store_true", help="Auto-fix issues (send FIX_REQUEST)")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    parser.add_argument("--collect", action="store_true", help="Collect pending responses (don't send new requests)")
    parser.add_argument("--timeout", type=int, default=300, help="Max seconds to wait for responses")
    args = parser.parse_args()

    registry = load_registry()
    current_sha = get_current_sha()
    state = read_current_state()
    dispatch_id = str(uuid.uuid4())

    if args.collect:
        # Poll for responses from a previous dispatch
        agents = get_agents_for_update(registry)
        responses = []
        for agent in agents:
            queue = f"inbox_moses"
            msg = read_inbox_queue(queue)
            if msg and msg.get("body", {}).get("subject") == "UPDATE_RESULT":
                responses.append(msg["body"])
                log(f"  Retrieved UPDATE_RESULT from {msg['body'].get('from', '?')}")

        if args.json:
            print(json.dumps({
                "action": "collect",
                "responses": responses,
                "count": len(responses),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }, indent=2))
        else:
            log(f"Collected {len(responses)} response(s)")
            for r in responses:
                agent = r.get("from", "?")
                body = r.get("body", {})
                status = "✅" if body.get("success") else "❌"
                sha = body.get("git_sha_after", "?")
                log(f"  {status} {agent}: {sha}")

        # Exit with appropriate code
        if responses and all(r.get("body", {}).get("success") for r in responses):
            sys.exit(0)
        elif responses:
            sys.exit(1)
        sys.exit(0)

    # ── Agent discovery ──
    agents = get_agents_for_update(registry)
    push_only = [k for k in registry.get("agents", {}) if k in PUSH_ONLY_AGENTS]

    if not args.json:
        log(f"Fleet update dispatch — SHA: {current_sha}")
        log(f"  {len(agents)} agent(s) reachable via bus: {', '.join(a['key'] for a in agents)}")
        if push_only:
            log(f"  {len(push_only)} push-only agent(s) (skipped): {', '.join(push_only)}")
        log(f"  Mode: {'EXECUTE' if args.execute else 'DRY-RUN'}")

    # ── Send UPDATE_REQUEST ──
    results = []
    for agent in agents:
        queue = f"inbox_{agent['inbox_user']}"
        corr_id = f"fleet-update-{dispatch_id[:8]}-{agent['key']}"

        if args.execute:
            success = send_bus_message(queue, {
                "to": agent["key"],
                "topic": "fleet-update",
                "subject": "UPDATE_REQUEST",
                "body": {
                    "target_sha": current_sha,
                    "target_version": "2.0.0",
                    "branch": "main",
                    "mode": "force-all",
                    "run_doctor": True,
                    "deadline_minutes": 10,
                    "summary": f"Update to {current_sha}",
                },
            }, correlation_id=corr_id)
        else:
            success = True  # dry-run
            if not args.json:
                log(f"  [DRY-RUN] Would send UPDATE_REQUEST to {agent['key']} for SHA {current_sha}")

        results.append({"agent": agent["key"], "dispatched": success, "correlation_id": corr_id})

    # ── Wait for responses ──
    if args.execute and results:
        deadline = time.time() + min(args.timeout, 600)
        pending = {r["agent"]: r for r in results if r["dispatched"]}
        responses = {}

        if not args.json:
            log(f"  Waiting for {len(pending)} agent(s) to respond (timeout={args.timeout}s)…")

        while pending and time.time() < deadline:
            msg = read_inbox_queue("inbox_moses", vt=30)
            if msg:
                body = msg.get("body", {})
                agent = body.get("from", "")
                subj = body.get("subject", "")
                body_payload = body.get("body", {})

                if agent in pending and subj == "UPDATE_RESULT":
                    responses[agent] = body_payload
                    success = body_payload.get("success", False)
                    sha = body_payload.get("git_sha_after", "?")
                    if not args.json:
                        icon = "✅" if success else "❌"
                        log(f"  {icon} {agent} responded: SHA={sha} success={success}")
                    del pending[agent]
                elif subj == "UPDATE_RESULT":
                    # Agent not in our dispatch — store anyway
                    responses[agent] = body_payload
                    if not args.json:
                        log(f"  ℹ️  Got unexpected UPDATE_RESULT from {agent}")
            else:
                time.sleep(2)

        if pending and not args.json:
            log(f"  ⚠️  {len(pending)} agent(s) did not respond: {', '.join(pending.keys())}")

        # ── Evaluate results ──
        healthy_count = sum(1 for r in responses.values() if r.get("success"))
        unhealthy_count = sum(1 for r in responses.values() if not r.get("success"))
        unreachable = len(pending)

        if not args.json:
            log(f"\n  Fleet update summary:")
            log(f"    ✅ Healthy:  {healthy_count}")
            log(f"    ❌ Unhealthy: {unhealthy_count}")
            log(f"    ⚠️  No response: {unreachable}")
            log(f"    ⏭️  Push-only:  {len(push_only)}")

        # ── Auto-fix (optional) ──
        if args.fix:
            for agent_key, resp in responses.items():
                if not resp.get("success"):
                    errors = resp.get("errors", [])
                    doctor = resp.get("doctor", {})
                    if not doctor.get("healthy", True):
                        issue = f"Doctor has {doctor.get('warn', 0)} warning(s) on {agent_key}"
                        if not args.json:
                            log(f"  🔧 Would send FIX_REQUEST to {agent_key}: {issue}")
                        # TODO: implement FIX_REQUEST send in future iteration

        # ── Save state ──
        state["dispatches"].append({
            "dispatch_id": dispatch_id,
            "sha": current_sha,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agents_dispatched": len(results),
            "responses": responses,
            "pending": list(pending.keys()),
            "healthy": healthy_count,
            "unhealthy": unhealthy_count,
            "unreachable": unreachable,
            "push_only": push_only,
        })
        # Keep only last 5 dispatches
        state["dispatches"] = state["dispatches"][-5:]
        save_current_state(state)

        if args.json:
            print(json.dumps({
                "action": "dispatch",
                "dispatch_id": dispatch_id,
                "sha": current_sha,
                "agents_dispatched": len(results),
                "responses": responses,
                "pending": list(pending.keys()),
                "healthy": healthy_count,
                "unhealthy": unhealthy_count,
                "unreachable": unreachable,
                "push_only": push_only,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }, indent=2))
        else:
            log(f"\n  State saved to {DISPATCH_LOG}")

        # Exit code
        if unhealthy_count > 0 or unreachable > 0:
            sys.exit(1)

    elif not args.execute and not args.json:
        log(f"\n  Run with --execute to actually send bus messages.")
        log(f"  Run with --collect to gather pending responses.")
    elif args.json and not args.execute:
        print(json.dumps({
            "action": "dry_run",
            "sha": current_sha,
            "reachable": [a["key"] for a in agents],
            "push_only": push_only,
            "agent_count": len(agents),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, indent=2))


if __name__ == "__main__":
    main()
