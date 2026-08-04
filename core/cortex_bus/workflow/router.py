"""
Workflow Router — evaluates route_if from step results, dispatches next step.

Reads from `workflow_step_result` queue, matches step output status against
route_if rules (case-insensitive, _fallback support), dispatches the next
step or ends the workflow.

NEVER re-reads YAML files — routing always uses the snapshotted route_if.
"""

from __future__ import annotations
import json
from typing import Any, Optional

from cortex_bus.queue import get_queue, BusClient
from cortex_bus.workflow.db import (
    get_workflow, get_step, get_steps_for_workflow,
    update_workflow_state, update_step_state,
    write_audit, create_step,
)
from cortex_bus.workflow.dispatcher import _dispatch_to_agent


class RouteError(Exception):
    """Raised when a step result cannot be routed."""


def process_step_result(msg: dict) -> Optional[str]:
    """Process a single step result message from workflow_step_result queue.
    
    Expected message body:
        workflow_id: str
        step_id: str
        status: str  # 'success', 'failure', 'needs_review', etc.
        result: dict (optional — step output data)
        error: str (optional)
    
    Returns:
        'completed', 'failed', 'blocked', or None if not routable
    """
    body = msg.get("body", {})
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            raise RouteError(f"Invalid JSON body: {body[:100]}")
    
    workflow_id = body.get("workflow_id", "")
    step_id = body.get("step_id", "")
    status = (body.get("status") or "").lower().strip()
    result = body.get("result", {})
    error = body.get("error", "")
    
    if not workflow_id or not step_id:
        raise RouteError("workflow_id and step_id are required")
    
    # Step 1: Load workflow + completed step
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise RouteError(f"Workflow not found: {workflow_id}")
    
    completed_step = get_step(step_id)
    if not completed_step:
        raise RouteError(f"Step not found: {step_id}")
    
    # Step 2: Check if workflow is still running (might have timed out)
    if workflow["state"] not in ("running", "blocked"):
        return workflow["state"]  # Already done — just acknowledge
    
    # Step 3: Update step result
    update_step_state(step_id, "completed" if status == "success" else "failed",
                      error=error, result=result)
    write_audit(workflow_id, "step_completed", actor="router",
                step_id=step_id, detail={"status": status})
    
    # Step 4: Evaluate route_if from snapshotted data
    route_if = completed_step.get("route_if") or {}
    next_step = _evaluate_route(route_if, status, completed_step["step_name"])
    
    if next_step is None:
        # No route found — fail the workflow
        update_workflow_state(workflow_id, "failed",
                              error=f"Step '{completed_step['step_name']}' status '{status}' has no matching route")
        write_audit(workflow_id, "workflow_failed", actor="router",
                    step_id=step_id,
                    detail={"error": f"No route for status '{status}'", "route_if": route_if})
        return "failed"
    
    if next_step == "_end" or next_step.startswith("_end:"):
        # Workflow complete
        reason = next_step.split(":", 1)[1] if ":" in next_step else "completed"
        update_workflow_state(workflow_id, "completed",
                              result={"completion_reason": reason})
        write_audit(workflow_id, "workflow_completed", actor="router",
                    step_id=step_id, detail={"reason": reason})
        return "completed"
    
    # Step 5: Dispatch next step
    all_steps = get_steps_for_workflow(workflow_id)
    next_step_data = _find_step(all_steps, next_step)
    
    if not next_step_data:
        update_workflow_state(workflow_id, "failed",
                              error=f"Route target '{next_step}' not found in workflow steps")
        write_audit(workflow_id, "workflow_failed", actor="router",
                    detail={"error": f"Route target '{next_step}' not found"})
        return "failed"
    
    # Check if next step depends on other in-progress steps (parallel gate)
    pending_deps = _get_pending_dependencies(all_steps, next_step_data, workflow_id)
    if pending_deps:
        # Stay blocked until dependencies complete
        update_workflow_state(workflow_id, "blocked")
        write_audit(workflow_id, "step_blocked", actor="router",
                    step_id=next_step_data["id"],
                    detail={"pending_deps": pending_deps, "step": next_step})
        return "blocked"
    
    # Check if it's a human-in-the-loop step
    if next_step_data.get("route_if", {}).get("human_review") or next_step_data.get("step_name", "").lower() in (
        s.lower() for s in next_step_data.get("route_if", {}).get("routes", {}).values()
    ):
        # Actually, human_review is in the snapshotted workflow_definition
        # Let me check the workflow definition
        wf_def = workflow.get("workflow_definition", {})
        steps_def = wf_def.get("steps", []) if isinstance(wf_def, dict) else []
        for s in steps_def:
            if isinstance(s, dict) and s.get("name") == next_step:
                if s.get("human_review"):
                    update_workflow_state(workflow_id, "blocked")
                    write_audit(workflow_id, "step_waiting_human", actor="router",
                                step_id=next_step_data["id"],
                                detail={"step": next_step, "assigned_to": next_step_data.get("assigned_to")})
                    return "blocked"
    
    # Dispatch to agent
    update_step_state(next_step_data["id"], "running")
    
    # Build the WorkflowStep object for dispatch
    from cortex_bus.workflow import WorkflowStep, RouteIf
    step_obj = WorkflowStep(
        name=next_step_data["step_name"],
        assigned_to=next_step_data.get("assigned_to", "moses"),
        timeout_seconds=next_step_data.get("timeout_seconds", 300),
        max_retries=next_step_data.get("max_retries", 2),
    )
    
    _dispatch_to_agent(workflow_id, next_step_data["id"], step_obj,
                       workflow.get("payload", {}))
    
    return "running"


