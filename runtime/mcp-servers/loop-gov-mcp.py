#!/usr/bin/env python3
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
from typing import Any

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
    the directory name directly. This avoids the cwd-mismatch gap
    between begin_change (session cwd) and the enforcer (gateway/cron cwd).
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


def _governance_lock_path(slug: str | None = None) -> Path:
    """Return a repo-scoped governance lock path.

    Derives the slug deterministically via _derive_slug() so the
    same path is produced regardless of the calling process's cwd.
    Falls back to ``.governance-generic.json`` only when no git repo
    is found anywhere.

    When called from begin_change/end_change (which already know the
    slug), pass the slug explicitly to skip re-derivation.
    """
    if slug:
        return GOVERNANCE_STATE_DIR / f".governance-{slug}.json"
    slug = _derive_slug()
    return GOVERNANCE_STATE_DIR / f".governance-{slug}.json"


def _generic_lock_path() -> Path:
    """Return the generic lock path."""
    return GOVERNANCE_STATE_DIR / ".governance-generic.json"


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
        # Parse ISO timestamp (handle both Z and +00:00 formats)
        hb_str = heartbeat_str.replace("Z", "+00:00").replace("+00:00", "+00:00")
        heartbeat = datetime.fromisoformat(hb_str)
        now = datetime.now(timezone.utc)
        elapsed = (now - heartbeat).total_seconds()
        return elapsed > ttl
    except (ValueError, TypeError):
        return False


def _read_lock(slug: str | None = None) -> dict | None:
    """Read the current lock file, return state dict or None.

    First tries the repo-scoped path. If not found, falls back
    to the generic lock (for enforcers running outside git cwd).
    """
    path = _governance_lock_path(slug)
    if path.exists():
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            return None
    # Fallback: try generic lock (enforcer bridge)
    generic = _generic_lock_path()
    if generic.exists():
        try:
            return json.loads(generic.read_text())
        except (json.JSONDecodeError, OSError):
            return None
    return None


def _write_lock(state: dict) -> None:
    """Write lock state to file."""
    path = _governance_lock_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))
    # Also write generic lock so enforcer (which may run from non-git cwd) finds it
    generic = _generic_lock_path()
    generic.parent.mkdir(parents=True, exist_ok=True)
    generic.write_text(json.dumps(state, indent=2))


def _release_lock() -> None:
    """Remove the lock file."""
    path = _governance_lock_path()
    if path.exists():
        path.unlink()
    # Also clean up generic lock
    generic = _generic_lock_path()
    if generic.exists():
        generic.unlink()


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
            description="MANDATORY: Call before making any code/config change. Creates a governance lock AND a pending cycle in the loop-governance DB. You must call feedback_accept on the pending cycle before end_change will release the lock.",
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

    # Check if already locked
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
        # Force override: release current lock with audit trail
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

    # Create lock file with session ID, TTL, heartbeat
    state = {
        "task_id": task_id,
        "description": description,
        "started_at": now_iso,
        "agent": os.environ.get("AGENT_NAME", "unknown"),
        "session_id": session_id,
        "ttl_seconds": ttl,
        "heartbeat_at": now_iso,
        "scored": False,
    }
    _write_lock(state)

    # Create pending cycle in loop-governance DB
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
        pending_msg = (
            f"\n⚠️  Could not create pending cycle: {e}\n"
            f"   end_change will reject — force-clear with: rm {_governance_lock_path()}"
        )

    prefix = "🔒 " if not force else "🔓⚠️ "
    force_msg = f" (forced — replaced session {released_session})" if force else ""
    return CallToolResult(content=[TextContent(
        type="text",
        text=(
            f"{prefix}Governance session started: {task_id} — {description}{force_msg}\n"
            f"Lock file: {_governance_lock_path()}\n"
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

    # Step 1: Check if lock file exists
    if not _governance_lock_path().exists():
        return CallToolResult(content=[TextContent(
            type="text", text="No governance session active. Nothing to release."
        )])

    # Step 2: Verify task_id matches
    try:
        existing = json.loads(_governance_lock_path().read_text())
        stored_task = existing.get("task_id", "")
        if stored_task and stored_task != task_id:
            return CallToolResult(content=[TextContent(
                type="text",
                text=f"Error: Lock belongs to task '{stored_task}', not '{task_id}'. Use end_change('{stored_task}')."
            )])
    except (json.JSONDecodeError, OSError) as e:
        return CallToolResult(content=[TextContent(
            type="text", text=f"Error reading lock file: {e}. Remove manually: rm {_governance_lock_path()}"
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
            "file": str(_governance_lock_path()),
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
