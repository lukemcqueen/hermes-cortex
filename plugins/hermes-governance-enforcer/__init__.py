"""Governance Enforcer Plugin — Hard blocks write tools unless governance lock exists.

Uses the Hermes Plugin System's ``pre_tool_call`` hook to intercept tools
before they execute. If a write-class tool (write_file, patch, terminal with
modifying commands, cronjob, skill_manage) is called without an active
governance lock in the state directory, the tool is blocked.

Session-ID handoff via PID-scoped file:
  Each Hermes session has a unique session ID known to the plugin system.
  The enforcer writes this ID to ~/.hermes-cortex/state/.hermes-session-{PID}.id
  at each pre_tool_call. The MCP loop-governance server (a child process)
  reads .hermes-session-{PPID}.id to learn the Hermes session ID. This gives
  both sides the same namespace without schema changes to begin_change.

Lock discovery — exact match:
  Looks for .governance-{hermes_session_id}.json. Since the MCP now creates
  locks with the Hermes session ID (via the PID handoff), the enforcer finds
  them by exact filename. No scan, no companion, no cross-session bleed.

Phase 2 scan fallback:
  If exact match fails (backward compat with old MCP locks), scans by
  repo_slug in lock content. This is the safety net for MCP versions that
  don't support the PID handoff yet.

This is the structural enforcement layer that I, as an agent, cannot bypass
or talk my way out of — the block comes from outside myself.

Install: ln -sf ~/hermes-cortex/plugins/hermes-governance-enforcer ~/.hermes/plugins/
"""

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

GOVERNANCE_STATE_DIR = Path.home() / ".hermes-cortex" / "state"


def _write_session_marker(hermes_session_id: str) -> None:
    """Write the Hermes session ID to PID-scoped AND fixed-path marker files.

    The MCP loop-governance server reads the fixed-path marker
    (~/.hermes-cortex/state/.hermes-session-current.id) to learn the Hermes
    session ID. This avoids the PID-chain problem: if there's a watchdog
    between Hermes and the MCP server, os.getppid() in the MCP returns the
    watchdog PID, not the Hermes PID.

    The PID-scoped marker (`.hermes-session-{pid}.id`) is kept for backward
    compat with MCP versions that scan by PPID.
    """
    pid = os.getpid()
    try:
        GOVERNANCE_STATE_DIR.mkdir(parents=True, exist_ok=True)
        # Fixed-path marker (primary) — MCP reads this without needing PPID
        fixed_marker = GOVERNANCE_STATE_DIR / ".hermes-session-current.id"
        fixed_marker.write_text(hermes_session_id)
        # PID-scoped marker (legacy fallback)
        pid_marker = GOVERNANCE_STATE_DIR / f".hermes-session-{pid}.id"
        pid_marker.write_text(hermes_session_id)
    except OSError:
        pass  # Best-effort — MCP will fall back to cached session.id


def _derive_repo_slug() -> str:
    """Derive the current repo slug via git rev-parse.
    Returns "" when outside a git repo — enforcer blocks all writes.
    """
    # Strategy 1: git rev-parse (fast, authoritative)
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            git_dir = result.stdout.strip()
            if git_dir:
                return Path(git_dir).name
    except (OSError, subprocess.TimeoutExpired):
        pass

    # Fallback: enforcer blocks all writes (correct behaviour)
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
            from datetime import datetime, timezone
            st = datetime.fromisoformat(started)
            # Fix: normalize timezone-aware timestamps (Z suffix) to naive UTC
            if st.tzinfo is not None:
                st = st.astimezone(timezone.utc).replace(tzinfo=None)
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            age = (now - st).total_seconds()
            return age > effective_ttl * 2
        except (ValueError, TypeError):
            pass
    return True  # no timestamps = stale


def _governance_lock_path(session_id: str = "") -> Path:
    """Return the governance lock path for the given session.

    Used by tests and external callers to determine where a governance
    lock file lives for a given session ID. Returns None when no
    session_id is provided — caller should scan for active locks.
    """
    if session_id:
        return GOVERNANCE_STATE_DIR / f".governance-{session_id}.json"
    return None


