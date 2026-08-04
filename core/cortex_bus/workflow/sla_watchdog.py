"""Workflow SLA Watchdog + DLQ Monitor — combined cron job.

Checks:
  1. Running workflows past their deadline -> mark timed_out, notify agent
  2. All DLQ depths -> alert on growth trend (not absolute depth)
  3. Running steps past timeout -> mark timed_out, handle retry/DLQ

Silent when all clear (watchdog pattern — no output = all good).

DLQ alert logic:
  - Cascade DLQs (dlq_dlq): ANY depth -> critical alert (structural defect)
  - Single DLQs: alert only if depth grew >20 since last check
    (stable high depth is pre-existing, not actionable)
"""

from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from cortex_bus.queue import get_queue, BusClient
from cortex_bus.workflow.db import (
    get_workflow, get_step, get_steps_for_workflow,
    update_workflow_state, update_step_state, write_audit,
    list_active_workflows,
)


def run_watchdog() -> list[str]:
    """Run one watchdog cycle. Returns list of alert messages.
    
    Silent (empty list) when all clear.
    """
    alerts = []
    bus = get_queue()
    now = datetime.now(timezone.utc)
    
    # ── 1. Timed-out workflows ──────────────────────────
    timed_out = _find_timed_out_workflows(now)
    for wf in timed_out:
        wf_id = wf["id"]
        wf_name = wf.get("name", "unknown")
        
        update_workflow_state(wf_id, "timed_out",
                              error=f"Deadline passed: {wf.get('deadline_at', 'unknown')}")
        write_audit(wf_id, "workflow_timed_out", actor="watchdog",
                    detail={"deadline": str(wf.get("deadline_at"))})
        
        # Mark all running/pending steps as skipped
        steps = get_steps_for_workflow(wf_id)
        for step in steps:
            if step["state"] in ("pending", "running"):
                update_step_state(step["id"], "skipped",
                                  error="Workflow timed out")
        
        # Notify the owner
        owner = wf.get("owner_agent", "moses")
        alerts.append(
            f"⏰ Workflow '{wf_name}' ({wf_id[:8]}) timed out. "
            f"Owner: {owner}. {len(steps)} steps skipped."
        )
    
    # ── 2. Timed-out steps ──────────────────────────────
    timed_out_steps = _find_timed_out_steps(now)
    for step in timed_out_steps:
        wf_id = step["workflow_id"]
        step_name = step["step_name"]
        step_id = step["id"]
        retry_count = step.get("retry_count", 0)
        max_retries = step.get("max_retries", 2)
        
        if retry_count < max_retries:
            # Retry: increment counter and requeue
            new_count = retry_count + 1
            update_step_state(step_id, "pending", retry_count=new_count,
                              error=f"Timed out (attempt {new_count}/{max_retries})")
            write_audit(wf_id, "step_retrying", actor="watchdog",
                        step_id=step_id,
                        detail={"attempt": new_count, "max": max_retries})
            
            alerts.append(
                f"🔄 Step '{step_name}' in workflow '{wf_id[:8]}' timed out. "
                f"Retrying ({new_count}/{max_retries})."
            )
        else:
            # Max retries exhausted — move to DLQ
            update_step_state(step_id, "failed",
                              error=f"Timed out after {max_retries} retries")
            write_audit(wf_id, "step_max_retries", actor="watchdog",
                        step_id=step_id,
                        detail={"retries": max_retries})
            
            # Send a notification to the owner
            wf = get_workflow(wf_id)
            owner = wf.get("owner_agent", "moses") if wf else "moses"
            alerts.append(
                f"❌ Step '{step_name}' in workflow '{wf_id[:8]}' failed "
                f"after {max_retries} retries. Owner: {owner}."
            )
    
    # ── 3. DLQ depth check ──────────────────────────────
    dlq_alerts = _check_dlqs()
    alerts.extend(dlq_alerts)
    
    return alerts


