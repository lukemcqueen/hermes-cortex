"""
Governance Enforcer Plugin — Hard blocks write tools unless governance lock exists.

Uses the Hermes Plugin System's ``pre_tool_call`` hook to intercept tools
before they execute. If a write-class tool (write_file, patch, terminal with
modifying commands, cronjob, skill_manage) is called without an active
governance lock at ``~/.hermes-cortex/state/.governance-<repo>.json``,
the tool is blocked with a clear message.

Lock files are scoped per git repo: the slug is derived from
``git rev-parse --show-toplevel``. This means working in repo A and repo B
on the same machine each has its own independent governance lock.
Outside a git repo, the generic fallback ``.governance-generic.json`` is used.

This is the structural enforcement layer that I, as an agent, cannot bypass
or talk my way out of — the block comes from outside myself.

Harness v3 integration: the PolicyEngine (core/governance/policy_engine.py)
evaluates tool calls against ABAC rules ADDITIVELY to the binary lock check.
The engine can only *narrow* permissions (DENY override), never widen.
The lock check remains as a separate fallback gate per §9 step 1 of
harness-v2-requirements.md.

Agent identity (§1.6) is derived locally from hostname since the Hermes
pre_tool_call hook does not pass agent identity from the runtime.

Install: ln -sf ~/hermes-cortex/plugins/hermes-governance-enforcer ~/.hermes/plugins/
"""

import json
import os
import re
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

GOVERNANCE_STATE_DIR = Path.home() / ".hermes-cortex" / "state"

# ── PolicyEngine import (add repo core/ to sys.path) ──────────────────────
_CORTEX_REPO = Path.home() / "hermes-cortex"
_CORE_PATH = _CORTEX_REPO / "core"
if _CORE_PATH.exists() and str(_CORE_PATH) not in sys.path:
    sys.path.insert(0, str(_CORE_PATH))

try:
    from governance.policy_engine import (
        DENY_OVERRIDES,
        PolicyEffect,
        PolicyEngine,
        build_context,
    )
    _ENGINE = PolicyEngine()
    _ENGINE_AVAILABLE = True
except ImportError:
    _ENGINE = None
    _ENGINE_AVAILABLE = False


def _local_agent_identity() -> str:
    """Derive local agent identity from hostname (§1.6).

    Falls back to environment variable, then hostname, then 'unknown'.
    This is the authoritative identity source since the pre_tool_call hook
    does not pass agent identity from the Hermes runtime.
    """
    return os.environ.get("AGENT_NAME") or socket.gethostname().split(".")[0] or "unknown"


def _read_task_fields() -> dict:
    """Read task-derived fields from the governance lock file."""
    lock_path = _governance_lock_path()
    if not lock_path.exists():
        return {}
    try:
        state = json.loads(lock_path.read_text())
        return {
            "task_id": state.get("task_id", ""),
            "task_status": state.get("status", ""),
            "task_allowed_scope": state.get("allowed_scope", []),
        }
    except (json.JSONDecodeError, OSError):
        return {}


# ── Lock path ─────────────────────────────────────────────────────────────

def _governance_lock_path() -> Path:
    """Return a repo-scoped governance lock path.

    Derives a slug from ``git rev-parse --show-toplevel`` so that each
    repo on the same machine gets its own lock file.  Falls back to
    ``.governance-generic.json`` when not inside a git repository.
    """
    try:
        repo_root = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
            timeout=3,
        ).decode().strip()
        slug = Path(repo_root).name  # e.g. "hermes-cortex", "project-b"
    except Exception:
        slug = "generic"
    return GOVERNANCE_STATE_DIR / f".governance-{slug}.json"


# Tools that modify system state — require governance lock
WRITE_TOOLS = {
    "write_file",
    "patch",
}

# Tools that CAN modify system state but also have read-only uses
CONDITIONAL_WRITE_TOOLS = {
    "terminal",
    "cronjob",
    "skill_manage",
}

