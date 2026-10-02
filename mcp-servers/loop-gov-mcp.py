#!/usr/bin/env python3.12
"""
Loop Governance MCP Server — exposes loop governance DB, config,
feedback, and embedding cache as MCP tools.

Usage:
    hermes mcp add --command python3 --args /path/to/loop-gov-mcp.py loop-governance

Tools:
    begin_change    Acquire a governance lock (with session ID, TTL, force override)
    end_change      Release a governance lock (requires scored cycle)
    check_lock      Check lock state, update heartbeat, auto-release stale locks
    cycle_query     Query scored cycles by task, score range, date
    cycle_stats     Summary statistics
    config_show     Show current thresholds/weights
    config_set      Modify a threshold or weight
    feedback_accept Mark a decision as correct
    feedback_override Override a decision
    cache_search    Search the embedding cache
"""
import asyncio
import importlib.util
import hashlib
import json
import logging
import os
import re
import shlex
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# ── Task State Machine ───────────────────────────────────────
# Harness v3 state machine (derived from v2 §5)

TASK_STATES = {
    "idle", "planning", "executing", "verifying", "reporting",
    "completed", "blocked", "cancelled", "suspended", "interrupt_req",
}

TERMINAL_STATES = {"completed", "cancelled"}

VALID_TRANSITIONS = {
    "idle":         {"planning"},
    "planning":     {"executing", "blocked", "cancelled"},
    "executing":    {"verifying", "blocked", "interrupt_req", "cancelled"},
    "verifying":    {"reporting", "executing", "blocked", "cancelled"},
    "reporting":    {"completed", "executing", "cancelled"},
    "blocked":      {"planning", "cancelled"},
    "interrupt_req": {"suspended", "cancelled"},
    "suspended":    {"executing", "cancelled"},
}


def is_valid_transition(from_state: str, to_state: str) -> bool:
    """Check if a state transition is valid per the state machine."""
    if from_state in TERMINAL_STATES:
        return False
    allowed = VALID_TRANSITIONS.get(from_state, set())
    return to_state in allowed


# Ensure hermes_models.py is importable. Candidates in order:
#   1. ~/.hermes/scripts            — Hermes agent scripts dir (often a symlink
#      to ~/.hermes-cortex/scripts, but NOT guaranteed — macOS hosts can lack it)
#   2. ~/.hermes-cortex/scripts     — canonical deploy location; cortex-update.sh
#      registers hermes_models.py here on EVERY host (add 2026-08-25: the old
#      _REPO_SCRIPTS computed ~/.hermes-cortex/tools/scripts which never exists)
#   3. <script_dir>/scripts         — repo-layout fallback (mcp-servers/../scripts)
_HERMES_HOME = Path.home() / ".hermes"
_HERMES_SCRIPTS = _HERMES_HOME / "scripts"
_CORTEX_DEPLOY_SCRIPTS = Path.home() / ".hermes-cortex" / "scripts"
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_SCRIPTS = _SCRIPT_DIR.parent / "scripts"
for _candidate in (_HERMES_SCRIPTS, _CORTEX_DEPLOY_SCRIPTS, _REPO_SCRIPTS):
    if _candidate.exists():
        sys.path.insert(0, str(_candidate))

# Fail-soft: hermes_models is a model-name LOOKUP with a documented default —
# NOT an enforcement gate. If it cannot be imported (e.g. macOS host without
# the ~/.hermes/scripts symlink), degrade to the default instead of killing the
# MCP server at import (Titus 2026-08-25: "subprocess has exited", governance
# lockout). The embedding model only affects scoring quality, never enforcement.
try:
    from hermes_models import get_model

    NOMIC_MODEL = get_model("EMBEDDING_MODEL", "nomic-embed-text:v1.5")
except Exception as _model_lookup_err:
    NOMIC_MODEL = "nomic-embed-text:v1.5"
    print(
        "[mcp-server] WARNING: hermes_models.py not importable "
        f"({_model_lookup_err.__class__.__name__}: {_model_lookup_err}) — "
        f"using default embedding model '{NOMIC_MODEL}'",
        file=sys.stderr,
    )

# ── Dependency Check: mcp package ────────────────────────────
_HAVE_MCP = importlib.util.find_spec("mcp")
if _HAVE_MCP is None:
    # NOT a hard exit. The tool handlers are SDK-independent, so the module must
    # stay importable and drivable on a host with no MCP client — that is the
    # whole point of the CLI adapter. Only the stdio SERVER needs the SDK, and
    # main() refuses cleanly without it. Exiting here made the guard below
    # unreachable and broke governance for exactly the hosts this serves.
    print("[mcp-server] WARNING: the 'mcp' package is not installed — the stdio "
          "server cannot start; the CLI adapter (ops/scripts/loop-gov.py) still "
          "works.\n"
          f"[mcp-server]   {sys.executable} -m pip install mcp", file=sys.stderr)

log = logging.getLogger("loop-governance")
logging.basicConfig(level=logging.DEBUG, format="[mcp-server] %(levelname)s: %(message)s", stream=sys.stderr, force=True)

try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent, CallToolResult, ListToolsResult
    MCP_AVAILABLE = True
except ImportError:  # pragma: no cover — governance without the MCP SDK
    # Governance must be usable by a host with no MCP client (Pi). Rather than
    # fork the implementation, this module stays importable without the SDK: the
    # handlers below build CallToolResult/TextContent objects, so minimal
    # stand-ins keep the SAME code path working. The CLI is then an adapter over
    # this file, not a second implementation of it.
    MCP_AVAILABLE = False

    class TextContent:  # type: ignore[no-redef]
        def __init__(self, type: str = "text", text: str = ""):
            self.type = type
            self.text = text

        def model_dump(self) -> dict:
            return {"type": self.type, "text": self.text}

    class CallToolResult:  # type: ignore[no-redef]
        def __init__(self, content: list | None = None, is_error: bool = False):
            self.content = content or []
            self.is_error = is_error

        def model_dump(self) -> dict:
            return {
                "content": [c.model_dump() if hasattr(c, "model_dump") else c
                            for c in self.content],
                "isError": self.is_error,
            }

    class Tool:  # type: ignore[no-redef]
        def __init__(self, name: str = "", description: str = "",
                     inputSchema: dict | None = None, input_schema: dict | None = None):
            self.name = name
            self.description = description
            # The real SDK (and every call site here) uses the camelCase
            # `inputSchema`; accept both so the shim cannot diverge from it.
            self.input_schema = inputSchema if inputSchema is not None else (input_schema or {})

    class ListToolsResult:  # type: ignore[no-redef]
        def __init__(self, tools: list | None = None):
            self.tools = tools or []

    class Server:  # type: ignore[no-redef]
        """Placeholder: the stdio server is only constructed when MCP is present."""

        def __init__(self, *args, **kwargs):
            pass

    def stdio_server():  # type: ignore[no-redef]
        raise RuntimeError("the MCP SDK is not installed — run the CLI adapter instead")

HOME = Path.home()
SESSION_FILE = HOME / ".hermes" / "session.id"

# Process-scoped session id for NON-Hermes callers (2026-09-29).
#
# Hermes callers get args["session_id"] injected by the enforcer (Priority 0).
# Non-Hermes callers (Claude Code via .mcp.json) do NOT — and the old fallback
# read the HOST-GLOBAL ~/.hermes/session.id cache, which every session shares:
# two Claude invocations (or Claude + a live Hermes session on the same box)
# resolved to the SAME id, so begin_change from one blocked the next and any
# session could release a lock it didn't own.
#
# Claude Code spawns one stdio MCP child per session/project, so a per-process
# id is a correct session discriminator: stable across begin→end within one
# Claude session, disjoint across concurrent sessions, and never the Hermes id.
#
# We also STOP reading the Hermes marker files (~/.hermes-cortex/state/
# .hermes-session-*) on this path — those belong to whatever Hermes session
# last wrote them and are the collision source. If no per-call id was injected
# we are a non-Hermes caller; use our own process id.
_PROCESS_SESSION_ID: str = ""
LOOP_DB = HOME / ".hermes-cortex" / "data" / "loop-governance.db"
CONFIG_PATH = HOME / ".hermes-cortex" / "data" / "loop-governance-config.json"
CACHE_DB = HOME / ".hermes-cortex" / "data" / "session-embeddings.db"
GOVERNANCE_STATE_DIR = HOME / ".hermes-cortex" / "state"
DEFAULT_TTL = 3600  # 1 hour


# ── Dogfood Gate ─────────────────────────────────────────────
# Structural enforcement: begin_change checks if the deployed governance
# plugin matches the repo source. If not, the agent pushed code but didn't
# run cortex-update.sh to deploy it locally. Block until they dogfood.

import hashlib as _dogfood_hashlib

GOVERNANCE_REPO_PATH = HOME / "hermes-cortex" / "plugins" / "governance-enforcer" / "__init__.py"
GOVERNANCE_DEPLOY_PATH = HOME / ".hermes" / "plugins" / "governance-enforcer" / "__init__.py"


def _require_dogfood() -> Optional[str]:
    """Check if deployed plugin matches repo source.

    Returns None if everything matches (dogfood is up to date).
    Returns an error string blocking the change if dogfood is needed.
    """
    repo_file = GOVERNANCE_REPO_PATH
    deploy_file = GOVERNANCE_DEPLOY_PATH

    if not repo_file.exists() or not deploy_file.exists():
        return None  # Can't check either path — allow

    try:
        repo_hash = _dogfood_hashlib.sha256(repo_file.read_bytes()).hexdigest()
        deploy_hash = _dogfood_hashlib.sha256(deploy_file.read_bytes()).hexdigest()

        if repo_hash != deploy_hash:
            return (
                "❌  DOGFOOD REQUIRED\n\n"
                "    You pushed code to the repo but haven't deployed it locally.\n"
                "    The governance plugin at ~/.hermes/plugins/governance-enforcer/ differs from\n"
                "    the repo source (the commit you just pushed).\n\n"
                "    Dogfooding means: deploy AND test.\n"
                "      1. bash ~/hermes-cortex/ops/scripts/cortex-update.sh\n"
                "         (this exact command is sanctioned to run WITHOUT a governance lock;\n"
                "          the enforcer allows it lock-free so you can self-recover)\n"
                "      2. Run the changed code path — verify it works with actual output\n"
                "      3. Run doctor, fix every issue it reports\n"
                "      4. Run doctor again — confirm clean before claiming anything\n\n"
                "    Then call begin_change again (the deploy purged locks).\n"
                "    If the sanctioned command runs but write tools are STILL blocked:\n"
                "    deploy ≠ load — the gateway hasn't restarted. The new enforcer activates\n"
                "    only after the operator restarts the gateway service (agents cannot).\n"
                "    This enforcement is structural — cannot be bypassed."
            )
    except (OSError, PermissionError, FileNotFoundError) as _read_err:
        log.warning("Could not read governance files for dogfood check: %s", _read_err)
        # If files can't be read, allow through (dogfood check is best-effort)
    return None


# ── Session ID ───────────────────────────────────────────────

def get_session_id(args: dict | None = None) -> str:
    """Return a persistent session ID, creating one on first call.

    Resolution order:
    0. Per-call session_id injected into the tool call args by the
       governance-enforcer plugin (Hermes gateway). The ONLY reliable signal
       for Hermes: the MCP server is one shared process for all Hermes
       sessions, and the shared marker files below are clobbered by concurrent
       sessions.
    1. Non-Hermes caller (no per-call id): a PROCESS-scoped id, generated once
       per MCP server process. Claude Code spawns one stdio child per
       session/project, so this is a correct session discriminator. We do NOT
       fall back to the host-global ~/.hermes/session.id cache or the Hermes
       marker files — those are shared by every session and caused
       begin/end to collide across concurrent Claude+Hermes sessions
       (2026-09-29).

    The old Priority 1-3 marker-file fallbacks were REPLACED by the
    process-scoped id. Rationale: the markers only ever hold the last Hermes
    session id, so a non-Hermes caller adopting them stole another session's
    identity instead of getting its own. A per-process id cannot collide.
    """
    # Priority 0: per-call session ID injected by the enforcer plugin
    if isinstance(args, dict):
        sid = args.get("session_id", "")
        if isinstance(sid, str) and sid.strip():
            sid = sid.strip()
            SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            SESSION_FILE.write_text(sid)
            return sid

    # Priority 1: process-scoped id for non-Hermes callers — stable per MCP
    # child (per Claude session), disjoint across concurrent sessions, and
    # never adopts another session's Hermes id. PERSISTED per project
    # (repo slug of cwd, same resolution the git hooks use) so the id
    # survives an MCP-child restart mid-session (adversarial finding
    # ADV-2872-2: an in-memory-only id orphans the lock when Claude Code
    # restarts the server between begin_change and end_change). Same-project
    # sharing is correct governance semantics — begin_change already
    # serializes a repo to one active change; cross-PROJECT ids stay disjoint,
    # which is the collision class this fix removes.
    global _PROCESS_SESSION_ID
    if not _PROCESS_SESSION_ID:
        slug = _derive_slug()
        persist = GOVERNANCE_STATE_DIR / f".session-{slug}.id"
        try:
            if persist.exists():
                cached = persist.read_text().strip()
                if cached:
                    _PROCESS_SESSION_ID = cached
            if not _PROCESS_SESSION_ID:
                _PROCESS_SESSION_ID = f"sess_{uuid.uuid4().hex[:12]}"
                GOVERNANCE_STATE_DIR.mkdir(parents=True, exist_ok=True)
                persist.write_text(_PROCESS_SESSION_ID)
        except OSError:
            # Persist failure must not break the session — fall back to the
            # in-memory id (restart orphan risk returns, but the lock system
            # still works for the common no-restart path).
            if not _PROCESS_SESSION_ID:
                _PROCESS_SESSION_ID = f"sess_{uuid.uuid4().hex[:12]}"
    return _PROCESS_SESSION_ID


# ── Governance Lock Path ─────────────────────────────────────

def _derive_slug() -> str:
    """Derive repo slug matching the enforcer plugin's approach.

    The MCP server is a shared daemon spawned by the gateway: its own cwd is
    a launch artifact (often the hermes-agent checkout, itself a git repo) and
    is NEVER a reliable signal of the session's working repo. Trusting
    ``git rev-parse`` from cwd first made locks carry ``hermes-agent`` while
    the git hooks (which derive the slug from the repo they run in) expected
    ``hermes-cortex`` — the lock never matched and every commit/push on
    hermes-cortex was blocked. So the canonical governed repo is resolved
    FIRST; the cwd git repo is only a fallback for project-repo-only hosts.
    """
    # Priority 1: canonical governed repo — the repo the git hooks enforce on.
    for candidate in [HOME / "hermes-cortex", HOME / ".hermes-cortex"]:
        if (candidate / ".git").exists():
            return candidate.name
    # Priority 2: cwd git repo (hosts with no canonical governed repo, e.g.
    # a project-repo-only workstation). Same resolution the hooks use.
    try:
        repo_root = subprocess.check_output(  # noqa: S603,S404 — fixed argv; timeout=3 below
            ["git", "rev-parse", "--show-toplevel"], timeout=3, stderr=subprocess.DEVNULL,
        ).decode().strip()
        if repo_root:
            return Path(repo_root).name
    except Exception:
        log.warning("Expected failure for: except Exception")
        pass
    return "generic"


def _session_lock_path(session_id: str) -> Path:
    """Return a unique lock file path per session.

    Each governance lock is named by its session ID, making it
    impossible for two sessions to collide on the same file.
    The enforcer scans all .governance-*.json files and matches
    by the repo_slug stored in each lock's content.
    """
    return GOVERNANCE_STATE_DIR / f".governance-{session_id}.json"


def _secondary_lock_path(state: dict) -> Path | None:
    """Return the secondary lock marker path inside the git repo.

    The secondary lock lives at <repo_root>/.hermes-cortex/.governance-lock
    and is a lightweight marker that the enforcer checks as a fallback
    when the primary lock directory is outside the repo.

    Returns None if the repo slug can't be mapped to a known repo path.
    """
    repo_slug = state.get("repo_slug", "")
    if not repo_slug:
        return None
    # Try known repo paths
    for candidate in [HOME / repo_slug, HOME / ".hermes-cortex", HOME / "hermes-cortex"]:
        if candidate.name == repo_slug and (candidate / ".git").exists():
            return candidate / ".hermes-cortex" / ".governance-lock"
    return None


# ── Lock helpers ─────────────────────────────────────────────

def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string with seconds precision."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _is_lock_stale(state: dict, mtime_fallback: float | None = None) -> bool:
    """Check if a lock's heartbeat has exceeded its TTL.

    2026-09-17 (Titus LEAK report): two heartbeat formats defeat the old
    parser and pin a lock in 'never stale' forever:
      * time-only heartbeat ("09:12:00Z") — datetime.fromisoformat raises,
        caught, returned False → lock never aged, orphan PENDING cycle blocked
        every push until a manual feedback_accept.
      * naive (no-tz) heartbeat — aware-vs-naive subtraction raises TypeError,
        caught, returned False → same indefinite pin.
    Fix: when the heartbeat can't be aged in-band, fall back to the lock
    file's mtime (last write). An abandoned lock's mtime is long in the past,
    so it still ages out; a lock mid-write that P1-A protects is a fresh mtime,
    so it is never falsely purged. Naive timestamps are treated as UTC.
    """
    ttl = state.get("ttl_seconds", DEFAULT_TTL)
    heartbeat_str = state.get("heartbeat_at", state.get("started_at", ""))
    now = datetime.now(timezone.utc)
    if heartbeat_str:
        try:
            hb_str = heartbeat_str.replace("Z", "+00:00")
            heartbeat = datetime.fromisoformat(hb_str)
            if heartbeat.tzinfo is None:
                heartbeat = heartbeat.replace(tzinfo=timezone.utc)  # naive = UTC
            return (now - heartbeat).total_seconds() > ttl
        except (ValueError, TypeError):
            # Time-only / malformed heartbeat — can't age it in-band.
            # Fall through to mtime if provided (caller has the file).
            pass
    if mtime_fallback is not None:
        return (now.timestamp() - mtime_fallback) > ttl
    return False


