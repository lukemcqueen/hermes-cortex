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

Install: ln -sf ~/hermes-cortex/plugins/governance-enforcer ~/.hermes/plugins/
"""

import json
import logging
import os
import re
import sqlite3
import subprocess
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

GOVERNANCE_STATE_DIR = Path.home() / ".hermes-cortex" / "state"
SURVEY_MARKER = GOVERNANCE_STATE_DIR / ".cron-survey-done"
# ── Skills-loading proof: PER-SESSION files (2026-08-01) ──────────────
# Previously a single shared .skills-loaded file gated every session on a
# machine. Concurrent sessions (telegram + cli 1 + cli 2 on one server)
# each loaded skills and overwrote that one file with their own session ID,
# blocking the other sessions' write tools mid-task. Now each session owns
# its proof at state/skills-loaded/<session_id> and its state at
# state/skills-state/<session_id>.json — sessions physically cannot stomp
# each other. The legacy single-file constants below are kept so the
# doctor's structural check and backward-compat references still resolve,
# but new code never reads or writes them (see _skills_marker_dir()).
SKILLS_MARKER = GOVERNANCE_STATE_DIR / ".skills-loaded"          # legacy — inert
SKILLS_STATE_FILE = GOVERNANCE_STATE_DIR / "skills-state.json"   # legacy — inert
SKILLS_MARKER_DIR = GOVERNANCE_STATE_DIR / "skills-loaded"       # per-session markers
SKILLS_STATE_DIR = GOVERNANCE_STATE_DIR / "skills-state"         # per-session state

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

# Per-session loaded-skill registry (2026-08-08 — cross-session bleed fix).
# The legacy `_skills_loaded_in_session` set is PROCESS-global: any session's
# skill_view() calls count for EVERY session, so session B's marker auto-created
# and the domain/adversarial gates passed when session A (not B) loaded the
# skill — agents on long turns never had to load skills themselves. This dict
# keys loaded skill names by session_id so each session must load its own
# skills. Populated in pre_tool_call_hook on skill_view; read by the marker
# auto-create condition, _check_domain_skill_gate, and
# _check_adversarial_commit_gate.
_session_skills_loaded: dict[str, set] = {}
_skills_loaded_in_session: set = set()

# ── Domain skill gate ──────────────────────────────────
# Before write_file/patch, check if the file type's domain
# skill has been loaded. First offense → suggest (educate).
# Repeat → block (enforce). Path context refines suggestion.
# MUST stay in sync with survey-before-action Phase 0a.
_EXT_DOMAIN_SKILLS = {
    ".sh":    ("shell-scripting",           "Bash portability, strict-mode, path patterns"),
    ".bash":  ("shell-scripting",           "Bash portability, strict-mode, path patterns"),
    ".py":    ("codebase-design",           "Module depth, seams, testability patterns"),
    ".conf":  ("nginx-web-app-deployment",  "nginx upstream, SSL, auth configs"),
    ".yml":   ("docker-management",         "Docker compose, layering, networking"),
    ".yaml":  ("docker-management",         "Docker compose, layering, networking"),
    ".md":    ("documentation-auditing",    "Cross-ref freshness, stale-path detection"),
    ".env":   ("secure-credential-handling","Secrets, PII, gitignore patterns"),
    ".toml":  None,   # known gap
    ".json":  None,   # known gap
    ".sql":   None,   # known gap
}
_FILENAME_DOMAIN_SKILLS = {
    "Makefile":     ("project-run-scripts",  "Docker lifecycle, dev servers, testing"),
    "Dockerfile":   ("docker-management",    "Multi-stage, layer caching, security"),
    ".env":         ("secure-credential-handling","Secrets, PII, gitignore patterns"),
}
# Path fragments that override the extension-based suggestion
_PATH_CTX_HINTS = {
    "test":      "test-driven-development",
    "spec":      "test-driven-development",
    "deploy":    "cortex-preflight",
    "install":   "cortex-preflight",
    "cron":      "cron-job-management",
    "docs":      "documentation-auditing",
    "reference": "documentation-auditing",
}
# Tracking: {session_id: {ext_or_filename: warning_count}}
_domain_warnings: dict = {}
# Previous action context: {session_id: {"last_action": str}}
_prev_action: dict = {}

# ── Adversarial commit gate ───────────────────────────
# Before git commit/push of critical-system changes, require
# adversarial-verifier skill. Same 💡/⛔/✅ pattern as domain gate.
# MUST stay in sync with ops/scripts/cortex_doctor/ paths.
_ADVERSARIAL_COMMIT_PATTERNS = [
    r"\bgit\s+commit\b",
    r"\bgit\s+push\b",
]
# Paths whose changes REQUIRE adversarial verification before commit/push.
# Broadened 2026-08-04: any ops/scripts/ change (not just manage/doctor),
# the verifier itself (quality/), all plugins, skills, hooks, mcp-servers.
# MUST stay in sync with ops/scripts/cortex_doctor/ paths and the
# pre-commit hook's ADV_A4_PREFIXES list.
_ADVERSARIAL_CRITICAL_PATHS = [
    "tests/",
    "ops/scripts/",
    "plugins/",
    "skills/",
    "docs/templates/",
    "hooks/",
    "mcp-servers/",
    "docs/orchestrator-only-paths.txt",
]
_adversarial_warnings: dict = {}  # {session_id: count}
# Critical path display names per prefix (for the ⛔ message)
_ADVERSARIAL_DISPLAY = {
    "tests/": "tests/",
    "ops/scripts/": "scripts (ops/scripts/)",
    "plugins/": "plugins/",
    "skills/": "skills/",
    "docs/templates/": "docs templates (skills/config)",
    "hooks/": "repo hooks",
    "mcp-servers/": "MCP servers",
    "docs/orchestrator-only-paths.txt": "orchestrator path list",
}


def _detect_domain_skill_needed(tool_name: str, args: dict) -> tuple:
    """Detect what domain skill an agent needs before a file write.

    Returns (skill_name_or_None, why_message_or_None).

    Intelligence sources (in priority order):
      1. Filename match (Makefile, Dockerfile)
      2. Path-context hint (file under tests/, deploy/, etc.)
      3. Extension match (.sh, .py, .yml, etc.)
    """
    if tool_name not in ("write_file", "patch", "skill_manage"):
        return None, None
    if tool_name == "skill_manage":
        # skill_manage writes to ~/.hermes/skills/<name>/... — it has no
        # path arg, so map by the skill name / optional file_path instead.
        # SKILL.md → skill-authoring domain skill (check filename FIRST —
        # Path('SKILL.md').suffix is '.md', not ''); a supporting file
        # with a known extension → that domain skill.
        fpath = args.get("file_path", "")
        fname = Path(fpath).name if fpath else "SKILL.md"
        if fname.lower() == "skill.md":
            return ("hermes-agent-skill-authoring",
                    "Skill authoring conventions, frontmatter validation, PII guardrails")
        ext = Path(fname).suffix.lower() if Path(fname).suffix else ""
        if ext and ext in _EXT_DOMAIN_SKILLS and _EXT_DOMAIN_SKILLS[ext]:
            entry = _EXT_DOMAIN_SKILLS[ext]
            return entry[0], entry[1]
        return ("hermes-agent-skill-authoring",
                "Skill authoring conventions, frontmatter validation, PII guardrails")
    path = args.get("path", "")
    if not path:
        return None, None
    fname = Path(path).name
    ext = Path(path).suffix.lower() if Path(path).suffix else ""

    # 1. Filename match
    if fname in _FILENAME_DOMAIN_SKILLS:
        entry = _FILENAME_DOMAIN_SKILLS[fname]
        return entry[0], entry[1]

    # 1b. Dotfile match — files like .env, .gitignore, etc.
    # Path('.env').suffix is '' because the whole name is the "extension"
    if fname.startswith('.') and ext == '':
        dot_name = fname  # e.g. ".env"
        if dot_name in _FILENAME_DOMAIN_SKILLS:
            entry = _FILENAME_DOMAIN_SKILLS[dot_name]
            return entry[0], entry[1]
        # Also check the extension map with the dot-name as extension
        if dot_name in _EXT_DOMAIN_SKILLS:
            entry = _EXT_DOMAIN_SKILLS[dot_name]
            if entry is not None:
                return entry[0], entry[1]
            return None, None  # known gap

    # 2. Path-context hint — look for known fragments in the full path
    path_lower = path.lower()
    for fragment, ctx_skill in _PATH_CTX_HINTS.items():
        if fragment in path_lower:
            return ctx_skill, f"File in `{fragment}/` context — this skill covers the workflow patterns"

    # 3. Extension match
    if ext in _EXT_DOMAIN_SKILLS:
        entry = _EXT_DOMAIN_SKILLS[ext]
        if entry is None:
            return None, None  # known gap, no dedicated skill
        return entry[0], entry[1]

    # 4. Unknown — no mapping
    return None, None


def _skills_marker_dir() -> Path:
    """Per-session skills marker dir — derived at call time so tests can
    repoint GOVERNANCE_STATE_DIR without reloading the module."""
    return GOVERNANCE_STATE_DIR / "skills-loaded"


def _skills_state_dir() -> Path:
    """Per-session skills state dir (same call-time derivation rationale)."""
    return GOVERNANCE_STATE_DIR / "skills-state"


def _session_marker_path(session_id: str) -> Path:
    """Path of THIS session's skills-loaded marker file."""
    _assert_safe_session_id(session_id)
    return _skills_marker_dir() / session_id


