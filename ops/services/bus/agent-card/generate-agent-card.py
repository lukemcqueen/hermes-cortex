#!/usr/bin/env python3
"""generate-agent-card.py — Generate A2A agent card JSON.

Usage:
  generate-agent-card.py --output <path>

Environment variables:
  AGENT_NAME             — Agent name (default: "agent")
  CORTEX_AGENT_NAME      — Fallback for AGENT_NAME
  CORTEX_DOMAIN          — Domain for the A2A endpoint (default: "localhost")
  CORTEX_A2A_PORT        — Port for the A2A endpoint (default: "14004")
  AGENT_DESCRIPTION      — Agent description (optional, auto-generated if blank)
"""
import argparse
import json
import os
import sys
from pathlib import Path


def get_env(name: str, fallback: str, *alternatives: str) -> str:
    """Read env var, trying alternatives in order."""
    for key in (name, *alternatives):
        val = os.environ.get(key)
        if val:
            return val
    return fallback


def generate_card() -> dict:
    """Build the A2A agent card from environment and known defaults."""
    agent_name = get_env("AGENT_NAME", "agent", "CORTEX_AGENT_NAME")
    domain = os.environ.get("CORTEX_DOMAIN", "localhost")
    port = os.environ.get("CORTEX_A2A_PORT", "14004")

    # Build a description based on the agent name
    description = os.environ.get(
        "AGENT_DESCRIPTION",
        f"{agent_name.title()} agent — part of the Hermes Cortex multi-agent fleet."
    )

    return {
        "name": agent_name,
        "description": description,
        "url": f"https://{domain}:{port}/bus/agent-card",
        "provider": {
            "name": "Hermes Cortex",
            "version": "1.0",
        },
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "stateTransitionHistory": True,
        },
        "skills": [
            {
                "id": "bus.agent-card",
                "name": "Agent Card",
                "description": "Serve agent card via bus for agent discovery",
            },
            {
                "id": "bus.task-delegation",
                "name": "Task Delegation",
                "description": "Submit and track tasks via bus protocol",
            },
            {
                "id": "system.health",
                "name": "System Health",
                "description": "Check server health, disk, memory, services, and Ollama status",
            },
            {
                "id": "inbox.messaging",
                "name": "Inbox Messaging",
                "description": "Send and receive inter-agent messages with topic channels and priority",
            },
            {
                "id": "loop.governance",
                "name": "Loop Governance",
                "description": "Score-cycle, feedback, and audit trail for all code changes",
            },
            {
                "id": "knowledge.gbrain",
                "name": "gbrain Knowledge",
                "description": "Persistent knowledge brain with auto-sync, dream cycles, and search",
            },
        ],
        "authentication": {
            "type": "mTLS",
            "verify": "required",
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Generate A2A Agent Card")
    parser.add_argument("--output", required=True, help="Output JSON file path")
    args = parser.parse_args()

    output_path = Path(args.output)
    card = generate_card()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(card, indent=2) + "\n")
    print(f"✅ Agent card written to {output_path}")


if __name__ == "__main__":
    main()