def _read_lock(args: dict | None = None) -> dict | None:
    """Read this session's lock file, return state dict or None."""
    session_id = get_session_id(args)
    path = _session_lock_path(session_id)
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None
    return None


def _write_lock(state: dict, args: dict | None = None) -> None:
    """Write lock state to a session-scoped file.

    The lock filename uses the session_id so two sessions never
    collide on the same file. The repo_slug in the content lets
    the enforcer filter locks by repo.

    P1-A fix: writes atomically (temp file + rename) so a concurrent
    purge scan (_purge_stale_locks / enforcer _has_governance_lock)
    never reads a partial JSON and deletes a fresh lock mid-write.

    Also writes a secondary marker inside the git repo
    (.hermes-cortex/.governance-lock) so the enforcer can find
    governance state even when the primary lock directory is
    outside the repo filesystem.
    """
    session_id = state.get("session_id", get_session_id(args))
    path = _session_lock_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomic write: temp file in same dir + rename (same filesystem)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.rename(path)

    # Write secondary marker inside repo for extra safety
    secondary = _secondary_lock_path(state)
    if secondary:
        secondary.parent.mkdir(parents=True, exist_ok=True)
        tmp2 = secondary.with_suffix(".tmp")
        tmp2.write_text(json.dumps(state, indent=2))
        tmp2.rename(secondary)


def _release_lock(args: dict | None = None) -> None:
    """Remove this session's lock file and secondary marker."""
    session_id = get_session_id(args)
    path = _session_lock_path(session_id)
    if path.exists():
        # Read state before unlinking so we know the repo_slug for cleanup
        try:
            state = json.loads(path.read_text())
            secondary = _secondary_lock_path(state)
            if secondary and secondary.exists():
                secondary.unlink()
        except (json.JSONDecodeError, OSError):
            log.warning("Best-effort operation — expected failure: except (json.JSONDecodeError, OSError)")
            pass
        path.unlink()


# ── Force-acquire audit trail ────────────────────────────────

FORCE_AUDIT_PATH = GOVERNANCE_STATE_DIR / "force-acquire-audit.json"


def _log_force_acquire(
    new_session: str,
    new_task: str,
    released_session: str,
    released_task: str,
) -> None:
    """Persist a force-acquire event to an audit log outside the lock lifecycle.

    This file lives alongside the lock files but is NEVER deleted by
    _release_lock or _purge_stale_locks. It provides a persistent history
    of all lock-stealing events for audit purposes.
    """
    try:
        GOVERNANCE_STATE_DIR.mkdir(parents=True, exist_ok=True)

        existing = []
        if FORCE_AUDIT_PATH.exists():
            try:
                existing = json.loads(FORCE_AUDIT_PATH.read_text())
            except (json.JSONDecodeError, OSError):
                existing = []

        if not isinstance(existing, list):
            existing = []

        existing.append({
            "timestamp": _now_iso(),
            "new_session": new_session,
            "new_task": new_task,
            "released_session": released_session,
            "released_task": released_task,
            "type": "force_acquire",
        })

        FORCE_AUDIT_PATH.write_text(json.dumps(existing, indent=2))
    except OSError:
        log.warning("Best-effort operation — expected failure: except OSError")
        pass


def _purge_stale_locks() -> int:
    """Proactively remove all stale lock files from ANY session.

    Fix GAP #9: scans all .governance-*.json files and removes those
    whose heartbeat has exceeded their TTL. This prevents stale lock
    buildup from crashed sessions and ensures every session starts clean.

    P1-A fix: NEVER deletes unparseable files. An unparseable lock file
    is a lock being written right now (atomic rename window) — deleting
    it steals another session's fresh lock. Only parseable-and-stale
    locks are removed.

    2026-09-17 (Titus LEAK report): this only removed the LOCK FILE — the
    orphaned PENDING cycle for the purged task was left behind, so the
    doctor still FAILed "PENDING cycles" (leak, blocked push) even after
    the lock vanished. Now also resolves those cycles to MOVE_ON here, so
    a crashed session's debris can't gate the repo indefinitely.
    Also passes the lock file's mtime as a fallback so time-only/naive
    heartbeats (which the old parser pinned as never-stale) finally age out.

    Returns the number of stale locks removed.
    """
    removed = 0
    resolved_cycles = 0
    purged_task_ids: set[str] = set()
    if not GOVERNANCE_STATE_DIR.exists():
        return 0
    for lock_file in sorted(GOVERNANCE_STATE_DIR.glob(".governance-*.json")):
        try:
            if lock_file.is_symlink():
                real_path = lock_file.resolve()
                # Skip symlinks — we'll process the real file separately
                continue
            state = json.loads(lock_file.read_text())
            try:
                mtime = lock_file.stat().st_mtime
            except OSError:
                mtime = None
            if _is_lock_stale(state, mtime):
                tid = state.get("task_id")
                if tid:
                    purged_task_ids.add(tid)
                lock_file.unlink()
                removed += 1
        except (json.JSONDecodeError, OSError, ValueError) as _parse_err:
            log.warning("Skipping unparseable lock file (mid-write?): %s (%s)", lock_file.name, _parse_err)
            # P1-A: unparseable = possibly mid-write. Leave it — never delete.
    # Resolve orphaned PENDING cycles for tasks whose locks were just purged
    # (their owning session is gone — the cycle can never be scored by them).
    if purged_task_ids:
        resolved_cycles = _resolve_orphaned_pending_cycles(purged_task_ids)
    # Also clean up orphan symlinks (pointing to deleted targets)
    for lock_file in sorted(GOVERNANCE_STATE_DIR.glob(".governance-*.json")):
        try:
            if lock_file.is_symlink() and not lock_file.exists():
                lock_file.unlink()
                removed += 1
        except OSError:
            log.warning("Expected failure for: except OSError")
            pass
    if resolved_cycles:
        log.warning("Purge: resolved %d orphaned PENDING cycle(s) for purged tasks", resolved_cycles)
    return removed


def _resolve_orphaned_pending_cycles(task_ids: set[str] | None = None) -> int:
    """MOVE_ON PENDING cycles whose task holds no live lock (leaked/abandoned).

    The doctor's rule (cortex_doctor/checks.py, single source of truth):
    a PENDING cycle whose task_id has NO active .governance-*.json lock is a
    LEAK — begin_change ran but feedback_accept never did, and the session
    (or its lock) is gone. This is the auto-resolve half of that rule so a
    crashed/lost session can't FAIL the doctor forever and gate every push.

    When task_ids is provided (purge path), only those tasks are touched
    (their locks were just removed as stale — provably abandoned). When
    task_ids is None (gate/startup path), every PENDING cycle whose task
    has no live lock is resolved — but only if it is OLDER than the lock TTL,
    to avoid racing a session that is CURRENTLY mid-begin_change (cycle row
    written, lock write microseconds later).

    Never touches hook-created cycles (decision LOOP/MOVE_ON, not PENDING),
    never touches a PENDING cycle whose task still holds a live lock (that's
    the current task — expected mid-session, INFO).

    Returns the number of cycles resolved to MOVE_ON.
    """
    try:
        conn = _db()
    except Exception as e:
        log.warning("resolve-orphans: DB unavailable (%s) — skipping", e)
        return 0
    # Live task ids = those with a non-terminal lock file.
    _terminal = {"completed", "cancelled"}
    live: set[str] = set()
    if GOVERNANCE_STATE_DIR.is_dir():
        for lf in GOVERNANCE_STATE_DIR.glob(".governance-*.json"):
            try:
                ld = json.loads(lf.read_text())
                if ld.get("task_id") and ld.get("status") not in _terminal:
                    live.add(ld["task_id"])
            except (OSError, ValueError):
                continue  # P1-A: unparseable = possibly mid-write — skip, never delete
    try:
        if task_ids:
            ph = ",".join("?" * len(task_ids))
            pending = conn.execute(
                f"SELECT id, task_id, timestamp FROM loop_cycles "
                f"WHERE decision='PENDING' AND user_overrode IS NULL AND task_id IN ({ph})",
                tuple(task_ids),
            ).fetchall()
        else:
            pending = conn.execute(
                "SELECT id, task_id, timestamp FROM loop_cycles "
                "WHERE decision='PENDING' AND user_overrode IS NULL LIMIT 5000"
            ).fetchall()
        now = datetime.now(timezone.utc)
        resolved = 0
        for r in pending:
            if r["task_id"] in live:
                continue  # current task — expected, not a leak
            # When not explicitly targeting purged tasks, require the cycle to
            # be older than the TTL so a mid-begin_change row is never raced.
            if task_ids is None:
                try:
                    ts = datetime.fromisoformat(str(r["timestamp"]).replace("Z", "+00:00"))
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                except (ValueError, TypeError):
                    ts = None  # unparseable timestamp → treat as young, skip
                if ts is None or (now - ts).total_seconds() <= DEFAULT_TTL:
                    continue
            conn.execute(
                "UPDATE loop_cycles SET decision='MOVE_ON', "
                "outcome_note='auto-resolved by governance MCP — task has no live lock (abandoned/crashed session)' "
                "WHERE id=?",
                (r["id"],),
            )
            resolved += 1
        conn.commit()
        conn.close()
        return resolved
    except Exception as e:
        log.warning("resolve-orphans failed (non-critical): %s", e)
        try:
            conn.close()
        except Exception:
            pass
        return 0


# ── Embedding helpers ────────────────────────────────────────

OLLAMA_URL = "http://localhost:11434/api/embeddings"


