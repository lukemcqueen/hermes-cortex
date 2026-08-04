"""
Workflow Dispatcher — dequeues dispatch messages, snapshots YAML, creates workflow rows.

Workflow:
  1. Read from `workflow_dispatch` queue
  2. Load workflow YAML definition (snapshotted at dispatch — never re-read)
  3. Create workflow + step rows in Postgres
  4. Send first step to assigned agent via PGMQ
  5. Write audit log
"""

from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from cortex_bus.queue import get_queue, BusClient
from cortex_bus.workflow import Workflow, WorkflowStep, RouteIf
from cortex_bus.workflow.yaml_loader import load_workflow, parse_workflow_yaml
from cortex_bus.workflow.db import (
    create_workflow, create_step, update_workflow_state,
    write_audit, get_workflow, get_steps_for_workflow,
    update_step_state, get_step, _row_to_dict,
)

# Standard workflow directories
WORKFLOW_DIRS = [
    Path.home() / "hermes-cortex" / "core" / "cortex_bus" / "workflows",
]


class DispatchError(Exception):
    """Raised when a workflow dispatch fails."""


def process_dispatch_message(msg: dict) -> Optional[str]:
    """Process a single dispatch queue message.
    
    Args:
        msg: The message from workflow_dispatch queue.
             Expected shape:
               workflow_name: str
               workflow_source: str (file path or yaml string prefixed with 'yaml:')
               payload: dict (optional — {{variables}})
               priority: int (optional)
               correlation_id: str (optional)
    
    Returns:
        workflow_id if dispatched successfully, None if skipped.
    """
    body = msg.get("body", {})
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            raise DispatchError(f"Invalid JSON body: {body[:100]}")
    
    workflow_name = body.get("workflow_name", "")
    workflow_source = body.get("workflow_source", "")
    payload = body.get("payload", {})
    priority = body.get("priority", 0)
    correlation_id = body.get("correlation_id")
    
    if not workflow_name or not workflow_source:
        raise DispatchError("workflow_name and workflow_source are required")
    
    # Step 1: Load workflow YAML (snapshot at dispatch!)
    try:
        if workflow_source.startswith("yaml:"):
            # Inline YAML
            workflow = parse_workflow_yaml(workflow_source[5:])
        else:
            # File path
            wf_path = _resolve_workflow_path(workflow_source)
            workflow = load_workflow(wf_path)
    except Exception as e:
        raise DispatchError(f"Failed to load workflow '{workflow_name}': {e}")
    
    # Step 2: Create workflow row (snapshot full definition)
    wf_id = create_workflow(
        name=workflow.name,
        workflow_definition=workflow.to_dict(),
        payload=payload,
        priority=priority,
        deadline_seconds=workflow.deadline_seconds,
        owner_agent=body.get("owner_agent", "moses"),
        correlation_id=correlation_id,
    )
    
    # Step 3: Create all step rows
    step_ids = {}
    for i, step in enumerate(workflow.steps):
        step_id = create_step(
            workflow_id=wf_id,
            step_name=step.name,
            step_order=i,
            assigned_to=step.assigned_to,
            timeout_seconds=step.timeout_seconds,
            max_retries=step.max_retries,
            depends_on=step.depends_on,
            route_if=step.route_if.to_dict() if step.route_if else None,
        )
        step_ids[step.name] = step_id
    
    # Step 4: Find first step(s) to dispatch
    start_step = workflow.get_step(workflow.start_step)
    if not start_step:
        update_workflow_state(wf_id, "failed", error=f"Start step '{workflow.start_step}' not found")
        write_audit(wf_id, "dispatch_failed", detail={"error": f"start_step '{workflow.start_step}' not found"})
        raise DispatchError(f"Start step '{workflow.start_step}' not found in workflow")
    
    # Step 5: Mark workflow as running
    update_workflow_state(wf_id, "running")
    write_audit(wf_id, "workflow_dispatched", detail={
        "workflow_name": workflow.name,
        "start_step": start_step.name,
        "assigned_to": start_step.assigned_to,
        "total_steps": len(workflow.steps),
    })
    
    # Step 6: Dispatch the first step
    _dispatch_to_agent(wf_id, step_ids[start_step.name], start_step, payload)
    
    return wf_id


def _resolve_workflow_path(source: str) -> Path:
    """Resolve a workflow name to a YAML file path."""
    # Try as absolute/relative path first
    p = Path(source)
    if p.exists():
        return p
    
    # Try with .yaml extension
    p2 = Path(source + ".yaml")
    if p2.exists():
        return p2
    
    # Search workflow directories
    for d in WORKFLOW_DIRS:
        for ext in (".yaml", ".yml"):
            candidate = d / (source + ext)
            if candidate.exists():
                return candidate
    
    raise DispatchError(f"Workflow file not found: {source} (searched: {[str(d) for d in WORKFLOW_DIRS]})")


def _dispatch_to_agent(wf_id: str, step_id: str, step: WorkflowStep, payload: dict):
    """Send a step to the assigned agent's inbox queue."""
    bus = get_queue()
    
    agent_queue = f"inbox_{step.assigned_to}"
    
    message = {
        "type": "workflow_step",
        "workflow_id": wf_id,
        "step_id": step_id,
        "step_name": step.name,
        "assigned_to": step.assigned_to,
        "prompt": step.prompt or "",
        "skills": step.skills or [],
        "timeout_seconds": step.timeout_seconds,
        "max_retries": step.max_retries,
        "payload": payload,
    }
    
    bus.send(agent_queue, message, priority=0)
    write_audit(wf_id, "step_dispatched", actor="dispatcher",
                step_id=step_id, detail={"step": step.name, "agent": step.assigned_to})


def dispatch_workflow(workflow_name: str, workflow_source: str,
                      payload: Optional[dict] = None,
                      priority: int = 0,
                      correlation_id: Optional[str] = None) -> str:
    """Convenience: directly dispatch a workflow (no queue)."""
    from cortex_bus.workflow.db import get_queue as _get_queue
    
    msg = {
        "body": {
            "workflow_name": workflow_name,
            "workflow_source": workflow_source,
            "payload": payload or {},
            "priority": priority,
            "correlation_id": correlation_id,
        }
    }
    result = process_dispatch_message(msg)
    if result:
        return result
    raise DispatchError("Dispatch returned no workflow_id")


# ── Cron entry point ────────────────────────────────────────

def poll_and_dispatch(max_messages: int = 5) -> list[str]:
    """Poll the workflow_dispatch queue and process messages.
    
    Designed to be called from a cron job.
    Returns list of dispatched workflow IDs.
    """
    bus = get_queue()
    dispatched = []
    
    for _ in range(max_messages):
        msg = bus.read("workflow_dispatch", vt=120)
        if not msg or not msg.get("msg_id"):
            break
        
        try:
            wf_id = process_dispatch_message(msg)
            if wf_id:
                bus.archive("workflow_dispatch", msg["msg_id"], "dispatcher")
                dispatched.append(wf_id)
        except DispatchError as e:
            # Message is malformed — move to DLQ
            bus.requeue("workflow_dispatch", msg["msg_id"], str(e)[:500])
            write_audit("unknown", "dispatch_error", detail={"error": str(e)[:200]})
        except Exception as e:
            bus.requeue("workflow_dispatch", msg["msg_id"], str(e)[:500])
    
    return dispatched
