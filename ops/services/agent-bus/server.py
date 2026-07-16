"""
Hermes Cortex Agent Bus Server — PGMQ Backend on Postgres

FastAPI server that provides a REST API for the Postgres-native message queue.
All operations authenticated via Bearer tokens, authorized via permission model.

Endpoints:
    POST   /api/pgmq/send          — send a message
    POST   /api/pgmq/read          — read (dequeue) a message
    POST   /api/pgmq/archive       — archive a processed message
    POST   /api/pgmq/requeue       — requeue a failed message
    DELETE /api/pgmq/delete        — delete a message
    GET    /api/pgmq/depth/{queue}  — queue depth
    GET    /api/pgmq/queues         — list all queues
    GET    /api/pgmq/queue/{name}   — queue details
    GET    /health                  — health check
    GET    /                        — HTML dashboard
    /.well-known/agent-card.json    — agent discovery card

Usage:
    uvicorn server:app --host 127.0.0.1 --port 8905
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

# ── Add src to path for agent_bus imports ──
SRC_DIR = Path.home() / "hermes-cortex" / "runtime"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from agent_bus.queue import get_queue, NotAvailableError, BusClient
from agent_bus.auth import validate_token
from agent_bus.circuit_breaker import get_circuit_breaker
from agent_bus.workflow.dispatcher import dispatch_workflow, process_dispatch_message
from agent_bus.workflow.router import process_step_result as router_process_step
from agent_bus.workflow.human_gate import get_pending_hil, process_hil_response
from agent_bus.workflow.db import get_workflow, get_steps_for_workflow, list_active_workflows

app = FastAPI(title="Hermes Cortex Agent Bus")

# ── Auth dependency ──────────────────────────────────────────

AUTH_HEADER = "Authorization"
TOKEN_PREFIX = "Bearer "


def _authenticate(request: Request) -> str:
    """Extract and validate Bearer token. Returns agent name."""
    auth = request.headers.get(AUTH_HEADER, "")
    
    if not auth.startswith(TOKEN_PREFIX):
        raise HTTPException(401, "Missing or invalid Authorization header. Use: Authorization: Bearer <token>")
    
    token = auth[len(TOKEN_PREFIX):].strip()
    agent_name = validate_token(token)
    
    if not agent_name:
        # Log failed auth attempt
        try:
            bus = BusClient()
            bus._ensure_conn()
            with bus._conn.cursor() as cur:
                cur.execute(
                    "SELECT bus.audit('unknown', 'auth_failed', NULL, "
                    "  jsonb_build_object('ip', %s), %s, false)",
                    (request.client.host if request.client else "unknown", token[:16] + "..."),
                )
                bus._conn.commit()
        except Exception:
            pass
        raise HTTPException(401, "Invalid or expired token")
    
    return agent_name


def _check_permission(agent: str, queue: str, action: str):
    """Check if agent has permission to perform action on queue.
    
    action: 'read' or 'write'
    """
    from agent_bus.queue import get_queue
    bus = get_queue()
    bus._ensure_conn()
    with bus._conn.cursor() as cur:
        column = "can_read" if action == "read" else "can_write"
        cur.execute(
            f"SELECT {column} FROM bus.permissions WHERE agent_name = %s",
            (agent,),
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(403, f"Agent '{agent}' has no permissions configured")
        
        allowed_queues = row[0] or []
        is_admin = len(allowed_queues) > 0 and allowed_queues[0] == '*'  # future: wildcard support
        
        if not is_admin and queue not in allowed_queues:
            raise HTTPException(
                403,
                f"Agent '{agent}' does not have {action} access to queue '{queue}'"
            )


def _log_audit(agent: str, action: str, queue: Optional[str] = None,
               detail: Optional[dict] = None, ip: Optional[str] = None,
               success: bool = True):
    """Write an audit log entry (fire-and-forget)."""
    try:
        bus = BusClient()
        bus._ensure_conn()
        with bus._conn.cursor() as cur:
            cur.execute(
                "SELECT bus.audit(%s, %s, %s, %s::jsonb, %s, %s)",
                (agent, action, queue, json.dumps(detail or {}), ip, success),
            )
            bus._conn.commit()
    except Exception:
        pass  # Audit failures should not break the request


# ── API Endpoints ────────────────────────────────────────────

@app.post("/api/pgmq/send")
async def api_send(request: Request):
    """Send a message to a queue."""
    agent = _authenticate(request)
    try:
        body = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(400, "Invalid JSON body")
    
    if not isinstance(body, dict):
        raise HTTPException(400, "Body must be a JSON object")
    queue = body.get("queue", "")
    message = body.get("message", {})
    priority = body.get("priority", 0)
    correlation_id = body.get("correlation_id")
    
    if not queue or not message:
        raise HTTPException(400, "queue and message are required")
    
    _check_permission(agent, queue, "write")
    
    try:
        bus = get_queue()
        msg_id = bus.send(queue, message, priority, correlation_id)
        _log_audit(agent, "send", queue, {"msg_id": msg_id}, 
                   request.client.host if request.client else None)
        return {"msg_id": msg_id}
    except Exception as e:
        _log_audit(agent, "send", queue, {"error": str(e)[:200]},
                   request.client.host if request.client else None, False)
        # Check circuit breaker
        cb = get_circuit_breaker()
        cb.record_failure(str(e))
        raise HTTPException(503, f"Bus unavailable: {str(e)[:200]}")


@app.post("/api/pgmq/read")
async def api_read(request: Request):
    """Read (dequeue) a message from a queue."""
    agent = _authenticate(request)
    body = await request.json()
    queue = body.get("queue", "")
    vt = body.get("vt", 60)  # visibility timeout in seconds
    
    if not queue:
        raise HTTPException(400, "queue is required")
    
    _check_permission(agent, queue, "read")
    
    try:
        bus = get_queue()
        msg = bus.read(queue, vt)
        _log_audit(agent, "read", queue, 
                   {"has_msg": msg is not None},
                   request.client.host if request.client else None)
        if msg:
            return msg
        return {"msg_id": None, "queue": queue}
    except Exception as e:
        _log_audit(agent, "read", queue, {"error": str(e)[:200]},
                   request.client.host if request.client else None, False)
        cb = get_circuit_breaker()
        cb.record_failure(str(e))
        raise HTTPException(503, f"Bus unavailable: {str(e)[:200]}")


@app.post("/api/pgmq/archive")
async def api_archive(request: Request):
    """Archive a processed message."""
    agent = _authenticate(request)
    body = await request.json()
    queue = body.get("queue", "")
    msg_id = body.get("msg_id", "")
    
    if not queue or not msg_id:
        raise HTTPException(400, "queue and msg_id are required")
    
    # Validate msg_id format
    import uuid
    try:
        uuid.UUID(msg_id)
    except (ValueError, AttributeError):
        raise HTTPException(400, f"Invalid msg_id format: '{msg_id}' is not a valid UUID")
    
    _check_permission(agent, queue, "write")
    
    try:
        bus = get_queue()
        result = bus.archive(queue, msg_id, agent)
        _log_audit(agent, "archive", queue, {"msg_id": msg_id, "success": result},
                   request.client.host if request.client else None)
        return {"success": result}
    except Exception as e:
        _log_audit(agent, "archive", queue, {"msg_id": msg_id, "error": str(e)[:200]},
                   request.client.host if request.client else None, False)
        raise HTTPException(503, f"Bus unavailable: {str(e)[:200]}")


@app.post("/api/pgmq/requeue")
async def api_requeue(request: Request):
    """Re-queue a failed message (increments retry)."""
    agent = _authenticate(request)
    body = await request.json()
    queue = body.get("queue", "")
    msg_id = body.get("msg_id", "")
    error = body.get("error", "")
    
    if not queue or not msg_id:
        raise HTTPException(400, "queue and msg_id are required")
    
    import uuid
    try:
        uuid.UUID(msg_id)
    except (ValueError, AttributeError):
        raise HTTPException(400, f"Invalid msg_id: '{msg_id}'")
    
    _check_permission(agent, queue, "write")
    
    try:
        bus = get_queue()
        result = bus.requeue(queue, msg_id, error)
        _log_audit(agent, "requeue", queue, {"msg_id": msg_id, "success": result},
                   request.client.host if request.client else None)
        return {"success": result}
    except Exception as e:
        _log_audit(agent, "requeue", queue, {"msg_id": msg_id, "error": str(e)[:200]},
                   request.client.host if request.client else None, False)
        raise HTTPException(503, f"Bus unavailable: {str(e)[:200]}")


@app.delete("/api/pgmq/delete")
async def api_delete(request: Request):
    """Delete a message from a queue."""
    agent = _authenticate(request)
    body = await request.json()
    queue = body.get("queue", "")
    msg_id = body.get("msg_id", "")
    
    if not queue or not msg_id:
        raise HTTPException(400, "queue and msg_id are required")
    
    _check_permission(agent, queue, "write")
    
    try:
        bus = get_queue()
        result = bus.delete(queue, msg_id)
        return {"success": result}
    except Exception as e:
        raise HTTPException(503, f"Bus unavailable: {str(e)[:200]}")


@app.get("/api/pgmq/depth/{queue}")
async def api_depth(queue: str, request: Request):
    """Get the number of pending messages in a queue."""
    agent = _authenticate(request)
    _check_permission(agent, queue, "read")
    
    try:
        bus = get_queue()
        depth = bus.depth(queue)
        return {"queue": queue, "depth": depth}
    except Exception as e:
        raise HTTPException(503, f"Bus unavailable: {str(e)[:200]}")


@app.get("/api/pgmq/queues")
async def api_queues(request: Request):
    """List all queues with depth and metadata."""
    agent = _authenticate(request)
    
    try:
        bus = get_queue()
        queues = bus.list_queues()
        return {"queues": queues, "total": len(queues)}
    except Exception as e:
        raise HTTPException(503, f"Bus unavailable: {str(e)[:200]}")


@app.get("/api/pgmq/queue/{name}")
async def api_queue_detail(name: str, request: Request):
    """Get detailed info about a specific queue."""
    agent = _authenticate(request)
    _check_permission(agent, name, "read")
    
    try:
        bus = get_queue()
        queues = bus.list_queues()
        for q in queues:
            if q["name"] == name:
                return q
        raise HTTPException(404, f"Queue '{name}' not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(503, f"Bus unavailable: {str(e)[:200]}")


@app.get("/api/bus/dashboard")
async def api_dashboard_json(request: Request):
    """JSON dashboard data for monitoring."""
    agent = _authenticate(request)
    
    try:
        bus = get_queue()
        queues = bus.list_queues()
        cb = get_circuit_breaker()
        
        total_pending = sum(q["depth"] for q in queues)
        total_processing = sum(q["processing"] for q in queues)
        dlqs = [q for q in queues if q["dlq"]]
        dlq_with_messages = [q for q in dlqs if q["depth"] > 0 or q["processing"] > 0]
        
        return {
            "status": "ok",
            "backend": cb.get_backend(),
            "queues": {
                "total": len(queues),
                "pending": total_pending,
                "processing": total_processing,
            },
            "dlq_alerts": [
                {"name": q["name"], "depth": q["depth"]}
                for q in dlq_with_messages
            ],
            "circuit_breaker": cb._state.to_dict(),
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)[:200],
            "backend": get_circuit_breaker().get_backend(),
        }


@app.get("/health")
async def health():
    """Health check — reports bus status."""
    cb = get_circuit_breaker()
    backend = cb.get_backend()
    
    try:
        bus = get_queue()
        queues = bus.list_queues()
        return {
            "status": "ok",
            "backend": backend,
            "queues": len(queues),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        return {
            "status": "degraded" if backend == "file" else "error",
            "backend": backend,
            "error": str(e)[:200],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


@app.get("/.well-known/agent-card.json")
async def agent_card():
    """Agent discovery card (public, no auth)."""
    return {
        "name": "hermes-cortex-bus",
        "version": "2.0.0",
        "description": "Hermes Cortex Agent Bus — PGMQ message queue + workflow engine",
        "capabilities": [
            "pgmq_messaging",
            "workflow_dispatch",
            "workflow_routing",
            "human_in_the_loop",
            "deterministic_routing",
        ],
        "endpoints": {
            "send": "POST /api/pgmq/send",
            "read": "POST /api/pgmq/read",
            "archive": "POST /api/pgmq/archive",
            "workflows": "GET /api/workflows",
            "dispatch": "POST /api/workflows/dispatch",
            "hil": "POST /api/workflows/hil",
            "health": "GET /health",
            "dashboard": "GET /",
        },
    }


# ── HTML Dashboard ───────────────────────────────────────────

DASHBOARD_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Hermes Agent Bus</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0d1117; color: #c9d1d9; padding: 20px; }
  h1 { color: #58a6ff; font-size: 24px; margin-bottom: 20px; }
  h2 { color: #8b949e; font-size: 16px; text-transform: uppercase; letter-spacing: 1px; margin: 20px 0 10px; }
  .status-bar { display: flex; gap: 20px; margin-bottom: 20px; flex-wrap: wrap; }
  .status-card { background: #161b22; border: 1px solid #30363d; border-radius: 6px; padding: 16px; flex: 1; min-width: 150px; }
  .status-card h3 { font-size: 12px; color: #8b949e; text-transform: uppercase; }
  .status-card .value { font-size: 28px; font-weight: 600; margin-top: 4px; }
  .status-card .value.ok { color: #3fb950; }
  .status-card .value.degraded { color: #d29922; }
  .status-card .value.error { color: #f85149; }
  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; padding: 8px 12px; border-bottom: 1px solid #30363d; font-size: 12px; color: #8b949e; text-transform: uppercase; }
  td { padding: 8px 12px; border-bottom: 1px solid #21262d; font-size: 14px; }
  tr:hover td { background: #161b22; }
  .dlq { background: #2d1b1b; }
  .dlq:hover td { background: #3d2323; }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: 500; }
  .badge.ok { background: #1b3a1b; color: #3fb950; }
  .badge.warn { background: #3a2f1b; color: #d29922; }
  .badge.err { background: #3a1b1b; color: #f85149; }
  .footer { margin-top: 20px; font-size: 12px; color: #484f58; text-align: center; }
  .refresh { float: right; font-size: 12px; color: #58a6ff; cursor: pointer; }
  .refresh:hover { text-decoration: underline; }
</style>
</head>
<body>
<h1>Hermes Agent Bus <span class="refresh" onclick="location.reload()">↻ refresh</span></h1>

<div class="status-bar" id="status-bar">
  <div class="status-card">
    <h3>Backend</h3>
    <div class="value" id="backend">--</div>
  </div>
  <div class="status-card">
    <h3>Active Queues</h3>
    <div class="value" id="queue-count">--</div>
  </div>
  <div class="status-card">
    <h3>Pending Messages</h3>
    <div class="value" id="pending">--</div>
  </div>
  <div class="status-card">
    <h3>Processing</h3>
    <div class="value" id="processing">--</div>
  </div>
  <div class="status-card">
    <h3>DLQ Alerts</h3>
    <div class="value" id="dlq-alerts">--</div>
  </div>
</div>

<h2>Queues <span id="queue-subtitle" style="font-weight:normal;font-size:12px;color:#484f58"></span></h2>
<table>
<thead><tr><th>Queue</th><th>Depth</th><th>Processing</th><th>DLQ</th><th>Parent</th><th>Status</th></tr></thead>
<tbody id="queue-table"></tbody>
</table>

<div class="footer">Hermes Cortex Agent Bus &mdash; real-time queue monitoring</div>

<h2>Workflows <span id="wf-subtitle" style="font-weight:normal;font-size:12px;color:#484f58"></span></h2>
<table>
<thead><tr><th>ID</th><th>Name</th><th>State</th><th>Steps</th><th>Deadline</th><th>Actions</th></tr></thead>
<tbody id="workflow-table"></tbody>
</table>

<script>
async function load() {
  try {
    const r = await fetch('/api/bus/dashboard');
    const d = await r.json();
    
    if (d.status === 'error') throw new Error(d.error);
    
    document.getElementById('backend').textContent = d.backend;
    document.getElementById('backend').className = 'value ' + d.status;
    document.getElementById('queue-count').textContent = d.queues.total;
    document.getElementById('pending').textContent = d.queues.pending;
    document.getElementById('processing').textContent = d.queues.processing;
    
    if (d.dlq_alerts && d.dlq_alerts.length > 0) {
      document.getElementById('dlq-alerts').textContent = d.dlq_alerts.length;
      document.getElementById('dlq-alerts').className = 'value error';
    } else {
      document.getElementById('dlq-alerts').textContent = '0';
      document.getElementById('dlq-alerts').className = 'value ok';
    }
    
    // Load queue details
    const qr = await fetch('/api/pgmq/queues');
    const qd = await qr.json();
    const tbody = document.getElementById('queue-table');
    const queues = (qd.queues || []).sort((a,b) => a.name.localeCompare(b.name));
    
    document.getElementById('queue-subtitle').textContent = '(' + queues.length + ' total)';
    
    tbody.innerHTML = queues.map(q => {
      const isDlq = q.dlq ? ' dlq' : '';
      const depthClass = q.depth > 0 ? (q.dlq ? 'err' : 'warn') : 'ok';
      return '<tr class="' + isDlq + '">' +
        '<td>' + q.name + '</td>' +
        '<td><span class="badge ' + depthClass + '">' + q.depth + '</span></td>' +
        '<td>' + q.processing + '</td>' +
        '<td>' + (q.dlq ? '⚠' : '—') + '</td>' +
        '<td>' + (q.parent || '—') + '</td>' +
        '<td>' + (q.depth > 0 ? '⚠ messages' : '✓ empty') + '</td>' +
        '</tr>';
    }).join('');
  } catch(e) {
    document.getElementById('status-bar').innerHTML = '<div class="status-card"><h3>Error</h3><div class="value error">' + e.message + '</div></div>';
  }
  
  // Load workflows
  try {
    const wr = await fetch('/api/workflows');
    const wd = await wr.json();
    const wtbody = document.getElementById('workflow-table');
    const wfs = (wd.workflows || []);
    
    document.getElementById('wf-subtitle').textContent = '(' + wfs.length + ' active)';
    
    wtbody.innerHTML = wfs.map(w => {
      const stateClass = w.state === 'running' ? 'ok' : (w.state === 'blocked' ? 'warn' : 'err');
      const deadline = w.deadline_at ? new Date(w.deadline_at).toLocaleTimeString() : '—';
      const shortId = w.id ? w.id.substring(0, 8) : '—';
      const steps = w.steps ? w.steps.length : '?';
      return '<tr>' +
        '<td>' + shortId + '</td>' +
        '<td>' + (w.name || '—') + '</td>' +
        '<td><span class="badge ' + stateClass + '">' + w.state + '</span></td>' +
        '<td>' + steps + '</td>' +
        '<td>' + deadline + '</td>' +
        '<td>' + (w.state === 'blocked' ? '🧑 HIL' : '—') + '</td>' +
        '</tr>';
    }).join('');
  } catch(e) {
    // Silently skip — workflows table may not be available on older buses
  }
}
load();
setInterval(load, 10000);
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """HTML dashboard for the agent bus."""
    return DASHBOARD_HTML


# ── Workflow API Endpoints ───────────────────────────────────


@app.get("/api/workflows/hil")
async def api_hil_list(request: Request):
    """List workflow steps waiting for human review."""
    agent = _authenticate(request)
    pending = get_pending_hil()
    return {"pending_reviews": pending, "total": len(pending)}


@app.post("/api/workflows/hil")
async def api_hil_respond(request: Request):
    """Respond to a human-in-the-loop request."""
    agent = _authenticate(request)
    body = await request.json()
    
    wf_id = body.get("workflow_id", "")
    step_id = body.get("step_id", "")
    decision = body.get("decision", "")
    feedback = body.get("feedback")
    
    if not wf_id or not step_id or not decision:
        raise HTTPException(400, "workflow_id, step_id, and decision are required")
    
    try:
        result = process_hil_response(wf_id, step_id, decision, feedback)
        _log_audit(agent, "hil_response", "workflow_hil",
                   {"workflow_id": wf_id, "decision": decision},
                   request.client.host if request.client else None)
        return {"workflow_id": wf_id, "decision": decision, "new_state": result}
    except ValueError as e:
        raise HTTPException(400, str(e)[:300])


@app.get("/api/workflows")
async def api_list_workflows(request: Request, state: str = ""):
    """List workflows, optionally filtered by state."""
    agent = _authenticate(request)
    if state:
        from agent_bus.workflow.db import get_queue
        bus = get_queue()
        bus._ensure_conn()
        with bus._conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM bus.agent_workflows WHERE state = %s ORDER BY created_at DESC",
                (state,),
            )
            from agent_bus.workflow.db import _row_to_dict
            workflows = [_row_to_dict(cur, r) for r in cur.fetchall()]
    else:
        workflows = list_active_workflows()
    return {"workflows": workflows, "total": len(workflows)}


@app.post("/api/workflows/dispatch")
async def api_dispatch_workflow(request: Request):
    """Dispatch a workflow via the dispatch queue."""
    agent = _authenticate(request)
    body = await request.json()
    
    try:
        msg = {"body": body}
        wf_id = process_dispatch_message(msg)
        if wf_id:
            _log_audit(agent, "workflow_dispatch", "workflow_dispatch",
                       {"workflow_id": wf_id, "name": body.get("workflow_name")},
                       request.client.host if request.client else None)
            return {"workflow_id": wf_id, "status": "dispatched"}
        else:
            raise HTTPException(500, "Dispatch returned no workflow ID")
    except Exception as e:
        raise HTTPException(400, str(e)[:300])


@app.get("/api/workflows/{wf_id}")
async def api_get_workflow(wf_id: str, request: Request):
    """Get workflow details with steps."""
    agent = _authenticate(request)
    wf = get_workflow(wf_id)
    if not wf:
        raise HTTPException(404, f"Workflow not found: {wf_id}")
    
    steps = get_steps_for_workflow(wf_id)
    wf["steps"] = steps
    return wf



# ── Main ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("CORTEX_BUS_PORT", "8905"))
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")
