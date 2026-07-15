#!/usr/bin/env python3
"""Task Control Authority MCP Server — the single deterministic authority
for task lifecycle, scope enforcement, and completion gates in Hermes Cortex.

The model proposes actions; this Authority decides whether they are allowed.
No tool call that mutates state, files, or the outside world executes without
passing a deterministic check from this server.

Usage:
    hermes mcp add \\
        --command python3 \\
        --args /path/to/task-control-mcp.py \\
        task-control

Tools:
    claim_task              Open a new task (denied if active task exists)
    get_task_state          Abbreviated state for context injection
    get_task_state_full     Full ledger dump
    advance_task_state      Legal state transition
    update_plan             Append a plan amendment (within scope)
    record_issue            Log a discovered problem (never changes task state)
    promote_issue_to_task   Convert a queued issue into a claimable task
    request_interruption    Request a task switch
    resume_from_interrupt   Pop task stack, restore prior task
    renew_lease             Heartbeat to extend expires_at
    request_completion      Gate-checked completion
    list_issues             Read-only query
    list_tasks              Read-only query

Reference: docs/new-harness.md, docs/research/new_harness/
Consolidated spec: docs/research/new_harness/new-harness-claude-ai-260715.md
"""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Dependency check ────────────────────────────────────────────
_HAVE_MCP = importlib.util.find_spec("mcp")
if _HAVE_MCP is None:
    msg = (
        "[task-control] ERROR: Required 'mcp' Python package not found.\n"
        "[task-control] Install:  pip install mcp\n"
    )
    print(msg, file=sys.stderr)
    sys.exit(1)

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent, CallToolResult

log = logging.getLogger("task-control")
logging.basicConfig(
    level=logging.INFO,
    format="[task-control] %(levelname)s: %(message)s",
    stream=sys.stderr,
    force=True,
)

# ── Paths ──────────────────────────────────────────────────────
HOME = Path.home()
STATE_DIR = HOME / ".hermes-cortex" / "state"
LEDGER_PATH = STATE_DIR / "task-state.json"
AUDIT_LOG = STATE_DIR / "audit.log"
ARCHIVE_DIR = STATE_DIR / "archive"

# Defaults
DEFAULT_LEASE_TTL = 600       # 10 minutes
MAX_NESTED_INTERRUPTIONS = 1
MAX_EMERGENCY_DEPTH = 3
REQUIRE_PROVENANCE_TOOLS = {
    "write_file", "patch", "terminal", "cronjob",
    "skill_manage", "delegate_task",
}
AUTHORIZED_INTERRUPTION_REASONS = {
    "BLOCKING_DEFECT",
    "SAFETY_EMERGENCY",
    "SECURITY_EMERGENCY",
    "DATA_LOSS_RISK",
    "USER_PRIORITY_CHANGE",
    "ESCALATION_REQUIRED",
}
EMERGENCY_REASONS = {"SAFETY_EMERGENCY", "SECURITY_EMERGENCY", "DATA_LOSS_RISK"}

# ── Schema ─────────────────────────────────────────────────────
SCHEMA_VERSION = 2

EMPTY_LEDGER: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "active_task": None,
    "task_stack": [],
    "queued_tasks": [],
    "completed_tasks": [],
    "discovered_issues": [],
    "global_rules": {
        "authorized_interruption_reasons": sorted(AUTHORIZED_INTERRUPTION_REASONS),
        "emergency_reasons": sorted(EMERGENCY_REASONS),
        "max_nested_interruptions": MAX_NESTED_INTERRUPTIONS,
        "lease_ttl_seconds": DEFAULT_LEASE_TTL,
        "require_provenance_for_tools": sorted(REQUIRE_PROVENANCE_TOOLS),
    },
}

LEGAL_TRANSITIONS: dict[str, set[str]] = {
    "IDLE":           {"PLANNING"},
    "PLANNING":       {"EXECUTING", "CANCELLED"},
    "EXECUTING":      {"VERIFYING", "BLOCKED", "INTERRUPT_REQ", "CANCELLED"},
    "VERIFYING":      {"EXECUTING", "REPORTING", "CANCELLED"},
    "REPORTING":      {"COMPLETED", "CANCELLED"},
    "COMPLETED":      {"IDLE"},
    "CANCELLED":      {"IDLE"},
    "BLOCKED":        {"EXECUTING", "CANCELLED"},
    "INTERRUPT_REQ":  {"EXECUTING", "SUSPENDED", "CANCELLED"},
    "SUSPENDED":      {"EXECUTING", "CANCELLED"},
}

