#!/usr/bin/env python3
"""
bus-git-auth-check.py — Verify each agent can pull from the remote.

Sends GIT_AUTH_CHECK to server-agents and collects GIT_AUTH_RESULT.
For dev-agents, auth is verified locally or skipped (reported in UPDATE_RESULT).

Usage:
    python3 bus-git-auth-check.py                    # dry-run
    python3 bus-git-auth-check.py --execute           # send checks
    python3 bus-git-auth-check.py --json              # machine-readable

Exit codes:
    0 = all agents authenticated
    1 = some agents failed auth
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

EXPECTED_REMOTE = "https://github.com/fleet-operator/hermes-cortex.git"


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}")


def load_registry() -> dict:
    if not REGISTRY_PATH.exists():
        print(json.dumps({"error": "Registry not found"}))
        sys.exit(2)
    return json.loads(REGISTRY_PATH.read_text())


def check_local_git_auth() -> dict:
    """Verify local git can pull from origin."""
    checks = []
    try:
        # Check git is installed
        r = subprocess.run(["git", "version"], capture_output=True, text=True, timeout=5)
        checks.append(("Git installed", r.returncode == 0, r.stdout.strip()))
    except FileNotFoundError:
        checks.append(("Git installed", False, "git not found"))
        return {"authenticated": False, "checks": checks}

    try:
        # Check remote URL
        r = subprocess.run(
            ["git", "-C", str(CORTEX_REPO), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5
        )
        remote_url = r.stdout.strip()
        url_match = EXPECTED_REMOTE in remote_url
        checks.append(("Remote URL", url_match, remote_url))
    except Exception as e:
        checks.append(("Remote URL", False, str(e)))
        return {"authenticated": False, "checks": checks}

    try:
        # Verify auth: git ls-remote returns 0 on success
        r = subprocess.run(
            ["git", "-C", str(CORTEX_REPO), "ls-remote", "origin", "HEAD"],
            capture_output=True, text=True, timeout=15
        )
        auth_ok = r.returncode == 0 and r.stdout.strip() != ""
        detail = f"HEAD at {r.stdout.strip()[:12]}..." if auth_ok else r.stderr[:200]
        checks.append(("Git auth (ls-remote)", auth_ok, detail))
    except subprocess.TimeoutExpired:
        checks.append(("Git auth (ls-remote)", False, "Timed out after 15s"))
        return {"authenticated": False, "checks": checks}
    except Exception as e:
        checks.append(("Git auth (ls-remote)", False, str(e)))
        return {"authenticated": False, "checks": checks}

    all_ok = all(c[1] for c in checks)
    return {
        "authenticated": all_ok,
        "remote_url": remote_url if 'remote_url' in dir() else "unknown",
        "checks": [{"name": c[0], "pass": c[1], "detail": c[2]} for c in checks],
    }


def send_git_auth_check(agent: str) -> bool:
    """Send GIT_AUTH_CHECK to an agent."""
    correlation_id = f"git-auth-{uuid.uuid4().hex[:8]}-{agent}"
    body = {
        "from": "moses",
        "to": agent,
        "topic": "fleet-update",
        "subject": "GIT_AUTH_CHECK",
        "correlation_id": correlation_id,
        "priority": "normal",
        "body": {
            "remote": "origin",
            "expected_url": EXPECTED_REMOTE,
        },
    }
    try:
        from lib.cortex_bus import bus_send
        result = bus_send(f"inbox_{agent}", body)
        return result is not None
    except Exception:
        return False


def read_inbox(vt: int = 30) -> dict | None:
    try:
        from lib.cortex_bus import bus_read
        return bus_read("inbox_moses", vt)
    except Exception:
        return None


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Git auth check for fleet agents")
    parser.add_argument("--execute", action="store_true", help="Send auth checks")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    parser.add_argument("--timeout", type=int, default=60, help="Max seconds to wait for responses")
    args = parser.parse_args()

    registry = load_registry()
    agents = registry.get("agents", {})

    # Check local first
    local_auth = check_local_git_auth()

    if not args.json:
        log("Git Auth Check")
        log(f"  Local: {'✅' if local_auth['authenticated'] else '❌'} {local_auth.get('remote_url', '?')}")

    # Server-agents that get a bus message
    server_agents = [k for k, v in agents.items()
                     if v.get("role") == "server-agent" and v.get("capabilities", {}).get("has_git")]
    dev_agents = [k for k, v in agents.items() if v.get("role") == "dev-agent"]
    orchestrators = [k for k, v in agents.items() if v.get("role") == "orchestrator"]

    if not args.json:
        log(f"  Server-agents: {', '.join(server_agents) if server_agents else 'none'}")
        log(f"  Dev-agents (self-check): {', '.join(dev_agents) if dev_agents else 'none'}")
        log(f"  Orchestrators (local): {', '.join(orchestrators) if orchestrators else 'none'}")
        log(f"  Mode: {'EXECUTE' if args.execute else 'DRY-RUN'}")

    results = {}
    if args.execute:
        # Send to each server-agent
        for agent in server_agents:
            ok = send_git_auth_check(agent)
            if ok:
                log(f"  Sent GIT_AUTH_CHECK to {agent}")
            results[agent] = {"sent": ok}

        # Dev-agents: check is done on their side during updates
        for agent in dev_agents:
            results[agent] = {"sent": True, "note": "dev-agent (self-check during update)"}

        # Wait for responses
        deadline = time.time() + min(args.timeout, 120)
        pending = [a for a in server_agents if results.get(a, {}).get("sent")]
        auth_results = {}

        if pending:
            log(f"  Waiting for {len(pending)} agent(s) to respond…")
            while pending and time.time() < deadline:
                msg = read_inbox(vt=30)
                if msg:
                    body = msg.get("body", {})
                    agent = body.get("from", "")
                    subj = body.get("subject", "")
                    payload = body.get("body", {})

                    if agent in pending and subj == "GIT_AUTH_RESULT":
                        auth_results[agent] = payload
                        ok = payload.get("authenticated", False)
                        url = payload.get("remote_url", "?")
                        log(f"  {'✅' if ok else '❌'} {agent}: {url}")
                        del pending[pending.index(agent)]
                else:
                    time.sleep(2)

            for agent in pending:
                auth_results[agent] = {"authenticated": False, "error": "No response"}

    if args.json:
        print(json.dumps({
            "local": local_auth,
            "results": results,
            "auth_responses": auth_results if args.execute else {},
            "server_agents": server_agents,
            "dev_agents": dev_agents,
            "orchestrators": orchestrators,
            "all_authenticated": local_auth["authenticated"] and (
                all(v.get("authenticated", False) for v in (auth_results.values() if args.execute else [{}]))
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, indent=2))
    else:
        log(f"\n  Run with --execute to send auth checks to server-agents.")

    # Exit code
    if not local_auth["authenticated"]:
        sys.exit(1)
    if args.execute:
        failed = [k for k, v in auth_results.items() if not v.get("authenticated", True)]
        if failed:
            log(f"\n  ⚠️  {len(failed)} agent(s) failed auth: {', '.join(failed)}")
            sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
