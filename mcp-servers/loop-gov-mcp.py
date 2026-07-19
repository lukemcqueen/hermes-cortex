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
import json
import logging
import os
import sqlite3
import subprocess
import sys
import time
import traceback
import urllib.error
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


# Ensure hermes_models.py is importable
_HERMES_HOME = Path.home() / ".hermes"
_HERMES_SCRIPTS = _HERMES_HOME / "scripts"
if _HERMES_SCRIPTS.exists():
    sys.path.insert(0, str(_HERMES_SCRIPTS))
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_SCRIPTS = _SCRIPT_DIR.parent / "scripts"
if _REPO_SCRIPTS.exists():
    sys.path.insert(0, str(_REPO_SCRIPTS))

from hermes_models import get_model

NOMIC_MODEL = get_model("EMBEDDING_MODEL", "nomic-embed-text:v1.5")

# ── Dependency Check: mcp package ────────────────────────────
_HAVE_MCP = importlib.util.find_spec("mcp")
if _HAVE_MCP is None:
    msg = (
        "[mcp-server] ERROR: Required 'mcp' Python package not found.\n"
        "[mcp-server] Install it with:\n"
        f"[mcp-server]   {sys.executable} -m pip install mcp\n"
        "[mcp-server] Or if using system Python:\n"
        "[mcp-server]   pip install mcp"
    )
    print(msg, file=sys.stderr)
    sys.exit(1)

log = logging.getLogger("loop-governance")
logging.basicConfig(level=logging.DEBUG, format="[mcp-server] %(levelname)s: %(message)s", stream=sys.stderr, force=True)

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, CallToolResult

HOME = Path.home()
SESSION_FILE = HOME / ".hermes" / "session.id"
LOOP_DB = HOME / ".hermes-cortex" / "data" / "loop-governance.db"
CONFIG_PATH = HOME / ".hermes-cortex" / "data" / "loop-governance-config.json"
CACHE_DB = HOME / ".hermes-cortex" / "data" / "session-embeddings.db"
GOVERNANCE_STATE_DIR = HOME / ".hermes-cortex" / "state"
DEFAULT_TTL = 3600  # 1 hour


# ── Session ID ───────────────────────────────────────────────

def get_session_id() -> str:
    """Return a persistent session ID, creating one on first call.

    The session ID lives in ~/.hermes/session.id and persists across
    tool calls within one Hermes session. A new Hermes session (e.g. a
    separate terminal window) gets its own ID.
    """
    if SESSION_FILE.exists():
        return SESSION_FILE.read_text().strip()
    sid = f"sess_{uuid.uuid4().hex[:12]}"
    SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_FILE.write_text(sid)
    return sid


# ── Governance Lock Path ─────────────────────────────────────

def _derive_slug() -> str:
    """Derive repo slug deterministically — no cwd or git PATH dependency.

    Checks the canonical repo locations for a .git directory and uses
    the directory name directly. This slug is stored in the lock content
    for the enforcer to match against — the lock filename is session-scoped.
    """
    for candidate in [HOME / "hermes-cortex", HOME / ".hermes-cortex"]:
        if (candidate / ".git").exists():
            return candidate.name
    # Last resort: try git rev-parse from cwd
    try:
        repo_root = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL, timeout=3,
        ).decode().strip()
        return Path(repo_root).name
    except Exception:
        return "generic"


def _session_lock_path(session_id: str) -> Path:
    """Return a unique lock file path per session.

    Each governance lock is named by its session ID, making it
    impossible for two sessions to collide on the same file.
    The enforcer scans all .governance-*.json files and matches
    by the repo_slug stored in each lock's content.
    """
    return GOVERNANCE_STATE_DIR / f".governance-{session_id}.json"


# ── Lock helpers ─────────────────────────────────────────────

def _now_iso() -> str:
    """Return current UTC time as ISO 8601 string with seconds precision."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _is_lock_stale(state: dict) -> bool:
    """Check if a lock's heartbeat has exceeded its TTL."""
    ttl = state.get("ttl_seconds", DEFAULT_TTL)
    heartbeat_str = state.get("heartbeat_at", state.get("started_at", ""))
    if not heartbeat_str:
        return False
    try:
        hb_str = heartbeat_str.replace("Z", "+00:00").replace("+00:00", "+00:00")
        heartbeat = datetime.fromisoformat(hb_str)
        now = datetime.now(timezone.utc)
        elapsed = (now - heartbeat).total_seconds()
        return elapsed > ttl
    except (ValueError, TypeError):
        return False


