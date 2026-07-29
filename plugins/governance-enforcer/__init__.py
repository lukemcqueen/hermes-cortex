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
import logging
import os
import re
import subprocess
import traceback
from pathlib import Path
from typing import Any, Dict, Optional

GOVERNANCE_STATE_DIR = Path.home() / ".hermes-cortex" / "state"
SURVEY_MARKER = GOVERNANCE_STATE_DIR / ".cron-survey-done"
SKILLS_MARKER = GOVERNANCE_STATE_DIR / ".skills-loaded"

log = logging.getLogger("governance-enforcer")

# ── Skills-loading verification ────────────────────────────
# The enforcer tracks actual skill_view() calls and auto-creates the
# .skills-loaded marker with session-proof content when all 8 required
# skills have been loaded. A bare `touch .skills-loaded` creates an
# empty file that fails content verification — blocking the bypass.
# See SOUL.md Principle 23 for agent-side guardrail.
_REQUIRED_SKILLS: set = {
    "task-start", "agent-flow", "reasoning-patterns",
    "reflexion-check", "change-checklist", "survey-before-action",
    "cortex-preflight", "agent-contract",
}
_skills_loaded_in_session: set = set()


def _check_skills_loaded_marker(session_id: str = "") -> bool:
    """Verify the .skills-loaded marker exists with valid session content.

    The marker must contain session-proof content (not just exist).
    A bare `touch .skills-loaded` creates an empty file that fails
    this check — closing the file-existence bypass.

    Verification logic:
      - Session-content markers (content starts with 'session:'):
        - With session_id: require exact match 'session:{session_id}'
        - Without session_id: accept any valid 'session:*' marker
      - Non-session-content (legacy): accept only when non-empty
      - Empty/whitespace: always reject (touch bypass)
    """
    if not SKILLS_MARKER.exists():
        return False
    try:
        content = SKILLS_MARKER.read_text().strip()
        if not content or content.isspace():
            # Empty or whitespace-only (touch bypass) → reject
            return False
        if content.startswith("session:"):
            # Session-verified marker — check match
            if session_id and content != f"session:{session_id}":
                # Wrong session → reject
                return False
            # Matching session or no session_id passed → accept
            return True
        # Non-session, non-empty content (legacy backward compat) → accept
        return True
    except OSError:
        return False


def _auto_create_skills_marker(session_id: str) -> None:
    """Write the .skills-loaded marker with session-specific proof content.

    Called automatically when all 8 required skills have been loaded
    via skill_view() in this session. The session_id in the content
    prevents reuse across sessions and blocks `touch` bypass.
    """
    if not session_id:
        return
    try:
        GOVERNANCE_STATE_DIR.mkdir(parents=True, exist_ok=True)
        SKILLS_MARKER.write_text(f"session:{session_id}")
        log.info("Skills-loaded marker auto-created for session %s", session_id)
    except OSError as e:
        log.warning("Cannot auto-create skills-loaded marker: %s", e)


def _write_session_marker(hermes_session_id: str) -> None:
    """Write the Hermes session ID to PID-scoped AND fixed-path marker files."""
    pid = os.getpid()
    try:
        GOVERNANCE_STATE_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        log.warning("Cannot create governance state dir: %s", e)
        return

    try:
        fixed_marker = GOVERNANCE_STATE_DIR / ".hermes-session-current.id"
        fixed_marker.write_text(hermes_session_id)
    except OSError as e:
        log.warning("Cannot write fixed-path session marker: %s", e)

    try:
        pid_marker = GOVERNANCE_STATE_DIR / f".hermes-session-{pid}.id"
        pid_marker.write_text(hermes_session_id)
    except OSError as e:
        log.warning("Cannot write PID-scoped session marker: %s", e)

    try:
        hermes_session_path = Path.home() / ".hermes" / "session.id"
        hermes_session_path.parent.mkdir(parents=True, exist_ok=True)
        hermes_session_path.write_text(hermes_session_id)
    except OSError as e:
        log.warning("Cannot write fallback session.id cache: %s", e)


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
        log.warning("Cannot derive repo slug via git rev-parse")
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
            log.warning("Cannot parse heartbeat timestamp: %s", heartbeat)
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
            log.warning("Cannot parse started_at timestamp: %s", started)
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