def _skills_state_path(session_id: str) -> Path:
    """Path of THIS session's skills-state JSON file."""
    _assert_safe_session_id(session_id)
    return _skills_state_dir() / f"{session_id}.json"


def _assert_safe_session_id(session_id: str) -> None:
    """Reject session IDs that could escape the state dirs via path traversal.

    Hermes generates session IDs server-side (timestamp_hex), so this is
    defense-in-depth: a hostile or corrupted session ID must never be able
    to write a marker/state file outside state/skills-loaded|skills-state
    (e.g. ``../evil`` or ``a/b``). Raises ValueError — callers treat it
    like a missing marker (graceful failure).
    """
    if (
        not session_id
        or session_id in (".", "..")
        or "/" in session_id
        or "\\" in session_id
        or "\x00" in session_id
    ):
        raise ValueError(f"Unsafe session_id: {session_id!r}")


def _read_skills_state(session_id: str = "") -> dict:
    """Read THIS session's skills-state file. Returns {} if missing or corrupt.

    Per-session state files (skills-state/<session_id>.json) replaced the
    shared skills-state.json on 2026-08-01 — concurrent sessions can no
    longer clobber each other's progress.
    """
    if not session_id:
        return {}
    try:
        path = _skills_state_path(session_id)
        if path.exists():
            with open(path) as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
    except (json.JSONDecodeError, OSError, ValueError):
        log.debug("Cannot read skills-state json — starting fresh")
    return {}


def _write_skills_state(
    session_id: str,
    always_loaded: set = None,
    state_updates: dict = None,
) -> dict:
    """Write THIS session's skills-state file.

    Merges with any existing state for the same session. Creates or updates
    the always_skills dict with timestamps, and applies any additional
    state_updates (task_type, workflow_state, etc.).

    Returns the final state dict.
    """
    if not session_id:
        return {}
    state = _read_skills_state(session_id)
    if not state:
        state = {
            "session_id": session_id,
            "always_skills": {},
            "on_task_skills": {},
            "workflow_state": {},
        }

    if always_loaded:
        now = datetime.now(timezone.utc).isoformat()
        if "always_skills" not in state:
            state["always_skills"] = {}
        for name in always_loaded:
            if name not in state["always_skills"]:
                state["always_skills"][name] = {
                    "loaded_at": now,
                    "verified": True,
                }

    if state_updates:
        state.update(state_updates)

    state["last_updated"] = datetime.now(timezone.utc).isoformat()
    try:
        path = _skills_state_path(session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w") as f:
            json.dump(state, f, indent=2)
        tmp.rename(path)
    except (OSError, ValueError) as e:
        log.warning("Cannot write skills-state.json: %s", e)
    return state


def _get_loaded_skills_summary(session_id: str = "") -> dict:
    """Return a dict of {skill_name: bool} for all 8 required skills
    for the given session."""
    state = _read_skills_state(session_id)
    always = state.get("always_skills", {})
    return {
        s: s in always
        for s in _REQUIRED_SKILLS
    }


def _is_subagent_session(session_id: str) -> bool:
    """Detect delegate_task subagent sessions via state.db.

    Subagents spawn with date-based session IDs (e.g. 20260731_123105_8b1c9a)
    — NOT the documented bg_ prefix — so prefix guards miss them. They ARE
    distinguishable: the sessions table records `parent_session_id` and
    `source='subagent'` for delegated children.

    LEGACY (2026-08-01): This was used to keep subagents from stealing the
    shared .skills-loaded marker. Markers are now per-session files, so the
    guard class is obsolete — retained for the guardrail registry and any
    future lock-lifecycle logic that needs subagent awareness.
    """
    if not session_id or not session_id.startswith("20"):
        return False
    try:
        db = Path.home() / ".hermes" / "state.db"
        if not db.exists():
            return False
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=3)
        try:
            row = conn.execute(
                "SELECT source, parent_session_id FROM sessions WHERE id = ?",
                (session_id,),
            ).fetchone()
            if row:
                source, parent = row
                return source == "subagent" or bool(parent)
        finally:
            conn.close()
    except Exception:
        log.warning("Cannot query state.db for subagent detection", exc_info=True)
    return False


