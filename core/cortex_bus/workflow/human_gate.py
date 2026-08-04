"""
Human-in-the-Loop Gate — handles workflow steps that need human approval.

When a workflow routes to a human (assigned_to == 'luke'):
  1. Workflow is marked 'blocked'
  2. A PGMQ message is sent to inbox_luke
  3. The HTML dashboard shows the pending review
  4. REST API endpoints allow Approve / Reject / Request Changes

Integration with Telegram is handled by the existing message delivery
pipeline — when a message hits inbox_luke, the normal inbox-watch cron
delivers it.
"""

from __future__ import annotations
from typing import Any, Optional

from cortex_bus.queue import get_queue, BusClient
from cortex_bus.workflow.db import (
    get_workflow, get_step, get_steps_for_workflow,
    update_workflow_state, update_step_state, write_audit,
)


def create_hil_request(workflow_id: str, step_id: str, step_name: str,
                       prompt: str, context: Optional[dict] = None):
    """Create a human-in-the-loop request.
    
    Sends a message to inbox_luke with the workflow context
    and available actions.
    """
    bus = get_queue()
    
    message = {
        "type": "human_review",
        "workflow_id": workflow_id,
        "step_id": step_id,
        "step_name": step_name,
        "prompt": prompt or "Human review needed",
        "context": context or {},
        "actions": ["approve", "reject", "request_changes"],
    }
    
    bus.send("inbox_luke", message)
    write_audit(workflow_id, "hil_requested", actor="system",
                step_id=step_id,
                detail={"step": step_name, "actions": ["approve", "reject", "request_changes"]})


def process_hil_response(workflow_id: str, step_id: str, decision: str,
                         feedback: Optional[str] = None) -> str:
    """Process a human's response to a HIL request.
    
    Args:
        workflow_id: The workflow to act on
        step_id: The step being reviewed
        decision: 'approve', 'reject', or 'request_changes'
        feedback: Optional human comment
    
    Returns:
        Workflow state after processing
    """
    bus = get_queue()
    decision = decision.lower().strip()
    
    workflow = get_workflow(workflow_id)
    if not workflow:
        raise ValueError(f"Workflow not found: {workflow_id}")
    
    step = get_step(step_id)
    if not step:
        raise ValueError(f"Step not found: {step_id}")
    
    if decision == "approve":
        # Mark step completed with 'approved' status, route continues
        update_step_state(step_id, "completed",
                          result={"hil_decision": "approved", "feedback": feedback})
        write_audit(workflow_id, "hil_approved", actor="human",
                    step_id=step_id, detail={"feedback": feedback})
        
        # Send to router via workflow_step_result queue
        bus.send("workflow_step_result", {
            "workflow_id": workflow_id,
            "step_id": step_id,
            "status": "approved",
            "result": {"hil_decision": "approved", "feedback": feedback},
        })
        
        update_workflow_state(workflow_id, "running")
        return "running"
    
    elif decision == "reject":
        update_step_state(step_id, "failed",
                          error=f"Rejected by human: {feedback or 'No reason given'}")
        update_workflow_state(workflow_id, "failed",
                              error=f"Rejected by human: {feedback or 'No reason given'}")
        write_audit(workflow_id, "hil_rejected", actor="human",
                    step_id=step_id, detail={"feedback": feedback})
        
        # Also route the rejection to the router
        bus.send("workflow_step_result", {
            "workflow_id": workflow_id,
            "step_id": step_id,
            "status": "rejected",
            "error": feedback,
        })
        return "failed"
    
    elif decision == "request_changes":
        # Re-queue the step with human feedback
        update_step_state(step_id, "pending",
                          error=f"Changes requested: {feedback}")
        write_audit(workflow_id, "hil_changes_requested", actor="human",
                    step_id=step_id, detail={"feedback": feedback})
        
        # Notify the assigned agent with the feedback
        assigned_to = step.get("assigned_to", "")
        if assigned_to and assigned_to != "luke":
            bus.send(f"inbox_{assigned_to}", {
                "type": "workflow_changes_requested",
                "workflow_id": workflow_id,
                "step_id": step_id,
                "step_name": step["step_name"],
                "feedback": feedback,
            })
        
        update_workflow_state(workflow_id, "running")
        return "running"
    
    else:
        raise ValueError(f"Unknown decision: {decision}. Use approve, reject, or request_changes.")


def get_pending_hil() -> list[dict]:
    """Get all workflow steps waiting for human review."""
    bus = get_queue()
    bus._ensure_conn()
    with bus._conn.cursor() as cur:
        cur.execute(
            """SELECT s.*, w.name as workflow_name, w.payload
               FROM bus.agent_workflow_steps s
               JOIN bus.agent_workflows w ON s.workflow_id = w.id
               WHERE s.state = 'running'
               AND w.state = 'blocked'
               ORDER BY w.priority DESC, s.started_at ASC"""
        )
        from cortex_bus.workflow.db import _row_to_dict
        return [_row_to_dict(cur, r) for r in cur.fetchall()]