# Terminal commands that modify state — require governance lock
WRITE_COMMAND_PATTERNS = [
    r"^\s*(sudo\s+)?(rm|mv|cp|install|apt|apt-get|dpkg|pip|npm|brew|make|cmake|docker compose|kubectl)\s",
    r"^\s*(sudo\s+)?(systemctl|service)\s+(start|stop|restart|reload|enable|disable|daemon-reload)\s",
    r"^\s*(sudo\s+)?(chmod|chown|chattr|mkfs|fdisk|mount|umount|dd)\s",
    r"^\s*(sudo\s+)?(sed|awk|tee)\s.*-i\s",
    r"^\s*(sudo\s+)?(git)\s+(push|commit|merge|rebase|reset|cherry-pick|branch\s+-[dD]|tag)",
    r"^\s*(sudo\s+)?(cronjob)\s+(create|update|remove|delete)",
    r"^\s*(sudo\s+)?(uv|python3?)\s.*-(m\s+pip\s+install)",
    r"^\s*(sudo\s+)?wget\s.*-O\s",
    r"^\s*(sudo\s+)?curl\s.*-o\s",
    r"^\s*(sudo\s+)?nohup\s",
    r"^\s*(sudo\s+)?docker\s+(run|build|push|commit|tag|save|load|rmi|system\s+prune)",
    r"^\s*(sudo\s+)?crontab\s",
    r"^\s*(sudo\s+)?usermod|groupmod|useradd|groupadd|passwd",
    r"^\s*(sudo\s+)?ufw\s+(enable|disable|allow|deny|reject|delete|reset)",
    r"^\s*(sudo\s+)?nginx\s+(-s\s+(reload|stop|quit))",
    r"^\s*(sudo\s+)?journalctl\s+--rotate",
    r"^\s*echo\s+.*[>|>>]\s",
]

# Cronjob actions that require governance
WRITE_CRON_ACTIONS = {"create", "update", "remove"}

# Skill management actions that require governance
WRITE_SKILL_ACTIONS = {"create", "edit", "delete", "write_file", "remove_file", "patch"}


def _is_terminal_write(args: Dict[str, Any]) -> bool:
    """Check if a terminal command is a write/modify operation."""
    command = args.get("command", "")
    if not command:
        return False
    for pattern in WRITE_COMMAND_PATTERNS:
        if re.search(pattern, command):
            return True
    return False


def _is_cronjob_write(args: Dict[str, Any]) -> bool:
    action = args.get("action", "")
    return action in WRITE_CRON_ACTIONS


def _is_skill_write(args: Dict[str, Any]) -> bool:
    action = args.get("action", "")
    return action in WRITE_SKILL_ACTIONS


def _has_governance_lock() -> bool:
    """Check if an active governance lock exists for the current repo."""
    lock_path = _governance_lock_path()
    if not lock_path.exists():
        return False
    try:
        state = json.loads(lock_path.read_text())
        task_id = state.get("task_id", "")
        return bool(task_id)
    except (json.JSONDecodeError, OSError):
        return False


def _is_write_tool(tool_name: str, args: Dict[str, Any]) -> bool:
    if tool_name in WRITE_TOOLS:
        return True
    if tool_name == "terminal" and _is_terminal_write(args):
        return True
    if tool_name == "cronjob" and _is_cronjob_write(args):
        return True
    if tool_name == "skill_manage" and _is_skill_write(args):
        return True
    return False


def _build_block_response(tool_name: str, args: Dict[str, Any], message: str) -> Dict[str, str]:
    """Build a standardized block response for the pre_tool_call hook."""
    lock_path = _governance_lock_path()
    if tool_name == "terminal":
        extra = "\n  Command preview: " + str(args.get('command', ''))[:120] + "..."
    elif tool_name == "cronjob":
        extra = "\n  Action: " + str(args.get('action', ''))
    else:
        extra = ""

    return {
        "action": "block",
        "message": (
            f"GOVERNANCE LOCK REQUIRED\n\n"
            f"Tool '{tool_name}' modifies system state{extra}\n\n"
            f"{message}\n\n"
            f"This repo requires an active governance lock at:\n"
            f"  {lock_path}\n\n"
            f"Call begin_change() first:\n"
            f"  mcp_loop_governance_begin_change(\n"
            f"    task_id=\"<short-description>\",\n"
            f"    description=\"<what this does>\"\n"
            f"  )\n\n"
            f"After the change, score and release:\n"
            f"  mcp_loop_governance_cycle_query(task_id=\"<task>\")\n"
            f"  mcp_loop_governance_feedback_accept(cycle_id=N, note=\"verified: ...\")\n"
            f"  mcp_loop_governance_end_change(task_id=\"<task>\")\n\n"
            f"This enforcement comes from ~/.hermes/plugins/governance-enforcer/ (source: ~/hermes-cortex/plugins/hermes-governance-enforcer/).\n"
            f"Lock files are scoped per git repo — two repos can govern independently.\n"
            f"I cannot bypass or disable this mid-session."
        ),
    }