def _session_type(session_id: str) -> str:
    """Classify a session for lock-lifecycle purposes.

    P1-A: cron/daemon locks must not purge interactive locks. The prefix
    is the reliable signal (cron_ = scheduler, bg_ = background subagent).
    Everything else (date-based interactive, cli-source) is interactive.
    """
    if not session_id:
        return "interactive"
    if session_id.startswith("cron_"):
        return "cron"
    if session_id.startswith("bg_"):
        return "bg"
    return "interactive"


def _check_skills_loaded_marker(session_id: str = "") -> bool:
    """Verify THIS session's per-session skills marker exists with valid content.

    Per-session marker files (state/skills-loaded/<session_id>) replaced the
    single shared .skills-loaded file on 2026-08-01 (P1-A structural fix,
    gap-doc candidate #3). Concurrent sessions on one machine each own their
    marker, so no session can ever stomp another's skills-loaded proof —
    telegram + cli sessions on the same server no longer block each other.
    This removes the entire guard class that was bolted onto the shared file
    (daemon guard, subagent guard, sticky-marker-per-lock).

    Content verification is preserved, so the touch bypass stays closed:
    a bare `touch` creates an empty file that fails the exact-match rule.

    Verification logic:
      - With session_id: the file must exist AND contain
        'session:{session_id}|skills:{current_fingerprint}' — the
        fingerprint pins the marker to the deployed skill versions it was
        created against, so a deploy that updates the skills invalidates
        old markers (skills-before-task gate, Luke 2026-08-05). Legacy
        'session:{session_id}' markers are accepted once (backward compat).
      - Without session_id (bootstrap/legacy callers): any valid per-session
        marker proves skills were loaded by SOME session
    """
    if session_id:
        try:
            path = _session_marker_path(session_id)
            if not path.exists():
                return False
            content = path.read_text().strip()
            if content == f"session:{session_id}":
                # Legacy marker (pre-fingerprint) — accept once; the next
                # skill_view round refreshes it with the fingerprint.
                return True
            return content == f"session:{session_id}|skills:{_skills_fingerprint()}"
        except (OSError, ValueError):
            return False
    # No session_id: accept any valid per-session marker
    try:
        if not _skills_marker_dir().exists():
            return False
        for path in _skills_marker_dir().iterdir():
            try:
                if path.is_file() and path.read_text().strip().startswith("session:"):
                    return True
            except OSError:
                continue
    except OSError:
        return False
    return False


def _skills_fingerprint() -> str:
    """Fingerprint of the deployed always-skills (skills-before-task gate).

    Computed from the mtimes of the 8 required skills' deployed SKILL.md
    files. When cortex-update.sh deploys new skill versions, the mtimes
    change → the fingerprint changes → previously-issued skills markers
    go stale → the agent MUST re-skill_view before write tools unblock.

    This enforces Luke's principle (2026-08-05): agents must USE skills
    before a task. The old marker check was existence-only, so after a
    deploy the stale marker passed and agents never loaded the new skill
    content — a 'dumb agent' failure. Fingerprinting makes the reload
    mandatory and mechanical, WITHOUT touching governance locks (the
    deploy lock-purge TZ bug was fixed separately — locks stay stable).

    Uses mtimes (not content hashes) for speed — the check runs on every
    write-tool call. mtime granularity (1s) is fine: a deploy that changes
    a skill updates its mtime.
    """
    import hashlib as _hl
    _h = _hl.md5()
    _skills_root = _skills_dir()
    for _name in sorted(_REQUIRED_SKILLS):
        _candidates = [
            _skills_root / _name / "SKILL.md",
            _skills_root / "devops" / _name / "SKILL.md",
            _skills_root / "software-development" / _name / "SKILL.md",
            _skills_root / "workflow" / _name / "SKILL.md",
        ]
        _found = ""
        for _c in _candidates:
            try:
                if _c.is_file():
                    _found = str(int(_c.stat().st_mtime))
                    break
            except OSError:
                continue
        _h.update(f"{_name}:{_found}|".encode())
    return _h.hexdigest()[:16]


def _skills_dir() -> Path:
    """Deployed skills root — resolves HERMES_HOME correctly.

    HERMES_HOME defaults to ~/.hermes and IS the .hermes dir when set
    explicitly (the gateway sets HERMES_HOME=/home/<user>/.hermes).
    Appending '/.hermes' to an already-set HERMES_HOME produced
    ~/.hermes/.hermes/skills (nonexistent), so _skills_fingerprint()
    computed from an EMPTY dir: a CONSTANT that never changed, silently
    defeating the skills-before-task fingerprint invalidation — markers
    never went stale after deploys, so agents were never forced to
    reload the always-skills mid-turn (found 2026-08-08 audit).
    """
    _home = Path(os.environ.get("HERMES_HOME", str(Path.home())))
    if (_home / "skills").is_dir():
        return _home / "skills"
    return _home / ".hermes" / "skills"


def _auto_create_skills_marker(session_id: str) -> None:
    """Write THIS session's per-session skills marker with session-proof content.

    Called automatically when all 8 required skills have been loaded
    via skill_view() in this session. Each session owns a marker file at
    state/skills-loaded/<session_id> — concurrent sessions can never
    overwrite each other (the pre-2026-08-01 shared .skills-loaded file had
    this race and required daemon/subagent/lock guards; per-session files
    make the whole guard class unnecessary).

    Content is 'session:{session_id}|skills:{fingerprint}' — prevents reuse
    across sessions, blocks `touch` bypass (empty file fails
    _check_skills_loaded_marker), and pins the marker to the deployed skill
    versions it was created against. After a deploy changes the skills, the
    fingerprint mismatches → marker stale → agent must re-skill_view.
    Written atomically (temp + rename) so a reader never sees a
    half-written marker.
    """
    if not session_id:
        return
    try:
        marker_dir = _skills_marker_dir()
        marker_dir.mkdir(parents=True, exist_ok=True)
        path = _session_marker_path(session_id)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(f"session:{session_id}|skills:{_skills_fingerprint()}")
        tmp.rename(path)  # atomic — readers never see a half-written marker
        log.info("Skills-loaded marker auto-created for session %s", session_id)

        # ── Also write this session's skills-state file ──
        # Tracks individual skill load times and workflow progress. Read by
        # block messages to show which skills are loaded. Per-session file
        # (skills-state/<session_id>.json) — no cross-session bleed.
        _sess_set = _session_skills_loaded.get(session_id, set())
        _write_skills_state(
            session_id,
            always_loaded=_sess_set.copy() if _sess_set else None,
            state_updates={"skill_source": "user_session"},
        )
    except (OSError, ValueError) as e:
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
        result = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            git_dir = result.stdout.strip()
            if git_dir:
                return Path(git_dir).name
    except (OSError, subprocess.TimeoutExpired):
        log.warning("Cannot derive repo slug via git rev-parse")

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


