#!/usr/bin/env python3
"""
generate-agent-card.py — Generate an A2A-compliant Agent Card.

Reads the local static card from ops/services/a2a/agent-card.json (template with
identity/skills) and overlays server-specific info from the environment
(domain, port). Outputs the merged card to stdout or a target path.

no_agent watchdog pattern:
  Always outputs the card to stdout (the cron delivers it for verification).
  Use --output to write to a specific path for nginx serving.

Usage:
  python3 generate-agent-card.py                          # stdout
  python3 generate-agent-card.py --output /path/card.json  # write to file
  CORTEX_DOMAIN=mydomain.com CORTEX_A2A_PORT=13005 \\     # override domains
    python3 generate-agent-card.py

Output:
  A2A Agent Card JSON (A2A v1.0 spec)
"""

import json
import os
import re
import sys
from pathlib import Path


# ── Paths ──
REPO_HOME = Path.home() / "hermes-cortex"
CARD_TEMPLATE = REPO_HOME / "ops" / "services" / "a2a" / "agent-card.json"
CORTEX_HOME = Path(os.environ.get("CORTEX_HOME", str(Path.home() / "hermes-cortex")))
STATE_DIR = Path.home() / ".hermes-cortex" / "state"


def load_template() -> dict:
    """Load the static Agent Card template."""
    if not CARD_TEMPLATE.exists():
        print(f"ERROR: Template not found at {CARD_TEMPLATE}", file=sys.stderr)
        sys.exit(1)
    return json.loads(CARD_TEMPLATE.read_text())


def resolve_url(template: dict) -> str:
    """Resolve the agent's A2A URL from env vars or the template."""
    domain = os.environ.get("CORTEX_DOMAIN", "")
    port = os.environ.get("CORTEX_A2A_PORT", "13004")

    if domain:
        return f"https://{domain}:{port}/a2a"
    return template.get("url", f"https://localhost:{port}/a2a")


def main():
    output_path = None
    if "--output" in sys.argv:
        idx = sys.argv.index("--output")
        if idx + 1 < len(sys.argv):
            output_path = Path(sys.argv[idx + 1])

    template = load_template()
    card = dict(template)  # shallow copy

    # Resolve dynamic fields
    card["url"] = resolve_url(template)

    # Generate output
    output = json.dumps(card, indent=2) + "\n"

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output)
        print(f"Agent Card written to {output_path}", file=sys.stderr)
    else:
        print(output, end="")


if __name__ == "__main__":
    main()
