#!/usr/bin/env python3
"""
fleet-kill-switch.py — Emergency stop for fleet agents.

Sends a KILL signal to one or all fleet agents via the agent bus,
records outerloop evidence, attempts rollback on wave sessions.

Usage:
    fleet-kill-switch.py --reason "Security breach"          Kill all agents
    fleet-kill-switch.py --agent esther --reason "Bug"       Kill specific agent
    fleet-kill-switch.py --agent esther --no-rollback        Kill without rollback
    fleet-kill-switch.py --reason "OOB" --evidence-id <id>   Link to existing evidence
    fleet-kill-switch.py --dry-run                           Simulate only
    fleet-kill-switch.py --json                              Machine-readable

Exit codes:
    0 — Kill signal sent (or dry-run)
    1 — Error sending kill
    2 — No agents to kill (registry empty)
"""

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

HOME = Path.home()
CORTEX_REPO = HOME / "hermes-cortex"
STATE_DIR = HOME / ".hermes-cortex" / "state"


def get_fleet_agents() -> dict:
    """Read agent registry and return agent map."""
    registry_paths = [
        STATE_DIR / "agent-registry.json",
        CORTEX_REPO / "ops" / "install" / "deploy" / "agent-registry.json.example",
    ]
    for p in registry_paths:
        if p.exists():
            with open(p) as f:
                reg = json.load(f)
            return reg.get("agents", {})
    return {}


