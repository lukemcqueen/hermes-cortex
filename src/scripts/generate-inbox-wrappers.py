#!/usr/bin/env python3
"""generate-inbox-wrappers.py — Generate per-agent inbox watch wrappers from registry.

Reads ~/.hermes/state/agent-registry.json and creates wrapper scripts
for each agent that has inbox_user and inbox_watch_schedule set.

Usage:
    python3 generate-inbox-wrappers.py              # generate all wrappers
    python3 generate-inbox-wrappers.py --apply-crons  # generate + create cron jobs
    python3 generate-inbox-wrappers.py --dry-run      # show what would be created

Registry format:
{
  "agents": {
    "titus": {
      "name": "Titus",
      "inbox_user": "titus",
      "inbox_watch_schedule": "every 10m",
      "inbox_deliver": "local"
    },
    ...
  }
}

Each wrapper sets CONFIG and execs agent-inbox-watch.sh.
Each cron job runs the wrapper on schedule.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
SCRIPTS_DIR = HOME / ".hermes" / "scripts"
REGISTRY_PATH = HOME / ".hermes" / "state" / "agent-registry.json"
WATCH_SCRIPT = SCRIPTS_DIR / "agent-inbox-watch.sh"
STATE_DIR = HOME / ".hermes" / "state"


def get_registry():
    """Read the agent registry."""
    if not REGISTRY_PATH.exists():
        print(f"Registry not found: {REGISTRY_PATH}", file=sys.stderr)
        return None
    with open(REGISTRY_PATH) as f:
        return json.load(f)


def generate_wrapper(agent_name, agent_data, dry_run=False):
    """Generate a wrapper script for one agent."""
    user = agent_data.get("inbox_user")
    if not user:
        return None

    wrapper_path = SCRIPTS_DIR / f"agent-inbox-{agent_name}.sh"
    wrapper_content = f"""#!/bin/bash
# Auto-generated from agent-registry.json
CONFIG="${{HOME}}/.hermes/agent-inbox-{agent_name}.conf" exec "${{HOME}}/.hermes/scripts/agent-inbox-watch.sh"
"""
    if dry_run:
        print(f"[DRY RUN] Would create: {wrapper_path}")
        return str(wrapper_path)

    wrapper_path.write_text(wrapper_content)
    wrapper_path.chmod(0o755)
    return str(wrapper_path)


def create_cron(agent_name, agent_data, dry_run=False):
    """Create a cron job for one agent's inbox watch."""
    schedule = agent_data.get("inbox_watch_schedule")
    deliver = agent_data.get("inbox_deliver")
    if not schedule or not deliver:
        return None

    wrapper_script = f"agent-inbox-{agent_name}.sh"

    if dry_run:
        print(f"[DRY RUN] Would create cron: inbox-{agent_name}")
        print(f"  schedule: {schedule}")
        print(f"  script: {wrapper_script}")
        print(f"  deliver: {deliver}")
        return

    # Check if cron already exists
    result = subprocess.run(
        ["hermes", "cron", "list", "--json"],
        capture_output=True, text=True, timeout=30,
    )
    existing = set()
    if result.returncode == 0:
        try:
            data = json.loads(result.stdout)
            jobs = data if isinstance(data, list) else data.get("jobs", [])
            existing = {j.get("name", "") for j in jobs}
        except (json.JSONDecodeError, KeyError):
            pass

    cron_name = f"inbox-{agent_name}"
    if cron_name in existing:
        print(f"  → Cron '{cron_name}' already exists, skipping")
        return

    # Create the cron
    script_path = SCRIPTS_DIR / wrapper_script
    if not script_path.exists():
        print(f"  → Wrapper '{wrapper_script}' not found, generate first", file=sys.stderr)
        return

    result = subprocess.run(
        ["hermes", "cron", "create",
         "--name", cron_name,
         "--script", wrapper_script,
         "--no-agent",
         "--schedule", schedule,
         "--deliver", deliver],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode == 0:
        print(f"  ✓ Created cron: {cron_name} ({schedule})")
    else:
        print(f"  ✗ Failed to create cron {cron_name}: {result.stderr.strip()}", file=sys.stderr)


def main():
    dry_run = "--dry-run" in sys.argv
    apply_crons = "--apply-crons" in sys.argv

    registry = get_registry()
    if not registry:
        sys.exit(1)

    agents = registry.get("agents", {})
    if not agents:
        print("No agents in registry", file=sys.stderr)
        sys.exit(1)

    print(f"Agent registry: {len(agents)} agent(s)")
    print()

    # Generate wrappers
    wrappers_created = 0
    for agent_name, agent_data in agents.items():
        if not agent_data.get("inbox_user"):
            continue
        if agent_data.get("inbox_watch_schedule") is None:
            continue
        # Skip moses — handled by orch-check-agent-messages.sh
        if agent_name == "moses":
            continue
        path = generate_wrapper(agent_name, agent_data, dry_run=dry_run)
        if path:
            wrappers_created += 1
            print(f"  ✓ Wrapper: {Path(path).name}")
        elif dry_run:
            pass

    print()
    print(f"Wrappers: {wrappers_created} created/verified")

    if apply_crons:
        print()
        print("Creating cron jobs...")
        for agent_name, agent_data in agents.items():
            if agent_name == "moses":
                continue
            create_cron(agent_name, agent_data, dry_run=dry_run)

    print()
    print("Done. To add a new agent:")
    print("  1. Add entry to ~/.hermes/state/agent-registry.json")
    print("  2. Create htpasswd entry: htpasswd /usr/local/etc/nginx/.htpasswd <user>")
    print("  3. Create config: ~/.hermes/agent-inbox-<agent>.conf")
    print("  4. Run: python3 generate-inbox-wrappers.py --apply-crons")


if __name__ == "__main__":
    main()