def register(ctx):
    """Register the governance enforcer plugin hooks."""

    # Read command patterns that never need governance
    READ_COMMAND_PATTERNS = [
        r"^\s*(ls|cat|head|tail|less|more|grep|find|which|whoami|id|pwd|date|echo|printf)\s",
        r"^\s*(ps|top|htop|df|du|free|uptime|uname|hostname|dmesg|journalctl)\s",
        r"^\s*(git)\s+(status|log|diff|show|branch|stash\s+list)",
        r"^\s*(docker)\s+(ps|images|logs|inspect|stats)",
        r"^\s*(pip|npm)\s+(list|show|search)",
        r"^\s*(hermes)\s+(--version|doctor|config\s+get|config\s+show|config\s+path|config\s+check|env-path)",
        r"^\s*(systemctl)\s+(is-active|is-enabled|status|list-units)",
    ]

    def pre_tool_call_hook(
        tool_name: str = "",
        args: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Optional[Dict[str, str]]:
        if not tool_name:
            return None

        args = args or {}

        if not _is_write_tool(tool_name, args):
            return None

        # Read-only terminal commands pass through
        if tool_name == "terminal":
            command = args.get("command", "")
            for pattern in READ_COMMAND_PATTERNS:
                if re.search(pattern, command):
                    return None

        # Cronjob read operations pass through
        if tool_name == "cronjob" and args.get("action") in ("list", "run"):
            return None

        # ── Harness v3: PolicyEngine evaluation (ADDITIVE — can only narrow) ──
        if _ENGINE_AVAILABLE:
            task_fields = _read_task_fields()
            # Determine resource path for scope checking
            resource = ""
            if tool_name in ("write_file", "patch"):
                resource = args.get("path", "")
            elif tool_name == "terminal":
                resource = args.get("command", "")[:80]
            elif tool_name == "cronjob":
                resource = f"cron:{args.get('action', '')}:{args.get('name', '')}"
            elif tool_name == "skill_manage":
                resource = f"skill:{args.get('action', '')}:{args.get('name', '')}"

            ctx = build_context(
                tool=tool_name,
                agent=_local_agent_identity(),
                command=args.get("command", ""),
                cron_action=args.get("action", ""),
                skill_action=args.get("action", ""),
                resource=resource,
                has_lock=_has_governance_lock(),
            )
            # Populate task-derived fields
            ctx.task_id = task_fields.get("task_id", "")
            ctx.task_status = task_fields.get("task_status", "")
            ctx.task_allowed_scope = task_fields.get("task_allowed_scope", [])

            result = _ENGINE.evaluate(ctx)
            if result.effect == PolicyEffect.DENY:
                return _build_block_response(
                    tool_name, args,
                    f"Denied by policy: {result.rule}\n"
                    f"  Agent: {ctx.agent}\n"
                    f"  Resource: {ctx.resource}\n"
                    f"  Matched rules: {', '.join(result.matched_rules)}"
                )

            # REQUIRE_APPROVAL result also blocks (for now — future: async approval)
            if result.effect == PolicyEffect.REQUIRE_APPROVAL:
                return _build_block_response(
                    tool_name, args,
                    f"Requires approval: {result.rule}\n"
                    f"  Agent: {ctx.agent}\n"
                    f"  Resource: {ctx.resource}"
                )

        # ── Binary lock check (fallback gate — engine can only narrow) ──
        if _has_governance_lock():
            return None

        # BLOCKED
        lock_path = _governance_lock_path()
        if tool_name == "terminal":
            extra = "\n  Command preview: " + str(args.get('command', ''))[:120] + "..."
        elif tool_name == "cronjob":
            extra = "\n  Action: " + str(args.get('action', ''))
        else:
            extra = ""

        return {
            "action": "block",
            "message": (
                "GOVERNANCE LOCK REQUIRED\n\n"
                "Tool '" + tool_name + "' modifies system state" + extra + "\n\n"
                "This repo requires an active governance lock at:\n"
                "  " + str(lock_path) + "\n\n"
                "Call begin_change() first:\n"
                "  mcp_loop_governance_begin_change(\n"
                "    task_id=\"<short-description>\",\n"
                "    description=\"<what this does>\"\n"
                "  )\n\n"
                "After the change, score and release:\n"
                "  mcp_loop_governance_cycle_query(task_id=\"<task>\")\n"
                "  mcp_loop_governance_feedback_accept(cycle_id=N, note=\"verified: ...\")\n"
                "  mcp_loop_governance_end_change(task_id=\"<task>\")\n\n"
                "This enforcement comes from ~/.hermes/plugins/governance-enforcer/ (source: ~/hermes-cortex/plugins/hermes-governance-enforcer/).\n"
                "Lock files are scoped per git repo — two repos can govern independently.\n"
                "I cannot bypass or disable this mid-session."
            ),
        }

    ctx.register_hook("pre_tool_call", pre_tool_call_hook)