def _read_lock() -> dict | None:
    """Read this session's lock file, return state dict or None."""
    session_id = get_session_id()
    path = _session_lock_path(session_id)
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None
    return None


def _write_lock(state: dict) -> None:
    """Write lock state to a session-scoped file.

    The lock filename uses the session_id so two sessions never
    collide on the same file. The repo_slug in the content lets
    the enforcer filter locks by repo.
    """
    session_id = state.get("session_id", get_session_id())
    path = _session_lock_path(session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))


def _release_lock() -> None:
    """Remove this session's lock file."""
    session_id = get_session_id()
    path = _session_lock_path(session_id)
    if path.exists():
        path.unlink()


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

def _db() -> sqlite3.Connection:
    """Get or create the loop-governance DB with auto-schema init."""
    LOOP_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(LOOP_DB))
    conn.row_factory = sqlite3.Row
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
        pass  # column already exists

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
        pass

    conn.commit()
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

server = Server("loop-governance")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="begin_change",
            description="MANDATORY: Call before making any code/config change. Creates a governance lock AND a pending cycle in the loop-governance DB. You must call feedback_accept on the pending cycle before end_change will release the lock. Optional: pass acceptance_criteria, allowed_scope, or plan for full task tracking (v3 extended schema).",
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
            description="RELEASE the governance lock. Checks loop-governance DB for a reviewed cycle (feedback_accept/override) matching this task_id. If the pending cycle hasn't been scored, the release is REJECTED — call feedback_accept first.",
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
            description="Mark a scored cycle decision as correct.",
            inputSchema={
                "type": "object",
                "properties": {
                    "cycle_id": {"type": "integer", "description": "Cycle ID from cycle_query"},
                    "note": {"type": "string", "description": "Optional note"},
                },
                "required": ["cycle_id"],
            },
        ),
        Tool(
            name="feedback_override",
            description="Mark a scored cycle decision as wrong and record the correct decision.",
            inputSchema={
                "type": "object",
                "properties": {
                    "cycle_id": {"type": "integer", "description": "Cycle ID from cycle_query"},
                    "correct_decision": {
                        "type": "string",
                        "enum": ["STOP", "LOOP", "MOVE_ON"],
                        "description": "What the decision should have been",
                    },
                    "note": {"type": "string", "description": "Why the override"},
                },
                "required": ["cycle_id"],
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
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any] | None) -> CallToolResult:
    args = arguments or {}
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

    session_id = get_session_id()
    now_iso = _now_iso()

    # Defaults for audit trail (may be overwritten by force-override below)
    audit_note = ""
    released_session = ""

    # ── Step 1: Resolve any existing lock (force path) BEFORE DB cycle ──
    # For force=True: read old lock info and release it. The new lock file
    # is NOT written yet — that happens only after DB cycle confirms.
    # For normal (non-force): just check and reject if lock exists.
    existing = _read_lock()
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
        _release_lock()
        audit_note = (
            f"Lock overridden by force=True.\n"
            f"  Released session: {released_session}\n"
            f"  Released task:    {released_task}\n"
            f"  New session:      {session_id}\n"
            f"  New task:         {task_id}"
        )

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
            f"     1. mcp_loop_governance_cycle_query(task_id='{task_id}')\n"
            f"     2. mcp_loop_governance_feedback_accept(id={cycle_id}, note='...')\n"
            f"     3. mcp_loop_governance_end_change(task_id='{task_id}')"
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
    state = {
        "task_id": task_id,
        "description": description,
        "repo_slug": _derive_slug(),
        "started_at": now_iso,
        "agent": os.environ.get("AGENT_NAME", "unknown"),
        "session_id": session_id,
        "ttl_seconds": ttl,
        "heartbeat_at": now_iso,
        "scored": False,
        # Harness v3 extended fields (optional — empty = lightweight task mode)
        "acceptance_criteria": args.get("acceptance_criteria", []),
        "allowed_scope": args.get("allowed_scope", []),
        "plan": args.get("plan", []),
        "task_stack": [],
        "status": "executing",
    }
    _write_lock(state)

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


