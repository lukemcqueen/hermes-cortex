"""
Workflow database CRUD — Postgres access for workflow engine.

All operations go through the existing BusClient connection pool.
Tables live in the `bus` schema alongside queue tables.
"""

from __future__ import annotations
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from agent_bus.queue import get_queue, BusClient


# ── Workflow CRUD ───────────────────────────────────────────

def create_workflow(
    name: str,
    workflow_definition: dict,
    payload: Optional[dict] = None,
    priority: int = 0,
    deadline_seconds: Optional[int] = None,
    owner_agent: str = "moses",
    correlation_id: Optional[str] = None,
) -> str:
    """Create a new workflow row. Returns workflow ID."""
    bus = get_queue()
    bus._ensure_conn()
    wf_id = str(uuid.uuid4())
    deadline = None
    if deadline_seconds:
        deadline = datetime.now(timezone.utc) + timedelta(seconds=deadline_seconds)
    
    with bus._conn.cursor() as cur:
        cur.execute(
            """INSERT INTO bus.agent_workflows
               (id, name, workflow_definition, payload, priority, deadline_at, owner_agent, correlation_id)
               VALUES (%s, %s, %s::jsonb, %s::jsonb, %s, %s, %s, %s)""",
            (wf_id, name, json.dumps(workflow_definition),
             json.dumps(payload or {}), priority,
             deadline, owner_agent, correlation_id),
        )
        bus._conn.commit()
    return wf_id


def get_workflow(wf_id: str) -> Optional[dict]:
    """Fetch a workflow by ID."""
    bus = get_queue()
    bus._ensure_conn()
    with bus._conn.cursor() as cur:
        cur.execute("SELECT * FROM bus.agent_workflows WHERE id = %s", (wf_id,))
        row = cur.fetchone()
        if not row:
            return None
        return _row_to_dict(cur, row)


def update_workflow_state(wf_id: str, state: str, error: Optional[str] = None,
                          result: Optional[dict] = None):
    """Update workflow state with optional error/result."""
    bus = get_queue()
    bus._ensure_conn()
    now = datetime.now(timezone.utc)
    completed_states = {"completed", "failed", "timed_out", "canceled"}
    
    with bus._conn.cursor() as cur:
        if state in completed_states:
            cur.execute(
                """UPDATE bus.agent_workflows
                   SET state = %s, completed_at = %s, error = %s, result = %s::jsonb
                   WHERE id = %s""",
                (state, now, error, json.dumps(result or {}), wf_id),
            )
        else:
            cur.execute(
                """UPDATE bus.agent_workflows
                   SET state = %s, error = %s, result = %s::jsonb
                   WHERE id = %s""",
                (state, error, json.dumps(result or {}), wf_id),
            )
        bus._conn.commit()


def list_active_workflows() -> list[dict]:
    """List workflows that are in progress (pending, running, blocked)."""
    bus = get_queue()
    bus._ensure_conn()
    with bus._conn.cursor() as cur:
        cur.execute(
            """SELECT * FROM bus.agent_workflows
               WHERE state IN ('pending', 'running', 'blocked')
               ORDER BY priority DESC, created_at ASC"""
        )
        rows = cur.fetchall()
        return [_row_to_dict(cur, r) for r in rows]


# ── Step CRUD ───────────────────────────────────────────────

def create_step(
    workflow_id: str,
    step_name: str,
    step_order: int,
    assigned_to: str,
    timeout_seconds: int = 300,
    max_retries: int = 2,
    depends_on: Optional[list[str]] = None,
    route_if: Optional[dict] = None,
) -> str:
    """Create a workflow step row. Returns step ID."""
    bus = get_queue()
    bus._ensure_conn()
    step_id = str(uuid.uuid4())
    
    with bus._conn.cursor() as cur:
        cur.execute(
            """INSERT INTO bus.agent_workflow_steps
               (id, workflow_id, step_name, step_order, assigned_to,
                timeout_seconds, max_retries, depends_on, route_if)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s::uuid[], %s::jsonb)""",
            (step_id, workflow_id, step_name, step_order, assigned_to,
             timeout_seconds, max_retries,
             depends_on or [], json.dumps(route_if or {})),
        )
        bus._conn.commit()
    return step_id


def get_step(step_id: str) -> Optional[dict]:
    """Fetch a step by ID."""
    bus = get_queue()
    bus._ensure_conn()
    with bus._conn.cursor() as cur:
        cur.execute("SELECT * FROM bus.agent_workflow_steps WHERE id = %s", (step_id,))
        row = cur.fetchone()
        if not row:
            return None
        return _row_to_dict(cur, row)


def get_steps_for_workflow(wf_id: str) -> list[dict]:
    """Get all steps for a workflow, ordered by step_order."""
    bus = get_queue()
    bus._ensure_conn()
    with bus._conn.cursor() as cur:
        cur.execute(
            """SELECT * FROM bus.agent_workflow_steps
               WHERE workflow_id = %s
               ORDER BY step_order ASC""",
            (wf_id,),
        )
        return [_row_to_dict(cur, r) for r in cur.fetchall()]


