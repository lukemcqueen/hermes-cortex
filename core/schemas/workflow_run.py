"""
WorkflowRun — Canonical durable workflow state machine.

Defines the core entities for multi-step, resumable, auditable workflow
execution.  Every multi-step action should have one durable run ID and
state machine.

See: docs/research/enterprise-grade-hermes-cortex.md § "durable workflow runtime"
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


# ── State machine ───────────────────────────────────────────────────────────


class WorkflowStatus(str, Enum):
    """Lifecycle states for a workflow run, in order."""

    PENDING = "pending"               # Created but not yet started
    RUNNING = "running"               # Actively executing
    PAUSED = "paused"                 # Waiting for human input / external event
    APPROVAL_REQUIRED = "approval_required"  # Blocked on human approval
    RETRYING = "retrying"             # Step failed, automatic retry in progress
    COMPLETED = "completed"           # All steps succeeded
    FAILED = "failed"                 # Unrecoverable error
    CANCELLED = "cancelled"           # Aborted by operator
    ROLLING_BACK = "rolling_back"     # Undoing completed steps
    ROLLED_BACK = "rolled_back"       # All steps undone


VALID_TRANSITIONS: dict[WorkflowStatus, set[WorkflowStatus]] = {
    WorkflowStatus.PENDING: {WorkflowStatus.RUNNING, WorkflowStatus.CANCELLED},
    WorkflowStatus.RUNNING: {WorkflowStatus.PAUSED, WorkflowStatus.COMPLETED,
                              WorkflowStatus.FAILED, WorkflowStatus.CANCELLED,
                              WorkflowStatus.APPROVAL_REQUIRED, WorkflowStatus.RETRYING},
    WorkflowStatus.PAUSED: {WorkflowStatus.RUNNING, WorkflowStatus.CANCELLED},
    WorkflowStatus.APPROVAL_REQUIRED: {WorkflowStatus.RUNNING, WorkflowStatus.CANCELLED},
    WorkflowStatus.RETRYING: {WorkflowStatus.RUNNING, WorkflowStatus.FAILED},
    WorkflowStatus.COMPLETED: set(),
    WorkflowStatus.FAILED: {WorkflowStatus.ROLLING_BACK, WorkflowStatus.RETRYING},
    WorkflowStatus.CANCELLED: set(),
    WorkflowStatus.ROLLING_BACK: {WorkflowStatus.ROLLED_BACK, WorkflowStatus.FAILED},
    WorkflowStatus.ROLLED_BACK: set(),
}


class StepStatus(str, Enum):
    """Status of an individual step within a workflow run."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    APPROVAL_REQUIRED = "approval_required"
    ROLLED_BACK = "rolled_back"


# ── Core entities ───────────────────────────────────────────────────────────


@dataclass
class WorkflowDefinition:
    """A reusable workflow template — defines the steps and metadata.

    ``id`` is a stable content-addressed identifier (SHA-256 of name + version).
    """

    id: str = ""
    name: str = ""
    version: str = "1.0.0"
    description: str = ""
    steps: list[StepDefinition] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    owner: str = ""
    created_at: str = ""

    def __post_init__(self):
        if not self.id:
            raw = f"{self.name}:{self.version}"
            self.id = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
        if not self.created_at:
            self.created_at = _now()


@dataclass
class StepDefinition:
    """One step in a workflow definition."""

    name: str = ""
    description: str = ""
    action: str = ""                   # What to do: "llm:call", "tool:execute", "human:approve", "script:run"
    timeout_seconds: int = 300
    retry_count: int = 3
    retry_delay_seconds: int = 10
    depends_on: list[str] = field(default_factory=list)  # Step names that must complete first
    required_approval: bool = False
    required_role: str = ""            # Agent role needed to approve
    rollback_action: str = ""          # What to do on rollback