def _find_timed_out_workflows(now: datetime) -> list[dict]:
    """Find active workflows past their deadline."""
    bus = get_queue()
    bus._ensure_conn()
    with bus._conn.cursor() as cur:
        cur.execute(
            """SELECT * FROM bus.agent_workflows
               WHERE state IN ('running', 'blocked')
               AND deadline_at IS NOT NULL
               AND deadline_at < %s""",
            (now,),
        )
        from cortex_bus.workflow.db import _row_to_dict
        return [_row_to_dict(cur, r) for r in cur.fetchall()]


def _find_timed_out_steps(now: datetime) -> list[dict]:
    """Find running steps past their timeout."""
    bus = get_queue()
    bus._ensure_conn()
    with bus._conn.cursor() as cur:
        # A step has timed out if:
        # - It's in 'running' state AND
        # - started_at + timeout_seconds < now
        cur.execute(
            """SELECT s.* FROM bus.agent_workflow_steps s
               JOIN bus.agent_workflows w ON s.workflow_id = w.id
               WHERE s.state = 'running'
               AND w.state NOT IN ('completed', 'failed', 'timed_out', 'canceled')
               AND (s.started_at + (s.timeout_seconds || ' seconds')::interval) < %s""",
            (now,),
        )
        from cortex_bus.workflow.db import _row_to_dict
        return [_row_to_dict(cur, r) for r in cur.fetchall()]


DLQ_STATE_FILE = Path.home() / ".hermes-cortex" / "state" / "sla-watchdog-dlq-state.json"
DLQ_ALERT_THRESHOLD = 20  # alert if DLQ depth grew by more than this since last check


def _check_dlqs() -> list[str]:
    """Check DLQ queues. Alerts on growth trend, not absolute depth.
    
    - Cascade DLQs (dlq_dlq): ANY depth > 0 -> critical alert
    - Single DLQs: alert only if depth grew > DLQ_ALERT_THRESHOLD since last tick
      (stable high depth means pre-existing artifacts, not active issues)
    """
    bus = get_queue()
    alerts = []
    
    try:
        queues = bus.list_queues()
    except Exception:
        return ["⚠ Could not list queues for DLQ check"]
    
    # Load previous depths
    prev_depths: dict[str, int] = {}
    if DLQ_STATE_FILE.exists():
        try:
            prev_depths = json.loads(DLQ_STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            prev_depths = {}
    
    # Check each DLQ
    current_depths: dict[str, int] = {}
    for q in queues:
        if not q.get("dlq"):
            continue
        
        dlq_name = q["name"]
        depth = q.get("depth", 0)
        current_depths[dlq_name] = depth
        
        if depth == 0:
            continue  # empty queue, no alert needed
        
        parent_name = q.get("parent", dlq_name.replace("_dlq", ""))
        
        # Cascade DLQs are a STRUCTURAL DEFECT — always alert
        if dlq_name.count("_dlq") > 1:
            alerts.append(
                f"🔴 CRITICAL: Cascade DLQ '{dlq_name}' has {depth} messages. "
                f"Parent: {parent_name}. This indicates the DLQ guard "
                f"has failed — run test-bus-schema.sh immediately."
            )
            continue
        
        # Single DLQ: check growth trend
        prev_depth = prev_depths.get(dlq_name, 0)
        delta = depth - prev_depth
        
        if delta > DLQ_ALERT_THRESHOLD:
            alerts.append(
                f"⚠️ DLQ '{dlq_name}' grew by {delta}→{depth} since last check. "
                f"Source queue: {parent_name}"
            )
        # else: stable or slow growth — no alert
    
    # Save current depths for next tick
    DLQ_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    DLQ_STATE_FILE.write_text(json.dumps(current_depths))
    
    return alerts


# ── Cron entry point (no_agent pattern) ─────────────────────

def main():
    """Cron entry point — silent when all clear."""
    try:
        alerts = run_watchdog()
    except Exception as e:
        print(f"[watchdog] ERROR: {e}")
        return
    
    if alerts:
        print(f"━━━ Workflow Watchdog — {datetime.now(timezone.utc).strftime('%H:%M UTC')} ━━━")
        for alert in alerts:
            print(f"  {alert}")
        print(f"\n{len(alerts)} alert(s)")


if __name__ == "__main__":
    main()