def _secondary_lock_path() -> Path | None:
    """Return path to the secondary lock marker inside the git repo.

    The secondary marker lives at <repo_root>/.hermes-cortex/.governance-lock
    and is written by the MCP server's begin_change() alongside the primary
    lock in ~/.hermes-cortex/state/. The enforcer checks this as a fallback
    when the primary lock directory is inaccessible.
    """
    current_slug = _derive_repo_slug()
    if not current_slug:
        return None
    for candidate in [Path.home() / current_slug]:
        if (candidate / ".git").exists():
            return candidate / ".hermes-cortex" / ".governance-lock"
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

    Phase 3 — Secondary lock marker (extra safety):
      Checks the repo-located marker at .hermes-cortex/.governance-lock
      as a fallback when the primary state directory is inaccessible.
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
    # NOTE: This is a TIGHTENED fallback. When the lock has a session_id
    # and the current session has an ID, we require an exact session match.
    # This prevents cross-session bypass where Session B writes using
    # Session A's lock. Old sessionless locks (no session_id field) are
    # still accepted for backward compat with MCP versions before PID handoff.
    for lock_file in sorted(GOVERNANCE_STATE_DIR.glob(".governance-*.json")):
        try:
            state = json.loads(lock_file.read_text())
            # When current session has an ID AND lock has session_id,
            # require exact match — closes cross-session bypass vector
            lock_session = state.get("session_id", "")
            if hermes_session_id and lock_session and lock_session != hermes_session_id:
                continue
            # When current_slug is "" (CWD not in a git repo), match
            # any lock with a real repo_slug. This fixes Phase 2 being
            # a no-op when the Hermes gateway CWD (~/.hermes) is outside git.
            if current_slug:
                if state.get("repo_slug") is not None and state.get("repo_slug") != current_slug:
                    continue
            else:
                if state.get("repo_slug") is None:
                    continue
            if _is_lock_stale(state):
                try:
                    lock_file.unlink(missing_ok=True)
                except OSError:
                    log.warning("Cannot remove stale lock file: %s", lock_file)
                    pass
                continue
            if state.get("task_id", ""):
                return True
        except (json.JSONDecodeError, OSError):
            try:
                lock_file.unlink(missing_ok=True)
            except OSError:
                log.warning("Cannot remove unparseable lock file: %s", lock_file)
                pass

    # ── Phase 3: Secondary lock marker inside repo ──
    # Check the repo-located marker when primary state directory
    # doesn't exist or has no matching locks. The MCP server writes
    # this alongside the primary lock during begin_change().
    # Same session-match tightening as Phase 2.
    secondary = _secondary_lock_path()
    if secondary and secondary.exists():
        try:
            state = json.loads(secondary.read_text())
            lock_session = state.get("session_id", "")
            if hermes_session_id and lock_session and lock_session != hermes_session_id:
                pass  # skip — not our session
            elif state.get("task_id", ""):
                return True
        except (json.JSONDecodeError, OSError):
            log.warning("Cannot read secondary lock marker: %s", secondary)
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
    "computer_use",
}

# Process actions that require governance
WRITE_PROCESS_ACTIONS = {"write", "submit", "close", "kill"}

# Computer use actions that modify state — require governance lock
WRITE_COMPUTER_USE_ACTIONS = {
    "click", "double_click", "right_click", "middle_click",
    "drag", "scroll", "type", "key", "set_value", "focus_app",
}