def _evaluate_route(route_if: dict, status: str, step_name: str) -> Optional[str]:
    """Evaluate route_if rules against a status string.
    
    Args:
        route_if: Raw dict from DB (keys may be mixed case)
        status: Lowercased, stripped status string
        step_name: For error messages
    
    Returns:
        Next step name, '_end', or None if no match
    """
    if not route_if:
        return None
    
    # Normalize route keys to lowercase
    routes = {}
    fallback = None
    for k, v in route_if.items():
        if k == "_fallback":
            fallback = v
        elif k == "human_review":
            continue  # Skip meta-key
        else:
            routes[k.lower().strip()] = v
    
    # Match status
    if status in routes:
        return routes[status]
    
    # Try wildcard-fallback
    if fallback:
        return fallback
    
    return None


def _find_step(steps: list[dict], step_name: str) -> Optional[dict]:
    """Find a step by name in the list."""
    for s in steps:
        if s["step_name"] == step_name:
            return s
    return None


def _get_pending_dependencies(all_steps: list[dict], step: dict,
                              workflow_id: str) -> list[str]:
    """Get names of dependencies that haven't completed yet."""
    from cortex_bus.workflow.db import get_step
    
    pending = []
    for dep_name in step.get("depends_on", []):
        dep_step = _find_step(all_steps, dep_name)
        if dep_step and dep_step["state"] not in ("completed", "skipped"):
            pending.append(dep_name)
    return pending


# ── Cron entry point ────────────────────────────────────────

def poll_and_route(max_messages: int = 10) -> list[str]:
    """Poll the workflow_step_result queue and process messages.
    
    Returns list of workflow IDs that were processed.
    """
    bus = get_queue()
    processed = []
    
    for _ in range(max_messages):
        msg = bus.read("workflow_step_result", vt=120)
        if not msg or not msg.get("msg_id"):
            break
        
        try:
            result = process_step_result(msg)
            bus.archive("workflow_step_result", msg["msg_id"], "router")
            if result:
                wf_id = ""
                body = msg.get("body", {})
                if isinstance(body, dict):
                    wf_id = body.get("workflow_id", "")
                if wf_id:
                    processed.append(wf_id)
        except RouteError as e:
            # Use the actual queue the message came from (may be DLQ)
            actual_queue = msg.get("queue", "workflow_step_result")
            bus.requeue(actual_queue, msg["msg_id"], str(e)[:500])
        except Exception as e:
            actual_queue = msg.get("queue", "workflow_step_result")
            bus.requeue(actual_queue, msg["msg_id"], str(e)[:500])
    
    return processed