def _embed(text: str) -> list[float] | None:
    try:
        payload = json.dumps({"model": NOMIC_MODEL, "prompt": text[:2000]}).encode()
        req = urllib.request.Request(OLLAMA_URL, payload, {"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())["embedding"]
    except Exception:
        return None


def _cosine_sim(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    return 0.0 if na == 0 or nb == 0 else dot / (na * nb)


# ── Database ─────────────────────────────────────────────────
# Schema-init-once flag: see _db() docstring. DDL runs once per process;
# later calls skip it (schema is immutable, DDL is idempotent). Guarded by a
# lock because the MCP daemon is threaded: two sessions' first _db() could
# otherwise interleave the flag-set and both run DDL (adversarial-gate flag,
# lost-update race). The lock makes the DDL run-once atomic.
_SCHEMA_DONE = False
_SCHEMA_LOCK = threading.Lock()

def _decision_class(decision) -> str:
    """Bucket a decision label into its canonical class.

    Legacy rows carry emoji and prose ('LOOP 🔄 — keep iterating',
    'MOVE ON → …', 'STOP ✗ — hard fail'), so every gate must compare the
    CLASS and never the exact string: exact equality against "LOOP" silently
    let decorated cycles through the close-out gate unscored (2026-09-23).
    """
    text = (decision or "").strip().upper()
    if not text:
        return "PENDING"
    if text.startswith("MOVE"):
        return "MOVE_ON"
    for known in ("STOP", "LOOP", "PENDING"):
        if text.startswith(known):
            return known
    return text


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Run schema DDL exactly once per process (guard: _SCHEMA_DONE).

    2026-09-29 friction fix: the DDL block was previously inlined in _db()
    and ran on EVERY connection, re-invoking two swallowed-ALTER-exception
    warning logs and a no-op write-lock commit per call. The schema is
    immutable after first creation; extracting it behind the guard makes
    later _db() calls pure reads (connect + pragmas) with zero DDL/re-exception/
    write-commit overhead. No table, column, or index is skipped — the DDL is
    byte-identical, only its execution frequency changes.
    """
    global _SCHEMA_DONE
    with _SCHEMA_LOCK:
        if _SCHEMA_DONE:
            return
        _SCHEMA_DONE = True
    conn.execute(
        """CREATE TABLE IF NOT EXISTS loop_cycles (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp       TEXT NOT NULL DEFAULT (datetime('now')),
            task_id         TEXT NOT NULL,
            cycle_num       INTEGER NOT NULL,
            spec_hash       TEXT,
            code_hash       TEXT,
            test_output_hash TEXT,
            completeness    REAL NOT NULL,
            quality         REAL NOT NULL,
            progress        REAL NOT NULL,
            composite       REAL NOT NULL,
            no_progress     INTEGER NOT NULL DEFAULT 0,
            decision        TEXT NOT NULL,
            user_overrode   INTEGER,
            outcome_note    TEXT,
            schema_version  INTEGER DEFAULT 2,
            model_name      TEXT DEFAULT 'nomic-embed-text'
        )"""
    )
    # Add session_id column if missing (schema migration v1→v2)
    try:
        conn.execute("ALTER TABLE loop_cycles ADD COLUMN session_id TEXT")
    except sqlite3.OperationalError:
        log.warning("SQL migration: column already exists — expected")
        pass

    # Add unscored_reason column if missing (schema v2→v3, 2026-09-23):
    # a cycle closed WITHOUT a measurement must record WHY it is unscored,
    # so "accepted, composite 0.0" stops meaning both "trivial" and "unmeasured".
    try:
        conn.execute("ALTER TABLE loop_cycles ADD COLUMN unscored_reason TEXT")
    except sqlite3.OperationalError:
        log.warning("SQL migration: unscored_reason already exists — expected")
        pass

    # Task events table (harness v3)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS task_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp   TEXT NOT NULL DEFAULT (datetime('now')),
            task_id     TEXT NOT NULL,
            agent       TEXT,
            event_type  TEXT NOT NULL,
            from_state  TEXT,
            to_state    TEXT,
            detail      TEXT
        )"""
    )
    try:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_task_events_task ON task_events(task_id)")
    except sqlite3.OperationalError:
        log.warning("Expected failure for: except sqlite3.OperationalError")
        pass
    conn.commit()


def _db() -> sqlite3.Connection:
    """Get or create the loop-governance DB with auto-schema init.

    Multi-session concurrency (2026-09-29): every interactive Hermes session
    spawns its OWN loop-gov-mcp.py daemon with its own connection to the
    shared ~/.hermes-cortex/data/loop-governance.db. Two sessions calling
    begin_change()/feedback/end_change concurrently must SERIALIZE on the
    SQLite write lock, not fail. WAL mode lets readers run while a writer
    commits, and a generous busy-timeout makes a second writer WAIT for the
    first to release instead of erroring with 'database is locked' (observed:
    concurrent hermes-cortex sessions on moses blocked each other for minutes).

    Schema-init-once (2026-09-29 friction fix): DDL is delegated to
    _ensure_schema(), guarded by _SCHEMA_DONE, so it runs once per process.
    Later calls are pure reads. WAL/busy_timeout stay per-connection and
    their verification is unchanged — concurrency safety is not relaxed.
    """
    LOOP_DB.parent.mkdir(parents=True, exist_ok=True)
    # timeout=busy_timeout: wait up to 30s for a concurrent writer to release
    # (default 5s is too short under real interleaved begin_change contention).
    conn = sqlite3.connect(str(LOOP_DB), timeout=30.0)
    conn.row_factory = sqlite3.Row
    try:
        # WAL: concurrent readers never block the single writer; a second
        # writer queues on the busy timeout instead of erroring.
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
    except sqlite3.OperationalError as e:
        # Don't silently swallow (adversarial ADV-0-3): a failed pragma means
        # concurrent sessions will NOT serialize — log it loudly so a doctor
        # reviewer can see WAL/busy_timeout are not in effect on this DB.
        log.warning("loop-gov: could not enable WAL/busy_timeout on %s: %s", LOOP_DB, e)
    else:
        # Verify the pragma actually took (a pragma can be silently ignored if
        # another connection holds the DB open in a conflicting journal mode).
        try:
            jm = conn.execute("PRAGMA journal_mode").fetchone()[0]
            bt = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            if str(jm).lower() != "wal":
                log.warning("loop-gov: journal_mode=%s (expected wal) on %s", jm, LOOP_DB)
            if int(bt) < 30000:
                log.warning("loop-gov: busy_timeout=%s (expected >=30000) on %s", bt, LOOP_DB)
        except sqlite3.OperationalError as e:
            log.warning("loop-gov: could not verify pragmas on %s: %s", LOOP_DB, e)

    _ensure_schema(conn)
    return conn


def _config() -> dict:
    if CONFIG_PATH.exists():
        return json.loads(CONFIG_PATH.read_text())
    return {
        "version": 1,
        "weights": {"completeness": 0.4, "quality": 0.3, "progress": 0.3},
        "thresholds": {"stop": 8.0, "loop": 5.0, "move_on": 3.0},
        "embed_weight": 0.15,
        "no_progress_limit": 3,
    }


# ── MCP Server ───────────────────────────────────────────────

async def list_tools(ctx, params=None) -> ListToolsResult:
    return ListToolsResult(tools=[
        Tool(
            name="rereview_change",
            description=(
                "Re-judge an OPEN cycle after its adversarial findings were FIXED. The "
                "verdict is stored once per cycle, so without this a FINDINGS verdict was "
                "permanent: correct the code, and the reviewer still read the same frozen "
                "note and refused forever — forcing agents toward an override. Requires a "
                "NEW note stating what changed AND the evidence for it (command output, not "
                "a narrative) — an unchanged note is REFUSED, because this exists to re-judge "
                "a fixed change, not to re-roll a verdict. The reviewer still runs live against "
                "the current diff and decides; this cannot manufacture a CLEAN."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "The task whose cycle should be re-judged."},
                    "note": {
                        "type": "string",
                        "description": (
                            "What changed since the findings, WITH the evidence attached — paste "
                            "the command output, do not summarise it. Must differ from the note "
                            "that was reviewed."
                        ),
                    },
                },
                "required": ["task_id", "note"],
            },
        ),
        Tool(
            name="begin_change",
            description="MANDATORY: Call before making any code/config change. Creates a governance lock AND a pending cycle in the loop-governance DB. Scoring is handled by log_cycle() — STOP decisions auto-accept. After work, call end_change() to release.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Short task identifier (e.g. 'fix-auth-403')"},
                    "description": {"type": "string", "description": "What this change does"},
                    "force": {
                        "type": "boolean",
                        "description": "Force-acquire the lock even if another session holds it. Releases the existing lock first (default: false).",
                        "default": False,
                    },
                    "ttl": {
                        "type": "integer",
                        "description": "Time-to-live in seconds. Lock auto-releases if heartbeat is not refreshed within this window (default: 3600 = 1 hour).",
                        "default": DEFAULT_TTL,
                    },
                    "acceptance_criteria": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string", "description": "AC identifier (e.g. 'AC-1')"},
                                "description": {"type": "string", "description": "What passing this criterion means"},
                                "status": {"type": "string", "description": "pending / in_progress / verified", "default": "pending"},
                                "verified_by": {"type": "string", "description": "Optional: 'loop_scorer' to gate on scored cycles"},
                            },
                            "required": ["id", "description"],
                        },
                        "description": "Acceptance criteria — required gates that must pass before end_change. When omitted, the task is lightweight (no scope or AC enforcement).",
                    },
                    "allowed_scope": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Glob patterns for files/resources this task is allowed to touch. Writes outside this scope are denied by the PolicyEngine. When omitted, no scope restriction beyond the existing lock check.",
                    },
                    "plan": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "step_id": {"type": "string", "description": "Step identifier (e.g. 'STEP-1')"},
                                "description": {"type": "string", "description": "What this step does"},
                                "status": {"type": "string", "description": "pending / in_progress / completed / blocked", "default": "pending"},
                            },
                            "required": ["step_id", "description"],
                        },
                        "description": "Optional execution plan steps. Steps can be advanced via advance_task_state (future tool).",
                    },
                },
                "required": ["task_id", "description"],
            },
        ),
        Tool(
            name="end_change",
            description="RELEASE the governance lock. Check is informational only — scoring/acceptance handled by log_cycle() at write time (STOP auto-accepts). Lock releases unconditionally.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID matching the begin_change call"},
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="check_lock",
            description="Check if a governance lock is active. Returns the full lock state including session_id, heartbeat_at, and ttl_seconds if active. On every call, refreshes the heartbeat to prevent staleness. Auto-releases stale locks where heartbeat has exceeded TTL.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="cycle_query",
            description="Query scored cycles. Filter by task_id, min_score, max_score, limit.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Filter by task name (partial match)"},
                    "min_score": {"type": "number", "description": "Minimum composite score"},
                    "max_score": {"type": "number", "description": "Maximum composite score"},
                    "limit": {"type": "integer", "description": "Max results (default 10)"},
                    "unreviewed": {"type": "boolean", "description": "Only cycles needing feedback"},
                },
            },
        ),
        Tool(
            name="cycle_stats",
            description="Summary statistics for the loop governance DB.",
            inputSchema={
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Lookback window in days (default 30)"},
                },
            },
        ),
        Tool(
            name="config_show",
            description="Show current thresholds and weights.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="config_set",
            description="Modify a threshold or weight value. Use with care - safety bounds enforced.",
            inputSchema={
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "description": "Dot-separated path like thresholds.stop or weights.completeness",
                    },
                    "value": {"type": "number", "description": "New value"},
                },
                "required": ["key", "value"],
            },
        ),
        Tool(
            name="feedback_accept",
            description="Mark a cycle decision as correct. REQUIRED up front (2026-09-29, to end the bare-note-refusal retry loop): pass either the three scores/completeness/quality/progress (0-10) OR unscored_reason. A bare note is refused — a close must carry a measurement or say why it is unscored. Provide cycle_id OR task_id (resolves to the session's current PENDING cycle).",
            inputSchema={
                "type": "object",
                "properties": {
                    "cycle_id": {"type": "integer", "description": "Cycle ID from cycle_query (alternative to task_id)"},
                    "task_id": {"type": "string", "description": "Task ID — resolves to the session's current PENDING cycle (alternative to cycle_id)"},
                    "note": {"type": "string", "description": "Optional note"},
                    "completeness": {"type": "number", "description": "Self-reported 0-10: did the work cover the stated scope?"},
                    "quality": {"type": "number", "description": "Self-reported 0-10: was it verified (tests, real output, docs)?"},
                    "progress": {"type": "number", "description": "Self-reported 0-10: how much of the goal advanced?"},
                    "unscored_reason": {"type": "string", "description": "Required when no scores are passed: why nothing could be measured (e.g. 'read-only audit — no diff to measure'). An unscored close must state its reason."},
                },
            },
        ),
        Tool(
            name="feedback_override",
            description="Mark a scored cycle decision as wrong and record the correct decision. Provide cycle_id OR task_id (resolves to session's current PENDING cycle).",
            inputSchema={
                "type": "object",
                "properties": {
                    "cycle_id": {"type": "integer", "description": "Cycle ID from cycle_query (alternative to task_id)"},
                    "task_id": {"type": "string", "description": "Task ID — resolves to the session's current PENDING cycle (alternative to cycle_id)"},
                    "correct_decision": {
                        "type": "string",
                        "enum": ["STOP", "LOOP", "MOVE_ON"],
                        "description": "What the decision should have been",
                    },
                    "note": {"type": "string", "description": "Why the override"},
                },
            },
        ),
        Tool(
            name="cache_search",
            description="Search the session embedding cache for similar content.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Text to search for"},
                    "top_k": {"type": "integer", "description": "Number of results (default 5)"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="record_issue",
            description="Record a discovered issue or obstacle during task execution. Writes to the task_events table. Never modifies the lock file — purely informational.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task identifier (must match active lock)"},
                    "description": {"type": "string", "description": "What was discovered — the issue, obstacle, or finding"},
                    "severity": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "critical"],
                        "description": "Issue severity (default: medium)",
                        "default": "medium",
                    },
                    "category": {
                        "type": "string",
                        "description": "Optional category (e.g. 'bug', 'blocker', 'tech-debt', 'research')",
                    },
                },
                "required": ["task_id", "description"],
            },
        ),
        Tool(
            name="advance_task_state",
            description="Transition the active task to a new state. Validates against the state machine before applying. Logs the transition to task_events.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task identifier (must match active lock)"},
                    "new_state": {
                        "type": "string",
                        "enum": ["planning", "executing", "verifying", "reporting",
                                 "completed", "blocked", "cancelled", "suspended"],
                        "description": "Target state to transition to",
                    },
                    "reason": {"type": "string", "description": "Optional reason for the transition"},
                },
                "required": ["task_id", "new_state"],
            },
        ),
        Tool(
            name="request_interruption",
            description="Push the current task onto the task_stack and create a new sub-task. The original task can be resumed later with resume_from_interrupt.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Interruption sub-task identifier"},
                    "description": {"type": "string", "description": "Description of the interruption"},
                    "reason": {"type": "string", "description": "Why the interruption is needed"},
                },
                "required": ["task_id", "description"],
            },
        ),
        Tool(
            name="resume_from_interrupt",
            description="Pop the top task from task_stack and restore it as the active task. The current sub-task is saved to the stack.",
            inputSchema={
                "type": "object",
                "properties": {},
            },
        ),
        Tool(
            name="request_completion",
            description="Request completion of the active task. Validates all acceptance_criteria against the loop-scorer DB. If all pass, marks the lock as completion_verified — a prerequisite for end_change when acceptance_criteria are set.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task identifier (must match active lock)"},
                    "evidence": {
                        "type": "object",
                        "additionalProperties": {"type": "string"},
                        "description": "Optional map of criterion_id → evidence description. For criteria with verified_by='loop_scorer', the evidence is auto-checked against the loop-governance DB. For other criteria, provide evidence here.",
                    },
                },
                "required": ["task_id"],
            },
        ),
        Tool(
            name="promote_issue_to_task",
            description="Promote a recorded issue to a new standalone task. Only valid when no active lock exists.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "New task identifier"},
                    "description": {"type": "string", "description": "What this new task does"},
                    "issue_event_id": {"type": "integer", "description": "Optional: ID of the issue event from record_issue to reference"},
                    "ttl": {
                        "type": "integer",
                        "description": "Time-to-live in seconds (default: 3600)",
                        "default": 3600,
                    },
                },
                "required": ["task_id", "description"],
            },
        ),
    ])


async def call_tool(ctx, params=None) -> CallToolResult:
    name = params.name if params else ""
    args = (params.arguments or {}) if params else {}
    try:
        handlers = {
            "begin_change": _begin_change,
            "end_change": _end_change,
            "check_lock": _check_lock,
            "cycle_query": _cycle_query,
            "cycle_stats": _cycle_stats,
            "config_show": _config_show,
            "config_set": _config_set,
            "feedback_accept": _feedback_accept,
            "feedback_override": _feedback_override,
            "cache_search": _cache_search,
            "record_issue": _record_issue,
            "advance_task_state": _advance_task_state,
            "request_interruption": _request_interruption,
            "resume_from_interrupt": _resume_from_interrupt,
            "request_completion": _request_completion,
            "promote_issue_to_task": _promote_issue_to_task,
        }
        handler = handlers.get(name)
        if handler:
            return handler(args)
        return CallToolResult(content=[TextContent(type="text", text="Unknown tool: " + name)])
    except Exception as e:
        return CallToolResult(content=[TextContent(type="text", text="Error: " + str(e))])


# ── Tool Implementations ─────────────────────────────────────

def _begin_change(args: dict) -> CallToolResult:
    """Create a governance lock file AND a pending cycle in the loop-governance DB."""
    task_id = args.get("task_id", "").strip()
    description = args.get("description", "").strip()
    force = args.get("force", False)
    ttl = args.get("ttl", DEFAULT_TTL)

    if not task_id:
        return CallToolResult(content=[TextContent(type="text", text="Error: task_id is required")])
    if not description:
        return CallToolResult(content=[TextContent(type="text", text="Error: description is required")])
    if ttl < 60:
        return CallToolResult(content=[TextContent(type="text", text="Error: TTL must be at least 60 seconds")])
    if ttl > 86400:
        return CallToolResult(content=[TextContent(type="text", text="Error: TTL cannot exceed 86400 seconds (24 hours)")])

    # ── Dogfood gate ──
    dogfood_msg = _require_dogfood()
    if dogfood_msg:
        return CallToolResult(content=[TextContent(type="text", text=dogfood_msg)])

    session_id = get_session_id(args)
    now_iso = _now_iso()

    # ── Step 0: Purge stale locks + resolve orphaned PENDING cycles ──
    # (2026-09-17, Titus LEAK report) The gate entry point must clear
    # crashed-session debris BEFORE acquiring, so a stale lock / orphan
    # PENDING cycle from a dead session can't block begin_change or leave
    # the doctor FAILing on every subsequent push. _purge_stale_locks also
    # resolves the orphaned PENDING cycle(s) for the tasks whose locks it
    # removes; _resolve_orphaned_pending_cycles() additionally sweeps any
    # PENDING cycle (older than TTL) that has no live lock at all.
    try:
        _purge_stale_locks()
        _resolve_orphaned_pending_cycles()  # task_ids=None → sweep all lockless
    except Exception as _purge_err:
        log.warning("begin_change: pre-purge failed (non-critical): %s", _purge_err)

    # ── Step 0: Close-out gate — score before moving to a new task ──
    # Luke directive (2026-08-08): agents must close out/score before moving
    # to a new task. If THIS session still holds unscored PENDING cycles from
    # earlier tasks, refuse to open a new lock until they are scored. Without
    # this gate, end_change's warning-only unscored path + begin_change's
    # lock-only check let a session stack unbounded PENDING cycles that the
    # doctor only catches at push time. Hook-created cycles (session_id NULL)
    # are untouched by this query. If the DB is unavailable, proceed (the
    # lock + doctor still guard) rather than deadlock the agent.
    if session_id:
        try:
            _conn = _db()
            prior = _conn.execute(
                "SELECT id, task_id, decision FROM loop_cycles WHERE session_id = ?",
                (session_id,),
            ).fetchall()
            _conn.close()
            # Class, not exact string (2026-09-23): a row whose decision reads
            # 'PENDING ' or another decorated spelling is still an unclosed
            # cycle and must trip this gate. The score-or-reason requirement is
            # enforced at feedback_accept (you cannot create an unscored close)
            # and at end_change (you cannot release the lock with one), so this
            # gate stays about *unclosed* work and does not retro-block sessions
            # holding cycles accepted under the older rules.
            prior = [r for r in prior if _decision_class(r["decision"]) == "PENDING"]
            if prior:
                listing = ", ".join(f"#{r['id']} ({r['task_id']})" for r in prior)
                return CallToolResult(content=[TextContent(
                    type="text",
                    text=(
                        "❌ Close out your previous task before starting a new one.\n\n"
                        "This session still has unscored PENDING cycles:\n"
                        f"  {listing}\n\n"
                        "Score them first (AGENTS.md RULE 2 — score before moving on):\n"
                        "  mcp__loop_governance__feedback_accept(task_id='<task>', note='...')\n"
                        "  or mcp__loop_governance__feedback_override(task_id='<task>', "
                        "correct_decision='...', note='...')\n"
                        "  then mcp__loop_governance__end_change(task_id='<task>')\n\n"
                        "No new lock is acquired until prior cycles are scored."
                    )
                )])
        except Exception as e:
            log.warning("begin_change: close-out check failed (proceeding): %s", e)

    # Defaults for audit trail (may be overwritten by force-override below)
    audit_note = ""
    released_session = ""

    # ── Step 1: Resolve any existing lock (force path) BEFORE DB cycle ──
    # For force=True: read old lock info and release it. The new lock file
    # is NOT written yet — that happens only after DB cycle confirms.
    # For normal (non-force): just check and reject if lock exists.
    existing = _read_lock(args)
    if existing is not None:
        if not force:
            return CallToolResult(content=[TextContent(
                type="text",
                text=(
                    f"Error: A governance session is already active:\n"
                    f"  task_id:     {existing.get('task_id')}\n"
                    f"  description: {existing.get('description')}\n"
                    f"  session_id:  {existing.get('session_id', 'unknown')}\n"
                    f"  started_at:  {existing.get('started_at')}\n"
                    f"  heartbeat:   {existing.get('heartbeat_at')}\n"
                    f"  agent:       {existing.get('agent')}\n\n"
                    f"Call end_change('{existing.get('task_id')}') first, or use force=True to override."
                )
            )])
        # Force override: build audit note and release old lock
        released_task = existing.get("task_id", "unknown")
        released_session = existing.get("session_id", "unknown")
        _release_lock(args)
        audit_note = (
            f"Lock overridden by force=True.\n"
            f"  Released session: {released_session}\n"
            f"  Released task:    {released_task}\n"
            f"  New session:      {session_id}\n"
            f"  New task:         {task_id}"
        )
        # Persist force-acquire event to audit log outside lock lifecycle
        _log_force_acquire(session_id, task_id, released_session, released_task)

        # ── Fix GAP #1: Auto-score the replaced task's PENDING cycle ──
        # The old task's PENDING cycle (composite=0, decision='PENDING') would
        # otherwise orphan in the DB. Score it as overridden with a clear note.
        try:
            conn = _db()
            old_row = conn.execute(
                "SELECT id FROM loop_cycles WHERE task_id = ? AND decision = 'PENDING' AND user_overrode IS NULL ORDER BY id DESC LIMIT 1",
                (released_task,)
            ).fetchone()
            if old_row:
                conn.execute(
                    "UPDATE loop_cycles SET user_overrode=1, decision='MOVE_ON', outcome_note=? WHERE id=?",
                    (f"Auto-closed: force-acquire by task '{task_id}' (session {session_id}) replaced this task", old_row[0])
                )
                conn.commit()
        except Exception:
            log.warning("Could not auto-score replaced task cycle (non-critical)")
        finally:
            try:
                conn.close()
            except Exception:
                log.warning("Best-effort cleanup: conn close failed")

    # ── Step 2: Create pending cycle in loop-governance DB (BEFORE new lock file) ──
    # Critical ordering: if the DB write fails, no new lock file is written,
    # preventing orphaned locks. For force=True, the old lock is already released
    # but no NEW lock exists yet — the DB write must succeed to proceed.
    try:
        conn = _db()
        row = conn.execute(
            "SELECT COALESCE(MAX(cycle_num), 0) + 1 FROM loop_cycles WHERE task_id = ?",
            (task_id,)
        ).fetchone()
        cycle_num = row[0] if row else 1

        outcome = "Created by begin_change — call feedback_accept to score"
        if force:
            outcome = audit_note

        conn.execute(
            """INSERT INTO loop_cycles
               (task_id, cycle_num, completeness, quality, progress, composite,
                no_progress, decision, user_overrode, outcome_note, session_id)
               VALUES (?, ?, 0, 0, 0, 0, 0, 'PENDING', NULL, ?, ?)""",
            (task_id, cycle_num, outcome, session_id)
        )
        conn.commit()
        cycle_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()

        pending_msg = (
            f"\n📝 Pending cycle #{cycle_id} created in loop-governance DB.\n"
            f"   After your change, call:\n"
            f"     1. mcp__loop_governance__feedback_accept(cycle_id={cycle_id}"
            f", task_id='{task_id}', note='...')\n"
            f"     2. mcp__loop_governance__end_change(task_id='{task_id}')\n"
            f"\n   [CYCLE_ID={cycle_id}]"
        )
    except Exception as e:
        return CallToolResult(content=[TextContent(
            type="text",
            text=(
                f"Error: Could not create pending cycle — lock NOT acquired.\n"
                f"  DB error: {e}\n"
                f"  No lock file was written — nothing to clean up."
            )
        )])

    # ── Step 3: Write lock file (only after DB cycle confirmed) ──
    has_plan = bool(args.get("plan", []))
    state = {
        "task_id": task_id,
        "description": description,
        "repo_slug": _derive_slug(),
        "started_at": now_iso,
        "agent": os.environ.get("AGENT_NAME", "unknown"),
        "session_id": session_id,
        # P1-A: differentiate cron/daemon locks from interactive locks so
        # purge loops (enforcer + MCP + purge script) never let a cron
        # session delete an interactive session's fresh lock.
        "session_type": (
            "cron" if session_id.startswith("cron_")
            else "bg" if session_id.startswith("bg_")
            else "interactive"
        ),
        "ttl_seconds": ttl,
        "heartbeat_at": now_iso,
        "scored": False,
        # Harness v3 extended fields (optional — empty = lightweight task mode)
        "acceptance_criteria": args.get("acceptance_criteria", []),
        "allowed_scope": args.get("allowed_scope", []),
        "plan": args.get("plan", []),
        "task_stack": [],
        # Start in planning state when a plan is provided (fix GAP #6)
        "status": "planning" if has_plan else "executing",
    }
    _write_lock(state, args)

    prefix = "🔒 " if not force else "🔓⚠️ "
    force_msg = f" (forced — replaced session {released_session})" if force else ""
    return CallToolResult(content=[TextContent(
        type="text",
        text=(
            f"{prefix}Governance session started: {task_id} — {description}{force_msg}\n"
            f"Lock file: {_session_lock_path(session_id)}\n"
            f"Session ID: {session_id}\n"
            f"TTL: {ttl}s\n"
            f"Use end_change('{task_id}') when done."
            + pending_msg
        )
    )])


