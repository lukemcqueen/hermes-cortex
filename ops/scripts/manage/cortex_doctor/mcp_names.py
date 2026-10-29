"""Doctor check: loop-gov-mcp.py is registered as EXACTLY the two role-distinct servers.

Slice B (Moses plan, pro review 13983/13990): the single binary runs under TWO named
registrations distinguished by `--role` in their args — `loop-governance` (lock lifecycle
+ scoring + task state) and `review` (re-review + feedback + cycle-read, no lock authority).
This replaces the old one-name rule (2026-10-28: "keep the name review") because the
mcp__loop_governance__* vs mcp__review__* prefix confusion came from docs/agents calling the
lifecycle tools by the loop-governance name while the server was only registered as review.
Both names are now real, role-distinct, and the doctor enforces BOTH present and correctly
role-matched.

Exactly these two may run the probe; a THIRD registration of the probe would create a
second view of the lock store (begin_change/end_change/check_lock/reclaim_dead_locks are
single-lock-authority tools) and is a FAIL.
"""

import os
import re
from pathlib import Path

# Two role-distinct registrations of the single loop-gov binary (Slice B, pro review
# 13983/13990). `review` = the 7 no-lock-authority tools; `loop-governance` = the
# complement (lock lifecycle + scoring + task state). Each registration carries the
# matching `--role` in its args — the doctor's role of record. Exactly these two
# may run the probe; a third process would double the lock-store views.
ROLE_NAMES = {"loop-governance": "loop-governance", "review": "review"}
PROBE_BINARY = "loop-gov-mcp.py"
DEFAULT_CONFIG = Path(os.path.expanduser("~/.hermes/config.yaml"))


def _registered_role(joined_args: str) -> str:
    """Pull `--role <x>` out of a joined-args string; empty if absent."""
    parts = joined_args.split()
    for i, tok in enumerate(parts):
        if tok == "--role" and i + 1 < len(parts):
            return parts[i + 1]
    return ""

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


def check_mcp_role_names(res) -> None:
    """Exactly the two role-distinct loop-gov registrations, role-matched.

    loop-governance (--role loop-governance: lifecycle/scoring/task) and review
    (--role review: re-review/feedback/cycle-read) — both running the probe, each
    with the matching --role in its args, and no third registration of the probe
    (a third process would create a second view of the lock store)."""
    registered = _registrations()
    role_by_name = {n: _registered_role(args) for n, args in registered.items()
                    if PROBE_BINARY in args}
    if not role_by_name:
        res.add(
            "MCP loop-gov role servers",
            "FAIL",
            f"no MCP server runs {PROBE_BINARY} — governance is unreachable",
            fix="hermes mcp add loop-governance --command $(command -v python3) --args "
                f"$HOME/.hermes-cortex/tools/loop-governance/{PROBE_BINARY} --role loop-governance "
                "&& hermes mcp add review --command $(command -v python3) --args "
                f"$HOME/.hermes-cortex/tools/loop-governance/{PROBE_BINARY} --role review")
        return
    bad = []
    for n in sorted(role_by_name):
        if n not in ROLE_NAMES:
            bad.append(f"{n} (unexpected third registration runs the probe)")
    for name, want in ROLE_NAMES.items():
        if name not in role_by_name:
            bad.append(f"{name} missing")
            continue
        got = role_by_name[name]
        if got != want:
            bad.append(f"{name} has --role '{got or '(none)'}', expected '{want}'")
    if not bad:
        res.add("MCP loop-gov role servers", "PASS",
                "loop-gov MCP = exactly loop-governance(--role loop-governance) + "
                "review(--role review)")
        return
    res.add(
        "MCP loop-gov role servers",
        "FAIL",
        "; ".join(bad),
        fix="ensure loop-gov-mcp.py is registered under BOTH loop-governance and review "
            "with the matching --role (see docs/loop-governance-reference.md)",
    )
