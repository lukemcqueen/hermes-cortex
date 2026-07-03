#!/usr/bin/env python3
"""
Loop Governance MCP Server — exposes loop governance DB, config,
feedback, and embedding cache as MCP tools.

Usage:
    hermes mcp add --command python3 --args /path/to/loop-gov-mcp.py loop-governance

Tools:
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
import sys
import time
import urllib.error
import logging
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure hermes_models.py is importable when running from src/mcp-servers/
_SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPT_DIR.parent / "scripts"))

from hermes_models import get_model

# Embedding model used by all loop-governance tools
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
LOOP_DB = HOME / ".hermes" / "data" / "loop-governance.db"
CONFIG_PATH = HOME / ".hermes" / "data" / "loop-governance-config.json"
CACHE_DB = HOME / ".hermes" / "data" / "session-embeddings.db"
GOVERNANCE_STATE = HOME / ".hermes-cortex" / "state" / ".governance-active.json"
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


def _db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(LOOP_DB))
    conn.row_factory = sqlite3.Row
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


server = Server("loop-governance")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
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
            name="begin_change",
            description="MANDATORY: Call before making any code/config change. Creates a governance lock file that the pre-commit hook checks. Without this, the hook will reject the commit.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Short task identifier (e.g. 'fix-auth-403')"},
                    "description": {"type": "string", "description": "What this change does"},
                },
                "required": ["task_id", "description"],
            },
        ),
        Tool(
            name="end_change",
            description="Call after scoring a change to release the governance lock. The lock must be released before begin_change can be called again.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID matching the begin_change call"},
                },
                "required": ["task_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any] | None) -> CallToolResult:
    args = arguments or {}
    try:
        handlers = {
            "cycle_query": _cycle_query,
            "cycle_stats": _cycle_stats,
            "config_show": _config_show,
            "config_set": _config_set,
            "feedback_accept": _feedback_accept,
            "feedback_override": _feedback_override,
            "cache_search": _cache_search,
            "begin_change": _begin_change,
            "end_change": _end_change,
        }
        handler = handlers.get(name)
        if handler:
            return handler(args)
        return CallToolResult(content=[TextContent(type="text", text="Unknown tool: " + name)])
    except Exception as e:
        return CallToolResult(content=[TextContent(type="text", text="Error: " + str(e))])


# Tool implementations

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
    if not LOOP_DB.exists():
        return CallToolResult(content=[TextContent(type="text", text="No loop DB yet.")])
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
        return CallToolResult(content=[TextContent(type="text", text="Safety bound: max delta " + str(MAX_DELTA) + ". " + str(old_val) + " -> " + str(value) + " exceeds that.")])
    if value < 0 or value > 10:
        return CallToolResult(content=[TextContent(type="text", text="Value must be between 0 and 10")])
    section[last] = value
    CONFIG_PATH.write_text(json.dumps(config, indent=2))
    return CallToolResult(content=[TextContent(type="text", text=json.dumps({
        "updated": key, "from": old_val, "to": value,
    }, indent=2))])


def _feedback_accept(args: dict) -> CallToolResult:
    conn = _db()
    cycle_id = args["cycle_id"]
    note = args.get("note", "")
    conn.execute("UPDATE loop_cycles SET user_overrode=0, outcome_note=? WHERE id=?", (note, cycle_id))
    conn.commit()
    conn.close()
    return CallToolResult(content=[TextContent(type="text", text="Cycle " + str(cycle_id) + " marked as correct.")])


def _feedback_override(args: dict) -> CallToolResult:
    conn = _db()
    cycle_id = args["cycle_id"]
    correct = args.get("correct_decision", "LOOP")
    note = args.get("note", "")
    correct_note = correct + ": " + note
    conn.execute("UPDATE loop_cycles SET user_overrode=1, outcome_note=? WHERE id=?", (correct_note, cycle_id))
    conn.commit()
    conn.close()
    text = "Cycle " + str(cycle_id) + " overridden -> " + correct + "."
    return CallToolResult(content=[TextContent(type="text", text=text)])


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


def _begin_change(args: dict) -> CallToolResult:
    """Create a governance lock file. Pre-commit hook checks this exists."""
    task_id = args.get("task_id", "").strip()
    description = args.get("description", "").strip()
    if not task_id:
        return CallToolResult(content=[TextContent(type="text", text="Error: task_id is required")])
    if not description:
        return CallToolResult(content=[TextContent(type="text", text="Error: description is required")])

    # Check if already locked
    if GOVERNANCE_STATE.exists():
        try:
            existing = json.loads(GOVERNANCE_STATE.read_text())
            return CallToolResult(content=[TextContent(
                type="text",
                text=f"Error: A governance session is already active: '{existing.get('task_id')}' - {existing.get('description')}. Call end_change('{existing.get('task_id')}') first or use force=True."
            )])
        except (json.JSONDecodeError, OSError):
            pass
        # Stale lock — overwrite

    GOVERNANCE_STATE.parent.mkdir(parents=True, exist_ok=True)
    state = {
        "task_id": task_id,
        "description": description,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "agent": os.environ.get("AGENT_NAME", "unknown"),
    }
    GOVERNANCE_STATE.write_text(json.dumps(state, indent=2))
    return CallToolResult(content=[TextContent(
        type="text",
        text=f"Governance session started: {task_id} — {description}. Lock file: {GOVERNANCE_STATE}"
    )])


def _end_change(args: dict) -> CallToolResult:
    """Release the governance lock. Requires matching task_id."""
    task_id = args.get("task_id", "").strip()
    if not task_id:
        return CallToolResult(content=[TextContent(type="text", text="Error: task_id is required")])

    if not GOVERNANCE_STATE.exists():
        return CallToolResult(content=[TextContent(
            type="text", text="No governance session active (no lock file found). Nothing to release."
        )])

    try:
        existing = json.loads(GOVERNANCE_STATE.read_text())
        stored_task = existing.get("task_id", "")
        if stored_task and stored_task != task_id:
            return CallToolResult(content=[TextContent(
                type="text",
                text=f"Error: Lock belongs to task '{stored_task}', not '{task_id}'. Use end_change('{stored_task}') or force=True."
            )])
        GOVERNANCE_STATE.unlink()
        return CallToolResult(content=[TextContent(
            type="text", text=f"Governance session '{task_id}' closed. Lock released."
        )])
    except (json.JSONDecodeError, OSError) as e:
        return CallToolResult(content=[TextContent(
            type="text", text=f"Error reading lock file: {e}. Remove manually: rm {GOVERNANCE_STATE}"
        )])


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