# ═════════════════════════════════════════════════════════════════════════════
# Event-driven adversarial review — complexity-gated hard gate (2026-09-24)
#
# The reviewer fires at end_change (NOT a cron). A "sufficiently complex"
# change cannot close its cycle until an independent reviewer (fixed prompt,
# distinct model) returns CLEAN. Trivial changes skip review. If the reviewer
# is unavailable, the close is REFUSED (fail loudly — governance is essential,
# never silently degraded).
#
# Complexity is MEASURED, never self-reported: it is the git diff (added +
# removed lines, files touched) since the cycle began, plus a size-independent
# always-review path list for enforcement/security surface. Anti-gaming:
#  - added+removed counted separately (net-zero rewrite still complex)
#  - uncommitted work counts (staged + unstaged, not just committed)
#  - always-review paths gate BEFORE the noise allowlist, so a tiny change
#    to the enforcer/security is never "trivial"
#  - noise allowlist is exact-name only (lockfiles), so a worker cannot bury
#    a malicious line inside a "generated" file — that file still counts
#  - the reviewer is a separate process (this MCP daemon) with a fixed prompt
#    and a DISTINCT model the worker session cannot influence
# ═════════════════════════════════════════════════════════════════════════════

# Paths that are ALWAYS reviewed regardless of size — enforcement, governance,
# security, and shared-repo plumbing. A one-line change here is never trivial.
ALWAYS_REVIEW_PATHS = [
    "plugins/governance-enforcer/",
    "mcp-servers/loop-gov-mcp.py",
    "core/governance/",
    "ops/scripts/pre-commit-score",
    "ops/scripts/pre-push-pull",
    "ops/scripts/post-commit-audit",
    "ops/scripts/post-push-audit",
    "ops/scripts/cortex-update.sh",
    "ops/scripts/quality/adversarial-verify.py",
    ".hermes-cortex/hooks/",
]

# Exact-name noise: generated/lock files whose size is not a complexity signal.
# Checked AFTER always-review paths. A worker cannot hide a change here — a
# real source edit still counts; only a pure lockfile bump is discounted.
NOISE_PATHS = [
    "Cargo.lock", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "go.sum", "Gemfile.lock", "composer.lock",
]

# Complexity thresholds (diff-based). Complex when EITHER bound is crossed.
COMPLEXITY_LINE_THRESHOLD = 50      # added + removed lines (non-noise)
COMPLEXITY_FILE_THRESHOLD = 3       # files touched (non-noise)

REVIEWER_MODEL_DEFAULT = "deepseek/deepseek-v4-pro"  # distinct from worker
REVIEW_TEMPLATE_REL = "docs/templates/adversarial-reviewer-prompt.md"
REVIEW_MARKER = "=== REVIEWED MATERIAL ==="
DIFF_CHAR_BUDGET = 12000


def _git_capture(repo: Path, *args: str, timeout: int = 15) -> str:
    """Run a read-only git command in `repo`, return stdout ("" on any error)."""
    try:
        return subprocess.run(  # noqa: S603,S404 — fixed argv, git -C
            ["git", "-C", str(repo)] + list(args),
            capture_output=True, text=True, timeout=timeout,
        ).stdout
    except Exception:
        return ""


def _parse_numstat(text: str):
    """(files: set[str], added: int, removed: int) from `git diff --numstat`."""
    files = set()
    added = removed = 0
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        a, r, f = parts[0], parts[1], parts[2]
        if not f or f.startswith('"'):
            continue
        files.add(f)
        if a.isdigit():
            added += int(a)
        if r.isdigit():
            removed += int(r)
    return files, added, removed


def _is_noise(path: str) -> bool:
    return any(path == n or path.endswith("/" + n) for n in NOISE_PATHS)


def _agent_author(repo: Path) -> str:
    """Author identity of THIS agent's commits, or "" when unknown.

    Git authorship comes from the per-host agent env (AGENTS.md rule 21) and
    surfaces as the repo's git config user.email / user.name.
    """
    for key in ("user.email", "user.name"):
        val = _git_capture(repo, "config", "--get", key).strip()
        if val:
            return val
    return ""


def _authored_commits(repo: Path, base: str, author: str) -> list:
    """SHAs in ``base..HEAD`` authored by ``author``. Empty when unknown/none.

    A non-empty result is the ONLY licence to narrow the reviewed range: if we
    cannot positively identify this agent's commits we must keep auditing the
    whole window, or a worker could dodge review by committing under another
    name.
    """
    if not author or not base or base == "HEAD":
        return []
    out = _git_capture(repo, "log", "--format=%H", "--author=" + author, base + "..HEAD")
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def _complexity(repo: Path, started_at: str) -> dict:
    """Measured complexity of the change under the current cycle.

    Considers committed work since `started_at` PLUS staged and unstaged
    working-tree changes (uncommitted work counts — the worker cannot dodge
    the gate by leaving risky edits uncommitted).
    """
    # Base commit: last commit before the cycle started, else the empty tree.
    empty_tree = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
    base = ""
    if started_at:
        base = _git_capture(repo, "rev-list", "-1", "--before=" + started_at, "HEAD").strip()
    base = base or empty_tree

    # Committed work is scoped to THIS session's own commits. The window
    # (base..HEAD) can also hold commits pulled in by a rebase — other agents'
    # work — and counting those misattributes complexity and re-reports changes
    # that are not part of this cycle (and may already be gone at HEAD).
    _author = _agent_author(repo)
    _authored = _authored_commits(repo, base, _author)
    if _authored:
        numstat = _git_capture(repo, "log", "--numstat", "--format=",
                               "--author=" + _author, base + "..HEAD")
    else:
        # No positive identity / nothing authored: do NOT narrow (fail open).
        numstat = _git_capture(repo, "diff", "--numstat", base + "..HEAD")
    numstat += _git_capture(repo, "diff", "--cached", "--numstat")   # staged
    numstat += _git_capture(repo, "diff", "--numstat")               # unstaged

    files, added, removed = _parse_numstat(numstat)

    # FAIL-SAFE (never lessen review): a commit in the window that this session
    # did NOT author but which touches an always-review (enforcement /
    # governance) path still forces review. Without this, a worker could escape
    # the gate by committing risky work under another git identity.
    if _authored:
        _mine = set(_authored)
        _theirs = [s for s in _git_capture(repo, "log", "--format=%H", base + "..HEAD").split()
                   if s and s not in _mine]
        if _theirs:
            _of, _, _ = _parse_numstat(
                _git_capture(repo, "show", "--numstat", "--format=", *_theirs))
            files.update(f for f in _of if any(ap in f for ap in ALWAYS_REVIEW_PATHS))

    # Untracked new files (not yet `git add`ed) still count — a worker cannot
    # dodge review by creating a big new file and leaving it untracked, then
    # committing it after the review passed. Their full line count is the
    # "added" signal (there is no prior version to diff against).
    untracked_lines = 0
    for f in _git_capture(repo, "ls-files", "--others", "--exclude-standard").splitlines():
        f = f.strip()
        if not f:
            continue
        files.add(f)
        if not _is_noise(f):
            try:
                with open(repo / f, encoding="utf-8", errors="ignore") as fh:
                    untracked_lines += sum(1 for _ in fh)
            except OSError:
                pass

    # Always-review paths gate FIRST (size-independent, raw files).
    always = [f for f in files if any(ap in f for ap in ALWAYS_REVIEW_PATHS)]

    # Complexity from non-noise files.
    non_noise = [f for f in files if not _is_noise(f)]
    non_noise_lines = 0
    # Recompute lines restricted to non-noise files for an honest threshold.
    nn_added = nn_removed = 0
    for line in numstat.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        a, r, f = parts[0], parts[1], parts[2]
        if _is_noise(f):
            continue
        if a.isdigit():
            nn_added += int(a)
        if r.isdigit():
            nn_removed += int(r)
    non_noise_lines = nn_added + nn_removed + untracked_lines

    is_complex = bool(always) or (
        len(non_noise) >= COMPLEXITY_FILE_THRESHOLD
        or non_noise_lines >= COMPLEXITY_LINE_THRESHOLD
    )
    return {
        "is_complex": is_complex,
        "files": len(non_noise),
        "lines": non_noise_lines,
        "always_review": bool(always),
        "always_paths": sorted(set(always)),
        "numstat": numstat.strip(),
    }


def _review_template_text(repo: Path) -> str:
    """The fixed reviewer prompt, from the repo (or the deployed copy)."""
    for cand in (
        repo / REVIEW_TEMPLATE_REL,
        HOME / ".hermes-cortex" / "templates" / "adversarial-reviewer-prompt.md",
    ):
        if cand.is_file():
            return cand.read_text()
    return ""


def _reviewer_api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if key:
        return key
    env = HOME / ".hermes" / ".env"
    try:
        if env.is_file():
            for line in env.read_text().splitlines():
                if line.startswith("OPENROUTER_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except OSError:
        pass
    return ""


def _reviewer_backend() -> str:
    """Which reviewer backend runs the close-gate review. Default `llm`."""
    return (os.environ.get("ADVERSARIAL_REVIEW_BACKEND", "llm") or "llm").strip().lower()


def _reviewer_label() -> str:
    """What to RECORD as the reviewer: the model for the llm backend, the agent
    name for the agent backend. A stored review whose reviewer is ambiguous
    cannot be re-derived from the record."""
    if _reviewer_backend() == "agent":
        return "agent:" + ((os.environ.get("ADVERSARIAL_REVIEW_AGENT_NAME", "") or "unnamed").strip())
    return os.environ.get("ADVERSARIAL_REVIEWER_MODEL", REVIEWER_MODEL_DEFAULT)


def _call_reviewer_llm(prompt: str) -> str:
    """Review via a chat-completions model. Provider-agnostic: the default is
    OpenRouter, but ADVERSARIAL_REVIEW_BASE_URL lets a local or self-hosted
    endpoint do the reviewing, and ADVERSARIAL_REVIEW_API_KEY_ENV names the
    credential to read (never the value)."""
    model = os.environ.get("ADVERSARIAL_REVIEWER_MODEL", REVIEWER_MODEL_DEFAULT)
    base = ((os.environ.get("ADVERSARIAL_REVIEW_BASE_URL", "") or "").strip()
            or "https://openrouter.ai/api/v1").rstrip("/")
    key_env = (os.environ.get("ADVERSARIAL_REVIEW_API_KEY_ENV", "") or "").strip()
    if key_env:
        # An EXPLICITLY named credential is honoured strictly. Falling back to a
        # different one would mean the reviewer ran with a credential the operator
        # did not choose — silently, and from a file. Better to refuse.
        api_key = (os.environ.get(key_env, "") or "").strip()
    else:
        api_key = ((os.environ.get("OPENROUTER_API_KEY", "") or "").strip()
                   or _reviewer_api_key())
    if not api_key:
        raise RuntimeError(f"{key_env or 'OPENROUTER_API_KEY'} not set — reviewer cannot run")
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )
    timeout = int(os.environ.get("ADVERSARIAL_REVIEW_TIMEOUT", "300"))
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


def _call_reviewer_agent(prompt: str, author: Optional[str] = None) -> str:
    """Review by shelling out to a CODING AGENT, with the prompt on STDIN.

    The command is operator-supplied (ADVERSARIAL_REVIEW_AGENT_CMD) rather than a
    hardcoded per-CLI table. The fleet's agent CLIs each have their own flags, and
    inventing one produces a wiring that exists and does nothing — while a
    configured command works for ANY agent, including one this repo has never
    heard of (which is the flexibility this is for).

    Why an agent at all: an agent can open the repo, run the tests and check the
    claims, which a single chat completion cannot. That matters here because the
    recurring review finding is 'a self-report is not execution evidence'.

    READ-ONLY IS THE OPERATOR'S RESPONSIBILITY. This function grants no write
    access, but it also cannot revoke what the configured command itself allows,
    so the command must put the agent in its read-only/plan/sandbox mode. Do not
    point this at a command that can edit the tree: a reviewer that can write can
    fix its own objections.

    Self-review is refused: the agent name is compared against the change's git
    author (derived, not operator-supplied), because an author must not
    adjudicate its own work.
    """
    cmd = (os.environ.get("ADVERSARIAL_REVIEW_AGENT_CMD", "") or "").strip()
    if not cmd:
        raise RuntimeError(
            "ADVERSARIAL_REVIEW_BACKEND=agent requires ADVERSARIAL_REVIEW_AGENT_CMD "
            "(the agent CLI invocation — the review prompt is passed on stdin)")
    agent = (os.environ.get("ADVERSARIAL_REVIEW_AGENT_NAME", "") or "").strip()
    if agent and author and agent.lower() in author.lower():
        raise RuntimeError(
            f"refusing SELF-REVIEW: the review agent '{agent}' is this change's "
            f"author ('{author}') — an author cannot adversarially review its own work")
    timeout = int(os.environ.get("ADVERSARIAL_REVIEW_AGENT_TIMEOUT", "900"))
    proc = subprocess.run(
        shlex.split(cmd), input=prompt, capture_output=True, text=True, timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"review agent exited {proc.returncode}: {(proc.stderr or proc.stdout or '')[:400]}")
    out = (proc.stdout or "").strip()
    if not out:
        raise RuntimeError("review agent produced no output — refusing to treat silence as CLEAN")
    return out


def _call_reviewer(prompt: str, author: Optional[str] = None) -> str:
    """Dispatch to the configured reviewer backend. Return its text (raises on error).

    The backend is pluggable; the CONTRACT is not: given the review prompt, return
    text containing the findings JSON. Every backend must stay fail-closed —
    raising here refuses the close, it never passes it — so a misconfigured or
    unreachable reviewer can only make closing harder, never easier.
    """
    backend = _reviewer_backend()
    if backend == "agent":
        return _call_reviewer_agent(prompt, author=author)
    if backend == "llm":
        return _call_reviewer_llm(prompt)
    raise RuntimeError(
        f"unknown ADVERSARIAL_REVIEW_BACKEND {backend!r} (expected llm|agent) — "
        "refusing to guess a reviewer")


