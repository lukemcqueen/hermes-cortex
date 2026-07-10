"""Tests for core/schemas/workflow_run.py"""

from core.schemas.workflow_run import (
    VALID_TRANSITIONS,
    Checkpoint,
    StepDefinition,
    StepRun,
    StepStatus,
    WorkflowDefinition,
    WorkflowEvent,
    WorkflowRun,
    WorkflowStatus,
    create_workflow,
    describe_run,
)


class TestWorkflowStatus:
    def test_pending_to_running(self):
        assert WorkflowStatus.RUNNING in VALID_TRANSITIONS[WorkflowStatus.PENDING]

    def test_running_to_completed(self):
        assert WorkflowStatus.COMPLETED in VALID_TRANSITIONS[WorkflowStatus.RUNNING]

    def test_running_to_approval_required(self):
        assert WorkflowStatus.APPROVAL_REQUIRED in VALID_TRANSITIONS[WorkflowStatus.RUNNING]

    def test_approval_required_to_running(self):
        assert WorkflowStatus.RUNNING in VALID_TRANSITIONS[WorkflowStatus.APPROVAL_REQUIRED]

    def test_completed_has_no_transitions(self):
        assert VALID_TRANSITIONS[WorkflowStatus.COMPLETED] == set()

    def test_cancelled_has_no_transitions(self):
        assert VALID_TRANSITIONS[WorkflowStatus.CANCELLED] == set()

    def test_failed_to_retrying(self):
        assert WorkflowStatus.RETRYING in VALID_TRANSITIONS[WorkflowStatus.FAILED]

    def test_failed_to_rolling_back(self):
        assert WorkflowStatus.ROLLING_BACK in VALID_TRANSITIONS[WorkflowStatus.FAILED]


class TestWorkflowRunTransitions:
    def test_valid_transition(self):
        run = WorkflowRun()
        assert run.status == WorkflowStatus.PENDING
        run.start()
        assert run.status == WorkflowStatus.RUNNING

    def test_illegal_transition_raises(self):
        run = WorkflowRun()
        run.start()
        run.complete()
        # COMPLETED → RUNNING is illegal
        import pytest
        with pytest.raises(ValueError, match="Illegal transition"):
            run.start()

    def test_cancel_from_pending(self):
        run = WorkflowRun()
        run.cancel()
        assert run.status == WorkflowStatus.CANCELLED

    def test_cancel_from_running(self):
        run = WorkflowRun()
        run.start()
        run.cancel()
        assert run.status == WorkflowStatus.CANCELLED

    def test_fail_sets_error(self):
        run = WorkflowRun()
        run.start()
        run.fail("Something broke")
        assert run.status == WorkflowStatus.FAILED
        assert run.error == "Something broke"

    def test_state_version_increments(self):
        run = WorkflowRun()
        v0 = run.state_version
        run.start()
        assert run.state_version == v0 + 1
        run.complete()
        assert run.state_version == v0 + 2


class TestWorkflowLifecycle:
    def test_full_lifecycle(self):
        """PENDING → RUNNING → step1 → step2 → COMPLETED."""
        run = WorkflowRun()
        run.steps = [StepRun(step_name="ingest"), StepRun(step_name="validate")]
        run.start()
        assert run.status == WorkflowStatus.RUNNING
        assert run.current_step == "ingest"

        run.complete_step("ingest")
        assert "ingest" in run.completed_steps
        assert run.current_step == "validate"

        run.complete_step("validate")
        assert run.status == WorkflowStatus.COMPLETED
        assert run.started_at is not None
        assert run.completed_at is not None

    def test_complete_last_step_auto_completes_run(self):
        run = WorkflowRun()
        run.steps = [StepRun(step_name="only-step")]
        run.start()
        run.complete_step("only-step")
        assert run.status == WorkflowStatus.COMPLETED

    def test_checkpoint_creation(self):
        run = WorkflowRun()
        cp = run.checkpoint()
        assert isinstance(cp, Checkpoint)
        assert cp.run_id == run.id
        assert cp.status == "pending"
        assert run.last_checkpoint_at is not None

    def test_checkpoint_stores_state(self):
        run = WorkflowRun()
        run.steps = [StepRun(step_name="step_a"), StepRun(step_name="step_b")]
        run.start()
        run.complete_step("step_a")
        cp = run.checkpoint()
        assert "step_a" in cp.completed_steps
        assert cp.current_step == "step_b"

    def test_events_logged(self):
        run = WorkflowRun()
        run.start()
        assert len(run.events) >= 1
        assert run.events[0].event_type == "status_change"


