-- ─────────────────────────────────────────────────────────────
-- Hermes Cortex Agent Bus — Workflow + A2A Schema
--
-- Durable workflow engine for deterministic agent orchestration.
-- A2A (Agent-to-Agent) task management.
--
-- Tables:
--   bus.agent_workflows         — workflow instances
--   bus.agent_workflow_steps    — individual steps within a workflow
--   bus.agent_workflow_audit    — workflow event audit trail
--   bus.a2a_tasks               — agent-to-agent task entries
-- ─────────────────────────────────────────────────────────────

-- ── Workflows ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS bus.agent_workflows (
    id                  UUID PRIMARY KEY,
    name                TEXT NOT NULL,
    workflow_definition JSONB NOT NULL,
    payload             JSONB DEFAULT '{}',
    priority            INT DEFAULT 0,
    state               TEXT NOT NULL DEFAULT 'pending',
        CHECK (state IN ('pending', 'running', 'blocked', 'completed', 'failed', 'timed_out', 'canceled')),
    owner_agent         TEXT NOT NULL DEFAULT 'moses',
    correlation_id      TEXT,
    deadline_at         TIMESTAMPTZ,
    completed_at        TIMESTAMPTZ,
    error               TEXT,
    result              JSONB,
    created_at          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_workflows_state
    ON bus.agent_workflows (state);

CREATE INDEX IF NOT EXISTS idx_workflows_priority
    ON bus.agent_workflows (priority DESC, created_at ASC);

-- ── Workflow Steps ──────────────────────────────────────────

CREATE TABLE IF NOT EXISTS bus.agent_workflow_steps (
    id                  UUID PRIMARY KEY,
    workflow_id         UUID NOT NULL REFERENCES bus.agent_workflows(id) ON DELETE CASCADE,
    step_name           TEXT NOT NULL,
    step_order          INT NOT NULL,
    assigned_to         TEXT NOT NULL,
    state               TEXT NOT NULL DEFAULT 'pending',
        CHECK (state IN ('pending', 'running', 'completed', 'failed', 'timed_out', 'skipped')),
    timeout_seconds     INT DEFAULT 300,
    max_retries         INT DEFAULT 2,
    retry_count         INT DEFAULT 0,
    depends_on          UUID[],
    route_if            JSONB DEFAULT '{}',
    human_review        BOOLEAN DEFAULT false,
    human_decision      TEXT,
        CHECK (human_decision IS NULL OR human_decision IN ('approved', 'rejected', 'request_changes')),
    completed_at        TIMESTAMPTZ,
    error               TEXT,
    result              JSONB,
    created_at          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_steps_workflow
    ON bus.agent_workflow_steps (workflow_id, step_order);

CREATE INDEX IF NOT EXISTS idx_steps_assigned
    ON bus.agent_workflow_steps (assigned_to, state);

-- ── Workflow Audit ──────────────────────────────────────────

CREATE TABLE IF NOT EXISTS bus.agent_workflow_audit (
    id              BIGSERIAL PRIMARY KEY,
    workflow_id     UUID REFERENCES bus.agent_workflows(id) ON DELETE CASCADE,
    step_id         UUID REFERENCES bus.agent_workflow_steps(id) ON DELETE SET NULL,
    event           TEXT NOT NULL,
    actor           TEXT DEFAULT 'system',
    detail          JSONB DEFAULT '{}',
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_workflow
    ON bus.agent_workflow_audit (workflow_id, created_at DESC);

-- ── A2A Tasks ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS bus.a2a_tasks (
    id              UUID PRIMARY KEY,
    requester       TEXT NOT NULL,
    target_agent    TEXT NOT NULL,
    description     TEXT NOT NULL,
    priority        TEXT NOT NULL DEFAULT 'normal',
        CHECK (priority IN ('normal', 'urgent', 'critical')),
    state           TEXT NOT NULL DEFAULT 'pending',
        CHECK (state IN ('pending', 'running', 'completed', 'failed', 'canceled', 'rejected')),
    completed_at    TIMESTAMPTZ,
    result          TEXT,
    error           TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_a2a_tasks_agent
    ON bus.a2a_tasks (target_agent, state);

CREATE INDEX IF NOT EXISTS idx_a2a_tasks_priority
    ON bus.a2a_tasks (target_agent, priority DESC, created_at DESC);