def _extract_verdict(text: str):
    """(verdict, findings_json) from the reviewer's reply. Fail-closed: an
    unparseable reply is NEVER trusted as CLEAN — it is FINDINGS."""
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            obj = json.loads(text[start:end + 1])
            findings = obj.get("findings", [])
            if not isinstance(findings, list):
                findings = []
            verdict = obj.get("verdict", "FINDINGS" if findings else "CLEAN")
            return str(verdict).upper(), json.dumps(findings)
        except json.JSONDecodeError:
            pass
    return "FINDINGS", "[]"


# Severity policy (operator, 2026-10-02): MEDIUM and above BLOCK a close; LOW is
# recorded and surfaced but never blocks. Blocking on LOW turned the gate into a
# formatting police — cycles 10337 and 10371 were held open by LOW/MEDIUM
# evidence-format findings ("attach raw output", "diff stat header") while every
# real defect of the day was HIGH.
BLOCKING_SEVERITIES = ("critical", "high", "medium")


def _blocking_findings(findings_json):
    """``(blocking, annotating)`` — findings split by severity. Never returns None.

    Fail-closed: an unparseable payload, a non-list, or a finding with no
    recognised severity is returned as BLOCKING. This policy narrows WHICH
    findings block; it must never make an unknown finding stop blocking.
    """
    try:
        items = json.loads(findings_json or "[]")
    except Exception:
        return [{"finding_id": "unparseable-findings", "severity": "high",
                 "technique": "unverified-claim",
                 "evidence": str(findings_json)[:200],
                 "recommendation": "findings payload could not be parsed"}], []
    if not isinstance(items, list):
        return [{"finding_id": "malformed-findings", "severity": "high",
                 "technique": "unverified-claim",
                 "evidence": str(findings_json)[:200],
                 "recommendation": "findings payload was not a list"}], []
    blocking, annotating = [], []
    for it in items:
        sev = str((it or {}).get("severity", "")).lower() if isinstance(it, dict) else ""
        if sev in BLOCKING_SEVERITIES:
            blocking.append(it)
        elif sev:
            annotating.append(it)
        else:
            blocking.append(it)          # unknown/absent severity -> fail closed
    return blocking, annotating


def _parse_findings_list(findings_json):
    """Findings as a list of dicts. [] for anything unparseable (the caller's
    fail-closed path in _blocking_findings still applies to the RAW payload)."""
    try:
        items = json.loads(findings_json or "[]")
    except Exception:
        return []
    if not isinstance(items, list):
        return []
    return [f for f in items if isinstance(f, dict)]


# ── Triage: deterministic refutation + an optional fast-model classifier ──
#
# Rationale (operator 2026-10-02): most gate churn came from findings that are
# computably wrong, or merely administrative. Both are handled more reliably
# than by asking the sampling reviewer again.
#
# Two layers, in order:
#   1. _refute_findings  — DETERMINISTIC. A finding that quotes a string must be
#      quoting something the reviewer actually saw; if none of its quoted
#      fragments is in the material, the citation is fabricated or stale. This is
#      the failure that held cycle 10337 open by quoting text a later commit had
#      deleted. Conservative: a finding with NO quoted fragment is never refuted.
#   2. _triage_findings  — a fast "system 1" model, DISABLED unless
#      ADVERSARIAL_TRIAGE_MODEL is set. Classification only, never adjudication.
#
# Neither layer may RAISE a severity, and triage may only lower one to LOW for a
# finding it calls administrative AND that cites no artifact. Everything else
# keeps the reviewer's severity. All decisions are recorded on the finding.

_QUOTED_RE = re.compile(r"[`\"\u201c\u201d']([^`\"\u201c\u201d']{12,})[`\"\u201c\u201d']")


def _quoted_fragments(text):
    """Fragments a finding explicitly quotes (>=12 chars)."""
    return [m.group(1).strip() for m in _QUOTED_RE.finditer(str(text or ""))]


def _refute_findings(findings, material):
    """Findings whose quoted evidence is absent from the material.

    Returns the refuted subset; the caller reports them and excludes them from
    the blocking decision. Never refutes on a paraphrase (no quote -> no refute).
    """
    if not material or not isinstance(findings, list):
        return []
    refuted = []
    for f in findings:
        if not isinstance(f, dict):
            continue
        frags = _quoted_fragments(f.get("evidence", ""))
        if frags and not any(fr in material for fr in frags):
            refuted.append(f)
    return refuted


# The judgment client (ops/scripts/judgment.py) speaks the systemone wire format:
# typed QUESTIONS in, typed ANSWERS out —
#   POST {base_url}/v1/systemone
#     {"model":…, "state":…, "questions": {id: {type: noul|choice|score,
#                                               instructions, criteria?}}}
#  -> {"answers": {id: {type, …value}}, "usage": {…}}
# Jev and von consume exactly that and take NO chat prompt, so the triage layer
# must not ask for prose+JSON. Thresholds live HERE, in the caller, per the
# client's own contract ("code stays in control: this module returns typed
# answers; thresholds and actions belong to the caller").
TRIAGE_MAX_FINDINGS = 12
NOUL_TRUE = 0.7          # cites_artifact counts as TRUE at/above this probability


def _load_judgment_client():
    """Import the judgment client (repo first, then deployed). None if absent."""
    for cand in (Path(__file__).resolve().parents[1] / "ops" / "scripts" / "judgment.py",
                 HOME / ".hermes-cortex" / "scripts" / "judgment.py"):
        if cand.is_file():
            try:
                spec = importlib.util.spec_from_file_location("hc_judgment_client", cand)
                if spec is None or spec.loader is None:
                    log.warning("triage: judgment client spec unavailable at %s", cand)
                    return None
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                return mod
            except Exception as e:
                log.warning("triage: judgment client failed to load (%s: %s)",
                            type(e).__name__, e)
                return None
    return None


def _triage_questions(findings):
    """Typed questions for the review-triage class: one triple per finding.

    Question ids embed the finding id, and the client validates that the answer
    keys match the question ids EXACTLY — a provider that drops or invents an
    answer is rejected outright rather than half-consumed.
    """
    qs = {}
    for i, f in enumerate(findings[:TRIAGE_MAX_FINDINGS]):
        fid = str(f.get("finding_id") or f"f{i}")
        qs[f"{fid}.cites_artifact"] = {
            "type": "noul",
            "instructions": ("Does this finding name a concrete artifact — a file path, "
                             "commit sha, symbol, or quoted code — that the state shows?")}
        qs[f"{fid}.class"] = {
            "type": "choice",
            "instructions": ("Is this finding administrative (formatting, evidence "
                             "attachment, or note phrasing) or a judgement call about the "
                             "behaviour of the change?"),
            # criteria is a DICT of option -> what the option means. The live
            # systemone API rejects a list here with HTTP 422
            # ('questions.<id>.choice.criteria: Input should be a valid dictionary'),
            # so a list is not 'documentation shorthand' — it is a failed request.
            "criteria": {
                "administrative": "Formatting, evidence attachment, or note phrasing only.",
                "judgement": "A claim about the behaviour, correctness or safety of the change.",
            }}
        qs[f"{fid}.severity"] = {
            "type": "choice",
            "instructions": ("Severity. high = incorrect or unsafe behaviour, a broken "
                             "gate, or an unverified claim about the code; medium = a real "
                             "gap that should be fixed; low = administrative or presentation."),
            "criteria": {
                "low": "Administrative or presentation only.",
                "medium": "A real gap that should be fixed.",
                "high": ("Incorrect or unsafe behaviour, a broken gate, or an unverified "
                         "claim about the code."),
            }}
    return qs


def _triage_findings(findings, material, client=None, primary_fn=None, config=None):
    """Classify findings through the judgment client's typed (systemone) interface.

    Returns [{finding_id, class, cites_artifact, severity}] or None when triage is
    DISABLED (no model configured and no injected transport), UNAVAILABLE (client
    missing, provider error, non-ok status, or a reply the client rejected), or the
    findings list is empty. On None the caller keeps the reviewer's severities
    unchanged — a triage outage must never relax or tighten the gate.

    ``primary_fn`` is the injectable transport ``(base_url, payload, timeout) ->
    dict``, used by tests so they never touch the network.
    """
    if not findings:
        return None
    if primary_fn is None and not (os.environ.get("ADVERSARIAL_TRIAGE_MODEL", "") or "").strip():
        return None
    jc = client if client is not None else _load_judgment_client()
    if jc is None:
        log.warning("triage: judgment client unavailable — reviewer severities stand")
        return None
    state = {
        "material": (material or "")[:6000],
        "findings": [{k: f.get(k) for k in ("finding_id", "severity", "technique",
                                            "target", "evidence")}
                     for f in findings[:TRIAGE_MAX_FINDINGS]],
    }
    try:
        res = jc.decide("review-triage", state, _triage_questions(findings),
                        config=config, primary_fn=primary_fn)
    except Exception as e:
        log.warning("triage: judgement call failed (%s: %s) — reviewer severities stand",
                    type(e).__name__, e)
        return None
    if not isinstance(res, dict) or str(res.get("status")) != "ok":
        log.warning("triage: judgement status=%s — reviewer severities stand",
                    (res or {}).get("status"))
        return None
    ans = res.get("answers") or {}
    out = []
    for i, f in enumerate(findings[:TRIAGE_MAX_FINDINGS]):
        fid = str(f.get("finding_id") or f"f{i}")
        art = ans.get(f"{fid}.cites_artifact") or {}
        cls = ans.get(f"{fid}.class") or {}
        sev = ans.get(f"{fid}.severity") or {}
        try:
            cites = float(art.get("noul", 0.5)) >= NOUL_TRUE
        except (TypeError, ValueError):
            cites = True          # unusable probability -> assume it cites (fail safe)
        out.append({"finding_id": f.get("finding_id"),
                    "cites_artifact": cites,
                    "class": cls.get("choice"),
                    "severity": sev.get("choice")})
    return out


def _apply_triage(findings, triage):
    """Merge triage verdicts. Returns (findings, decisions).

    Only LOWERS a severity, and only to 'low', and only for a finding the
    classifier calls administrative AND that cites no artifact. The reviewer's
    original severity is preserved on the finding for audit.
    """
    if not triage:
        return findings, []
    by_id = {str(d.get("finding_id")): d for d in triage if d.get("finding_id")}
    out, decisions = [], []
    for f in findings:
        if not isinstance(f, dict):
            out.append(f)
            continue
        d = by_id.get(str(f.get("finding_id", "")))
        if d and str(d.get("class", "")).lower() == "administrative" \
                and not d.get("cites_artifact"):
            nf = dict(f)
            nf["severity_reviewer"] = f.get("severity")
            nf["severity"] = "low"
            nf["triage"] = "administrative/no-artifact -> low"
            decisions.append(f.get("finding_id"))
            out.append(nf)
        else:
            out.append(f)
    return out, decisions


def _record_review(cycle_id, reviewer_id, model, verdict, findings_json, summary,
                    replace: bool = False, fingerprint: str = ""):
    """Insert the verdict. Duplicate cycle_id is a no-op unless replace=True.

    Connection hygiene (2026-09-30): conn MUST be closed on EVERY path. cycle_id
    is UNIQUE, so a retried end_change re-runs the review and re-INSERTs ->
    IntegrityError. The old code swallowed that error without closing the
    connection, leaking its open write transaction into the long-lived serving
    daemon — in WAL that held the write reservation indefinitely, so each review
    retry wedged the DB for all sessions and forced pointless daemon kills.
    try/finally guarantees the connection (and its lock) is always released.

    `replace=True` is used by the gate for the judgement it just made: the frozen
    UNIQUE row is what made a cycle unclosable once FINDINGS was recorded, so a
    fixed change could never be re-judged. Replacing keeps ONE verdict per cycle
    (no history inflation) and is recorded in the governance log, so it stays
    auditable.

    `fingerprint` pins the verdict to the exact material it judged (note + diff).
    A CLEAN is only reusable while that material is unchanged, so a CLEAN cannot
    be carried over a later, unreviewed change.
    """
    conn = _db()
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS adversarial_reviews ("
            " review_id TEXT PRIMARY KEY,"
            " cycle_id INTEGER NOT NULL UNIQUE,"
            " reviewer_id TEXT NOT NULL,"
            " reviewer_model TEXT NOT NULL,"
            " verdict TEXT NOT NULL,"
            " findings_json TEXT NOT NULL,"
            " summary TEXT,"
            " ts TEXT NOT NULL,"
            " fingerprint TEXT)"
        )
        try:
            conn.execute("ALTER TABLE adversarial_reviews ADD COLUMN fingerprint TEXT")
        except sqlite3.OperationalError:
            pass  # column already exists — expected
        if replace:
            # UPSERT, not UPDATE. The first review of a cycle has no row to update,
            # so a plain UPDATE matched nothing and the verdict was never stored —
            # observed when rereview_change then reported "no recorded review" for a
            # cycle the gate had just judged. ON CONFLICT covers both first record
            # and replacement, which is exactly the pair of behaviours wanted.
            conn.execute(
                "INSERT INTO adversarial_reviews"
                " (review_id, cycle_id, reviewer_id, reviewer_model,"
                "  verdict, findings_json, summary, ts, fingerprint)"
                " VALUES (?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT(cycle_id) DO UPDATE SET"
                "  reviewer_id=excluded.reviewer_id,"
                "  reviewer_model=excluded.reviewer_model,"
                "  verdict=excluded.verdict,"
                "  findings_json=excluded.findings_json,"
                "  summary=excluded.summary,"
                "  ts=excluded.ts,"
                "  fingerprint=excluded.fingerprint",
                (str(uuid.uuid4()), cycle_id, reviewer_id, model,
                 verdict, findings_json, summary, _now_iso(), fingerprint),
            )
        else:
            conn.execute(
                "INSERT INTO adversarial_reviews"
                " (review_id, cycle_id, reviewer_id, reviewer_model,"
                "  verdict, findings_json, summary, ts, fingerprint)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (str(uuid.uuid4()), cycle_id, reviewer_id, model,
                 verdict, findings_json, summary, _now_iso(), fingerprint),
            )
        conn.commit()
    except sqlite3.IntegrityError:
        pass  # already reviewed — idempotent
    finally:
        conn.close()  # NEVER leak the connection (or its write lock) into the daemon


def _stored_review(cycle_id) -> Optional[dict]:
    """The recorded verdict for a cycle, or None. Never raises."""
    conn = _db()
    try:
        row = conn.execute(
            "SELECT verdict, findings_json, summary, fingerprint"
            " FROM adversarial_reviews WHERE cycle_id=?", (cycle_id,)).fetchone()
        return dict(row) if row else None
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def _review_fingerprint(material: str) -> str:
    """Identify the exact material a verdict was reached on (note + diff)."""
    return hashlib.sha256(material.encode("utf-8", "replace")).hexdigest()


def _rereview_change(args: dict) -> CallToolResult:
    """Re-judge an OPEN cycle after its findings were fixed.

    THE GAP THIS CLOSES: the adversarial verdict is stored under a UNIQUE
    cycle_id, so FINDINGS was permanent. Fix the code, re-run end_change, and the
    reviewer still read the same frozen outcome_note and the same recorded
    verdict — a legitimately fixed change could never close. The only escape was
    an override, which is exactly what governance should not force an agent to
    reach for.

    GOVERNANCE IS NOT WEAKENED — friction is:
      * the reviewer still runs LIVE against the current diff and decides. This
        cannot manufacture a CLEAN; it only asks again;
      * it REFUSES unless the material actually changed — a new note is required
        and must differ from the one that was reviewed. Re-rolling without doing
        the work is the same request twice and is rejected;
      * the replacement is logged and leaves exactly one verdict per cycle, so
        the record stays honest and auditable;
      * it is an explicit, named action — never a silent side effect of closing.
    """
    task_id = str(args.get("task_id") or "").strip()
    new_note = str(args.get("note") or "").strip()
    if not task_id:
        return CallToolResult(content=[TextContent(type="text", text=(
            "❌ rereview_change requires task_id."))])
    if not new_note:
        return CallToolResult(content=[TextContent(type="text", text=(
            "❌ rereview_change requires a NEW note describing what changed and the "
            "evidence for it. A re-review without new material is the same request "
            "twice — fix the findings first."))])

    lock, err = _verify_lock_for_task(task_id, args)
    if lock is None:
        return CallToolResult(content=[TextContent(type="text", text=(
            f"❌ Cannot re-review: {err or 'no live lock for this task'}"))])

    conn = _db()
    try:
        row = conn.execute(
            "SELECT id, outcome_note, decision FROM loop_cycles WHERE task_id=? "
            "ORDER BY id DESC LIMIT 1", (task_id,)).fetchone()
        if row is None:
            return CallToolResult(content=[TextContent(type="text", text=(
                f"❌ No cycle recorded for task '{task_id}'."))])
        cycle_id, old_note, decision = row["id"], (row["outcome_note"] or ""), row["decision"]

        rev = conn.execute(
            "SELECT verdict, findings_json FROM adversarial_reviews WHERE cycle_id=?",
            (cycle_id,)).fetchone()
        if rev is None:
            return CallToolResult(content=[TextContent(type="text", text=(
                f"❌ Cycle #{cycle_id} has no recorded review — nothing to re-review. "
                "Run end_change to get it reviewed."))])
        old_verdict = str(rev["verdict"] or "").upper()
        if old_verdict == "CLEAN":
            return CallToolResult(content=[TextContent(type="text", text=(
                f"✅ Cycle #{cycle_id} already CLEAN — call end_change to release."))])
        if new_note == (old_note or "").strip():
            return CallToolResult(content=[TextContent(type="text", text=(
                f"❌ Refused: the note is unchanged from what was reviewed on cycle "
                f"#{cycle_id}. Re-review exists for a FIXED change — describe what "
                "changed and attach the evidence (command output, not prose)."))])

        # The material changed: update the note the reviewer reads, then re-judge.
        conn.execute("UPDATE loop_cycles SET outcome_note=? WHERE id=?",
                     (new_note, cycle_id))
        conn.commit()
        cycle = dict(row)
        cycle["outcome_note"] = new_note
    finally:
        conn.close()

    log.info("rereview: cycle %s task %s — verdict was %s, material changed",
             cycle_id, task_id, old_verdict)

    block = _adversarial_review_gate(lock, cycle, force=True)
    if block is not None:
        # The gate already recorded the fresh verdict; report it plainly.
        return CallToolResult(content=[TextContent(type="text", text=(
            f"Cycle #{cycle_id}: re-review completed — the reviewer still has "
            "findings below. Governance is unchanged: fix them, then re-review "
            "again with the new evidence.\n\n"
            + "\n".join(c.text for c in block.content if getattr(c, "text", None))))])

    return CallToolResult(content=[TextContent(type="text", text=(
        f"✅ Cycle #{cycle_id} re-reviewed and CLEAN — the findings are resolved. "
        "Call end_change('" + task_id + "') to release the lock."))])


