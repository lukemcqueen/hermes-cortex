#!/usr/bin/env python3
"""
A2A Server v0.1 — JSON-RPC 2.0 endpoints for agent-to-agent task delegation.

Implements the A2A (Agent2Agent) protocol v1.0 specification for task submission,
status polling, and cancellation. Backed by the existing agent inbox for message
delivery and a SQLite database for task state tracking.

Endpoints:
    POST /a2a/task             — Submit a task (JSON-RPC tasks/send)
    GET  /a2a/task/{id}        — Poll task state (JSON-RPC tasks/get)
    POST /a2a/task/{id}/cancel  — Cancel a task (JSON-RPC tasks/cancel)
    GET  /health               — Health check

Usage:
    uvicorn a2a-server:app --host 127.0.0.1 --port 8906
"""

import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

# ── Paths ──
HOME = Path.home()
INBOX_DIR = Path(os.environ.get("AGENT_INBOX_DIR", str(HOME / "hermes-cortex-private" / "messages" / "inbox")))
A2A_DIR = HOME / ".hermes-cortex" / "a2a"
DB_PATH = A2A_DIR / "task-state.db"
INBOX_CONF = HOME / ".hermes" / "hermes-inbox.conf"
AGENT_NAME = os.environ.get("AGENT_NAME", "moses")

# Ensure directories
INBOX_DIR.mkdir(parents=True, exist_ok=True)
A2A_DIR.mkdir(parents=True, exist_ok=True)

# ── FastAPI ──
app = FastAPI(title="A2A Server", version="0.1.0")

# ── Database ──

def _get_db() -> sqlite3.Connection:
    """Get a thread-safe SQLite connection."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn

def _init_db():
    """Initialize the task state database."""
    conn = _get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            source_agent TEXT NOT NULL,
            target_agent TEXT NOT NULL,
            state TEXT NOT NULL DEFAULT 'submitted'
                CHECK(state IN ('submitted','working','completed','failed','canceled','rejected')),
            description TEXT DEFAULT '',
            priority TEXT DEFAULT 'normal'
                CHECK(priority IN ('normal','urgent','critical')),
            inbox_message_filename TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            completed_at TEXT,
            result_summary TEXT DEFAULT '',
            error TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_tasks_target ON tasks(target_agent, state);
        CREATE INDEX IF NOT EXISTS idx_tasks_state ON tasks(state);
    """)
    conn.commit()
    conn.close()

_init_db()


# ── Inbox helpers ──

def _load_inbox_config() -> tuple[str, str]:
    """Load inbox auth from config file (for writing messages to the inbox API)."""
    url = ""
    auth = ""
    if INBOX_CONF.exists():
        for line in INBOX_CONF.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip("'\"")
            if k in ("CORTEX_INBOX_URL", "MOSES_INBOX_URL") and not url:
                url = v.rstrip("/")
            elif k in ("CORTEX_INBOX_AUTH", "MOSES_INBOX_AUTH") and not auth:
                auth = v
    return url, auth


def _write_inbox_message(target: str, subject: str, body: str, priority: str = "normal") -> tuple[str, str]:
    """Write an inbox message file for the target agent. Returns the filename."""
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")[:17]
    task_id = f"task-{uuid.uuid4().hex[:12]}"
    filename = f"{ts}-{AGENT_NAME}-{task_id}.md"

    msg = (
        f"from: {AGENT_NAME}\n"
        f"to: {target}\n"
        f"subject: {subject}\n"
        f"topic: a2a\n"
        f"priority: {priority}\n"
        f"task_id: {task_id}\n"
        f"thread: a2a-{task_id}\n"
        f"---\n\n"
        f"{body}\n"
    )

    inbox_path = INBOX_DIR / filename
    inbox_path.write_text(msg)
    return filename, task_id


# ── Task state helpers ──

def _create_task(source: str, target: str, description: str, priority: str,
                 inbox_filename: str, task_id: str) -> dict:
    """Create a new task row in the database."""
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_db()
    conn.execute(
        "INSERT INTO tasks (id, source_agent, target_agent, state, description, priority, "
        "inbox_message_filename, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (task_id, source, target, "submitted", description, priority, inbox_filename, now, now),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    return dict(row)


def _get_task(task_id: str) -> Optional[dict]:
    """Get a task by ID."""
    conn = _get_db()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def _update_task_state(task_id: str, new_state: str, result: str = "", error: str = ""):
    """Update a task's state and timestamp."""
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_db()
    updates = {"updated_at": now, "state": new_state}
    if new_state in ("completed", "failed", "canceled"):
        updates["completed_at"] = now
    if result:
        updates["result_summary"] = result
    if error:
        updates["error"] = error

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?",
                 (*updates.values(), task_id))
    conn.commit()
    conn.close()