def _bypass_debt_count() -> int:
    """Read the consecutive --no-verify counter from bypass-debt.json.

    Bound the escape hatch (2026-08-05): 3 consecutive --no-verify commits
    are tolerated (logged + alerted by post-commit/watchdog); at >= 4 the
    hatch is EXHAUSTED and further --no-verify git commands are refused
    (even with a lock) until a fully verified commit resets the counter.
    Written by post-commit-audit; reset to 0 on every verified commit.
    """
    try:
        debt_file = Path.home() / ".hermes-cortex" / "state" / "bypass-debt.json"
        if debt_file.exists():
            data = json.loads(debt_file.read_text())
            return int(data.get("consecutive_no_verify", 0) or 0)
    except Exception:
        pass
    return 0


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

    # Proactively purge stale locks from any session (GAP #9).
    # P1-A hardening: an UNPARSEABLE lock file is a lock being written RIGHT
    # NOW (non-atomic write in loop-gov-mcp._write_lock) — deleting it steals
    # another session's fresh lock. Never delete unparseable files; only
    # delete locks that parse AND are stale. Also: a cron/daemon session
    # must never purge an interactive session's lock.
    current_type = _session_type(hermes_session_id)
    for lock_file in sorted(GOVERNANCE_STATE_DIR.glob(".governance-*.json")):
        try:
            state = json.loads(lock_file.read_text())
            if _is_lock_stale(state):
                # Cron/daemon sessions must not purge interactive locks
                lock_owner_type = _session_type(state.get("session_id", ""))
                if current_type in ("cron", "bg") and lock_owner_type == "interactive":
                    log.debug(
                        "Skipping stale interactive lock %s from %s session",
                        lock_file.name, current_type,
                    )
                    continue
                lock_file.unlink(missing_ok=True)
        except (json.JSONDecodeError, OSError):
            log.debug("Skipping unparseable lock file (possibly mid-write — leaving it, never delete): %s", lock_file.name)

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
                continue
            if state.get("task_id", ""):
                return True
        except (json.JSONDecodeError, OSError):
            log.debug("Skipping unparseable lock file (P1-A: possibly mid-write — leaving it, never delete): %s", lock_file.name)

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