@dataclass
class StepRun:
    """Executable state of one step within a workflow run."""

    step_name: str = ""
    status: StepStatus = StepStatus.PENDING
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    attempt: int = 0
    result: Optional[str] = None       # JSON-serializable result payload
    error: Optional[str] = None        # Error message if failed
    approval_by: Optional[str] = None  # Agent/user who approved
    output: dict[str, Any] = field(default_factory=dict)


@dataclass
class Checkpoint:
    """Snapshot of workflow state at a point in time."""

    id: str = ""
    run_id: str = ""
    timestamp: str = ""
    status: str = ""
    completed_steps: list[str] = field(default_factory=list)
    current_step: str = ""
    retry_count: int = 0
    data: dict[str, Any] = field(default_factory=dict)  # Arbitrary state snapshot

    def __post_init__(self):
        if not self.id:
            self.id = hashlib.md5(f"{self.run_id}:{self.timestamp}".encode()).hexdigest()[:12]
        if not self.timestamp:
            self.timestamp = _now()


@dataclass
class WorkflowRun:
    # ── Identity ──────────────────────────────────────────────────────────
    id: str = ""                       # Durable run ID — every multi-step action has one
    definition_id: str = ""            # Which WorkflowDefinition this instantiates
    name: str = ""                     # Human-readable, e.g. "invoice-4832"

    # ── State machine ─────────────────────────────────────────────────────
    status: WorkflowStatus = WorkflowStatus.PENDING
    current_step: str = ""             # Name of the step currently executing
    completed_steps: list[str] = field(default_factory=list)
    failed_steps: list[str] = field(default_factory=list)
    retry_count: int = 0
    state_version: int = 0             # Incremented on every state change

    # ── Actors & ownership ────────────────────────────────────────────────
    initiated_by: str = ""             # Agent or user who started this
    owner: str = ""                    # Currently responsible agent/user

    # ── Timeline ──────────────────────────────────────────────────────────
    created_at: str = ""
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    last_checkpoint_at: Optional[str] = None

    # ── Steps ─────────────────────────────────────────────────────────────
    steps: list[StepRun] = field(default_factory=list)

    # ── Audit / traceability ───────────────────────────────────────────────
    checkpoints: list[Checkpoint] = field(default_factory=list)
    events: list[WorkflowEvent] = field(default_factory=list)
    tags: dict[str, str] = field(default_factory=dict)

    # ── Error handling ─────────────────────────────────────────────────────
    error: Optional[str] = None        # Current error message if failed
    max_retries: int = 5

    def __post_init__(self):
        if not self.id:
            self.id = _generate_run_id()
        if not self.created_at:
            self.created_at = _now()

    # ── State transitions ─────────────────────────────────────────────────

    def transition_to(self, new_status: WorkflowStatus) -> None:
        """Move the state machine to ``new_status``.  Raises ValueError on illegal move."""
        allowed = VALID_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Illegal transition: {self.status.value} → {new_status.value}. "
                f"Allowed: {[s.value for s in allowed]}"
            )
        old = self.status
        self.status = new_status
        self.state_version += 1
        self._log_event("status_change", {"from": old.value, "to": new_status.value})

    def start(self) -> None:
        """Start execution: PENDING → RUNNING."""
        self.transition_to(WorkflowStatus.RUNNING)
        self.started_at = _now()
        if self.steps:
            self.current_step = self.steps[0].step_name
            self.steps[0].status = StepStatus.RUNNING
            self.steps[0].started_at = _now()

    def complete(self) -> None:
        """Mark as complete: → COMPLETED."""
        self.transition_to(WorkflowStatus.COMPLETED)
        self.completed_at = _now()

    def fail(self, error: str) -> None:
        """Mark as failed: → FAILED."""
        self.error = error
        self.transition_to(WorkflowStatus.FAILED)

    def cancel(self) -> None:
        """Cancel execution: → CANCELLED."""
        self.completed_at = _now()
        self.transition_to(WorkflowStatus.CANCELLED)

    def require_approval(self, step_name: str) -> None:
        """Pause for human approval."""
        self.current_step = step_name
        self.transition_to(WorkflowStatus.APPROVAL_REQUIRED)
        self._log_event("approval_required", {"step": step_name})

    def checkpoint(self) -> Checkpoint:
        """Create a state snapshot for resume/audit."""
        cp = Checkpoint(
            run_id=self.id,
            timestamp=_now(),
            status=self.status.value,
            completed_steps=list(self.completed_steps),
            current_step=self.current_step,
            retry_count=self.retry_count,
            data={"state_version": self.state_version, "error": self.error},
        )
        self.checkpoints.append(cp)
        self.last_checkpoint_at = cp.timestamp
        return cp

    # ── Step management ───────────────────────────────────────────────────

    def complete_step(self, step_name: str, result: Optional[str] = None) -> None:
        """Mark a step as completed and advance to the next pending step."""
        for step in self.steps:
            if step.step_name == step_name:
                step.status = StepStatus.COMPLETED
                step.completed_at = _now()
                step.result = result
                self.completed_steps.append(step_name)
                break
        # Advance to next pending step
        for step in self.steps:
            if step.status == StepStatus.PENDING:
                step.status = StepStatus.RUNNING
                step.started_at = _now()
                self.current_step = step.step_name
                return
        # No more steps → complete the run
        self.complete()

    def fail_step(self, step_name: str, error: str) -> None:
        """Mark a step as failed.  Auto-retry if attempts remain."""
        for step in self.steps:
            if step.step_name == step_name:
                step.status = StepStatus.FAILED
                step.error = error
                step.attempt += 1
                self.failed_steps.append(step_name)
                if step.attempt < self.max_retries:
                    self.retry_count += 1
                    self.transition_to(WorkflowStatus.RETRYING)
                    step.status = StepStatus.PENDING  # Reset for retry
                else:
                    self.fail(error)
                break

    # ── Internal ──────────────────────────────────────────────────────────

    def _log_event(self, event_type: str, data: dict[str, Any]) -> None:
        self.events.append(WorkflowEvent(
            run_id=self.id,
            event_type=event_type,
            data=data,
            timestamp=_now(),
            state_version=self.state_version,
        ))


