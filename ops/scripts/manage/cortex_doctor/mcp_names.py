"""Doctor check: the review-gateway MCP server must be registered as exactly `review`.

Luke, 2026-10-28: "keep the name 'review' for mcp instead of anything weird."

There is ONE canonical name for the governance/review gateway (the process running
mcp-servers/loop-gov-mcp.py). A host whose server is registered under any other name
still works - the tools all function - but the agent sees `mcp__<weirdname>__begin_change`
for its whole life, and docs/instructions that say "call mcp__review__*" no longer match
reality. The installed name is therefore enforced like any other crown-jewel invariant.

Only the REGISTRATION NAME is checked: the binary path tools/loop-governance/loop-gov-mcp.py
stays as the deploy path and is used here only to identify which registration IS the
review gateway.
"""

import os
import re
from pathlib import Path

CANONICAL_NAME = "review"
PROBE_BINARY = "loop-gov-mcp.py"
DEFAULT_CONFIG = Path(os.path.expanduser("~/.hermes/config.yaml"))

# "OPEN" checks also read the Pi/Claude mcp.json when present, so the same doctor run
# covers every harness a host may run.
PI_MCP = Path(os.path.expanduser("~/.pi/agent/mcp.json"))
CLAUDE_MCP = [
    Path(os.path.expanduser("~/.claude.json")),
    Path(os.path.expanduser("~/.claude/settings.local.json")),
]


def _parse_yaml_servers(config_path: Path) -> dict:
    """Dependency-free `mcp_servers:` block reader: {name: "joined args"}.

    YAML-lite by design - the agent runtime has shipped without a YAML library before,
    and a doctor check must never be the thing that needs one. Handles exactly the shape
    `hermes mcp add` writes:
        mcp_servers:
          <name>:
            command: ...
            args:
              - <arg>
            enabled: true
    """
    try:
        text = config_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {}
    servers, current, args = {}, None, []
    key_re = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")
    for line in text.splitlines():
        m = key_re.match(line)
        if m:
            if current is not None:
                servers[current] = " ".join(args)
            current, args = m.group(1), []
        elif current is not None and line.startswith("      - "):
            args.append(line[7:].strip())
    if current is not None:
        servers[current] = " ".join(args)
    return servers


def _parse_pi_servers(mcp_json: Path) -> dict:
    """~/.pi/agent/mcp.json: {"mcpServers": {name: {"args": [...]}}} — parsed without yaml."""
    try:
        import json
        doc = json.loads(mcp_json.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {name: " ".join((cfg or {}).get("args") or []) for name, cfg in
            (doc.get("mcpServers") or {}).items()}


def _registrations() -> dict:
    merged = dict(_parse_yaml_servers(DEFAULT_CONFIG))
    if PI_MCP.exists():
        for k, v in _parse_pi_servers(PI_MCP).items():
            merged.setdefault(k, v)
    return merged


def check_mcp_review_name(res) -> None:
    """One name for the review gateway: `review`, registered, and nothing else running the probe."""
    registered = _registrations()
    review_like = sorted(name for name, args in registered.items()
                         if PROBE_BINARY in args)
    if not review_like:
        res.add(
            "MCP review server name",
            "FAIL",
            f"no MCP server runs {PROBE_BINARY} — the review/close gate is unreachable",
            fix=f"hermes mcp add {CANONICAL_NAME} --command $(command -v python3) "
                f"--args $HOME/.hermes-cortex/tools/loop-governance/{PROBE_BINARY}")
        return
    if review_like == [CANONICAL_NAME]:
        res.add("MCP review server name", "PASS",
                f"review-gateway MCP registered as exactly '{CANONICAL_NAME}'")
        return
    res.add(
        "MCP review server name",
        "FAIL",
        f"review-gateway MCP registered as {review_like} — the canonical name is exactly "
        f"'{CANONICAL_NAME}' (Luke 2026-10-28: keep the name review, not anything weird)",
        fix="hermes mcp remove <old-name> && hermes mcp add "
            f"{CANONICAL_NAME} --command $(command -v python3) "
            f"--args $HOME/.hermes-cortex/tools/loop-governance/{PROBE_BINARY}",
    )