def _adversarial_review_gate(lock: dict, cycle: dict,
                            force: bool = False) -> Optional[CallToolResult]:
    """The complexity-gated hard gate. Returns None (proceed) or a block result.

    Simple changes pass through. Complex changes must earn a CLEAN review;
    a FINDINGS verdict or a reviewer outage REFUSES the close (fail loudly).

    `force=True` re-judges even when a verdict for this exact material is already
    stored. Only rereview_change uses it, and only after the material changed — it
    must not be a way to re-roll an unchanged verdict, so rereview_change refuses
    an unchanged note before it gets here.
    """
    repo_slug = lock.get("repo_slug", "")
    repo = HOME / repo_slug if repo_slug else None
    if repo is None or not (repo / ".git").exists():
        # No governed repo to diff — cannot measure complexity. Fail CLOSED:
        # an unmeasurable close is a complex close, and it must be reviewed.
        return CallToolResult(content=[TextContent(type="text", text=(
            "❌ Cannot close: no governed repo to measure complexity — "
            "adversarial review cannot run. Report to the orchestrator."
        ))])

    cx = _complexity(repo, lock.get("started_at", ""))
    if not cx["is_complex"]:
        log.info("adversarial review: cycle %s simple (%s lines, %s files) — skip",
                 cycle.get("id"), cx["lines"], cx["files"])
        return None

    # Complex: build the review material and run the reviewer.
    task_id = lock.get("task_id", "")
    description = lock.get("description", "")
    outcome_note = cycle.get("outcome_note") or "(no note)"
    _base = (
        _git_capture(repo, "rev-list", "-1", "--before=" + lock.get("started_at", ""), "HEAD").strip()
        or "HEAD"
    )
    _author = _agent_author(repo)
    _authored = _authored_commits(repo, _base, _author)
    if _authored:
        # AUDIT this session's own commits; show the rest of the window as
        # labelled CONTEXT so nothing is hidden from the reviewer. The window
        # also contains commits pulled in by a rebase (other agents' work, or an
        # automated pipeline) — reviewing those as the worker's change reports
        # work outside this cycle, which is what blocked cycles 10337 (esther)
        # and 2936 (moses).
        diff_text = _git_capture(repo, "log", "-p", "--no-ext-diff", "-U3",
                                 "--author=" + _author, _base + "..HEAD")
        _mine = set(_authored)
        _theirs = [s for s in _git_capture(repo, "log", "--format=%H", _base + "..HEAD").split()
                   if s and s not in _mine]
        if _theirs:
            _log = _git_capture(repo, "log", "--format=%h %an <%ae> %s", _base + "..HEAD")
            diff_text += (
                "\n\n[provenance — commits in this window NOT authored by this session; "
                "author identity shown per commit. Included for completeness.]\n"
                + _log + "\n"
                + _git_capture(repo, "show", "-p", "--no-ext-diff", "-U3", *_theirs)
            )
    else:
        # No positive identity / nothing authored: review the whole window.
        diff_text = _git_capture(repo, "diff", "--no-ext-diff", "-U3", _base + "..HEAD")
    # Bound the diff (head+tail) so a huge change still fits the reviewer.
    if len(diff_text) > DIFF_CHAR_BUDGET:
        diff_text = diff_text[:DIFF_CHAR_BUDGET] + "\n...[diff truncated]...\n"

    template = _review_template_text(repo)
    if not template or REVIEW_MARKER not in template:
        return CallToolResult(content=[TextContent(type="text", text=(
            "❌ Cannot close: adversarial reviewer prompt template is missing or "
            "corrupt. Run cortex-update.sh, then retry end_change."
        ))])

    # Identify WHICH session / agent / repo tree this material belongs to.
    # Concurrent sessions on one host share a repo and (without per-session git
    # identities) share an author, so material carrying no session header can be
    # conflated with another session's change — and a cycle can be judged against
    # a tree that does not contain its work (observed: a worktree-hosted change
    # reviewed against the primary tree). Both are attribution failures, so the
    # material states its own identity.
    _sid = lock.get("session_id", "") or get_session_id(None)
    _head_sha = _git_capture(repo, "rev-parse", "--short", "HEAD").strip()
    _branch = _git_capture(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    material = (
        f"Session: {_sid}\n"
        f"Agent (git author): {_author or '(unresolved)'}\n"
        f"Repo tree: {repo}  branch={_branch}  HEAD={_head_sha}\n"
        f"Audited range: {_base}..HEAD (commits authored by the agent above)\n"
        f"Cycle ID: {cycle.get('id', 0)}\n"
        f"Task: {task_id}\n"
        f"Description: {description}\n"
        f"Diff stat (files={cx['files']}, lines={cx['lines']}"
        + (f", always-review={','.join(cx['always_paths'])}" if cx["always_paths"] else "")
        + "):\n" + cx["numstat"] + "\n\n"
        f"Worker's note (self-report — the thing being reviewed):\n{outcome_note}\n\n"
        f"Full diff:\n{diff_text}\n"
    )
    prompt = f"{template}\n{material}\n"
    fingerprint = _review_fingerprint(material)

    # Honour a verdict already reached on THIS material.
    #
    # The reviewer is a sampling model: re-running it on byte-identical material can
    # return the opposite verdict. Observed on cycle 10301 — rereview_change returned
    # CLEAN, then end_change returned FINDINGS quoting the same note, and the claim
    # in one of those findings was itself measurably false. That made a complex cycle
    # close on a coin-flip while looking deliberate, and it made rereview_change
    # pointless. The verdict is stored once per cycle, pinned to this fingerprint;
    # only rereview_change (force=True, after the material changed) asks again.
    #
    # A stored verdict with no/mismatched fingerprint (e.g. recorded before this
    # existed, or the diff moved since) is NOT reused — the change is re-judged.
    if not force:
        stored = _stored_review(cycle.get("id"))
        if stored is not None and (stored.get("fingerprint") or "") == fingerprint:
            stored_verdict = str(stored.get("verdict") or "").upper()
            if stored_verdict == "CLEAN":
                log.info("adversarial review: cycle %s CLEAN (stored, material unchanged)",
                         cycle.get("id"))
                return None
            _block, _annot = _blocking_findings(stored.get("findings_json") or "[]")
            if not _block:
                log.info("adversarial review: cycle %s stored %s but all LOW (%d) — not blocking",
                         cycle.get("id"), stored_verdict, len(_annot))
                return None
            return CallToolResult(content=[TextContent(type="text", text=(
                "❌ Adversarial review FAILED — this complex change cannot close.\n\n"
                f"Verdict: {stored_verdict} (already recorded for exactly this material)\n"
                f"Findings: {stored.get('findings_json') or '[]'}\n\n"
                "Findings at MEDIUM or above block the close; LOW findings are recorded "
                "(they remain in the stored review) but do not block.\n"
                "Fix the findings, then call rereview_change with a NEW note describing "
                "what changed and the evidence for it. The lock stays held; nothing "
                "sufficiently complex ships unreviewed."
            ))])

    try:
        reviewer_text = _call_reviewer(prompt, author=_author)
    except Exception as e:
        log.error("adversarial review: reviewer call failed: %s", e)
        return CallToolResult(content=[TextContent(type="text", text=(
            "❌ Cannot close: adversarial reviewer is UNAVAILABLE. "
            "Governance requires review before this complex change ships — "
            f"the close is refused, not skipped. (error: {e})\n\n"
            "Retry end_change when the reviewer is reachable."
        ))])

    verdict, findings_json = _extract_verdict(reviewer_text)
    reviewer_id = f"adv-review-{uuid.uuid4().hex[:8]}"

    # Layer 1 — deterministic refutation; Layer 2 — optional fast-model triage.
    # Both run BEFORE the verdict is recorded, so what is stored is the final set.
    # Neither may raise a severity. Nothing is silently dropped: refuted findings
    # are appended to the stored summary and every triage decision is recorded.
    _ref_note = ""
    if verdict != "CLEAN":
        _findings = _parse_findings_list(findings_json)
        if _findings:
            _refuted = _refute_findings(_findings, material)
            if _refuted:
                _rids = {id(f) for f in _refuted}
                _findings = [f for f in _findings if id(f) not in _rids]
                _ref_note = ("\n\n[refuted by the deterministic pre-check: quoted evidence "
                             "absent from the material] " +
                             "; ".join(f"{f.get('finding_id', '?')}: {str(f.get('evidence', ''))[:160]}"
                                       for f in _refuted))
                log.warning("adversarial review: cycle %s REFUTED %d finding(s) whose quoted "
                            "evidence is absent from the material: %s",
                            cycle.get("id"), len(_refuted),
                            "; ".join(str(f.get("finding_id", "?")) for f in _refuted))
            _tri = _triage_findings(_findings, material)
            _findings, _tdec = _apply_triage(_findings, _tri)
            if _tdec:
                log.info("adversarial review: cycle %s triage lowered %d administrative "
                         "finding(s) to LOW: %s", cycle.get("id"), len(_tdec), _tdec)
            findings_json = json.dumps(_findings)

    # replace=True: this is the authoritative judgement for this cycle, and the row is
    # UNIQUE per cycle. Without it the judgement is silently DISCARDED on a re-review
    # (the IntegrityError path below is a no-op), which left a FINDINGS verdict frozen
    # forever — the exact gap rereview_change exists to close.
    _record_review(cycle.get("id"), reviewer_id,
                   _reviewer_label(),
                   verdict, findings_json, (reviewer_text[:2000] + _ref_note),
                   replace=True, fingerprint=fingerprint)

    if verdict == "CLEAN":
        log.info("adversarial review: cycle %s CLEAN", cycle.get("id"))
        return None

    # Severity policy: MEDIUM and above block; LOW annotates. LOW findings are NOT
    # discarded — they stay in the stored review row (findings_json, written just
    # above) and are logged here, so the observation survives without holding the
    # cycle open.
    _block, _annot = _blocking_findings(findings_json)
    if not _block:
        log.info("adversarial review: cycle %s FINDINGS with only LOW severity (%d) — "
                 "annotating, not blocking: %s",
                 cycle.get("id"), len(_annot),
                 "; ".join(str((f or {}).get("finding_id", "?")) for f in _annot[:6]))
        return None

    # MEDIUM+ (or unclassifiable): hard-block.
    return CallToolResult(content=[TextContent(type="text", text=(
        "❌ Adversarial review FAILED — this complex change cannot close.\n\n"
        f"Verdict: {verdict}\n"
        f"Findings: {findings_json}\n"
        f"Summary: {reviewer_text[:1200]}\n\n"
        "Findings at MEDIUM or above block the close; LOW findings are recorded but "
        "do not block.\n"
        "Resolve the findings and retry end_change. The lock stays held; "
        "nothing sufficiently complex ships unreviewed."
    ))])


def _end_change(args: dict) -> CallToolResult:
    """Release governance lock — requires a scored cycle in the loop-governance DB."""
    task_id = args.get("task_id", "").strip()
    if not task_id:
        return CallToolResult(content=[TextContent(type="text", text="Error: task_id is required")])

    # Step 1: Read this session's lock
    session_id = get_session_id(args)
    lock = _read_lock(args)
    if lock is None:
        return CallToolResult(content=[TextContent(
            type="text", text="No governance session active. Nothing to release."
        )])

    # Step 2: Verify task_id matches
    stored_task = lock.get("task_id", "")
    if stored_task and stored_task != task_id:
        return CallToolResult(content=[TextContent(
            type="text",
            text=f"Error: Lock belongs to task '{stored_task}', not '{task_id}'. Use end_change('{stored_task}')."
        )])

    # Step 3: Require a SCORED cycle before releasing the lock
    # (2026-08-08: upgraded from warning to BLOCK — Luke directive: agents
    # must close out/score before moving on. The old warning-only path let
    # agents end_change with the cycle still PENDING, then begin_change
    # stacked more unscored cycles. Scoring the cycle is the mandatory
    # precondition for releasing the lock; the lock then cannot be
    # released while its cycle is unscored, so begin_change's close-out
    # gate never sees a leaked PENDING from a completed task.)
    cycle_info = ""
    has_cycle = False
    cycle_data = None
    try:
        conn = _db()
        row = conn.execute(
            "SELECT id, composite, decision, user_overrode, unscored_reason, outcome_note "
            "FROM loop_cycles WHERE task_id = ? ORDER BY id DESC LIMIT 1",
            (task_id,)
        ).fetchone()
        conn.close()
        if row:
            has_cycle = True
            cycle_data = {"id": row["id"], "outcome_note": row["outcome_note"]}
            decision_class = _decision_class(row["decision"])
            composite = float(row["composite"] or 0.0)
            try:
                unscored_reason = (row["unscored_reason"] or "").strip()
            except (IndexError, KeyError):
                unscored_reason = ""
            accept = "✅" if decision_class == "STOP" else "⬜"
            cycle_info = f"Cycle #{row['id']} ({row['decision']}) {accept}"

            # (2026-09-23) Two independent requirements, both about the RECORD
            # rather than the spelling of the decision:
            #   1. class, not exact string — 'LOOP 🔄 — keep iterating' is LOOP;
            #   2. a closed-out cycle must carry a measurement OR say why it is
            #      unscored. 'user_overrode is not None' alone let an accepted
            #      cycle with composite 0.0 pass as "scored" when nothing was
            #      ever measured.
            if decision_class == "PENDING":
                return CallToolResult(content=[TextContent(
                    type="text",
                    text=(
                        "❌ Cannot release lock: this task's cycle is NOT scored — "
                        "it was never closed out.\n\n"
                        f"  Cycle #{row['id']} for task '{task_id}' is still PENDING "
                        "(no feedback recorded).\n\n"
                        "Close it out (AGENTS.md RULE 2 — score before moving on):\n"
                        f"  mcp__loop_governance__cycle_query(task_id='{task_id}')\n"
                        "  mcp__loop_governance__feedback_accept(cycle_id=" + str(row['id']) + ", note='…',\n"
                        "      completeness=<0-10>, quality=<0-10>, progress=<0-10>)\n"
                        "  or, when nothing could be measured:\n"
                        "  mcp__loop_governance__feedback_accept(cycle_id=" + str(row['id']) + ", note='…',\n"
                        "      unscored_reason='why nothing could be measured')\n"
                        "  or mcp__loop_governance__feedback_override(cycle_id=" + str(row['id']) + ", "
                        "correct_decision='…', note='…')\n\n"
                        "Then retry end_change. The lock stays held until the cycle is closed out."
                    )
                )])
            if composite <= 0.0 and not unscored_reason:
                return CallToolResult(content=[TextContent(
                    type="text",
                    text=(
                        "❌ Cannot release lock: this task's cycle is NOT scored.\n\n"
                        f"  Cycle #{row['id']} for task '{task_id}' reads "
                        f"'{row['decision']}' with composite 0.0 and no unscored_reason —\n"
                        "  an unscored close has to say WHY (2026-09-23).\n\n"
                        "Record the measurement:\n"
                        "  mcp__loop_governance__feedback_accept(cycle_id=" + str(row['id']) + ", note='…',\n"
                        "      completeness=<0-10>, quality=<0-10>, progress=<0-10>)\n"
                        "or state the reason it is unscored:\n"
                        "  mcp__loop_governance__feedback_accept(cycle_id=" + str(row['id']) + ", note='…',\n"
                        "      unscored_reason='why nothing could be measured')\n\n"
                        "Then retry end_change."
                    )
                )])
    except Exception as e:
        log.warning("end_change: cycle lookup failed: %s", e)
        has_cycle = False

    if not has_cycle:
        return CallToolResult(content=[TextContent(
            type="text",
            text=(
                "❌  Cannot release lock: no governance cycle found for this task.\n\n"
                "    A cycle must be created (via any write tool under this lock) and scored\n"
                "    before end_change() can release the lock.\n\n"
                "    To score: mcp__loop_governance__cycle_query(task_id='<task>')\n"
                "             mcp__loop_governance__feedback_accept(cycle_id=N, note='...')\n\n"
                "    This prevents orphan cycles that silently accumulate in the governance DB."
            )
        )])

    # Step 3b: Adversarial review hard gate (event-driven, complexity-gated).
    # A "sufficiently complex" change cannot close until an independent
    # reviewer returns CLEAN. Trivial changes skip. Reviewer outage refuses
    # the close (fail loudly). Runs AFTER the scored-cycle requirement and
    # BEFORE the lock release, so a blocked review keeps the lock held.
    review_block = _adversarial_review_gate(lock, cycle_data or {})
    if review_block is not None:
        return review_block

    # Step 4: Release the lock
    _release_lock(args)

    return CallToolResult(content=[TextContent(
        type="text",
        text=(
            f"🔓 Governance session '{task_id}' closed.\n"
            f"{cycle_info}\n"
            f"Lock released. You can start a new change with begin_change()."
        )
    )])


def _check_lock(args: dict | None = None) -> CallToolResult:
    """Check if a governance lock is active.

    Updates heartbeat on every call to prevent staleness.
    Auto-releases locks whose heartbeat has exceeded TTL.
    Proactively purges stale locks from other sessions (GAP #9).
    """
    _purge_stale_locks()
    state = _read_lock(args)
    if state is None:
        return CallToolResult(content=[TextContent(
            type="text", text=json.dumps({"active": False, "lock": None}, indent=2)
        )])

    # Check staleness
    if _is_lock_stale(state):
        stale = {
            "task_id": state.get("task_id", "unknown"),
            "session_id": state.get("session_id", "unknown"),
            "agent": state.get("agent", "unknown"),
            "started_at": state.get("started_at"),
            "heartbeat_at": state.get("heartbeat_at"),
            "ttl_seconds": state.get("ttl_seconds", DEFAULT_TTL),
        }
        _release_lock(args)
        return CallToolResult(content=[TextContent(
            type="text",
            text=json.dumps({
                "active": False,
                "lock": None,
                "auto_released": True,
                "released_lock": stale,
            }, indent=2)
        )])

    # Refresh heartbeat
    state["heartbeat_at"] = _now_iso()
    _write_lock(state, args)

    return CallToolResult(content=[TextContent(
        type="text",
        text=json.dumps({
            "active": True,
            "lock": state,
            "file": str(_session_lock_path(state.get("session_id", ""))),
        }, indent=2)
    )])


def _cycle_query(args: dict) -> CallToolResult:
    conn = _db()
    q = "SELECT * FROM loop_cycles WHERE 1=1"
    params = []
    if tid := args.get("task_id"):
        q += " AND task_id LIKE ?"
        params.append("%" + tid + "%")
    if mn := args.get("min_score"):
        q += " AND composite >= ?"
        params.append(mn)
    if mx := args.get("max_score"):
        q += " AND composite <= ?"
        params.append(mx)
    if args.get("unreviewed"):
        q += " AND user_overrode IS NULL"
    q += " ORDER BY id DESC LIMIT ?"
    params.append(args.get("limit", 10))
    rows = conn.execute(q, params).fetchall()
    conn.close()
    result = [dict(r) for r in rows]
    for r in result:
        for k, v in r.items():
            if isinstance(v, datetime):
                r[k] = v.isoformat()
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(result, indent=2, default=str))])