def _has_governance_lock(hermes_session_id: str = "") -> bool:
    """Check if THIS session has an active governance lock for this repo.

    Phase 1 — Exact match (primary):
      Looks for .governance-{hermes_session_id}.json. Since the MCP creates
      locks using the same Hermes session ID (via PID handoff), this finds
      the lock by exact filename. No cross-session bleed — each session's
      filename is unique to that session.

    Phase 2 — Scan by repo_slug (fallback):
      If exact match fails (backward compat with old MCP locks), scans all
      .governance-*.json files and matches by repo_slug in content.
    """
    current_slug = _derive_repo_slug()
    if not GOVERNANCE_STATE_DIR.exists():
        return False

    # Proactively purge stale locks from any session (GAP #9)
    for lock_file in sorted(GOVERNANCE_STATE_DIR.glob(".governance-*.json")):
        try:
            state = json.loads(lock_file.read_text())
            if _is_lock_stale(state):
                lock_file.unlink(missing_ok=True)
        except (json.JSONDecodeError, OSError):
            lock_file.unlink(missing_ok=True)

    # ── Phase 1: Exact match by Hermes session ID ──
    if hermes_session_id:
        lock_path = GOVERNANCE_STATE_DIR / f".governance-{hermes_session_id}.json"
        if lock_path.exists():
            try:
                state = json.loads(lock_path.read_text())
                if state.get("task_id", "") and not _is_lock_stale(state):
                    return True
                if state.get("task_id", ""):
                    lock_path.unlink(missing_ok=True)
            except (json.JSONDecodeError, OSError):
                lock_path.unlink(missing_ok=True)

    # ── Phase 2: Scan by repo_slug (backward compat fallback) ──
    for lock_file in sorted(GOVERNANCE_STATE_DIR.glob(".governance-*.json")):
        try:
            state = json.loads(lock_file.read_text())
            if state.get("repo_slug") is not None and state.get("repo_slug") != current_slug:
                continue
            if _is_lock_stale(state):
                try:
                    lock_file.unlink(missing_ok=True)
                except OSError:
                    pass
                continue
            if state.get("task_id", ""):
                return True
        except (json.JSONDecodeError, OSError):
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


def _on_session_start(session_id: str, **kwargs):
    """Write session marker at session start so MCP finds it before begin_change."""
    if session_id:
        _write_session_marker(session_id)


def register(ctx):
    """Register the governance enforcer plugin hooks."""

    # Write session marker at session start — before any tool call
    # This ensures the MCP server (child process) finds the Hermes session ID
    # when begin_change runs, so both sides use the same namespace.
    ctx.register_hook("on_session_start", _on_session_start)

    # Read command patterns that never need governance
    # NOTE: echo/printf intentionally NOT included here — they appear in
    # WRITE_COMMAND_PATTERNS with redirection operators (>|>>). If they were
    # also in READ_COMMAND_PATTERNS, `echo "data" > file` would match the
    # read pattern FIRST (line 330–332 in pre_tool_call_hook), bypassing
    # the write-lock check. This was a confirmed bypass (GAP #1, July 2026).
    READ_COMMAND_PATTERNS = [
        r"^\s*(ls|cat|head|tail|less|more|grep|find|which|whoami|id|pwd|date)\s",
        r"^\s*(ps|top|htop|df|du|free|uptime|uname|hostname|dmesg|journalctl)\s",
        r"^\s*(git)\s+(status|log|diff|show|branch|stash\s+list)",
        r"^\s*(docker)\s+(ps|images|logs|inspect|stats)",
        r"^\s*(pip|npm)\s+(list|show|search)",
        r"^\s*(hermes)\s+(--version|doctor|config\s+get|config\s+show|config\s+path|config\s+check|env-path)",
        r"^\s*(systemctl)\s+(is-active|is-enabled|status|list-units)",
    ]

    # ── Session-started hook ───────────────────────────────────
    def on_session_start_hook(**kwargs: Any) -> None:
        """Write PID-scoped marker at session start.

        Fires exactly once when a new Hermes session begins. This ensures the
        marker file exists before any MCP tool call (including begin_change),
        so the MCP server can learn the correct Hermes session ID via the
        PID handoff mechanism.
        """
        hermes_session_id = kwargs.get("session_id", "")
        if hermes_session_id:
            _write_session_marker(hermes_session_id)

    ctx.register_hook("on_session_start", on_session_start_hook)

    # ── Pre-tool-call hook ────────────────────────────────────

    def pre_tool_call_hook(
        tool_name: str = "",
        args: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Optional[Dict[str, str]]:
        if not tool_name:
            return None

        args = args or {}

        # ── ALWAYS write PID-scoped marker ──
        # Write on EVERY tool call so the MCP server's get_session_id() can
        # discover the Hermes session ID via the PID handoff at any point.
        # This guarantees that mcp__loop_governance__begin_change finds the
        # correct marker on the very first tool call of a session.
        hermes_session_id = kwargs.get("session_id", "")
        if hermes_session_id:
            _write_session_marker(hermes_session_id)

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