class TestApprovalFlow:
    def test_require_approval_pauses_execution(self):
        run = WorkflowRun()
        run.start()
        run.require_approval("finance_review")
        assert run.status == WorkflowStatus.APPROVAL_REQUIRED
        assert run.current_step == "finance_review"

    def test_resume_after_approval(self):
        run = WorkflowRun()
        run.start()
        run.require_approval("finance_review")
        run.transition_to(WorkflowStatus.RUNNING)
        assert run.status == WorkflowStatus.RUNNING

    def test_approval_event_logged(self):
        run = WorkflowRun()
        run.start()
        run.require_approval("finance_review")
        approvals = [e for e in run.events if "approval" in e.event_type]
        assert len(approvals) >= 1


class TestStepFailureAndRetry:
    def test_step_failure_with_retry(self):
        """Failing step with attempts remaining resets to RETRYING."""
        run = WorkflowRun()
        run.steps = [StepRun(step_name="fetch_data", attempt=0)]
        run.start()
        run.fail_step("fetch_data", "Connection timeout")
        assert run.status == WorkflowStatus.RETRYING
        assert run.retry_count == 1

    def test_step_failure_max_retries(self):
        """Failing after max retries sets workflow to FAILED."""
        run = WorkflowRun()
        run.max_retries = 2
        run.steps = [StepRun(step_name="fetch_data", attempt=0)]
        run.start()
        run.fail_step("fetch_data", "fail 1")
        # First retry: RETRYING → RUNNING
        run.start()
        run.fail_step("fetch_data", "fail 2")
        # Max retries exhausted
        assert run.status == WorkflowStatus.FAILED
        assert run.error is not None

    def test_step_failure_records_error(self):
        run = WorkflowRun()
        run.steps = [StepRun(step_name="fetch")]
        run.start()
        run.fail_step("fetch", "Timeout error")
        assert run.steps[0].error == "Timeout error"
        assert "fetch" in run.failed_steps


class TestDescribeRun:
    def test_format_matches_doc_example(self):
        """The output should look like the example in the doc."""
        run = WorkflowRun(id="invoice-4832", name="invoice-4832")
        run.steps = [
            StepRun(step_name="ingest"),
            StepRun(step_name="validate"),
            StepRun(step_name="finance_review"),
            StepRun(step_name="legal_approval"),
        ]
        run.start()
        run.complete_step("ingest")
        run.complete_step("validate")
        run.complete_step("finance_review")
        run.require_approval("legal_approval")

        desc = describe_run(run)
        assert "Workflow ID: invoice-4832" in desc
        assert "Current node: legal_approval" in desc
        assert "ingest" in desc
        assert "validate" in desc
        assert "finance_review" in desc
        assert "State version:" in desc

    def test_empty_run(self):
        run = WorkflowRun()
        desc = describe_run(run)
        assert "Workflow ID:" in desc
        assert "Retry count: 0" in desc


class TestCreateWorkflow:
    def test_creates_run_from_definition(self):
        definition = WorkflowDefinition(
            name="deploy-service",
            version="1.0.0",
            steps=[
                StepDefinition(name="build", action="tool:execute"),
                StepDefinition(name="test", action="tool:execute"),
                StepDefinition(name="deploy", action="tool:execute"),
            ],
        )
        run = create_workflow(definition, initiated_by="titus")
        assert run.definition_id == definition.id
        assert run.initiated_by == "titus"
        assert len(run.steps) == 3
        assert run.steps[0].step_name == "build"
        assert run.current_step == "build"

    def test_created_event_logged(self):
        definition = WorkflowDefinition(name="simple", steps=[StepDefinition(name="do")])
        run = create_workflow(definition)
        events = [e for e in run.events if e.event_type == "workflow_created"]
        assert len(events) == 1


class TestDefaults:
    def test_workflow_run_defaults(self):
        run = WorkflowRun()
        assert run.id != ""
        assert run.status == WorkflowStatus.PENDING
        assert run.steps == []
        assert run.state_version == 0
        assert run.checkpoints == []
        assert run.events == []
        assert run.created_at != ""

    def test_step_definition_defaults(self):
        step = StepDefinition(name="test")
        assert step.timeout_seconds == 300
        assert step.retry_count == 3
        assert step.required_approval is False

    def test_step_run_defaults(self):
        step = StepRun(step_name="ingest")
        assert step.status == StepStatus.PENDING
        assert step.attempt == 0

    def test_checkpoint_defaults(self):
        cp = Checkpoint(run_id="test-run")
        assert cp.id != ""
        assert cp.timestamp != ""
        assert cp.status == ""

    def test_workflow_definition_defaults(self):
        d = WorkflowDefinition(name="test")
        assert d.version == "1.0.0"
        assert d.steps == []


class TestWorkflowEvent:
    def test_event_created_with_timestamp(self):
        event = WorkflowEvent(run_id="r1", event_type="test")
        assert event.timestamp != ""