def _cycle_stats(args: dict) -> CallToolResult:
    try:
        conn = _db()
        total = conn.execute("SELECT COUNT(*) FROM loop_cycles").fetchone()[0]
        avg = conn.execute("SELECT ROUND(AVG(composite),1) FROM loop_cycles").fetchone()[0] or 0
        count_7 = conn.execute("SELECT COUNT(*) FROM loop_cycles WHERE composite >= 7.0").fetchone()[0]
        feedback = conn.execute("SELECT COUNT(*) FROM loop_cycles WHERE user_overrode IS NOT NULL").fetchone()[0]
        accepted = conn.execute("SELECT COUNT(*) FROM loop_cycles WHERE user_overrode = 0").fetchone()[0]
        overridden = conn.execute("SELECT COUNT(*) FROM loop_cycles WHERE user_overrode = 1").fetchone()[0]
        top_tasks = conn.execute(
            "SELECT task_id, COUNT(*) as n FROM loop_cycles GROUP BY task_id ORDER BY n DESC LIMIT 5"
        ).fetchall()
        conn.close()
        return CallToolResult(content=[TextContent(type="text", text=json.dumps({
            "total_cycles": total,
            "avg_composite": avg,
            "cycles_over_7": count_7,
            "feedback_count": feedback,
            "accepted": accepted,
            "overridden": overridden,
            "top_tasks": [dict(t) for t in top_tasks],
        }, indent=2))])
    except Exception as e:
        return CallToolResult(content=[TextContent(type="text", text=f"No loop DB yet, or error reading it: {e}")])


def _config_show(args: dict | None = None) -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(_config(), indent=2))])


def _config_set(args: dict) -> CallToolResult:
    key = args.get("key", "")
    value = args.get("value")
    if not key or value is None:
        return CallToolResult(content=[TextContent(type="text", text="Missing key or value")])
    config = _config()
    parts = key.split(".")
    section = config
    for p in parts[:-1]:
        if p not in section:
            return CallToolResult(content=[TextContent(type="text", text="Key not found: " + key)])
        section = section[p]
    last = parts[-1]
    if last not in section:
        return CallToolResult(content=[TextContent(type="text", text="Key not found: " + key)])
    old_val = section[last]
    # ── Config-aware delta enforcement (Fix GAP #2) ──
    # Weights use auto_apply.max_weight_delta (default 0.10).
    # Thresholds use auto_apply.max_threshold_delta (default 1.0).
    # Read from the actual config so admin tuning is respected.
    key_section = parts[0] if len(parts) >= 2 else ""
    auto_apply = config.get("auto_apply", {})
    if key_section == "weights":
        max_delta = auto_apply.get("max_weight_delta", 0.10)
        if abs(value - old_val) > max_delta:
            return CallToolResult(content=[TextContent(
                type="text",
                text=f"Safety bound: max delta for weights is {max_delta:.2f}. "
                     f"Cannot change from {old_val} to {value} (delta={abs(value-old_val):.3f})."
            )])
        if value < 0.05 or value > 0.80:
            return CallToolResult(content=[TextContent(
                type="text",
                text=f"Weight must be between 0.05 and 0.80 (got {value})."
            )])
        # ── Weight-sum validation (Fix GAP #3) ──
        # Changing one weight affects the total sum. Reject if the new sum
        # would fall outside [0.8, 1.2], preventing silent scoring-model skew.
        current_weights = config.get("weights", {})
        other_sum = sum(v for k, v in current_weights.items() if k != last)
        new_sum = other_sum + value
        if new_sum < 0.8 or new_sum > 1.2:
            return CallToolResult(content=[TextContent(
                type="text",
                text=f"Weight sum would be {new_sum:.2f} (outside [0.8, 1.2]). "
                     f"Other weights sum to {other_sum:.2f}, proposed '{last}'={value}. "
                     f"Adjust other weights first or choose a different value."
            )])
    elif key_section == "thresholds":
        max_delta = auto_apply.get("max_threshold_delta", 1.0)
        if abs(value - old_val) > max_delta:
            return CallToolResult(content=[TextContent(
                type="text",
                text=f"Safety bound: max delta for thresholds is {max_delta:.2f}. "
                     f"Cannot change from {old_val} to {value} (delta={abs(value-old_val):.2f})."
            )])
        if value < 0 or value > 10:
            return CallToolResult(content=[TextContent(type="text", text="Value must be between 0 and 10")])
    else:
        # Non-structured keys (version, embed_weight, etc.) — basic bounds
        if abs(value - old_val) > 1.0:
            return CallToolResult(content=[TextContent(
                type="text",
                text=f"Safety bound: max delta 1.0 for generic keys."
                     f" Cannot change from {old_val} to {value}."
            )])
        if value < 0 or value > 10:
            return CallToolResult(content=[TextContent(type="text", text="Value must be between 0 and 10")])
    section[last] = value
    CONFIG_PATH.write_text(json.dumps(config, indent=2))
    return CallToolResult(content=[TextContent(type="text", text=json.dumps({
        "updated": key, "from": old_val, "to": value,
    }, indent=2))])


def _feedback_accept(args: dict) -> CallToolResult:
    cycle_id = args.get("cycle_id")
    task_id = args.get("task_id", "").strip()
    note = args.get("note", "")
    if cycle_id is None and not task_id:
        return CallToolResult(content=[TextContent(type="text", text="Error: cycle_id or task_id is required")])
    try:
        conn = _db()
        # Resolve task_id to the session's current PENDING cycle
        if cycle_id is None and task_id:
            session_id = get_session_id(args)
            # Guard: verify session has at most 1 PENDING cycle
            all_pending = conn.execute(
                "SELECT id, task_id FROM loop_cycles "
                "WHERE session_id = ? AND decision = 'PENDING' AND user_overrode IS NULL "
                "ORDER BY id DESC",
                (session_id,),
            ).fetchall()
            if len(all_pending) > 1:
                conn.close()
                return CallToolResult(content=[TextContent(
                    type="text",
                    text=f"Error: Session has {len(all_pending)} PENDING cycles — "
                         f"use explicit cycle_id to disambiguate, not task_id."
                )])
            if len(all_pending) == 0:
                conn.close()
                return CallToolResult(content=[TextContent(
                    type="text",
                    text=f"Error: No PENDING cycle found for task '{task_id}' in this session. "
                         f"Use cycle_query to find valid cycle IDs or call begin_change first."
                )])
            # Confirm the resolved cycle matches the given task_id
            if all_pending[0]["task_id"] != task_id:
                conn.close()
                return CallToolResult(content=[TextContent(
                    type="text",
                    text=f"Error: Session has one PENDING cycle (#{all_pending[0]['id']} "
                         f"for task '{all_pending[0]['task_id']}'), not '{task_id}'. "
                         f"Use cycle_id={all_pending[0]['id']} instead."
                )])
            cycle_id = all_pending[0]["id"]
        existing = conn.execute("SELECT id, decision FROM loop_cycles WHERE id = ?", (cycle_id,)).fetchone()
        if not existing:
            conn.close()
            return CallToolResult(content=[TextContent(
                type="text",
                text=f"Error: Cycle #{cycle_id} not found in loop-governance DB. Use cycle_query to find valid cycle IDs."
            )])
        # Fix GAP #5: update decision from PENDING to MOVE_ON when accepted
        # Don't overwrite STOP decisions (from pre-commit hook score-cycle)
        current_decision = existing["decision"] or "PENDING"
        new_decision = current_decision
        if current_decision in ("PENDING", "LOOP"):
            new_decision = "MOVE_ON"

        # Optional self-reported scores (2026-09-23): an accepted cycle used to
        # keep composite 0.0, which trend queries read as a hard failure when
        # it only meant "never measured". The caller may now supply the three
        # components; composite is recomputed with the configured weights, so
        # nothing is invented — a cycle with no scores stays unscored.
        reported = {}
        for field in ("completeness", "quality", "progress"):
            raw = args.get(field)
            if raw is None:
                continue
            try:
                value = float(raw)
            except (TypeError, ValueError):
                conn.close()
                return CallToolResult(content=[TextContent(
                    type="text",
                    text=f"Error: '{field}' must be a number 0-10 (got {raw!r}).")])
            if not 0.0 <= value <= 10.0:
                conn.close()
                return CallToolResult(content=[TextContent(
                    type="text",
                    text=f"Error: '{field}' must be between 0 and 10 (got {value}).")])
            reported[field] = value

        unscored_reason = (args.get("unscored_reason") or "").strip()
        if not reported and not unscored_reason:
            conn.close()
            return CallToolResult(content=[TextContent(
                type="text",
                text=(
                    f"❌ Refusing to close cycle #{cycle_id} with nothing measured.\n\n"
                    "An accepted cycle must either carry a score or say why it is\n"
                    "unscored — 'composite 0.0' on its own is indistinguishable from a\n"
                    "failed change (2026-09-23).\n\n"
                    "  • scored —\n"
                    f"      mcp__loop_governance__feedback_accept(cycle_id={cycle_id}, note='…',\n"
                    "          completeness=<0-10>, quality=<0-10>, progress=<0-10>)\n"
                    "  • unscored —\n"
                    f"      mcp__loop_governance__feedback_accept(cycle_id={cycle_id}, note='…',\n"
                    "          unscored_reason='why nothing could be measured')\n\n"
                    "The cycle stays PENDING until one of the two is supplied."
                )
            )])

        if reported:
            row = conn.execute(
                "SELECT completeness, quality, progress FROM loop_cycles WHERE id = ?",
                (cycle_id,)).fetchone()
            components = {
                f: reported.get(f, float(row[f] or 0.0))
                for f in ("completeness", "quality", "progress")
            }
            weights = _config().get(
                "weights", {"completeness": 0.4, "quality": 0.3, "progress": 0.3})
            composite = round(sum(components[f] * float(weights.get(f, 0.0)) for f in components), 2)
            conn.execute(
                "UPDATE loop_cycles SET completeness=?, quality=?, progress=?, composite=?, "
                "unscored_reason=?, user_overrode=0, decision=?, outcome_note=? WHERE id=?",
                (components["completeness"], components["quality"], components["progress"],
                 composite, unscored_reason or None, new_decision, note, cycle_id))
        else:
            conn.execute(
                "UPDATE loop_cycles SET unscored_reason=?, user_overrode=0, decision=?, "
                "outcome_note=? WHERE id=?",
                (unscored_reason, new_decision, note, cycle_id))
        conn.commit()
        conn.close()
        scored = (
            f" Scored: completeness={components['completeness']}, quality={components['quality']}, "
            f"progress={components['progress']} → composite={composite}."
            if reported else f" Unscored (reason recorded: {unscored_reason})."
        )
        return CallToolResult(content=[TextContent(
            type="text",
            text=f"✅ Cycle #{cycle_id} marked as accepted (decision: {current_decision} → {new_decision}).{scored}"
        )])
    except Exception as e:
        return CallToolResult(content=[TextContent(type="text", text=f"Error accepting cycle #{cycle_id}: {e}")])


def _feedback_override(args: dict) -> CallToolResult:
    cycle_id = args.get("cycle_id")
    task_id = args.get("task_id", "").strip()
    if cycle_id is None and not task_id:
        return CallToolResult(content=[TextContent(type="text", text="Error: cycle_id or task_id is required")])
    correct = args.get("correct_decision", "LOOP")
    note = args.get("note", "")
    correct_note = correct + ": " + note
    try:
        conn = _db()
        # Resolve task_id to the session's current PENDING cycle
        if cycle_id is None and task_id:
            session_id = get_session_id(args)
            # Guard: verify session has at most 1 PENDING cycle
            all_pending = conn.execute(
                "SELECT id, task_id FROM loop_cycles "
                "WHERE session_id = ? AND decision = 'PENDING' AND user_overrode IS NULL "
                "ORDER BY id DESC",
                (session_id,),
            ).fetchall()
            if len(all_pending) > 1:
                conn.close()
                return CallToolResult(content=[TextContent(
                    type="text",
                    text=f"Error: Session has {len(all_pending)} PENDING cycles — "
                         f"use explicit cycle_id to disambiguate, not task_id."
                )])
            if len(all_pending) == 0:
                conn.close()
                return CallToolResult(content=[TextContent(
                    type="text",
                    text=f"Error: No PENDING cycle found for task '{task_id}' in this session. "
                         f"Use cycle_query to find valid cycle IDs or call begin_change first."
                )])
            # Confirm the resolved cycle matches the given task_id
            if all_pending[0]["task_id"] != task_id:
                conn.close()
                return CallToolResult(content=[TextContent(
                    type="text",
                    text=f"Error: Session has one PENDING cycle (#{all_pending[0]['id']} "
                         f"for task '{all_pending[0]['task_id']}'), not '{task_id}'. "
                         f"Use cycle_id={all_pending[0]['id']} instead."
                )])
            cycle_id = all_pending[0]["id"]
        existing = conn.execute("SELECT id FROM loop_cycles WHERE id = ?", (cycle_id,)).fetchone()
        if not existing:
            conn.close()
            return CallToolResult(content=[TextContent(
                type="text",
                text=f"Error: Cycle #{cycle_id} not found in loop-governance DB. Use cycle_query to find valid cycle IDs."
            )])
        conn.execute(
            "UPDATE loop_cycles SET user_overrode=1, decision=?, outcome_note=?, "
            "unscored_reason=COALESCE(?, unscored_reason) WHERE id=?",
            (correct, correct_note, (args.get("unscored_reason") or "").strip() or None, cycle_id))
        conn.commit()
        conn.close()
        return CallToolResult(content=[TextContent(type="text", text=f"⏩ Cycle #{cycle_id} overridden → {correct}.")])
    except Exception as e:
        return CallToolResult(content=[TextContent(type="text", text=f"Error overriding cycle #{cycle_id}: {e}")])


