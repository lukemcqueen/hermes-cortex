"""Governance Enforcer Plugin — Hard blocks write tools unless governance lock exists.

Uses the Hermes Plugin System's ``pre_tool_call`` hook to intercept tools
before they execute. If a write-class tool (write_file, patch, terminal with
modifying commands, cronjob, skill_manage) is called without an active
governance lock in the state directory, the tool is blocked.

Lock discovery uses a two-phase strategy:

Phase 1 — Exact match by Hermes session ID:
  Checks for a companion lock file named .governance-sess_<Hermes_sid>.json.
  If found, verifies the original MCP lock still exists. If the original
  is gone (end_change was called), the companion is deleted immediately —
  no stale window.

Phase 2 — Scan by repo_slug (fallback):
  Scans all .governance-*.json files, matches by repo_slug in content.
  When a valid MCP lock is found for this repo, the enforcer creates a
  companion lock named .governance-sess_<Hermes_sid>.json that points
  back to the MCP lock via a ``companion_of`` field. Future checks in
  this session skip the scan and use the exact match.

This two-phase approach is immune to session-ID namespace mismatches
between the Hermes plugin system and the MCP loop-governance server.
Each Hermes session gets its own uniquely-named companion lock, so
concurrent sessions on the same repo each have independent governance.

NOTE: The companion approach provides per-session lock naming but does
NOT prevent cross-session bleeding via Phase 2. Session A's MCP lock
will satisfy Session B's Phase 2 scan, causing Session B to create a
companion without ever calling begin_change. True per-session isolation
requires the MCP begin_change tool to use the Hermes session ID directly
(passing it as a parameter instead of generating its own UUID). This
is a planned improvement; until then, this is the practical fix.

This is the structural enforcement layer that I, as an agent, cannot
bypass or talk my way out of — the block comes from outside myself.

Install: ln -sf ~/hermes-cortex/plugins/hermes-governance-enforcer ~/.hermes/plugins/
"""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

GOVERNANCE_STATE_DIR = Path.home() / ".hermes-cortex" / "state"


def _derive_repo_slug() -> str:
    """Derive the current repo slug from git top-level."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip()).name
    except (OSError, subprocess.TimeoutExpired):
        pass
    return ""


def _is_lock_stale(state: dict, max_age: int = 7200) -> bool:
    """Check if a lock has exceeded its TTL and should be considered stale."""
    ttl = state.get("ttl_seconds", 3600)
    effective_ttl = max(ttl, max_age)
    heartbeat = state.get("heartbeat_at", "")
    if heartbeat:
        try:
            from datetime import datetime, timezone
            hb = datetime.fromisoformat(heartbeat)
            now = datetime.now(timezone.utc).replace(tzinfo=None) if hb.tzinfo is None else datetime.now(timezone.utc)
            age = (now - hb).total_seconds()
            return age > effective_ttl
        except (ValueError, TypeError):
            pass
    started = state.get("started_at", "")
    if started:
        try:
            from datetime import datetime
            st = datetime.fromisoformat(started)
            now = datetime.now()
            age = (now - st).total_seconds()
            return age > effective_ttl * 2
        except (ValueError, TypeError):
            pass
    return True  # no timestamps = stale


def _has_governance_lock(hermes_session_id: str = "") -> bool:
    """Check if THIS session has an active governance lock for this repo.

    Two-phase approach:

    1. Exact match by Hermes session ID (Phase 1):
       If a companion lock exists for this session's Hermes ID, verify
       the original MCP lock still exists. If the original is gone
       (end_change was called), delete the companion immediately.

    2. Scan by repo_slug (Phase 2):
       Fallback that scans all lock files and matches by repo_slug in
       content. When a valid MCP lock is found, creates a companion
       lock for this session's Hermes ID so future checks are Phase 1.
    """
    current_slug = _derive_repo_slug()
    if not GOVERNANCE_STATE_DIR.exists():
        return False

    # ── Phase 1: Exact match by Hermes session ID ──
    if hermes_session_id:
        companion_path = GOVERNANCE_STATE_DIR / f".governance-sess_{hermes_session_id}.json"
        if companion_path.exists():
            try:
                state = json.loads(companion_path.read_text())
                mcp_sid = state.get("companion_of", "")
                if mcp_sid:
                    # Verify original MCP lock still exists
                    mcp_path = GOVERNANCE_STATE_DIR / f".governance-{mcp_sid}.json"
                    if mcp_path.exists():
                        try:
                            mcp_state = json.loads(mcp_path.read_text())
                            if mcp_state.get("task_id", "") and not _is_lock_stale(mcp_state):
                                return True
                            # Stale MCP lock — clean both
                            mcp_path.unlink(missing_ok=True)
                        except (json.JSONDecodeError, OSError):
                            pass
                # Original is gone or stale — clean companion
                companion_path.unlink(missing_ok=True)
            except (json.JSONDecodeError, OSError):
                companion_path.unlink(missing_ok=True)

    # ── Phase 2: Scan by repo_slug (find MCP lock, create companion) ──
    for lock_file in sorted(GOVERNANCE_STATE_DIR.glob(".governance-*.json")):
        try:
            state = json.loads(lock_file.read_text())
            # Skip companion files during scan — they're Phase 1 only
            if "companion_of" in state:
                continue
            # Match by repo_slug in content (not filename)
            if state.get("repo_slug") is not None and state.get("repo_slug") != current_slug:
                continue
            # Skip stale locks — auto-clean
            if _is_lock_stale(state):
                try:
                    lock_file.unlink(missing_ok=True)
                except OSError:
                    pass
                continue
            if state.get("task_id", ""):
                # Found a valid MCP lock for this repo
                # Create companion lock for this Hermes session
                if hermes_session_id:
                    mcp_sid = state.get("session_id", "")
                    companion = dict(state)
                    companion["companion_of"] = mcp_sid
                    companion_path = GOVERNANCE_STATE_DIR / f".governance-sess_{hermes_session_id}.json"
                    companion_path.write_text(json.dumps(companion, indent=2))
                return True
        except (json.JSONDecodeError, OSError):
            # Corrupt lock file — clean it
            try:
                lock_file.unlink(missing_ok=True)
            except OSError:
                pass
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

        # Extract Hermes session ID from kwargs
        hermes_session_id = kwargs.get("session_id", "")

        # Check for active governance lock (Phase 1 exact + Phase 2 scan)
        if _has_governance_lock(hermes_session_id):
            return None

        # BLOCKED
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
                "This repo requires an active governance lock.\n"
                "Call begin_change() first:\n"
                "  mcp_loop_governance_begin_change(\n"
                '    task_id="<short-description>",\n'
                '    description="<what this does>"\n'
                "  )\n\n"
                "After the change, score and release:\n"
                '  mcp_loop_governance_cycle_query(task_id="<task>")\n'
                '  mcp_loop_governance_feedback_accept(cycle_id=N, note="verified: ...")\n'
                '  mcp_loop_governance_end_change(task_id="<task>")\n\n'
                "This enforcement comes from ~/.hermes/plugins/governance-enforcer/.\n"
                "Lock files are scoped per git repo — two repos can govern independently.\n"
                "I cannot bypass or disable this mid-session."
            ),
        }

    ctx.register_hook("pre_tool_call", pre_tool_call_hook)