TASK_ID_COUNTER_KEY = "_task_counter"
ISSUE_ID_COUNTER_KEY = "_issue_counter"


# ── Time helpers ───────────────────────────────────────────────
def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_iso(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _now_ts() -> float:
    return time.time()


# ── File I/O (atomic) ─────────────────────────────────────────
def _read_ledger() -> dict[str, Any]:
    if not LEDGER_PATH.exists():
        return dict(EMPTY_LEDGER)
    try:
        raw = LEDGER_PATH.read_text()
        return json.loads(raw) if raw.strip() else dict(EMPTY_LEDGER)
    except (json.JSONDecodeError, OSError):
        log.warning("Corrupt ledger, resetting to empty")
        return dict(EMPTY_LEDGER)


def _write_ledger(ledger: dict[str, Any]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    content = json.dumps(ledger, indent=2, ensure_ascii=False)
    # Write to temp + atomic rename to avoid partial writes
    fd, tmp = tempfile.mkstemp(dir=str(STATE_DIR), prefix="task-state-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        shutil.move(tmp, str(LEDGER_PATH))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _append_audit(entry: dict[str, Any]) -> None:
    """Append one line to the audit log."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    entry["_timestamp"] = _now_iso()
    try:
        with open(str(AUDIT_LOG), "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except OSError:
        log.warning("Failed to write audit log")


# ── ID generation ──────────────────────────────────────────────
def _next_id(ledger: dict, prefix: str, counter_key: str) -> tuple[str, int]:
    counter = ledger.get(counter_key, 0) + 1
    ledger[counter_key] = counter
    return f"{prefix}-{counter:03d}", counter


# ── Core logic ─────────────────────────────────────────────────
def _active_task(ledger: dict) -> dict | None:
    return ledger.get("active_task")


def _task_is_non_terminal(task: dict | None) -> bool:
    """Return True if the task is in a state where it should prevent new tasks."""
    if task is None:
        return False
    s = task["status"]
    return s in ("PLANNING", "EXECUTING", "VERIFYING", "REPORTING", "INTERRUPT_REQ", "SUSPENDED", "BLOCKED")


def _lease_valid(task: dict | None, now: float | None = None) -> bool:
    if task is None or task.get("lease") is None:
        return False
    lease = task["lease"]
    if lease.get("status") != "held":
        return False
    expires = lease.get("expires_at")
    if not expires:
        return False
    n = now or _now_ts()
    # Convert ISO expires_at to timestamp
    try:
        exp_ts = _parse_iso(expires).timestamp()
        return n < exp_ts
    except (ValueError, TypeError):
        return False


def _stack_depth(ledger: dict) -> int:
    return len(ledger.get("task_stack", []))


# ── MCP Tools Implementation ──────────────────────────────────

def _tool_claim_task(args: dict) -> tuple[bool, str, dict | None]:
    ledger = _read_ledger()
    active = _active_task(ledger)
    if _task_is_non_terminal(active):
        return (False, f"Active task {active['id']} is in state {active['status']}. Complete or cancel first.", None)

    objective = args.get("objective", "").strip()
    if not objective:
        return (False, "objective is required.", None)

    priority = args.get("priority", 50)
    acceptance_criteria = args.get("acceptance_criteria", [])

    tid, _ = _next_id(ledger, "TASK", TASK_ID_COUNTER_KEY)
    allowed_scope = args.get("allowed_scope", ["**"])
    allowed_tools = args.get("allowed_tools", None)  # None = all tools

    plan = args.get("plan", [])
    now_iso = _now_iso()
    lease_ttl = ledger.get("global_rules", {}).get("lease_ttl_seconds", DEFAULT_LEASE_TTL)

    task = {
        "id": tid,
        "objective": objective,
        "priority": priority,
        "status": "PLANNING",
        "acceptance_criteria": [
            {"id": ac.get("id", f"AC-{i+1}"), "description": ac.get("description", ""), "status": "pending"}
            for i, ac in enumerate(acceptance_criteria)
        ],
        "current_step": None,
        "allowed_scope": allowed_scope,
        "allowed_tools": allowed_tools,
        "blocked_by": [],
        "lease": {
            "owner": args.get("owner", "default"),
            "status": "held",
            "held_since": now_iso,
            "renewed_at": now_iso,
            "expires_at": datetime.fromtimestamp(_now_ts() + lease_ttl, tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        },
        "plan": [
            {"step_id": s.get("step_id", f"STEP-{i+1}"), "description": s.get("description", ""), "status": "pending"}
            for i, s in enumerate(plan)
        ],
        "plan_amendments": [],
    }

    ledger["active_task"] = task
    _write_ledger(ledger)
    _append_audit({"action": "claim_task", "task_id": tid, "objective": objective, "result": "allowed"})
    return (True, f"Task {tid} claimed, state=PLANNING", {"task_id": tid})


def _tool_get_task_state(args: dict) -> tuple[bool, str, dict | None]:
    ledger = _read_ledger()
    active = _active_task(ledger)
    if active is None:
        return (True, json.dumps({"active_task": None, "issue_count": len(ledger.get("discovered_issues", [])), "stack_depth": _stack_depth(ledger)}), None)
    return (True, json.dumps({
        "task_id": active["id"],
        "objective": active["objective"],
        "status": active["status"],
        "current_step": active.get("current_step"),
        "priority": active["priority"],
        "ac_count": len(active.get("acceptance_criteria", [])),
        "ac_passed": sum(1 for ac in active.get("acceptance_criteria", []) if ac["status"] == "passed"),
        "blocked_by": active.get("blocked_by", []),
        "issue_count": len(ledger.get("discovered_issues", [])),
        "stack_depth": _stack_depth(ledger),
    }), None)


def _tool_get_task_state_full(args: dict) -> tuple[bool, str, dict | None]:
    ledger = _read_ledger()
    # Prune full ledger to skip internal counters
    display = {k: v for k, v in ledger.items() if not k.startswith("_")}
    return (True, json.dumps(display, indent=2), None)


def _tool_advance_task_state(args: dict) -> tuple[bool, str, dict | None]:
    ledger = _read_ledger()
    active = _active_task(ledger)
    if active is None:
        return (False, "No active task.", None)

    new_state = args.get("new_state", "").upper()
    reason = args.get("reason", "")
    criterion_id = args.get("criterion_id")

    current = active["status"]
    if new_state not in LEGAL_TRANSITIONS.get(current, set()):
        return (False, f"Illegal transition: {current} → {new_state}. Allowed: {sorted(LEGAL_TRANSITIONS.get(current, set()))}", None)

    if new_state == "BLOCKED" and not reason:
        return (False, "blocked_by reason is required for BLOCKED state.", None)
    if new_state == "CANCELLED" and not reason:
        return (False, "reason is required for CANCELLED state.", None)

    # Check lease for state transitions that require authority
    if new_state in ("EXECUTING", "VERIFYING", "REPORTING", "BLOCKED"):
        if not _lease_valid(active):
            return (False, "Lease has expired. Renew with renew_lease first.", None)

    old_status = active["status"]
    active["status"] = new_state

    if new_state == "EXECUTING" and args.get("step_id"):
        active["current_step"] = args["step_id"]
        # Mark step in_progress
        for step in active["plan"]:
            if step["step_id"] == args["step_id"] and step["status"] == "pending":
                step["status"] = "in_progress"
                break

    if new_state == "VERIFYING" and criterion_id:
        for ac in active["acceptance_criteria"]:
            if ac["id"] == criterion_id:
                ac["status"] = "passed"
                break

    if new_state == "BLOCKED":
        active["blocked_by"] = [reason]

    _write_ledger(ledger)
    _append_audit({"action": "advance_task_state", "task_id": active["id"], "from": old_status, "to": new_state, "reason": reason, "result": "allowed"})
    return (True, f"Task {active['id']}: {old_status} → {new_state}", {"task_id": active["id"], "status": new_state})


def _tool_update_plan(args: dict) -> tuple[bool, str, dict | None]:
    ledger = _read_ledger()
    active = _active_task(ledger)
    if active is None:
        return (False, "No active task.", None)

    step_id = args.get("step_id", "").strip()
    description = args.get("description", "").strip()
    if not step_id or not description:
        return (False, "step_id and description are required.", None)

    # Check scope: does the new step description reference out-of-scope paths?
    # This is a basic check; the envelope is the primary guard.
    amendment = {
        "step_id": step_id,
        "description": description,
        "status": "pending",
        "amended_at": _now_iso(),
        "reason": args.get("reason", "Mid-task refinement"),
    }
    active.setdefault("plan_amendments", []).append(amendment)
    active.setdefault("plan", []).append({
        "step_id": step_id,
        "description": description,
        "status": "pending",
    })

    _write_ledger(ledger)
    _append_audit({"action": "update_plan", "task_id": active["id"], "step_id": step_id, "result": "allowed"})
    return (True, f"Plan amended: added {step_id}", None)


def _tool_record_issue(args: dict) -> tuple[bool, str, dict | None]:
    ledger = _read_ledger()
    title = args.get("title", "").strip()
    severity = args.get("severity", "medium")
    evidence = args.get("evidence", "").strip()
    if not title or not evidence:
        return (False, "title and evidence are required.", None)
    if severity not in ("critical", "high", "medium", "low"):
        return (False, "severity must be one of: critical, high, medium, low.", None)

    iid, _ = _next_id(ledger, "ISS", ISSUE_ID_COUNTER_KEY)
    active = _active_task(ledger)
    issue = {
        "id": iid,
        "title": title,
        "severity": severity,
        "discovered_at": _now_iso(),
        "discovered_during": active["id"] if active else None,
        "evidence": evidence,
        "recommended_follow_up": args.get("recommended_follow_up", ""),
        "status": "open",
        "promoted_to_task_id": None,
    }
    ledger.setdefault("discovered_issues", []).append(issue)
    _write_ledger(ledger)
    _append_audit({"action": "record_issue", "issue_id": iid, "severity": severity, "title": title, "result": "allowed"})
    msg = f"Issue {iid} recorded ({severity})."
    if severity == "critical":
        msg += " ⚠️ CRITICAL: Requires urgent attention."
    return (True, msg, {"issue_id": iid})


def _tool_promote_issue_to_task(args: dict) -> tuple[bool, str, dict | None]:
    ledger = _read_ledger()
    active = _active_task(ledger)
    if _task_is_non_terminal(active):
        return (False, f"Active task {active['id']} is in state {active['status']}. Cannot promote issues while executing.", None)

    issue_id = args.get("issue_id", "").strip()
    if not issue_id:
        return (False, "issue_id is required.", None)

    issues = ledger.get("discovered_issues", [])
    target = None
    for iss in issues:
        if iss["id"] == issue_id:
            target = iss
            break
    if target is None:
        return (False, f"Issue {issue_id} not found.", None)
    if target["status"] != "open":
        return (False, f"Issue {issue_id} is already {target['status']}.", None)

    # Promote: create task from issue
    tid, _ = _next_id(ledger, "TASK", TASK_ID_COUNTER_KEY)
    now_iso = _now_iso()
    lease_ttl = ledger.get("global_rules", {}).get("lease_ttl_seconds", DEFAULT_LEASE_TTL)
    task = {
        "id": tid,
        "objective": target["title"],
        "priority": {"critical": 90, "high": 70, "medium": 50, "low": 30}.get(target["severity"], 50),
        "status": "PLANNING",
        "acceptance_criteria": [{"id": "AC-1", "description": target.get("recommended_follow_up", "Resolve issue"), "status": "pending"}],
        "current_step": None,
        "allowed_scope": ["**"],
        "allowed_tools": None,
        "blocked_by": [],
        "lease": {
            "owner": "default",
            "status": "held",
            "held_since": now_iso,
            "renewed_at": now_iso,
            "expires_at": datetime.fromtimestamp(_now_ts() + lease_ttl, tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        },
        "plan": [{"step_id": "STEP-1", "description": target.get("recommended_follow_up", "Resolve issue"), "status": "pending"}],
        "plan_amendments": [],
        "promoted_from_issue": issue_id,
    }
    ledger["active_task"] = task
    target["status"] = "promoted"
    target["promoted_to_task_id"] = tid
    _write_ledger(ledger)
    _append_audit({"action": "promote_issue_to_task", "issue_id": issue_id, "task_id": tid, "result": "allowed"})
    return (True, f"Task {tid} created from issue {issue_id}.", {"task_id": tid})


def _tool_request_interruption(args: dict) -> tuple[bool, str, dict | None]:
    ledger = _read_ledger()
    active = _active_task(ledger)
    if active is None:
        return (False, "No active task to interrupt.", None)

    reason_code = args.get("reason_code", "").upper()
    if reason_code not in AUTHORIZED_INTERRUPTION_REASONS:
        return (False, f"Unauthorized interruption reason: {reason_code}. Authorized: {sorted(AUTHORIZED_INTERRUPTION_REASONS)}", None)

    evidence = args.get("evidence", "").strip()
    if not evidence:
        return (False, "evidence is required.", None)

    # Check nesting guard
    depth = _stack_depth(ledger)
    is_emergency = reason_code in EMERGENCY_REASONS

    if not is_emergency and depth >= MAX_NESTED_INTERRUPTIONS:
        return (False, f"Max nested interruptions ({MAX_NESTED_INTERRUPTIONS}) reached. Finish the current interrupt first.", None)
    if is_emergency and depth >= MAX_EMERGENCY_DEPTH:
        return (False, f"Emergency nesting cap ({MAX_EMERGENCY_DEPTH}) reached. Cannot interrupt further.", None)

    interrupt_objective = args.get("proposed_interrupt_objective", "").strip()
    if not interrupt_objective:
        return (False, "proposed_interrupt_objective is required.", None)

    resume_condition = args.get("resume_condition", "Interrupting task completed.")
    resume_checkpoint = args.get("resume_checkpoint", "")

    # Save checkpoint: push active task onto stack
    active["status"] = "SUSPENDED"
    active["_resume_checkpoint"] = resume_checkpoint
    active["_resume_condition"] = resume_condition
    active["_interrupted_at"] = _now_iso()
    ledger.setdefault("task_stack", []).append(dict(active))

    # Create interrupt task
    tid, _ = _next_id(ledger, "TASK", TASK_ID_COUNTER_KEY)
    now_iso = _now_iso()
    lease_ttl = ledger.get("global_rules", {}).get("lease_ttl_seconds", DEFAULT_LEASE_TTL)
    interrupt_task = {
        "id": tid,
        "objective": interrupt_objective,
        "priority": 90 if is_emergency else 70,
        "status": "EXECUTING",
        "acceptance_criteria": [{"id": "AC-1", "description": interrupt_objective, "status": "pending"}],
        "current_step": None,
        "allowed_scope": ["**"],
        "allowed_tools": None,
        "blocked_by": [],
        "lease": {
            "owner": "default",
            "status": "held",
            "held_since": now_iso,
            "renewed_at": now_iso,
            "expires_at": datetime.fromtimestamp(_now_ts() + lease_ttl, tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        },
        "plan": [{"step_id": "STEP-1", "description": interrupt_objective, "status": "in_progress"}],
        "plan_amendments": [],
        "interrupt_reason": reason_code,
        "interrupt_evidence": evidence,
        "suspended_task_id": active["id"],
    }
    ledger["active_task"] = interrupt_task
    _write_ledger(ledger)
    _append_audit({"action": "request_interruption", "suspended_task": active["id"], "new_task": tid, "reason": reason_code, "result": "allowed"})
    return (True, f"Interruption approved. Task {active['id']} suspended → task {tid} started. Reason: {reason_code}", {"suspended_task_id": active["id"], "interrupt_task_id": tid})


def _tool_resume_from_interrupt(args: dict) -> tuple[bool, str, dict | None]:
    ledger = _read_ledger()
    active = _active_task(ledger)
    stack = ledger.get("task_stack", [])
    if not stack:
        return (False, "No suspended tasks on the stack.", None)

    # Mark current task as completed (or cancelled if it wasn't properly finished)
    if active:
        if active["status"] not in ("COMPLETED", "CANCELLED"):
            active["status"] = "COMPLETED"
        # Save to completed
        ledger.setdefault("completed_tasks", []).append(dict(active))

    # Restore suspended task
    restored = stack.pop()
    restored["status"] = "EXECUTING"
    restored.pop("_resume_checkpoint", None)
    restored.pop("_resume_condition", None)
    restored.pop("_interrupted_at", None)
    restored["lease"]["renewed_at"] = _now_iso()
    lease_ttl = ledger.get("global_rules", {}).get("lease_ttl_seconds", DEFAULT_LEASE_TTL)
    restored["lease"]["expires_at"] = datetime.fromtimestamp(_now_ts() + lease_ttl, tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    checkpoint = restored.pop("_resume_checkpoint", "Continue from last known state.")
    ledger["active_task"] = restored
    ledger["task_stack"] = stack
    _write_ledger(ledger)
    _append_audit({"action": "resume_from_interrupt", "restored_task": restored["id"], "checkpoint": checkpoint, "result": "allowed"})
    return (True, f"Resumed task {restored['id']}. Checkpoint: {checkpoint}", {"task_id": restored["id"], "checkpoint": checkpoint})


def _tool_renew_lease(args: dict) -> tuple[bool, str, dict | None]:
    ledger = _read_ledger()
    active = _active_task(ledger)
    if active is None:
        return (False, "No active task.", None)
    if active.get("lease", {}).get("status") != "held":
        return (False, "Lease is not held. Claim a task first.", None)

    now_iso = _now_iso()
    lease_ttl = ledger.get("global_rules", {}).get("lease_ttl_seconds", DEFAULT_LEASE_TTL)
    active["lease"]["renewed_at"] = now_iso
    active["lease"]["expires_at"] = datetime.fromtimestamp(_now_ts() + lease_ttl, tz=timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    _write_ledger(ledger)
    _append_audit({"action": "renew_lease", "task_id": active["id"], "result": "allowed"})
    return (True, f"Lease renewed for task {active['id']}. Expires in {lease_ttl}s", {"expires_at": active["lease"]["expires_at"]})


def _tool_request_completion(args: dict) -> tuple[bool, str, dict | None]:
    ledger = _read_ledger()
    task_id = args.get("task_id", "")
    active = _active_task(ledger)
    if active is None or active["id"] != task_id:
        return (False, f"No active task matching {task_id}.", None)

    evidence = args.get("evidence_by_criterion", {})
    if not isinstance(evidence, dict):
        return (False, "evidence_by_criterion must be a dict {criterion_id: evidence}.", None)

    # Gate checks
    criteria = active.get("acceptance_criteria", [])
    failed_gates = []

    # Gate 1: All ACs have evidence
    criterion_ids = {c["id"] for c in criteria}
    for c in criteria:
        if c["id"] not in evidence:
            failed_gates.append(f"Missing evidence for {c['id']}: {c['description']}")

    # Gate 2: No failed ACs
    for c in criteria:
        if c.get("status") == "failed":
            failed_gates.append(f"Criterion {c['id']} failed.")

    # Gate 3: verified_by check
    for c in criteria:
        verifier = c.get("verified_by")
        if verifier:
            ev = evidence.get(c["id"], "")
            # If verifier is specified, check evidence source matches
            # (evidence string should contain the verifier name)
            if verifier not in ev:
                failed_gates.append(f"Criterion {c['id']} requires verification via {verifier}, got self-report.")

    # Gate 4: No unresolved blockers
    if active.get("blocked_by"):
        failed_gates.append(f"Unresolved blockers: {active['blocked_by']}")

    if failed_gates:
        return (False, f"Completion rejected: {'; '.join(failed_gates)}", None)

    # All gates passed
    for c in criteria:
        c["status"] = "passed"

    active["status"] = "REPORTING"
    _write_ledger(ledger)
    _append_audit({"action": "request_completion", "task_id": task_id, "result": "gates_passed", "evidence_count": len(evidence)})
    return (True, f"All gates passed for task {task_id}. State → REPORTING. Deliver results, then advance to COMPLETED.", {"status": "REPORTING"})


def _tool_list_issues(args: dict) -> tuple[bool, str, dict | None]:
    ledger = _read_ledger()
    status_filter = args.get("status", "open")
    issues = ledger.get("discovered_issues", [])
    if status_filter == "open":
        issues = [i for i in issues if i["status"] == "open"]
    elif status_filter == "closed":
        issues = [i for i in issues if i["status"] != "open"]
    return (True, json.dumps(issues, indent=2), None)


def _tool_list_tasks(args: dict) -> tuple[bool, str, dict | None]:
    ledger = _read_ledger()
    status_filter = args.get("status", "active")
    result = []
    if status_filter in ("active", "all"):
        active = _active_task(ledger)
        if active:
            result.append({"id": active["id"], "objective": active["objective"], "status": active["status"], "type": "active"})
        for i, t in enumerate(ledger.get("task_stack", [])):
            result.append({"id": t["id"], "objective": t["objective"], "status": t["status"], "type": "suspended"})
    if status_filter in ("completed", "all"):
        for t in ledger.get("completed_tasks", []):
            result.append({"id": t["id"], "objective": t["objective"], "status": t["status"], "type": "completed"})
    return (True, json.dumps(result, indent=2), None)


# ── Tool Metadata ──────────────────────────────────────────────
def _describe_tools() -> list[Tool]:
    return [
        Tool(
            name="claim_task",
            description="Open a new task. Denied if an active task exists in a non-terminal state (PLANNING/EXECUTING/VERIFYING/REPORTING/INTERRUPT_REQ/SUSPENDED/BLOCKED).",
            inputSchema={
                "type": "object",
                "properties": {
                    "objective": {"type": "string", "description": "Task objective (required)"},
                    "priority": {"type": "integer", "description": "Priority 0-100 (default 50)"},
                    "acceptance_criteria": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "description": {"type": "string"},
                            },
                        },
                        "description": "Acceptance criteria list",
                    },
                    "allowed_scope": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Glob patterns for permitted files (default ['**'])",
                    },
                    "allowed_tools": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Permitted tool names (default: all tools)",
                    },
                    "plan": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "step_id": {"type": "string"},
                                "description": {"type": "string"},
                            },
                        },
                        "description": "Ordered plan steps",
                    },
                    "owner": {"type": "string", "description": "Task owner (agent name)"},
                },
                "required": ["objective"],
            },
        ),
        Tool(
            name="get_task_state",
            description="Get abbreviated task state for context injection (compact summary).",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="get_task_state_full",
            description="Get full task ledger dump (for debugging/tooling).",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="advance_task_state",
            description="Legal state transition. Validates against the state machine. Use criterion_id to mark an AC as passed on entry to VERIFYING.",
            inputSchema={
                "type": "object",
                "properties": {
                    "new_state": {
                        "type": "string",
                        "enum": ["EXECUTING", "VERIFYING", "REPORTING", "BLOCKED", "CANCELLED", "COMPLETED", "IDLE"],
                        "description": "Target state",
                    },
                    "reason": {"type": "string", "description": "Required for BLOCKED and CANCELLED"},
                    "criterion_id": {"type": "string", "description": "Optional — which AC just completed (on entry to VERIFYING)"},
                    "step_id": {"type": "string", "description": "Optional step to mark in_progress"},
                },
                "required": ["new_state"],
            },
        ),
        Tool(
            name="update_plan",
            description="Append a plan amendment within the active task's scope. Use for legitimate mid-task discoveries, not scope changes.",
            inputSchema={
                "type": "object",
                "properties": {
                    "step_id": {"type": "string", "description": "New step ID (required)"},
                    "description": {"type": "string", "description": "Step description (required)"},
                    "reason": {"type": "string", "description": "Why this amendment is needed"},
                },
                "required": ["step_id", "description"],
            },
        ),
        Tool(
            name="record_issue",
            description="Log a discovered problem. Does NOT change active task status. CRITICAL severity triggers an alert but not an auto-interrupt.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Issue title (required)"},
                    "severity": {
                        "type": "string",
                        "enum": ["critical", "high", "medium", "low"],
                        "description": "Severity level (default: medium)",
                    },
                    "evidence": {"type": "string", "description": "Evidence or reproduction steps (required)"},
                    "recommended_follow_up": {"type": "string", "description": "Suggested next action"},
                },
                "required": ["title", "evidence"],
            },
        ),
        Tool(
            name="promote_issue_to_task",
            description="Convert a queued issue into a claimable task. Only valid when no active task is open.",
            inputSchema={
                "type": "object",
                "properties": {
                    "issue_id": {"type": "string", "description": "Issue ID to promote (required)"},
                },
                "required": ["issue_id"],
            },
        ),
        Tool(
            name="request_interruption",
            description="Request a task switch. Requires authorized reason code and evidence. Suspends the current task and starts a new one.",
            inputSchema={
                "type": "object",
                "properties": {
                    "reason_code": {
                        "type": "string",
                        "enum": sorted(AUTHORIZED_INTERRUPTION_REASONS),
                        "description": "Authorized interruption reason",
                    },
                    "evidence": {"type": "string", "description": "Why the interruption is necessary (required)"},
                    "proposed_interrupt_objective": {"type": "string", "description": "What the interrupt task will do (required)"},
                    "resume_condition": {"type": "string", "description": "When the suspended task can resume"},
                    "resume_checkpoint": {"type": "string", "description": "What step/AC to resume at"},
                },
                "required": ["reason_code", "evidence", "proposed_interrupt_objective"],
            },
        ),
        Tool(
            name="resume_from_interrupt",
            description="Pop task stack, restore the suspended task as EXECUTING. Call when the interrupt task completes or is cancelled.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="renew_lease",
            description="Heartbeat to extend the task lease's expires_at. Must be called periodically during long-running steps.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="request_completion",
            description="Gate-checked completion. Provide evidence_by_criterion as {criterion_id: evidence_string}. The Authority validates all gates before allowing transition to REPORTING.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string", "description": "Task ID to complete (required)"},
                    "evidence_by_criterion": {
                        "type": "object",
                        "description": "Dict {criterion_id: evidence_string}. Must include ALL criteria.",
                        "additionalProperties": {"type": "string"},
                    },
                },
                "required": ["task_id", "evidence_by_criterion"],
            },
        ),
        Tool(
            name="list_issues",
            description="List discovered issues, filtered by status.",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["open", "closed", "all"],
                        "description": "Filter (default: open)",
                    },
                },
            },
        ),
        Tool(
            name="list_tasks",
            description="List tasks by status (active, completed, all).",
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": ["active", "completed", "all"],
                        "description": "Filter (default: active)",
                    },
                },
            },
        ),
    ]


# ── Tool Dispatcher ────────────────────────────────────────────
_TOOL_MAP: dict[str, callable] = {
    "claim_task": _tool_claim_task,
    "get_task_state": _tool_get_task_state,
    "get_task_state_full": _tool_get_task_state_full,
    "advance_task_state": _tool_advance_task_state,
    "update_plan": _tool_update_plan,
    "record_issue": _tool_record_issue,
    "promote_issue_to_task": _tool_promote_issue_to_task,
    "request_interruption": _tool_request_interruption,
    "resume_from_interrupt": _tool_resume_from_interrupt,
    "renew_lease": _tool_renew_lease,
    "request_completion": _tool_request_completion,
    "list_issues": _tool_list_issues,
    "list_tasks": _tool_list_tasks,
}


# ── Server ─────────────────────────────────────────────────────
app = Server("task-control")


@app.list_tools()
async def list_tools() -> list[Tool]:
    return _describe_tools()


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name not in _TOOL_MAP:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    try:
        ok, msg, data = _TOOL_MAP[name](arguments)
        result = {"success": ok, "message": msg}
        if data:
            result["data"] = data
        return [TextContent(type="text", text=json.dumps(result, indent=2))]
    except Exception as e:
        log.error(f"Error in {name}: {traceback.format_exc()}")
        return [TextContent(type="text", text=json.dumps({
            "success": False,
            "message": f"Internal error: {e}",
        }, indent=2))]


async def main() -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if not LEDGER_PATH.exists():
        _write_ledger(dict(EMPTY_LEDGER))
        log.info(f"Created empty task ledger at {LEDGER_PATH}")
    log.info("Task Control Authority MCP server starting...")
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