def _cache_search(args: dict) -> CallToolResult:
    if not CACHE_DB.exists():
        return CallToolResult(content=[TextContent(type="text", text="Cache DB not found. Run session-cache build first.")])
    query = args.get("query", "")
    top_k = args.get("top_k", 5)
    if not query:
        return CallToolResult(content=[TextContent(type="text", text="No query provided.")])
    query_emb = _embed(query)
    if not query_emb:
        return CallToolResult(content=[TextContent(type="text", text="Embedding unavailable.")])
    conn = sqlite3.connect(str(CACHE_DB))
    rows = conn.execute("SELECT id, source, source_id, text, embedding, agent FROM embeddings").fetchall()
    conn.close()
    scored = []
    for row in rows:
        stored = json.loads(row[4])
        sim = _cosine_sim(query_emb, stored)
        scored.append((sim, {
            "id": row[0], "source": row[1], "source_id": row[2],
            "text": row[3][:200], "agent": row[5],
        }))
    scored.sort(key=lambda x: x[0], reverse=True)
    results = [s[1] for s in scored[:top_k]]
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(results, indent=2))])


def _record_issue(args: dict) -> CallToolResult:
    """Record a discovered issue to the task_events table."""
    task_id = args.get("task_id", "").strip()
    description = args.get("description", "").strip()
    severity = args.get("severity", "medium")
    category = args.get("category", "")

    if not task_id:
        return CallToolResult(content=[TextContent(type="text", text="Error: task_id is required")])
    if not description:
        return CallToolResult(content=[TextContent(type="text", text="Error: description is required")])

    detail = description
    if severity:
        detail = f"[{severity}] " + detail
    if category:
        detail = f"({category}) " + detail

    agent = os.environ.get("AGENT_NAME", "unknown")
    try:
        conn = _db()
        conn.execute(
            """INSERT INTO task_events (task_id, agent, event_type, detail)
               VALUES (?, ?, 'issue_recorded', ?)""",
            (task_id, agent, detail),
        )
        conn.commit()
        event_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        return CallToolResult(content=[TextContent(
            type="text",
            text=f"📋 Issue recorded as event #{event_id} for task '{task_id}'.",
        )])
    except Exception as e:
        return CallToolResult(content=[TextContent(
            type="text", text=f"Error recording issue: {e}",
        )])


# ── State Machine Helpers ────────────────────────────────────


def _verify_lock_for_task(task_id: str, args: dict | None = None) -> tuple[dict | None, str]:
    """Verify the active lock matches the given task_id. Returns (state, error_msg)."""
    state = _read_lock(args)
    if state is None:
        return None, "No active governance lock."
    stored_task = state.get("task_id", "")
    if stored_task != task_id:
        return None, f"Lock belongs to task '{stored_task}', not '{task_id}'."
    return state, ""


def _write_lock_and_log(state: dict, event_type: str, detail: str = "", args: dict | None = None) -> None:
    """Update the lock file and log a task event."""
    _write_lock(state, args)
    try:
        conn = _db()
        conn.execute(
            """INSERT INTO task_events (task_id, agent, event_type, from_state, to_state, detail)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (state.get("task_id", ""),
             os.environ.get("AGENT_NAME", "unknown"),
             event_type,
             state.get("status", ""),
             state.get("status", ""),
             detail),
        )
        conn.commit()
        conn.close()
    except Exception:
        log.warning("Best-effort operation — expected failure: except Exception")
        pass


# ── State Machine Tool Implementations ───────────────────────


def _advance_task_state(args: dict) -> CallToolResult:
    """Transition the active task to a new state."""
    task_id = args.get("task_id", "").strip()
    new_state = args.get("new_state", "").strip().lower()
    reason = args.get("reason", "")

    if not task_id:
        return CallToolResult(content=[TextContent(type="text", text="Error: task_id is required")])
    if not new_state:
        return CallToolResult(content=[TextContent(type="text", text="Error: new_state is required")])

    state, err = _verify_lock_for_task(task_id, args)
    if err:
        return CallToolResult(content=[TextContent(type="text", text=err)])

    old_state = state.get("status", "idle")

    if old_state == new_state:
        return CallToolResult(content=[TextContent(
            type="text", text=f"Already in state '{old_state}'. No transition needed."
        )])

    if not is_valid_transition(old_state, new_state):
        allowed = VALID_TRANSITIONS.get(old_state, set())
        return CallToolResult(content=[TextContent(
            type="text",
            text=f"Invalid transition: '{old_state}' → '{new_state}'. "
                 f"Allowed: {', '.join(sorted(allowed)) if allowed else '(terminal state)'}"
        )])

    # Apply transition
    state["status"] = new_state
    detail = f"Transition: {old_state} → {new_state}"
    if reason:
        detail += f" — {reason}"
    _write_lock_and_log(state, "state_transition", detail, args)

    return CallToolResult(content=[TextContent(
        type="text",
        text=f"🔄 Task '{task_id}' state: {old_state} → {new_state}."
        + (f" Reason: {reason}" if reason else "")
    )])


def _request_interruption(args: dict) -> CallToolResult:
    """Push current task onto stack and create a sub-task.
    
    Fix GAP #7: generates a unique sub-task_id by appending a counter suffix
    to the parent's task_id, avoiding duplicate IDs in the task stack.
    Fix GAP #3: enforces MAX_STACK_DEPTH (5) to prevent infinite-interrupt
    resource exhaustion.
    """
    task_id = args.get("task_id", "").strip()
    description = args.get("description", "").strip()
    reason = args.get("reason", "")

    if not task_id:
        return CallToolResult(content=[TextContent(type="text", text="Error: task_id is required")])
    if not description:
        return CallToolResult(content=[TextContent(type="text", text="Error: description is required")])

    state, err = _verify_lock_for_task(task_id, args)
    if err:
        return CallToolResult(content=[TextContent(type="text", text=err)])

    old_state = state.get("status", "idle")

    # Must be in executing/verifying/reporting to interrupt
    if old_state not in ("executing", "verifying", "reporting"):
        return CallToolResult(content=[TextContent(
            type="text",
            text=f"Cannot interrupt: task is in '{old_state}'. Can only interrupt from executing/verifying/reporting."
        )])

    # Transition to interrupt_req
    if not is_valid_transition(old_state, "interrupt_req"):
        return CallToolResult(content=[TextContent(
            type="text", text=f"Cannot transition to interrupt_req from '{old_state}'."
        )])

    # Fix GAP #3: Enforce max stack depth
    MAX_STACK_DEPTH = 5
    stack = state.get("task_stack", [])
    if len(stack) >= MAX_STACK_DEPTH:
        return CallToolResult(content=[TextContent(
            type="text",
            text=f"Cannot interrupt: stack depth limit ({MAX_STACK_DEPTH}) reached. "
                 f"Resume a parent task first before creating new interruptions."
        )])

    # Fix GAP #7: Generate unique sub-task_id by appending counter suffix
    sub_counter = len(stack) + 1
    sub_task_id = f"{task_id}_sub{sub_counter}"

    # Save current state to task_stack
    stacked = {
        "task_id": state["task_id"],
        "description": state.get("description", ""),
        "sub_task_id": sub_task_id,
        "status": old_state,
        "started_at": state.get("started_at", ""),
        "acceptance_criteria": state.get("acceptance_criteria", []),
        "allowed_scope": state.get("allowed_scope", []),
        "plan": state.get("plan", []),
    }
    stack.append(stacked)

    # Replace lock with interruption sub-task (using unique sub_task_id)
    now_iso = _now_iso()
    state["task_id"] = sub_task_id
    state["description"] = description
    state["status"] = "executing"
    state["started_at"] = now_iso
    state["heartbeat_at"] = now_iso
    state["task_stack"] = stack
    state["acceptance_criteria"] = []
    state["allowed_scope"] = []
    state["plan"] = []

    detail = f"Interrupted by: {sub_task_id} — {description}"
    if reason:
        detail += f" (reason: {reason})"
    _write_lock_and_log(state, "interruption_requested", detail, args)

    return CallToolResult(content=[TextContent(
        type="text",
        text=f"⏸️ Interruption: '{stacked['task_id']}' suspended. New sub-task '{sub_task_id}' started.\n"
             f"  Stack depth: {len(stack)}\n"
             f"  Max depth: {MAX_STACK_DEPTH}\n"
             f"  Use resume_from_interrupt to restore '{stacked['task_id']}' when done."
    )])


def _resume_from_interrupt(args: dict) -> CallToolResult:
    """Pop task_stack and restore the parent task."""
    state = _read_lock(args)
    if state is None:
        return CallToolResult(content=[TextContent(type="text", text="No active governance lock.")])

    stack = state.get("task_stack", [])
    if not stack:
        return CallToolResult(content=[TextContent(type="text", text="Task stack is empty. Nothing to resume.")])

    parent = stack.pop()
    now_iso = _now_iso()

    # Restore parent task state
    state["task_id"] = parent["task_id"]
    state["description"] = parent.get("description", "")
    state["status"] = parent.get("status", "executing")
    state["started_at"] = parent.get("started_at", now_iso)
    state["heartbeat_at"] = now_iso
    state["task_stack"] = stack
    state["acceptance_criteria"] = parent.get("acceptance_criteria", [])
    state["allowed_scope"] = parent.get("allowed_scope", [])
    state["plan"] = parent.get("plan", [])

    detail = f"Resumed: {parent['task_id']} (stack depth: {len(stack)})"
    _write_lock_and_log(state, "interruption_resumed", detail, args)

    return CallToolResult(content=[TextContent(
        type="text",
        text=f"▶️ Resumed task '{parent['task_id']}' (state: {state['status']}). Stack depth: {len(stack)}."
    )])


def _request_completion(args: dict) -> CallToolResult:
    """Validate all acceptance_criteria and mark task as completion_verified."""
    task_id = args.get("task_id", "").strip()
    evidence = args.get("evidence", {})

    if not task_id:
        return CallToolResult(content=[TextContent(type="text", text="Error: task_id is required")])

    state, err = _verify_lock_for_task(task_id, args)
    if err:
        return CallToolResult(content=[TextContent(type="text", text=err)])

    acs = state.get("acceptance_criteria", [])
    blocked_by = state.get("blocked_by", "")
    status = state.get("status", "")

    # Check for blockers
    if status == "blocked" or blocked_by:
        return CallToolResult(content=[TextContent(
            type="text",
            text=f"⛔ Cannot complete task '{task_id}': task is BLOCKED.\n"
                 f"  Blocked by: {blocked_by}\n"
                 f"  Use advance_task_state to resolve the blocker first."
        )])

    # No acceptance criteria = lightweight task, auto-verify
    if not acs:
        state["completion_verified"] = True
        state["completion_detail"] = "No acceptance criteria (lightweight task)"
        _write_lock_and_log(state, "completion_verified", "Auto-verified: lightweight task (no ACs)", args)
        return CallToolResult(content=[TextContent(
            type="text",
            text=f"✅ Task '{task_id}' has no acceptance criteria — auto-verified.\n"
                 f"  You can now call end_change('{task_id}')."
        )])

    # Validate each criterion
    failed = []
    passed = []
    for ac in acs:
        ac_id = ac.get("id", "")
        ac_desc = ac.get("description", "")
        verified_by = ac.get("verified_by", "")

        if verified_by == "loop_scorer":
            # Check loop-governance DB for a scored MOVE_ON cycle
            try:
                conn = _db()
                row = conn.execute(
                    """SELECT decision, composite, user_overrode
                       FROM loop_cycles
                       WHERE task_id = ? AND user_overrode IS NOT NULL
                       ORDER BY id DESC LIMIT 1""",
                    (task_id,),
                ).fetchone()
                conn.close()
                if row:
                    decision = row["decision"]
                    user_overrode = row["user_overrode"]
                    # MOVE_ON or user-overridden cycle counts as passing
                    if "MOVE" in decision.upper() or user_overrode == 0:
                        passed.append(f"{ac_id}: ✓ Loop-scorer verified (decision: {decision})")
                        continue
                    failed.append(f"{ac_id}: ✗ Loop-scorer decision was '{decision}' — not MOVE_ON")
                else:
                    failed.append(f"{ac_id}: ✗ No scored cycle found for task '{task_id}'. Run score-cycle first.")
            except Exception as e:
                failed.append(f"{ac_id}: ✗ Error checking loop DB: {e}")

        elif ac_id in evidence:
            passed.append(f"{ac_id}: ✓ Evidence provided: {evidence[ac_id]}")
        else:
            failed.append(f"{ac_id}: ✗ No evidence provided and no automated verifier configured ({verified_by or 'none'})")

    if failed:
        return CallToolResult(content=[TextContent(
            type="text",
            text=(
                f"⛔ Task '{task_id}' completion REJECTED.\n\n"
                f"Failed criteria:\n" + "\n".join(f"  {f}" for f in failed) + "\n\n"
                + ("Passed criteria:\n" + "\n".join(f"  {p}" for p in passed) + "\n\n" if passed else "")
                + "Fix the failed criteria and call request_completion again."
            )
        )])

    # All passed — mark as completion_verified
    state["completion_verified"] = True
    state["completion_detail"] = "; ".join(passed)
    _write_lock_and_log(state, "completion_verified", state["completion_detail"], args)

    return CallToolResult(content=[TextContent(
        type="text",
        text=f"✅ Task '{task_id}' completion verified.\n"
             + "\n".join(f"  {p}" for p in passed) + "\n\n"
             + f"All acceptance criteria met. You can now call end_change('{task_id}')."
    )])


def _promote_issue_to_task(args: dict) -> CallToolResult:
    """Promote an issue to a standalone task. Requires no active lock."""
    task_id = args.get("task_id", "").strip()
    description = args.get("description", "").strip()
    issue_event_id = args.get("issue_event_id")
    ttl = args.get("ttl", 3600)

    if not task_id:
        return CallToolResult(content=[TextContent(type="text", text="Error: task_id is required")])
    if not description:
        return CallToolResult(content=[TextContent(type="text", text="Error: description is required")])

    # Must not have an active lock
    existing = _read_lock(args)
    if existing is not None:
        return CallToolResult(content=[TextContent(
            type="text",
            text=f"Cannot promote issue: active lock exists for task '{existing.get('task_id')}'. "
                 f"Complete or cancel the current task first."
        )])

    session_id = get_session_id(args)
    now_iso = _now_iso()

    # Optionally look up the issue for the detail
    detail = description
    if issue_event_id:
        try:
            conn = _db()
            row = conn.execute(
                "SELECT detail FROM task_events WHERE id = ? AND event_type = 'issue_recorded'",
                (issue_event_id,),
            ).fetchone()
            conn.close()
            if row:
                detail = f"{description} (from issue #{issue_event_id}: {row[0]})"
            else:
                detail = f"{description} (issue #{issue_event_id} not found)"
        except Exception:
            detail = f"{description} (issue #{issue_event_id}: lookup failed)"

    state = {
        "task_id": task_id,
        "description": description,
        "started_at": now_iso,
        "agent": os.environ.get("AGENT_NAME", "unknown"),
        "session_id": session_id,
        "ttl_seconds": ttl,
        "heartbeat_at": now_iso,
        "scored": False,
        "acceptance_criteria": [],
        "allowed_scope": [],
        "plan": [],
        "task_stack": [],
        "status": "executing",
    }
    _write_lock(state, args)

    # Fix GAP #4: Create a cycle in loop-governance DB so promoted-issue
    # tasks are traceable and have a cycle record for end_change.
    try:
        conn = _db()
        row = conn.execute(
            "SELECT COALESCE(MAX(cycle_num), 0) + 1 FROM loop_cycles WHERE task_id = ?",
            (task_id,)
        ).fetchone()
        cycle_num = row[0] if row else 1
        conn.execute(
            """INSERT INTO loop_cycles
               (task_id, cycle_num, completeness, quality, progress, composite,
                no_progress, decision, user_overrode, outcome_note, session_id)
               VALUES (?, ?, 0, 0, 0, 0, 0, 'PENDING', NULL, ?, ?)""",
            (task_id, cycle_num, f"Promoted from issue: {description}", session_id)
        )
        conn.commit()
        cycle_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.close()
        cycle_msg = f"\n  Pending cycle #{cycle_id} created."
    except Exception:
        cycle_msg = "\n  (note: no cycle record — DB unavailable)"

    # Log as task event
    try:
        conn = _db()
        conn.execute(
            """INSERT INTO task_events (task_id, agent, event_type, detail)
               VALUES (?, ?, 'promoted_from_issue', ?)""",
            (task_id, os.environ.get("AGENT_NAME", "unknown"), detail),
        )
        conn.commit()
        conn.close()
    except Exception:
        log.warning("Expected failure for: except Exception")
        pass

    return CallToolResult(content=[TextContent(
        type="text",
        text=(
            f"📌 Issue promoted to task '{task_id}': {description}\\n"
            f"  Lock created with TTL: {ttl}s{cycle_msg}\\n"
            f"  Use end_change('{task_id}') when done."
        )
    )])


# ── MCP Server ───────────────────────────────────────────────
# Only constructed when the SDK is present. Everything above (the handlers) is
# SDK-independent so an MCP-less host can drive it through the CLI adapter.
server = Server("loop-governance", on_list_tools=list_tools, on_call_tool=call_tool) if MCP_AVAILABLE else None


# ── Main ─────────────────────────────────────────────────────

async def main():
    if not MCP_AVAILABLE:
        print("loop-governance: the MCP SDK is not installed. Use the CLI adapter "
              "(ops/scripts/loop-gov.py) or run this with a python that has 'mcp'.",
              file=sys.stderr)
        sys.exit(1)
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