# ── JSON-RPC Response helpers ──

def jsonrpc_success(request_id, result):
    return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": result})

def jsonrpc_error(request_id, code, message):
    return JSONResponse(
        {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}},
        status_code=200,  # JSON-RPC always returns 200
    )


# ── Routes ──

@app.get("/health")
async def health():
    return {"status": "ok", "service": "a2a-server", "agent": AGENT_NAME}


@app.post("/a2a/task")
async def tasks_send(request: Request):
    """
    JSON-RPC method: tasks/send

    Submit a task to this agent. Creates an inbox message for the target agent
    and a task state row. Returns the task ID and initial state.
    """
    try:
        body = await request.json()
    except Exception:
        return jsonrpc_error(None, -32700, "Parse error")

    req_id = body.get("id", None)
    method = body.get("method", "")
    params = body.get("params", {})

    if method not in ("tasks/send",):
        return jsonrpc_error(req_id, -32601, f"Method not found: {method}")

    task_params = params.get("task", params)
    messages = task_params.get("messages", [])
    if not messages:
        return jsonrpc_error(req_id, -32602, "Missing task.messages")

    # Extract task details from the first user message
    first_msg = messages[0]
    parts = first_msg.get("parts", [])
    text_parts = [p.get("text", "") for p in parts if p.get("type") == "text"]
    description = "\n".join(text_parts) if text_parts else "(no description)"

    # Determine target from sessionId or default to orchestrator
    target_agent = params.get("sessionId", AGENT_NAME)

    priority = "normal"
    for msg in messages:
        if "priority" in msg:
            priority = msg["priority"]

    # Write inbox message
    subject = f"A2A Task: {description[:80]}"
    inbox_filename, task_id = _write_inbox_message(target_agent, subject, description, priority)

    # Create task state
    task = _create_task(
        source=AGENT_NAME,
        target=target_agent,
        description=description,
        priority=priority,
        inbox_filename=inbox_filename,
        task_id=task_id,
    )

    return jsonrpc_success(req_id, {
        "id": task_id,
        "status": {
            "state": task["state"],
            "created_at": task["created_at"],
        },
    })


@app.get("/a2a/task/{task_id}")
async def tasks_get(task_id: str, request: Request):
    """
    JSON-RPC method: tasks/get

    Poll the current state of a task. Returns the full task status including
    result_summary if completed.
    """
    req_id = request.query_params.get("id", 1)

    task = _get_task(task_id)
    if not task:
        return jsonrpc_error(req_id, -32000, f"Task not found: {task_id}")

    return jsonrpc_success(req_id, {
        "id": task_id,
        "status": {
            "state": task["state"],
            "created_at": task["created_at"],
            "updated_at": task["updated_at"],
            "completed_at": task.get("completed_at"),
        },
        "artifacts": [{
            "type": "text",
            "text": task.get("result_summary", ""),
        }] if task.get("result_summary") else [],
    })


@app.post("/a2a/task/{task_id}/cancel")
async def tasks_cancel(task_id: str, request: Request):
    """
    JSON-RPC method: tasks/cancel

    Cancel a pending task. Only tasks in 'submitted' or 'working' state can be cancelled.
    """
    try:
        body = await request.json()
    except Exception:
        body = {}

    req_id = body.get("id", None)

    task = _get_task(task_id)
    if not task:
        return jsonrpc_error(req_id, -32000, f"Task not found: {task_id}")

    if task["state"] not in ("submitted", "working"):
        return jsonrpc_error(req_id, -32001,
                             f"Cannot cancel task in state '{task['state']}'")

    _update_task_state(task_id, "canceled", result="Task cancelled by request")

    return jsonrpc_success(req_id, {
        "id": task_id,
        "status": {"state": "canceled"},
    })


# ── State transition hook (called by inbox processor when agent reads/replies) ──

def mark_working(task_id: str):
    """Mark a task as 'working' (agent picked it up)."""
    task = _get_task(task_id)
    if task and task["state"] == "submitted":
        _update_task_state(task_id, "working")

def mark_completed(task_id: str, result: str = ""):
    """Mark a task as 'completed'."""
    _update_task_state(task_id, "completed", result=result)

def mark_failed(task_id: str, error: str = ""):
    """Mark a task as 'failed'."""
    _update_task_state(task_id, "failed", error=error)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("A2A_PORT", "8906"))
    uvicorn.run(app, host="127.0.0.1", port=port)