def update_step_state(step_id: str, state: str, error: Optional[str] = None,
                      result: Optional[dict] = None, retry_count: Optional[int] = None):
    """Update step state."""
    bus = get_queue()
    bus._ensure_conn()
    now = datetime.now(timezone.utc)
    completed_states = {"completed", "failed", "timed_out", "skipped"}
    
    with bus._conn.cursor() as cur:
        if state in completed_states:
            cur.execute(
                """UPDATE bus.agent_workflow_steps
                   SET state = %s, completed_at = %s, error = %s,
                       result = %s::jsonb
                   WHERE id = %s""",
                (state, now, error, json.dumps(result or {}), step_id),
            )
        else:
            cur.execute(
                """UPDATE bus.agent_workflow_steps
                   SET state = %s, error = %s, result = %s::jsonb
                   WHERE id = %s""",
                (state, error, json.dumps(result or {}), step_id),
            )
        bus._conn.commit()


def get_pending_steps_for_agent(agent: str) -> list[dict]:
    """Get all pending steps assigned to an agent."""
    bus = get_queue()
    bus._ensure_conn()
    with bus._conn.cursor() as cur:
        cur.execute(
            """SELECT s.*, w.name as workflow_name
               FROM bus.agent_workflow_steps s
               JOIN bus.agent_workflows w ON s.workflow_id = w.id
               WHERE s.state = 'pending' AND s.assigned_to = %s
               ORDER BY w.priority DESC, s.step_order ASC""",
            (agent,),
        )
        return [_row_to_dict(cur, r) for r in cur.fetchall()]


# ── Audit ───────────────────────────────────────────────────

def write_audit(workflow_id: str, event: str, actor: str = "system",
                step_id: Optional[str] = None, detail: Optional[dict] = None):
    """Write an audit log entry."""
    bus = get_queue()
    bus._ensure_conn()
    with bus._conn.cursor() as cur:
        cur.execute(
            """INSERT INTO bus.agent_workflow_audit
               (workflow_id, step_id, event, actor, detail)
               VALUES (%s, %s, %s, %s, %s::jsonb)""",
            (workflow_id, step_id, event, actor, json.dumps(detail or {})),
        )
        bus._conn.commit()


# ── A2A Task CRUD ───────────────────────────────────────────

def create_a2a_task(requester: str, target_agent: str, description: str,
                    priority: str = "normal") -> str:
    """Create an A2A task. Returns task ID."""
    bus = get_queue()
    bus._ensure_conn()
    task_id = str(uuid.uuid4())
    with bus._conn.cursor() as cur:
        cur.execute(
            """INSERT INTO bus.a2a_tasks
               (id, requester, target_agent, description, priority)
               VALUES (%s, %s, %s, %s, %s)""",
            (task_id, requester, target_agent, description, priority),
        )
        bus._conn.commit()
    return task_id


def get_a2a_task(task_id: str) -> Optional[dict]:
    bus = get_queue()
    bus._ensure_conn()
    with bus._conn.cursor() as cur:
        cur.execute("SELECT * FROM bus.a2a_tasks WHERE id = %s", (task_id,))
        row = cur.fetchone()
        return _row_to_dict(cur, row) if row else None


def update_a2a_task(task_id: str, state: str, result: Optional[str] = None,
                    error: Optional[str] = None):
    bus = get_queue()
    bus._ensure_conn()
    now = datetime.now(timezone.utc)
    with bus._conn.cursor() as cur:
        if state in ("completed", "failed", "canceled", "rejected"):
            cur.execute(
                """UPDATE bus.a2a_tasks SET state = %s, completed_at = %s,
                   result = %s, error = %s WHERE id = %s""",
                (state, now, result, error, task_id),
            )
        else:
            cur.execute(
                """UPDATE bus.a2a_tasks SET state = %s WHERE id = %s""",
                (state, task_id),
            )
        bus._conn.commit()


def list_a2a_tasks_for_agent(agent: str, state_filter: Optional[str] = None) -> list[dict]:
    bus = get_queue()
    bus._ensure_conn()
    with bus._conn.cursor() as cur:
        if state_filter:
            cur.execute(
                """SELECT * FROM bus.a2a_tasks
                   WHERE target_agent = %s AND state = %s
                   ORDER BY created_at DESC""",
                (agent, state_filter),
            )
        else:
            cur.execute(
                """SELECT * FROM bus.a2a_tasks
                   WHERE target_agent = %s
                   ORDER BY created_at DESC""",
                (agent,),
            )
        return [_row_to_dict(cur, r) for r in cur.fetchall()]


# ── Helpers ─────────────────────────────────────────────────

def _row_to_dict(cur, row) -> dict:
    """Convert a psycopg row (tuple or Record) to a dict, filtering pgvector junk."""
    cols = [d.name for d in cur.description]
    
    def _clean(v):
        if v is None:
            return None
        if isinstance(v, (datetime,)):
            return v.isoformat()
        if isinstance(v, uuid.UUID):
            return str(v)
        if isinstance(v, bytes):
            return None  # skip binary/pgvector
        return v
    
    return {col: _clean(val) for col, val in zip(cols, row)
            if col not in ('embedding', 'vector')}