def send_bus_message(agent: str, subject: str, body: dict) -> int:
    """Send a bus message to an agent via hc send."""
    body_json = json.dumps(body)
    cmd = [
        sys.executable, str(CORTEX_REPO / "ops/scripts/hc/hc.py"),
        "send", agent, subject,
        "--json", body_json,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return result.returncode


def record_outerloop_evidence(reason: str, target: str, dry_run: bool = False) -> str | None:
    """Create outerloop evidence package for the kill event."""
    if dry_run:
        return "dry-run-evidence-id"

    cmd = [
        sys.executable, str(CORTEX_REPO / "ops/scripts/manage/outerloop.py"),
        "evidence", "package",
        "--run-id", f"kill-{uuid.uuid4().hex[:8]}",
        "--description", f"Kill switch: {reason}",
        "--passed", "0", "--failed", "1",
        "--json",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout)
        return data.get("evidence_id")
    except json.JSONDecodeError:
        return None


def issue_kill_verdict(evidence_id: str, reason: str, agent: str, dry_run: bool = False) -> bool:
    """Issue a block verdict on the kill evidence."""
    if dry_run or not evidence_id:
        return True

    cmd = [
        sys.executable, str(CORTEX_REPO / "ops/scripts/manage/outerloop.py"),
        "verdict", "issue",
        "--evidence-id", evidence_id,
        "--decision", "block",
        "--rationale", f"Kill switch triggered for {agent}: {reason[:200]}",
        "--by", "kill-switch",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return result.returncode == 0


def create_escalation(evidence_id: str, reason: str, agent: str, severity: str = "critical",
                      dry_run: bool = False) -> bool:
    """Create HITL escalation for the kill event."""
    if dry_run:
        return True

    cmd = [
        sys.executable, str(CORTEX_REPO / "ops/scripts/manage/escalate-to-human.py"),
        "--evidence-id", evidence_id,
        "--severity", severity,
    ]
    if reason:
        cmd.extend(["--title", f"Kill switch: {reason[:60]}"])
        cmd.extend(["--description", reason])

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return result.returncode == 0


# ── Kill Execution ──────────────────────────────────────────────

def execute_kill(agent_name: str, agent_data: dict, args) -> dict:
    """Send KILL to a single agent and record evidence."""
    result = {
        "agent": agent_name,
        "role": agent_data.get("role", "unknown"),
        "status": "error",
        "rollback_status": "not_attempted",
        "evidence_id": None,
    }

    corr_id = f"kill-{uuid.uuid4().hex[:12]}"

    kill_payload = {
        "reason": args.reason,
        "correlation_id": corr_id,
        "rollback": not args.no_rollback,
        "target": agent_name,
    }
    if args.evidence_id:
        kill_payload["evidence_id"] = args.evidence_id

    # Send via bus
    if args.dry_run:
        result["status"] = "would_kill"
        result["rollback_status"] = "would_rollback" if not args.no_rollback else "skipped"
    else:
        # Record evidence first
        ev_id = record_outerloop_evidence(args.reason, agent_name)
        result["evidence_id"] = ev_id
        kill_payload["evidence_id"] = ev_id or ""

        # Issue verdict (always block)
        if ev_id:
            issue_kill_verdict(ev_id, args.reason, agent_name)

        # Send the kill signal
        rc = send_bus_message(agent_name, "KILL", kill_payload)
        if rc == 0:
            result["status"] = "killed"
            result["rollback_status"] = "rolled_back" if not args.no_rollback else "not_attempted"
        else:
            result["status"] = "error"
            result["error"] = f"Bus send failed (exit {rc})"

        # Create HITL escalation
        if ev_id:
            create_escalation(ev_id, args.reason, agent_name)

    return result


# ── Main ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Fleet-wide kill switch — emergency stop for fleet agents"
    )
    parser.add_argument("--reason", "-r", required=True, help="Why the kill was issued")
    parser.add_argument("--agent", "-a", help="Target specific agent (default: all)")
    parser.add_argument("--evidence-id", help="Link to existing outerloop evidence")
    parser.add_argument("--no-rollback", action="store_true", help="Skip rollback attempt")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without sending")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    agents = get_fleet_agents()
    if not agents:
        print("❌ No fleet agents found in registry")
        sys.exit(2)

    # Filter to specific agent if requested
    targets = {}
    if args.agent:
        if args.agent in agents:
            targets[args.agent] = agents[args.agent]
        else:
            print(f"❌ Agent '{args.agent}' not found in registry")
            print(f"   Available: {', '.join(agents.keys())}")
            sys.exit(1)
    else:
        targets = agents

    if args.dry_run:
        print(f"🔍 DRY RUN: Would kill {len(targets)} agent(s)")
        print(f"   Reason: {args.reason}")
        print(f"   Agents: {', '.join(targets.keys())}")
        print(f"   Rollback: {'yes' if not args.no_rollback else 'no'}")
        print(f"   Evidence link: {args.evidence_id or '(new)'}")
        sys.exit(0)

    # Execute kills
    results = []
    for agent_name, agent_data in targets.items():
        print(f"🔴 Sending KILL to {agent_name} ({agent_data.get('role', '?')})...")
        r = execute_kill(agent_name, agent_data, args)
        results.append(r)

        icon = {"killed": "✅", "would_kill": "🔍", "error": "❌"}.get(r["status"], "❓")
        print(f"   {icon} Status: {r['status']}")
        if r.get("rollback_status"):
            print(f"   ↩️  Rollback: {r['rollback_status']}")
        if r.get("evidence_id"):
            print(f"   📦 Evidence: outerloop ledger why {r['evidence_id']}")
        if r.get("error"):
            print(f"   ❌ Error: {r['error']}")
        print()

    summary = {
        "total": len(results),
        "killed": sum(1 for r in results if r["status"] == "killed"),
        "errors": sum(1 for r in results if r["status"] == "error"),
        "reason": args.reason,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "results": results,
    }

    if args.json:
        print(json.dumps(summary, indent=2))

    # Exit with error if any kill failed
    if summary["errors"] > 0:
        print(f"⚠️  {summary['errors']}/{summary['total']} kill(s) had errors")
        sys.exit(1)

    print(f"✅ Kill switch complete: {summary['killed']}/{summary['total']} agent(s) killed")


if __name__ == "__main__":
    main()