@dataclass
class WorkflowEvent:
    """An auditable event in a workflow run's timeline."""

    run_id: str = ""
    event_type: str = ""               # "status_change", "step_complete", "step_fail", "checkpoint", "approval"
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    state_version: int = 0

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = _now()


# ── Helpers ─────────────────────────────────────────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_run_id() -> str:
    """Generate a short, unique, human-friendly run ID."""
    import uuid
    return uuid.uuid4().hex[:12]


def create_workflow(
    definition: WorkflowDefinition,
    initiated_by: str = "",
    name: str = "",
    tags: Optional[dict[str, str]] = None,
) -> WorkflowRun:
    """Instantiate a WorkflowDefinition into a run with all steps initialized."""
    run = WorkflowRun(
        definition_id=definition.id,
        name=name or f"{definition.name}-{_now()[:10]}",
        initiated_by=initiated_by,
        steps=[StepRun(step_name=s.name, attempt=0) for s in definition.steps],
        tags=tags or {},
    )
    if run.steps:
        run.current_step = run.steps[0].step_name
    run._log_event("workflow_created", {
        "definition_id": definition.id,
        "definition_name": definition.name,
        "version": definition.version,
    })
    return run


def describe_run(run: WorkflowRun) -> str:
    """Return a human-readable one-line summary of a workflow run (as in the doc example)."""
    parts = [
        f"Workflow ID: {run.id}",
        f"Current node: {run.current_step or '—'}",
        f"Completed nodes: {', '.join(run.completed_steps) or '—'}",
        f"Pending node: {run.current_step if run.status in (WorkflowStatus.PENDING, WorkflowStatus.RUNNING, WorkflowStatus.APPROVAL_REQUIRED) else '—'}",
        f"Retry count: {run.retry_count}",
        f"State version: {run.state_version}",
        f"Checkpoint: {run.last_checkpoint_at or run.created_at}",
    ]
    return "\n".join(parts)
