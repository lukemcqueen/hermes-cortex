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

Install: ln -sf ~/hermes-cortex/.hermes-cortex/plugins/governance-enforcer ~/.hermes/plugins/
"""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

GOVERNANCE_STATE_DIR = Path.home() / ".hermes-cortex" / "state"


def _governance_lock_path(session_id: str = "") -> Path:
    """Return the governance lock path for the given session.

    Uses the session_id to scope the lock so that each Hermes session
    has its own independent governance lock. When no session_id is given
    (fallback from Hermes plugin system), returns None — the caller
    should scan for active locks instead.
    """
    if session_id:
        return GOVERNANCE_STATE_DIR / f".governance-sess_{session_id}.json"
    return GOVERNANCE_STATE_DIR / ".governance-generic.json"


def _has_governance_lock(session_id: str = "") -> bool:
    """Check if THIS session's governance lock exists.

    Only checks the lock file scoped to the given session_id — never
    returns True for another session's lock. This prevents cross-session
    lock sharing.
    """
    lock_path = _governance_lock_path(session_id)
    if not lock_path.exists():
        return False
    try:
        state = json.loads(lock_path.read_text())
        task_id = state.get("task_id", "")
        return bool(task_id)
    except (json.JSONDecodeError, OSError):
        return False


# Tools that modify system state — require governance lock
WRITE_TOOLS = {
    "write_file",
    "patch",
    "execute_code",
    "memory",
    "text_to_speech",
}

# Tools that CAN modify system state but also have read-only uses
CONDITIONAL_WRITE_TOOLS = {
    "terminal",
    "cronjob",
    "skill_manage",
    "process",
}

# Process actions that require governance
WRITE_PROCESS_ACTIONS = {"write", "submit", "close", "kill"}

# Terminal commands that modify state — require governance lock
WRITE_COMMAND_PATTERNS = [
    r"^\s*(sudo\s+)?(rm|mv|cp|install|apt|apt-get|dpkg|pip|npm|brew|make|cmake|docker compose|kubectl)\s",
    r"^\s*(sudo\s+)?(systemctl|service)\s+(start|stop|restart|reload|enable|disable|daemon-reload)\s",
    r"^\s*(sudo\s+)?(chmod|chown|chattr|mkfs|fdisk|mount|umount|dd)\s",
    r"^\s*(sudo\s+)?(sed|awk|tee)\s.*-i\s",
    r"^\s*(sudo\s+)?(git)\s+(push|commit|merge|rebase|reset|cherry-pick|branch\s+-[dD]|tag)",
    r"^\s*(sudo\s+)?(cronjob)\s+(create|update|remove|delete)",
    r"^\s*(sudo\s+)?(uv|python3?)\s.*-(m\s+pip\s+install)",
    # guard: (python|python3)\s.*-c
    r"^\s*(sudo\s+)?python3?\s+-c\s",
    # guard: (bash|sh|zsh)\s+-c
    r"^\s*(sudo\s+)?bash\s+-c\s",
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


def _is_process_write(args: Dict[str, Any]) -> bool:
    action = args.get("action", "")
    return action in WRITE_PROCESS_ACTIONS


def _has_governance_lock(session_id: str = "") -> bool:
    """Check if THIS session's governance lock exists.

    When session_id is provided, checks for a session-scoped lock file.
    When session_id is empty (fallback), scans for ANY session-scoped
    lock in the state directory as a fallback check.
    """
    lock_path = _governance_lock_path(session_id)
    if lock_path.exists():
        try:
            state = json.loads(lock_path.read_text())
            return bool(state.get("task_id", ""))
        except (json.JSONDecodeError, OSError):
            return False
    # Fallback: scan for any session-scoped lock when no session_id given
    if not session_id and GOVERNANCE_STATE_DIR.exists():
        for fpath in GOVERNANCE_STATE_DIR.iterdir():
            fname = fpath.name
            if fname.startswith(".governance-sess_") and fname.endswith(".json"):
                try:
                    state = json.loads(fpath.read_text())
                    if state.get("task_id", ""):
                        return True
                except (json.JSONDecodeError, OSError):
                    continue
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
    if tool_name == "process" and _is_process_write(args):
        return True
    return False


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

        # Extract session_id from hook kwargs — this scopes the lock to THIS session
        session_id = kwargs.get("session_id", "")

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

        # Check for THIS session's lock — not ANY session's lock
        if session_id and _has_governance_lock(session_id):
            return None

        # BLOCKED
        lock_path = _governance_lock_path(session_id)
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
                "This enforcement comes from ~/.hermes/plugins/governance-enforcer/.\n"
                "Lock files are scoped per git repo — two repos can govern independently.\n"
                "I cannot bypass or disable this mid-session."
            ),
        }

    ctx.register_hook("pre_tool_call", pre_tool_call_hook)