def _end_change(args: dict) -> CallToolResult:
    """Release governance lock — requires a scored cycle in the loop-governance DB."""
    task_id = args.get("task_id", "").strip()
    if not task_id:
        return CallToolResult(content=[TextContent(type="text", text="Error: task_id is required")])

    # Step 1: Read this session's lock
    session_id = get_session_id()
    lock = _read_lock()
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

    # Step 3: Check loop-governance DB for a scored cycle with this task_id
    try:
        conn = _db()
        row = conn.execute(
            """SELECT id, composite, decision, outcome_note
               FROM loop_cycles
               WHERE task_id = ? AND user_overrode IS NOT NULL
               ORDER BY id DESC LIMIT 1""",
            (task_id,)
        ).fetchone()
        conn.close()
    except Exception:
        row = None

    if not row:
        try:
            conn2 = _db()
            pending = conn2.execute(
                "SELECT id FROM loop_cycles WHERE task_id = ? AND user_overrode IS NULL ORDER BY id DESC LIMIT 1",
                (task_id,)
            ).fetchone()
            conn2.close()
            hint = f"   A pending cycle (#{pending[0]}) exists for this task — run:\n" if pending else ""
        except Exception:
            hint = ""

        return CallToolResult(content=[TextContent(
            type="text",
            text=(
                f"⛔ No scored cycle found for task '{task_id}'. "
                f"The pending cycle needs feedback_accept before release.\n\n"
                + hint
                + f"  1. mcp_loop_governance_feedback_accept(id=N, note='...') — score the cycle\n"
                + f"  2. mcp_loop_governance_end_change(task_id='{task_id}') — retry release\n\n"
                + "The lock stays active until you score. You cannot start a new task until this one is closed."
            )
        )])

    # Step 4: Score exists — release the lock
    cycle_id, composite, decision, note = row
    _release_lock()
    return CallToolResult(content=[TextContent(
        type="text",
        text=(
            f"🔓 Governance session '{task_id}' closed.\n"
            f"Scored: cycle #{cycle_id} (composite={composite}, decision={decision})\n"
            f"Lock released. You can start a new change with begin_change()."
        )
    )])


def _check_lock(args: dict | None = None) -> CallToolResult:
    """Check if a governance lock is active.

    Updates heartbeat on every call to prevent staleness.
    Auto-releases locks whose heartbeat has exceeded TTL.
    """
    state = _read_lock()
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
        _release_lock()
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
    _write_lock(state)

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
    MAX_DELTA = 1.0
    if abs(value - old_val) > MAX_DELTA:
        return CallToolResult(content=[TextContent(type="text", text=f"Safety bound: max delta {MAX_DELTA}. {old_val} -> {value} exceeds that.")])
    if value < 0 or value > 10:
        return CallToolResult(content=[TextContent(type="text", text="Value must be between 0 and 10")])
    section[last] = value
    CONFIG_PATH.write_text(json.dumps(config, indent=2))
    return CallToolResult(content=[TextContent(type="text", text=json.dumps({
        "updated": key, "from": old_val, "to": value,
    }, indent=2))])


def _feedback_accept(args: dict) -> CallToolResult:
    cycle_id = args.get("cycle_id")
    if cycle_id is None:
        return CallToolResult(content=[TextContent(type="text", text="Error: cycle_id is required")])
    note = args.get("note", "")
    try:
        conn = _db()
        existing = conn.execute("SELECT id FROM loop_cycles WHERE id = ?", (cycle_id,)).fetchone()
        if not existing:
            conn.close()
            return CallToolResult(content=[TextContent(
                type="text",
                text=f"Error: Cycle #{cycle_id} not found in loop-governance DB. Use cycle_query to find valid cycle IDs."
            )])
        conn.execute("UPDATE loop_cycles SET user_overrode=0, outcome_note=? WHERE id=?", (note, cycle_id))
        conn.commit()
        conn.close()
        return CallToolResult(content=[TextContent(type="text", text=f"✅ Cycle #{cycle_id} marked as accepted.")])
    except Exception as e:
        return CallToolResult(content=[TextContent(type="text", text=f"Error accepting cycle #{cycle_id}: {e}")])