# Terminal commands that modify state — require governance lock
WRITE_COMMAND_PATTERNS = [
    r"\s*(sudo\s+)?(rm|mv|cp|install|apt|apt-get|dpkg|brew|make|cmake|docker compose|kubectl)\s",
    r"\s*(sudo\s+)?(systemctl|service)\s+(start|stop|restart|reload|enable|disable|daemon-reload)\s",
    r"\s*(sudo\s+)?(chmod|chown|chattr|mkfs|fdisk|mount|umount|dd)\s",
    r"\s*(sudo\s+)?(sed|awk|tee)\s.*-i\s",
    r"\s*(sudo\s+)?(git)\s+(push|commit|merge|rebase|reset|cherry-pick|branch\s+-[dD]|tag|stash|checkout|restore|clean|rm|mv|update-ref|config|submodule)\s",
    r"\s*(sudo\s+)?(cronjob)\s+(create|update|remove|delete)",
    r"\s*(sudo\s+)?(uv|python3?)\s.*-(m\s+pip\s+install)",
    # guard: (python|python3)\s.*-c
    r"\s*(sudo\s+)?python3?\s+-c\s",
    # guard: (bash|sh|zsh)\s+-c
    r"\s*(sudo\s+)?bash\s+-c\s",
    r"\s*(sudo\s+)?wget\s.*-O\s",
    r"\s*(sudo\s+)?curl\s.*-o\s",
    r"\s*(sudo\s+)?nohup\s",
    r"\s*(sudo\s+)?docker\s+(run|build|push|commit|tag|save|load|rmi|system\s+prune)",
    r"\s*(sudo\s+)?crontab\s",
    r"\s*(sudo\s+)?(usermod|groupmod|useradd|groupadd|passwd)\s",
    r"\s*(sudo\s+)?ufw\s+(enable|disable|allow|deny|reject|delete|reset)",
    r"\s*(sudo\s+)?nginx\s+(-s\s+(reload|stop|quit))",
    r"\s*(sudo\s+)?journalctl\s+--rotate",
    r"\s*(sudo\s+)?(printf|cat|tee|head|tail|grep|find)\s+.*>\s",
    r"\s*(sudo\s+)?(printf|cat)\s+.*<<\s",
    r"\s*(sudo\s+)?(touch|mkdir|ln|rsync|unzip|tar|mkfifo|tee)\s",
    r"\s*(sudo\s+)?(npx|yarn|go|cargo|flatpak|snap)\s",
    r"\s*(sudo\s+)?(pip3?|npm)\s+(install|uninstall|remove|update|upgrade)",
    r"\s*echo\s+.*>\s",
    # guard: interpreter + script file execution
    # Catches `python3 script.py`, `node app.js`, `bash setup.sh`, etc.
    # The script argument must start with a non-dash character (excludes flags like -c, --version)
    # Requires .py/.js/.rb/.pl/.sh extension to distinguish from interactive mode
    r"\s*(sudo\s+)?(python3(?:\.\d+)?|node|ruby|perl|bash|sh|zsh)\s+[^\s-][^\s]*\.(py|js|rb|pl|sh)(?:\s|$)",
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


def _is_computer_use_write(args: Dict[str, Any]) -> bool:
    """Check if a computer_use action modifies system state."""
    action = args.get("action", "")
    return action in WRITE_COMPUTER_USE_ACTIONS


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
    if tool_name == "computer_use" and _is_computer_use_write(args):
        return True
    return False


def _on_session_start(session_id: str, **kwargs):
    """Write session marker at session start so MCP finds it before begin_change.

    For cron/automated sessions (session_id starts with 'cron_'), also
    auto-create the .skills-loaded marker if the 8 required always-section
    skills exist on disk. This breaks the bootstrapping deadlock where cron
    sessions can't load skills because all tools are blocked.

    Interactive sessions are unaffected — they still require skill_view()
    calls to create the marker, maintaining full governance security.
    """
    try:
        if session_id:
            _write_session_marker(session_id)

            # ── Cron bootstrap: auto-create .skills-loaded ──────────────
            # Cron sessions start fresh with no skills-loaded marker. The
            # enforcer blocks all write tools until skills are loaded, but
            # cron agents may not have skill_view() in their tool registry.
            # This bootstrap reads the always-section skills from disk and
            # pre-creates the marker, so cron agents can proceed normally.
            if session_id.startswith("cron_") and not SKILLS_MARKER.exists():
                _bootstrap_cron_skills(session_id)
    except Exception:
        log.error("on_session_start hook crashed:\n%s", traceback.format_exc())


def _bootstrap_cron_skills(session_id: str) -> bool:
    """For cron sessions: verify always-section skills exist on disk and
    auto-create the .skills-loaded marker.

    Reads skills.yaml to find the 'always' section, then verifies each
    skill has a SKILL.md file somewhere under ~/.hermes/skills/. If all
    required skills are found on disk, creates the marker so the cron
    agent can proceed without needing to call skill_view().

    Returns True if marker was created, False if skills are incomplete
    (cron agent will be blocked by the enforcer — but this is expected
    for a corrupted/bootstrapping environment).
    """
    import yaml

    skills_yaml = Path.home() / ".hermes-cortex" / "skills.yaml"
    if not skills_yaml.exists():
        log.warning("Cron bootstrap: skills.yaml not found at %s", skills_yaml)
        return False

    try:
        with open(skills_yaml) as f:
            manifest = yaml.safe_load(f)
    except Exception as e:
        log.warning("Cron bootstrap: cannot parse skills.yaml: %s", e)
        return False

    always_skills = manifest.get("always", []) if manifest else []
    always_names = {s.get("name", "") for s in always_skills if isinstance(s, dict)}

    # Must contain all required skills
    if not _REQUIRED_SKILLS.issubset(always_names):
        missing = _REQUIRED_SKILLS - always_names
        log.warning(
            "Cron bootstrap: skills.yaml missing required skills: %s", missing
        )
        return False

    # Verify each required skill has a SKILL.md on disk
    skills_root = Path.home() / ".hermes" / "skills"
    for skill_name in _REQUIRED_SKILLS:
        found = False
        if skills_root.exists():
            for skill_dir in skills_root.rglob(f"*/{skill_name}/SKILL.md"):
                found = True
                break
        if not found:
            log.warning(
                "Cron bootstrap: SKILL.md not found for '%s' under %s",
                skill_name, skills_root,
            )
            return False

    # All skills verified — create marker
    _auto_create_skills_marker(session_id)
    log.info(
        "Cron bootstrap: .skills-loaded auto-created for session %s "
        "(verified %d always-section skills on disk)",
        session_id, len(_REQUIRED_SKILLS),
    )
    return True


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

    # ── Pre-tool-call hook ────────────────────────────────────

    def pre_tool_call_hook(
        tool_name: str = "",
        args: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> Optional[Dict[str, str]]:
        try:
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

            # ── Track skill_view calls ──
            # Moved BEFORE the skills gate so agents can load skills.
            # When all 8 required skills are loaded, the marker is
            # auto-created with session-proof content.
            if tool_name == "skill_view":
                skill_name = args.get("name", "")
                if skill_name:
                    _skills_loaded_in_session.add(skill_name)
                    if hermes_session_id and _skills_loaded_in_session >= _REQUIRED_SKILLS:
                        _auto_create_skills_marker(hermes_session_id)

            # ── Read-only terminal fast-path: BEFORE skills gate (read-only fast-path passes) ──
            # Allow read-only terminal commands (ls, pwd, grep, etc.) even
            # without skills loaded, so agents can inspect the system.
            # Write-class terminal commands (touch, echo >, mkdir, etc.)
            # are blocked unless all 8 required skills are loaded.
            if tool_name == "terminal":
                command = args.get("command", "")
                if any(re.search(p, command) for p in READ_COMMAND_PATTERNS):
                    if not _is_terminal_write(args):
                        return None

            # ── Skills gate: blocks WRITE tools until skills loaded ──
            # Uses content verification — bare `touch .skills-loaded` creates
            # an empty file that fails _check_skills_loaded_marker().
            # Read-only tools (read_file, search_files, session_search, cron list/run,
            # web_search, vision_analyze, etc.) pass through — they can't modify state.
            # The enforcer auto-creates the marker when all 8 skills have
            # been loaded via actual skill_view() calls — no touch needed.
            if not _check_skills_loaded_marker(hermes_session_id):
                if _is_write_tool(tool_name, args):
                    return {
                        "action": "block",
                        "message": (
                            "WRITE TOOLS BLOCKED — SKILLS MUST BE LOADED FIRST\n\n"
                            "Tool '" + tool_name + "' modifies state — always-section skills not loaded.\n\n"
                            "Session-start sequence:\n"
                            "  1. skill_view('task-start')        # bundles the complete sequence\n"
                            "  2. skill_view('agent-flow')        # workflow router\n"
                            "  3. skill_view('reasoning-patterns') # choose how to think\n"
                            "  4. skill_view('reflexion-check')   # self-critique before deliver\n"
                            "  5. skill_view('change-checklist')  # pre-ship verification\n"
                            "  6. skill_view('survey-before-action')  # check existing resources\n"
                            "  7. skill_view('cortex-preflight')  # repo-specific pre-flight\n"
                            "  8. skill_view('agent-contract')    # execution rules\n\n"
                            "The marker is auto-created when all 8 are loaded.\n"
                            "Do NOT try to touch .skills-loaded directly — it will be rejected.\n\n"
                            "Read-only tools (read_file, search_files, session_search,\n"
                            "cron action=list/run, web tools, vision) ARE allowed.\n\n"
                            "This enforcement is at ~/.hermes/plugins/governance-enforcer/.\n"
                            "I cannot bypass or disable this.\n"
                        ),
                    }

            if not _is_write_tool(tool_name, args):
                return None

            # Cronjob read operations pass through
            if tool_name == "cronjob" and args.get("action") in ("list", "run"):
                return None

            # Survey gate: cronjob(create) requires survey-before-action marker
            # Call cronjob(action='list') + search_files() + skills_list() BEFORE
            # creating a new cron. Touch the marker to confirm survey done:
            #   touch ~/.hermes-cortex/state/.cron-survey-done
            if tool_name == "cronjob" and args.get("action") == "create":
                if not SURVEY_MARKER.exists():
                    return {
                        "action": "block",
                        "message": (
                            "SURVEY REQUIRED BEFORE CRON CREATION\n\n"
                            "Tool 'cronjob' action='create' requires a survey of existing resources.\n\n"
                            "Run these steps FIRST:\n"
                            "  1. cronjob(action='list')     — check existing crons for overlaps\n"
                            "  2. search_files(...)          — check for existing scripts\n"
                            "  3. skills_list()              — check for existing skills\n\n"
                            "After completing the survey:\n"
                            "  touch ~/.hermes-cortex/state/.cron-survey-done\n\n"
                            "Then retry cronjob(action='create').\n"
                            "The marker persists for this session.\n"
                            "This enforcement is at ~/.hermes/plugins/governance-enforcer/.\n"
                            "I cannot bypass or disable this.\n"
                        ),
                    }

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
        except Exception:
            log.error("Governance enforcer crashed:\n%s", traceback.format_exc())
            return {
                "action": "block",
                "message": (
                    "GOVERNANCE ENFORCER CRASHED — ALL WRITES BLOCKED\n\n"
                    "The enforcer plugin encountered an internal error and "
                    "cannot verify governance state.\n\n"
                    "All write operations are blocked until the enforcer "
                    "is reloaded or fixed.\n"
                    "Check Hermes logs for the full traceback.\n"
                    "This is a safety measure — the enforcer always fails closed."
                ),
            }

    ctx.register_hook("pre_tool_call", pre_tool_call_hook)