# Tools that NEVER modify system state — completely exempt from skills gate
# These inspect, read, search, or discover — they can't create/edit/delete anything.
# The skills gate (write-tool block) must never block these, as that would
# create a deadlock where the agent can't read to determine what to load.
READ_TOOLS = {
    "read_file",
    "search_files",
    "session_search",
    "web_search",
    "web_extract",
    "vision_analyze",
    "skill_view",
    "skills_list",
    "tool_search",
    "tool_describe",
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


# Read-only terminal commands that NEVER need a governance lock.
# Fail-closed policy (2026-07-31, governance-improvement-plan-gaps G2):
# a terminal command is lock-free ONLY when it matches this strict allowlist
# AND contains no metacharacters that could compose a write. Everything else
# falls through to the governance lock check.
#
# Security invariants (from adversarial review):
#  - Interpreter -c forms (python3 -c, bash -c, node -e ...) are NEVER
#    allowlisted: "no write intent" is not observable from the command string
#    (G1). They stay hard-blocked without a lock.
#  - `doctor --fix` is NOT read-only (G3): it mutates the fleet.
#  - sqlite3 CLI is NOT allowlisted: `.shell`, `-cmd`, multi-statement, and
#    load_extension all execute beyond a SELECT (G4).
READONLY_COMMAND_PATTERNS = [
    r"^\s*(ls|cat|head|tail|less|more|grep|find|which|whoami|id|pwd|date|stat|file|du|wc|sort|uniq|diff|comm|env|printenv|getent|nproc|lscpu|lsblk|pgrep)(?:\s|$)",
    r"^\s*(ps|top|htop|df|free|uptime|uname|hostname|dmesg|journalctl|ss|netstat)(?:\s|$)",
    r"^\s*(git)\s+(status|log|diff|show|branch|stash\s+list)",
    r"^\s*(docker)\s+(ps|images|logs|inspect|stats)",
    r"^\s*(pip|npm)\s+(list|show|search)",
    r"^\s*(hermes)\s+(--version|doctor|config\s+get|config\s+show|config\s+path|config\s+check|env-path)",
    r"^\s*(systemctl)\s+(is-active|is-enabled|status|list-units)",
    # curl GET/HEAD health checks — read-only. POST/PUT/DELETE/-d/-o/-O/-F/-X
    # are excluded because they mutate remote or local state.
    r"^\s*curl\s+(-s\s+)?(-o\s+/dev/null\s+)?-s?I\s+",
    r"^\s*curl\s+(-s\s+)?-s\s+(https?://|file:///dev/|localhost:|127\.0\.0\.1:)",
]

# Metacharacters that make a command compound/write-capable — a read-allowlisted
# prefix with any of these appended is NOT read-only (e.g. `git status > file`,
# `ls | grep x`, `grep foo; rm bar`). Rejects redirects, pipes, separators,
# command substitution, and backgrounding.
_COMMAND_COMPOUND_METACHARS = re.compile(r"[>|;&`]|\$\(")


def _is_readonly_terminal_command(command: str) -> bool:
    """Fail-closed read-only terminal check.

    A terminal command is lock-free ONLY when:
      1. it matches a strict read-only allowlist pattern, AND
      2. it contains no compound metacharacters (>, |, ;, &, `, $(), newline)
         that could turn the read primitive into a write.

    Everything else (interpreters, sqlite3 CLI, curl POST, wget, ssh, scp,
    redirections, compound commands) requires a governance lock.
    """
    if not command:
        return False
    # `doctor --fix` mutates the fleet (P1-5 auto-reconcile) — never read-only
    if re.search(r"hermes\s+doctor", command) and re.search(r"--fix|-f\b", command):
        return False
    # Compound/redirect/pipe/background/substitution → NOT read-only
    if _COMMAND_COMPOUND_METACHARS.search(command):
        return False
    # Multi-line commands are never read-only
    if "\n" in command:
        return False
    for pattern in READONLY_COMMAND_PATTERNS:
        if re.search(pattern, command):
            return True
    return False


# ── Sanctioned lock-free recovery command ──────────────────────────
# The DOGFOOD gate (loop-gov-mcp.py _require_dogfood) blocks begin_change()
# until the deployed governance enforcer matches the repo source. That
# leaves the agent with NO governance lock, and the fail-closed terminal
# policy classifies cortex-update.sh as write-class — so the sanctioned
# recovery command was itself blocked: a structural deadlock.
#
# This EXACT-PATH exception is the single carve-out that breaks it:
#   - only the literal cortex-update.sh invocation (optional leading `bash`,
#     `~` or absolute HOME path, allowlisted flags) is exempt from the
#     governance-lock requirement
#   - the skills gate, domain gate, and adversarial gate all still apply
#     BEFORE this check — nothing else changes
#   - no sudo, no `-c`, no chaining, no metacharacters: the anchored regex
#     plus _COMMAND_COMPOUND_METACHARS rejection make the match exact
# The pre-commit hook advertises this exact command as "allowed for every
# agent" (AGENTS.md RULE 7b) — this makes that promise true.
_SANCTIONED_CORTEX_UPDATE_RE = re.compile(
    r"^\s*(?:bash\s+)?(?:~|" + re.escape(str(Path.home())) + r")/hermes-cortex/ops/scripts/cortex-update\.sh"
    r"(?:\s+(?:--dry-run|--status|--delta|--clean-stale))*\s*$"
)


def _is_sanctioned_cortex_update_command(command: str) -> bool:
    """Exact-match check for the ONE lock-free recovery command.

    Returns True only for the literal cortex-update.sh deploy invocation
    (with optional `bash` prefix, `~`/absolute home, and allowlisted flags).
    Anything else — other scripts, sudo, `-c`, chained commands, redirects,
    pipes — is NOT sanctioned and still requires a governance lock.
    """
    if not command:
        return False
    if _COMMAND_COMPOUND_METACHARS.search(command):
        return False
    return _SANCTIONED_CORTEX_UPDATE_RE.fullmatch(command) is not None


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
    if tool_name == "terminal":
        # Fail-closed terminal policy (2026-07-31): a terminal command is
        # write-class UNLESS it is strictly read-only (allowlist + no
        # compound metacharacters). This closes the historical fail-open:
        # `curl -X POST -d`, `wget URL`, `ssh host 'rm -rf'`, and
        # `git status > ~/.bashrc` all previously passed the lock check
        # because they didn't match WRITE_COMMAND_PATTERNS.
        command = args.get("command", "")
        return not _is_readonly_terminal_command(command)
    if tool_name == "cronjob" and _is_cronjob_write(args):
        return True
    if tool_name == "skill_manage" and _is_skill_write(args):
        return True
    if tool_name == "process" and _is_process_write(args):
        return True
    if tool_name == "computer_use" and _is_computer_use_write(args):
        return True
    return False


def _check_domain_skill_gate(tool_name: str, args: dict, session_id: str) -> Optional[dict]:
    """Check if the agent has loaded the domain skill for the file being written.

    Intelligence model:
      - Detects file type via extension, filename, or path context
      - First offense per session → WARN + educate (pass through)
      - Repeat offense per session → BLOCK (escalate)
      - Known gap (no skill exists) → pass through silently
      - Skill already loaded → pass through (clear warnings)
      - Context-aware: if agent just created a cron, suggest cron-job-management

    Returns None (pass through) or {"action": "warn"|"block", "message": str}.
    """
    # ── Cron/bg sessions are exempt from the domain-skill gate (2026-08-07) ──
    # This gate is an EDUCATIONAL mechanism for interactive sessions: it
    # makes the agent load the craft skill before writing so it follows
    # the skill's conventions. Cron sessions (cron_/bg_ prefixes) execute
    # pre-vetted prompts whose write targets were declared at install time,
    # and their enabled_toolsets may exclude the skills toolset entirely
    # (e.g. ["terminal","file"]) — skill_view() is NOT in the tool registry,
    # so the gate is structurally unsatisfiable and every write deadlocks
    # (dream nightly 2026-08-06: blocked writing ~/brain/*/dreams/*.md,
    # demanding documentation-auditing). The always-skills cron bootstrap
    # (_bootstrap_cron_skills) exists for the SAME reason: cron agents may
    # not have skill_view(). Security gates below (PII, adversarial,
    # bypass-debt, governance lock) still apply to cron/bg writes — only
    # the skill-loading education requirement is lifted for unattended
    # sessions that cannot legitimately satisfy it.
    if _session_type(session_id) in ("cron", "bg"):
        return None

    skill_name, why = _detect_domain_skill_needed(tool_name, args)
    if skill_name is None:
        return None  # No mapping or known gap — pass through

    # Check if skill is already loaded — per-session (2026-08-08): the old
    # check used the PROCESS-global _skills_loaded_in_session set, so a skill
    # loaded by ANY session satisfied the gate for every session. On long
    # turns, agents then skipped loading the mid-turn domain skill entirely.
    # The per-session registry forces THIS session to load the skill.
    if skill_name in _session_skills_loaded.get(session_id or "", set()):
        # Clear any prior warnings for this file type
        if session_id in _domain_warnings:
            _domain_warnings[session_id].pop(skill_name, None)
        return None  # Skill loaded — pass through silently

    # Also check context — was the previous action related?
    # If agent just created a cron, also check cron-job-management
    prev = _prev_action.get(session_id, {})
    context_skills = set()
    if prev.get("last_action") == "cronjob_create":
        context_skills.add("cron-job-management")
    if skill_name in context_skills or not skill_name:
        return None  # Context skill already covers it — pass through

    # Extract file info for the message
    path = args.get("path", "")
    if not path and tool_name == "skill_manage":
        fpath = args.get("file_path", "")
        fname = Path(fpath).name if fpath else "SKILL.md"
        path = f"~/.hermes/skills/{args.get('name', '')}/{fname}"
    fname = Path(path).name if path else "file"
    ext = Path(path).suffix.lower() if path and Path(path).suffix else fname

    # Track warnings per file-type key
    if session_id not in _domain_warnings:
        _domain_warnings[session_id] = {}
    warning_key = ext if ext else fname
    warning_count = _domain_warnings[session_id].get(warning_key, 0)
    _domain_warnings[session_id][warning_key] = warning_count + 1

    if warning_count == 0:
        # 1st offense: EDUCATE — block with a teaching message
        # The agent resolves this by loading the skill and retrying.
        msg = (
            f"💡 DOMAIN SKILL SUGGESTION\n\n"
            f"You are writing `{fname}` without `{skill_name}` loaded.\n\n"
            f"**{skill_name}** covers: {why}\n\n"
            f"Load it:\n"
            f"  skill_view(name='{skill_name}')\n\n"
            f"Or discover related skills:\n"
            f"  skills_list(category='devops')\n\n"
            f"The write is blocked until you load the skill. "
            f"Read-only tools ARE available.\n"
        )
        return {"action": "block", "message": msg}
    else:
        # 2nd+ offense: BLOCK
        msg = (
            f"⛔ DOMAIN SKILL REQUIRED\n\n"
            f"You have been warned {warning_count} time(s) this session about "
            f"writing `{ext if ext else fname}` files without loading `{skill_name}`.\n\n"
            f"This skill exists to prevent the exact type of mistakes you keep making:\n"
            f"  {why}\n\n"
            f"You must load it before writing:\n"
            f"  skill_view(name='{skill_name}')\n\n"
            f"After loading, retry the write. Read-only tools ARE still available.\n"
        )
        return {"action": "block", "message": msg}


# ── PII content gate ────────────────────────────────────
# Real email addresses in the SHARED surface (~/.hermes/skills and
# ~/hermes-cortex — the public repo) block the write. This closes the
# gap where skill_manage writes never pass a git commit (so the
# pre-commit secret-leak-detector never ran) — see the 2026-08-04
# Titus PII incident. Writes OUTSIDE the shared surface (client
# projects, /tmp, other repos) are never blocked — the git hook still
# warns at commit time. Placeholder domains are allowlisted.
# NOTE: keep PLACEHOLDER_DOMAIN_RE in sync with
# ops/scripts/secret-leak-detector.sh (PLACEHOLDER_DOMAIN_RE).
_PII_EMAIL_RE = re.compile(
    r"[A-Za-z0-9._%+-]+@[A-Za-z][A-Za-z0-9.-]*\.[A-Za-z]{2,}"
)
_PLACEHOLDER_DOMAIN_RE = re.compile(
    r"^(|.*\.)(example\.(com|org|net)|client-domain\.com|customer\.org|"
    r"contoso\.com|test\.com|email\.com|b\.com|ex\.com|github\.com|"
    r"gitlab\.com|pinggy\.io|localhost\.run|openssh\.com|libssh\.org|"
    r"cluster\.mongodb\.net|all-hands\.dev|agentmail\.to|domain\.tld|"
    r"test|local|internal|acme)$"
)
_HERMES_CORTEX_REPO = Path.home() / "hermes-cortex"
_HERMES_SKILLS_DIR = Path.home() / ".hermes" / "skills"


def _skill_write_content(args: dict) -> str:
    """Extract the text being written by a skill_manage call (may be '')."""
    action = args.get("action", "")
    if action == "patch":
        return args.get("new_string", "")
    if action in ("create", "edit"):
        return args.get("content", "")
    if action == "write_file":
        return args.get("file_content", "")
    return ""


def _is_shared_surface_path(path: str) -> bool:
    """True when the target is the public repo or the shared skill lib."""
    if not path:
        return False
    p = str(Path(path).expanduser().resolve())
    repo = str(_HERMES_CORTEX_REPO.resolve())
    skills = str(_HERMES_SKILLS_DIR.resolve())
    return (
        p == repo
        or p.startswith(repo + os.sep)
        or p.startswith(skills + os.sep)
    )


def _check_pii_content_gate(tool_name: str, args: dict) -> Optional[dict]:
    """Block writes of real email addresses into the shared surface.

    Returns None (pass) or {"action": "block", "message": str}.
    """
    if tool_name == "skill_manage":
        content = _skill_write_content(args)
        shared = True  # skill_manage always targets ~/.hermes/skills
    elif tool_name in ("write_file", "patch"):
        content = (
            args.get("content", "")
            or args.get("new_string", "")
            or args.get("patch", "")
        )
        shared = _is_shared_surface_path(args.get("path", ""))
    else:
        return None
    if not content or not shared:
        return None

    bad_domains = set()
    for email in _PII_EMAIL_RE.findall(content):
        domain = email.split("@", 1)[1]
        if not _PLACEHOLDER_DOMAIN_RE.match(domain):
            bad_domains.add(domain)
    if not bad_domains:
        return None

    domain_list = ", ".join(sorted(bad_domains))
    return {
        "action": "block",
        "message": (
            "🛑 PII GUARD — real email address in content being written.\n\n"
            "Tool '" + tool_name + "' is writing into the shared surface "
            "(hermes-cortex repo or ~/.hermes/skills), and the content "
            "contains email addresses on non-placeholder domain(s): "
            + domain_list + "\n\n"
            "Rule 16 (agent-contract): never commit real email addresses, "
            "domains, or credentials. Replace them with placeholders:\n"
            "  admin@client-domain.com   (not a real address)\n"
            "  example.com               (not a real domain)\n\n"
            "The write is blocked until the PII is removed. Writes to "
            "client/project paths outside the shared surface are not "
            "affected.\n"
        ),
    }


def _check_adversarial_commit_gate(
    tool_name: str, args: dict, session_id: str,
) -> Optional[dict]:
    """Check if the agent has loaded adversarial-verifier before committing/pushing
    critical-system changes.

    Same 💡/⛔/✅ pattern as the domain skill gate. Blocks git commit/push
    when staged changes touch critical paths and adversarial-verifier hasn't
    been loaded in this session.

    Returns None (pass through) or {"action": "block", "message": str}.
    """
    if tool_name != "terminal":
        return None
    command = args.get("command", "")
    if not any(re.search(p, command) for p in _ADVERSARIAL_COMMIT_PATTERNS):
        return None

    # Skill already loaded — clear warnings and pass (per-session, 2026-08-08)
    if "adversarial-verifier" in _session_skills_loaded.get(session_id or "", set()):
        _adversarial_warnings.pop(session_id, None)
        return None

    # Check what files are about to be shipped
    try:
        if re.search(r"^\s*git\s+commit\b", command):
            result = subprocess.run(["git", "diff", "--cached", "--name-only"], capture_output=True, text=True, timeout=5, cwd=Path.home() / "hermes-cortex")
        else:
            # git push — check commits to push
            result = subprocess.run(["git", "diff", "@{upstream}..HEAD", "--name-only"], capture_output=True, text=True, timeout=5, cwd=Path.home() / "hermes-cortex")
        if result.returncode != 0:
            # May not have upstream — check last commit
            result = subprocess.run(["git", "diff", "HEAD~1..HEAD", "--name-only"], capture_output=True, text=True, timeout=5, cwd=Path.home() / "hermes-cortex")
        staged = [s.strip() for s in result.stdout.strip().split("\n") if s.strip()]
    except (OSError, subprocess.TimeoutExpired):
        return None  # Can't determine — don't block

    # Check if any staged/pushed file is in a critical path
    critical_hits = []
    for staged_file in staged:
        for critical_path in _ADVERSARIAL_CRITICAL_PATHS:
            if staged_file == critical_path or staged_file.startswith(critical_path):
                critical_hits.append(staged_file)
                break

    if not critical_hits:
        return None  # No critical paths affected — pass

    # Format readable path descriptions
    path_descriptions = set()
    for hit in critical_hits:
        for prefix, desc in _ADVERSARIAL_DISPLAY.items():
            if hit.startswith(prefix):
                path_descriptions.add(desc)
                break

    # Track warnings
    count = _adversarial_warnings.get(session_id, 0)
    _adversarial_warnings[session_id] = count + 1

    if count == 0:
        msg = (
            "⛔ ADVERSARIAL VERIFICATION REQUIRED\n\n"
            "You are shipping changes to "
            + ", ".join(sorted(path_descriptions))
            + " without adversarial verification loaded.\n\n"
            "Adversarial verification is MANDATORY for these paths — "
            "not a suggestion (Luke directive 2026-08-04).\n\n"
            "**adversarial-verifier** systematically breaks code before it ships. "
            "Load it, then run the gate on every changed file:\n\n"
            "  skill_view(name='adversarial-verifier')\n"
            "  python3 ~/.hermes-cortex/scripts/adversarial-verify.py \\\n"
            "      --file <changed-file> --level A2 --gate\n"
            "  # A4 for security/guard/hook/enforcer files\n\n"
            "Then retry the commit. The pre-commit hook's adversarial gate will "
            "also block critical/high findings — this check requires the skill "
            "to be loaded at all.\n"
        )
        return {"action": "block", "message": msg}

    msg = (
        "⛔ ADVERSARIAL VERIFICATION REQUIRED\n\n"
        f"You have been warned {count} time(s) this session about shipping "
        "critical changes without adversarial verification.\n\n"
        "You must load and run it before shipping:\n"
        "  skill_view(name='adversarial-verifier')\n"
        "  python3 ~/.hermes-cortex/scripts/adversarial-verify.py \\\n"
        "      --file <changed-file> --level A2 --gate\n\n"
        "Then retry the command.\n"
    )
    return {"action": "block", "message": msg}


def _on_session_start(session_id: str, **kwargs):
    """Write session marker at session start so MCP finds it before begin_change.

    For cron/automated sessions (session_id starts with 'cron_'), also
    auto-create the .skills-loaded marker if the 8 required always-section
    skills exist on disk. This breaks the bootstrapping deadlock where cron
    sessions can't load skills because all tools are blocked.

    Interactive sessions are unaffected — they still require skill_view()
    calls to create the marker, maintaining full governance security.
    """
    if not session_id:
        log.debug("_on_session_start without session_id — skipping marker")
        return
    try:
        if session_id:
            _write_session_marker(session_id)

            # ── Cron bootstrap: auto-create per-session skills marker ──
            # Cron sessions start fresh with no skills-loaded marker. The
            # enforcer blocks all write tools until skills are loaded, but
            # cron agents may not have skill_view() in their tool registry.
            # This bootstrap reads the always-section skills from disk and
            # pre-creates the marker, so cron agents can proceed normally.
            #
            # Markers are per-session files (skills-loaded/<session_id>),
            # so a cron session creating its own marker can never touch
            # another session's proof (pre-2026-08-01 shared-file race is
            # structurally gone — no "first marker owns the boot cycle"
            # rule needed anymore).
            if session_id.startswith("cron_"):
                if _session_marker_path(session_id).exists():
                    log.debug(
                        "Cron session %s skipped bootstrap — marker already exists",
                        session_id[:20],
                    )
                elif not _check_skills_loaded_marker(session_id):
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
        "Cron bootstrap: skills marker + state created for session %s "
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

            # ── Per-call session-ID injection into MCP governance calls ──
            # The loop-governance MCP server is ONE shared process serving ALL
            # sessions (spawned once per gateway). Its get_session_id() can
            # never learn the caller's Hermes session from a shared marker
            # file — concurrent sessions clobber .hermes-session-current.id
            # (the harden-hook cross-session lock bug). The enforcer runs
            # IN the gateway and knows the real session_id from kwargs, so it
            # injects it into the tool call args. args is passed by reference
            # through invoke_hook → tool executor → mcp_tool._handler →
            # session.call_tool(arguments=args), so the MCP server sees
            # session_id on every call — transparent to the agent session.
            if (
                hermes_session_id
                and isinstance(args, dict)
                and tool_name.startswith("mcp__loop_governance__")
            ):
                args["session_id"] = hermes_session_id

            # ── Track skill_view calls ──
            # Moved BEFORE the skills gate so agents can load skills.
            # When all 8 required skills are loaded, the marker is
            # auto-created with session-proof content.
            #
            # Per-session tracking (2026-08-08 — cross-session bleed fix):
            # the old code added to the PROCESS-global _skills_loaded_in_session
            # set and checked THAT for the 8-skill condition — concurrent
            # sessions contributed to each other's count, so a session that
            # loaded 2 skills could get a valid marker. Now each session has
            # its own set (_session_skills_loaded[session_id]) and must load
            # all 8 itself. The global set is retained only for the legacy
            # auto-create path and block-message summary.
            if tool_name == "skill_view":
                skill_name = args.get("name", "")
                if skill_name:
                    _skills_loaded_in_session.add(skill_name)
                    if hermes_session_id:
                        _session_skills_loaded.setdefault(hermes_session_id, set()).add(skill_name)
                        if _session_skills_loaded[hermes_session_id] >= _REQUIRED_SKILLS:
                            _auto_create_skills_marker(hermes_session_id)

            # ── Read-only tools exempt from skills gate ─────────────
            # Read-only tools (read_file, search_files, web_search, skill_view, etc.)
            # are completely exempt from the skills gate. They can't modify system state,
            # and blocking them creates a deadlock where the agent can't read to
            # determine what skills to load. This check runs BEFORE the skills gate.
            if tool_name in READ_TOOLS:
                return None

            # ── Read-only terminal fast-path: BEFORE skills gate ─────
            # Allow strictly read-only terminal commands (ls, pwd, grep, git
            # status, curl -sI, etc.) even without skills loaded, so agents
            # can inspect the system. Strict = allowlist match AND no compound
            # metacharacters (>, |, ;, &, `, $(), newline). Everything else
            # (interpreters, sqlite3 CLI, curl POST, wget, ssh, redirections)
            # falls through to the skills gate + governance lock check.
            if tool_name == "terminal":
                command = args.get("command", "")
                if _is_readonly_terminal_command(command):
                    return None

            # ── Sanctioned lock-free recovery command ──
            # The DOGFOOD gate (loop-gov-mcp.py _require_dogfood) blocks
            # begin_change() until repo == deployed, so a DOGFOOD-blocked
            # agent holds NO governance lock AND may have no skills marker
            # (cortex-update.sh invalidates it on deploy; AGENTS.md RULE 7b
            # order: run cortex-update.sh → reload 8 skills → re-acquire
            # lock). The ONLY sanctioned way to deploy the enforcement
            # chain is cortex-update.sh — this EXACT invocation (exact
            # path, allowlisted flags, no metacharacters, no sudo, no
            # chaining) is allowed lock-free and skill-free so the agent
            # can self-recover. Everything else still requires the skills
            # gate + governance lock. Enforced by _is_sanctioned_cortex_update_command.
            if (
                tool_name == "terminal"
                and _is_sanctioned_cortex_update_command(args.get("command", ""))
            ):
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
                    # ── Build helpful block message ──
                    # Read this session's skills-state file to show which
                    # skills are loaded.
                    loaded = _get_loaded_skills_summary(hermes_session_id)
                    loaded_count = sum(1 for v in loaded.values() if v)
                    loaded_list = ", ".join(
                        f"✅ {s}" if loaded[s] else f"  {s}"
                        for s in _REQUIRED_SKILLS
                    )
                    return {
                        "action": "block",
                        "message": (
                            "🛑 Write tool blocked — session skills not fully loaded.\n\n"
                            "Tool '" + tool_name + "' modifies state — "
                            + str(loaded_count) + "/8 always-section skills loaded.\n\n"
                            "Required always-section skills:\n"
                            + loaded_list + "\n\n"
                            "Load all 8 with:\n"
                            "  1. skill_view('task-start')        # bundles the complete sequence\n"
                            "  2. skill_view('agent-flow')        # workflow router\n"
                            "  3. skill_view('reasoning-patterns') # choose how to think\n"
                            "  4. skill_view('reflexion-check')   # self-critique before deliver\n"
                            "  5. skill_view('change-checklist')  # pre-ship verification\n"
                            "  6. skill_view('survey-before-action')  # check existing resources\n"
                            "  7. skill_view('cortex-preflight')  # repo-specific pre-flight\n"
                            "  8. skill_view('agent-contract')    # execution rules\n\n"
                            "The marker is auto-created when all 8 are loaded.\n"
                            "Do NOT try to set skills-state.json directly — it will be rejected.\n\n"
                            "Read-only tools (read_file, search_files, session_search,\n"
                            "skill_view, skills_list, web_search, web_extract,\n"
                            "vision_analyze, tool_search, tool_describe,\n"
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

            # ── Track previous action context ──
            # Connects related operations — if agent just created a cron,
            # the next write_file(.sh) knows it's a cron script.
            if hermes_session_id and tool_name == "cronjob" and args.get("action") == "create":
                _prev_action[hermes_session_id] = {"last_action": "cronjob_create"}
            elif hermes_session_id:
                # Track other write tools for context awareness
                current_action = None
                if tool_name == "write_file":
                    current_action = "write_file"
                elif tool_name == "terminal":
                    current_action = "terminal"
                if current_action:
                    _prev_action[hermes_session_id] = {"last_action": current_action}

            # ── Domain skill gate ──
            # Before write_file/patch: require domain skill loading.
            # First block educates. Repeat block escalates.
            # After the agent loads the skill, the gate passes silently.
            domain_result = _check_domain_skill_gate(tool_name, args, hermes_session_id)
            if domain_result is not None:
                # Block with educational message
                return domain_result

            # ── PII content gate ──
            # Real emails in shared-surface writes (hermes-cortex repo,
            # ~/.hermes/skills) block before the write lands. skill_manage
            # never passes a git commit, so this is the only layer that
            # catches PII in skill content (Titus 2026-08-04 incident).
            pii_result = _check_pii_content_gate(tool_name, args)
            if pii_result is not None:
                return pii_result

            # ── Adversarial commit gate ──
            # Before git commit/push of critical-system changes: require
            # adversarial-verifier loaded. Same 💡/⛔/✅ as domain gate.
            adversarial_result = _check_adversarial_commit_gate(
                tool_name, args, hermes_session_id,
            )
            if adversarial_result is not None:
                return adversarial_result

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

            # ── Bypass-debt mandate (2026-08-05) + hook-override gate (2026-08-08) ──
            # Bound the --no-verify escape hatch: 3 consecutive bypasses are
            # tolerated (logged + alerted); the 4th+ is MANDATED — refuse
            # further --no-verify git commands (even with a lock) until a
            # fully verified commit (pre-commit ran, sentinel written) resets
            # the counter. --no-verify skips every hook, so the primary
            # enforcement layer must refuse it at the tool gate.
            #
            # Per-invocation hook overrides (-c core.hooksPath=..., env
            # GIT_CONFIG_GLOBAL/SYSTEM=...) are a SECOND bypass class that the
            # old --no-verify-only regex never saw: they skip EVERY hook
            # INCLUDING post-commit-audit, so the debt counter can never
            # increment and the escape-hatch budget is unbounded. These are
            # blocked outright (2026-08-08) — they are not the sanctioned
            # escape hatch. The sanctioned path is a normal verified commit,
            # or at most a bounded --no-verify.
            if tool_name == "terminal":
                _cmd = str(args.get("command", ""))
                _no_verify = re.search(
                    r"\bgit\b[^|;&\n]*--no-verify",
                    _cmd,
                )
                _hook_override = re.search(
                    r"\bgit\b[^|;&\n]*(?:-c\s+(?:core\.)?hooksPath|"
                    r"(?:core\.)?hooksPath\s*=|"
                    r"GIT_CONFIG_(?:GLOBAL|SYSTEM)\s*=|"
                    r"GIT_DIR\s*=)",
                    _cmd,
                )
                # Env-prefixed form: GIT_CONFIG_GLOBAL=/dev/null git commit
                # has the override BEFORE git, which the git-first regex
                # misses. Match env vars anywhere in the command segment.
                if not _hook_override:
                    _hook_override = re.search(
                        r"(?:GIT_CONFIG_(?:GLOBAL|SYSTEM)\s*=|GIT_DIR\s*=)[^|;&\n]*\bgit\b",
                        _cmd,
                    )
                if _no_verify:
                    _debt = _bypass_debt_count()
                    if _debt >= 4:
                        return {
                            "action": "block",
                            "message": (
                                "🚫 ESCAPE HATCH EXHAUSTED — "
                                + str(_debt)
                                + " consecutive --no-verify commits.\n\n"
                                "Tool 'terminal' command uses --no-verify, which skips every "
                                "governance hook. The 4th bypass is MANDATED: the escape hatch "
                                "is closed until a fully verified commit lands.\n\n"
                                "Do this instead:\n"
                                "  1. Commit WITHOUT --no-verify so the pre-commit hook runs "
                                "(scoring + adversarial + append-only guards)\n"
                                "  2. A verified commit resets the counter to 0\n"
                                "  3. Only then may up to 3 bypasses be used again\n\n"
                                "This enforcement comes from ~/.hermes/plugins/governance-enforcer/."
                            ),
                        }
                if _hook_override:
                    return {
                        "action": "block",
                        "message": (
                            "🚫 GIT HOOK BYPASS DETECTED — the command overrides git's "
                            "hook execution path per-invocation.\n\n"
                            "  Command: " + _cmd[:160] + "\n\n"
                            "`-c core.hooksPath=...`, `core.hooksPath=...` and "
                            "`GIT_CONFIG_GLOBAL/SYSTEM=...` skip EVERY governance hook "
                            "including post-commit-audit, so the --no-verify debt counter "
                            "can never track them. This is NOT the sanctioned escape hatch "
                            "and is blocked outright.\n\n"
                            "Do this instead:\n"
                            "  1. Commit with a normal verified command so the pre-commit "
                            "hook runs (scoring + adversarial + audit)\n"
                            "  2. If a repo legitimately needs custom hooks, set "
                            "core.hooksPath as REPO CONFIG (the doctor validates it) — "
                            "never per-invocation\n\n"
                            "This enforcement comes from ~/.hermes/plugins/governance-enforcer/."
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