def _feedback_override(args: dict) -> CallToolResult:
    cycle_id = args.get("cycle_id")
    if cycle_id is None:
        return CallToolResult(content=[TextContent(type="text", text="Error: cycle_id is required")])
    correct = args.get("correct_decision", "LOOP")
    note = args.get("note", "")
    correct_note = correct + ": " + note
    try:
        conn = _db()
        existing = conn.execute("SELECT id FROM loop_cycles WHERE id = ?", (cycle_id,)).fetchone()
        if not existing:
            conn.close()
            return CallToolResult(content=[TextContent(
                type="text",
                text=f"Error: Cycle #{cycle_id} not found in loop-governance DB. Use cycle_query to find valid cycle IDs."
            )])
        conn.execute("UPDATE loop_cycles SET user_overrode=1, outcome_note=? WHERE id=?", (correct_note, cycle_id))
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


def _verify_lock_for_task(task_id: str) -> tuple[dict | None, str]:
    """Verify the active lock matches the given task_id. Returns (state, error_msg)."""
    state = _read_lock()
    if state is None:
        return None, "No active governance lock."
    stored_task = state.get("task_id", "")
    if stored_task != task_id:
        return None, f"Lock belongs to task '{stored_task}', not '{task_id}'."
    return state, ""


def _write_lock_and_log(state: dict, event_type: str, detail: str = "") -> None:
    """Update the lock file and log a task event."""
    _write_lock(state)
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
        pass  # event logging is best-effort


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

    state, err = _verify_lock_for_task(task_id)
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
    _write_lock_and_log(state, "state_transition", detail)

    return CallToolResult(content=[TextContent(
        type="text",
        text=f"🔄 Task '{task_id}' state: {old_state} → {new_state}."
        + (f" Reason: {reason}" if reason else "")
    )])


def _request_interruption(args: dict) -> CallToolResult:
    """Push current task onto stack and create a sub-task."""
    task_id = args.get("task_id", "").strip()
    description = args.get("description", "").strip()
    reason = args.get("reason", "")

    if not task_id:
        return CallToolResult(content=[TextContent(type="text", text="Error: task_id is required")])
    if not description:
        return CallToolResult(content=[TextContent(type="text", text="Error: description is required")])

    state, err = _verify_lock_for_task(task_id)
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

    # Save current state to task_stack
    stacked = {
        "task_id": state["task_id"],
        "description": state.get("description", ""),
        "status": old_state,
        "started_at": state.get("started_at", ""),
        "acceptance_criteria": state.get("acceptance_criteria", []),
        "allowed_scope": state.get("allowed_scope", []),
        "plan": state.get("plan", []),
    }
    stack = state.get("task_stack", [])
    stack.append(stacked)

    # Replace lock with interruption sub-task
    now_iso = _now_iso()
    state["task_id"] = task_id
    state["description"] = description
    state["status"] = "executing"
    state["started_at"] = now_iso
    state["heartbeat_at"] = now_iso
    state["task_stack"] = stack
    state["acceptance_criteria"] = []
    state["allowed_scope"] = []
    state["plan"] = []

    detail = f"Interrupted by: {task_id} — {description}"
    if reason:
        detail += f" (reason: {reason})"
    _write_lock_and_log(state, "interruption_requested", detail)

    return CallToolResult(content=[TextContent(
        type="text",
        text=f"⏸️ Interruption: '{stacked['task_id']}' suspended. New sub-task '{task_id}' started.\n"
             f"  Stack depth: {len(stack)}\n"
             f"  Use resume_from_interrupt to restore '{stacked['task_id']}' when done."
    )])


def _resume_from_interrupt(args: dict) -> CallToolResult:
    """Pop task_stack and restore the parent task."""
    state = _read_lock()
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
    _write_lock_and_log(state, "interruption_resumed", detail)

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

    state, err = _verify_lock_for_task(task_id)
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
        _write_lock_and_log(state, "completion_verified", "Auto-verified: lightweight task (no ACs)")
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
    _write_lock_and_log(state, "completion_verified", state["completion_detail"])

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
    existing = _read_lock()
    if existing is not None:
        return CallToolResult(content=[TextContent(
            type="text",
            text=f"Cannot promote issue: active lock exists for task '{existing.get('task_id')}'. "
                 f"Complete or cancel the current task first."
        )])

    session_id = get_session_id()
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
    _write_lock(state)

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
        pass

    return CallToolResult(content=[TextContent(
        type="text",
        text=f"📌 Issue promoted to task '{task_id}': {description}\n"
             f"  Lock created with TTL: {ttl}s\n"
             f"  Use end_change('{task_id}') when done."
    )])


# ── Main ─────────────────────────────────────────────────────

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
