-- ── Workflow Engine Schema (Phase II) ──
-- Adds workflow execution tables to the `bus` schema alongside the queue tables.
-- All tables use the bus Postgres user (no gbrain schema access).

-- ── Workflows ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bus.agent_workflows (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                 TEXT NOT NULL,
    version              TEXT NOT NULL DEFAULT '1.0.0',
    workflow_definition  JSONB,            -- YAML snapshot at dispatch time!
    state                TEXT NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending','running','blocked','completed','failed','timed_out','canceled')),
    priority             INT DEFAULT 0,
    payload              JSONB,
    result               JSONB,
    error                TEXT,
    created_at           TIMESTAMPTZ DEFAULT now(),
    started_at           TIMESTAMPTZ,
    completed_at         TIMESTAMPTZ,
    deadline_at          TIMESTAMPTZ,
    owner_agent          TEXT,
    correlation_id       TEXT
);

-- ── Workflow Steps ──────────────────────────────────────
CREATE TABLE IF NOT EXISTS bus.agent_workflow_steps (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id      UUID NOT NULL REFERENCES bus.agent_workflows(id) ON DELETE CASCADE,
    step_name        TEXT NOT NULL,
    step_order       INT NOT NULL,
    state            TEXT NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending','running','completed','failed','skipped','timed_out')),
    assigned_to      TEXT,
    result           JSONB,
    error            TEXT,
    started_at       TIMESTAMPTZ,
    completed_at     TIMESTAMPTZ,
    timeout_seconds  INT NOT NULL DEFAULT 300,
    retry_count      INT NOT NULL DEFAULT 0,
    max_retries      INT NOT NULL DEFAULT 2,
    depends_on       UUID[] DEFAULT '{}',
    route_if         JSONB               -- SNAPSHOT from YAML at dispatch
);

-- ── Append-only Audit ──────────────────────────────────
CREATE TABLE IF NOT EXISTS bus.agent_workflow_audit (
    id           BIGSERIAL PRIMARY KEY,
    workflow_id  UUID NOT NULL REFERENCES bus.agent_workflows(id),
    step_id      UUID REFERENCES bus.agent_workflow_steps(id),
    event        TEXT NOT NULL,
    actor        TEXT NOT NULL,
    detail       JSONB,
    created_at   TIMESTAMPTZ DEFAULT now()
);

-- Audit trigger: prevent UPDATE/DELETE on audit log
CREATE OR REPLACE FUNCTION bus.reject_audit_mod() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'bus.agent_workflow_audit is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_audit_no_mod ON bus.agent_workflow_audit;
CREATE TRIGGER trg_audit_no_mod
    BEFORE UPDATE OR DELETE ON bus.agent_workflow_audit
    FOR EACH ROW EXECUTE FUNCTION bus.reject_audit_mod();

-- ── A2A Tasks ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bus.a2a_tasks (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    requester       TEXT NOT NULL,
    target_agent    TEXT NOT NULL,
    description     TEXT NOT NULL,
    priority        TEXT DEFAULT 'normal'
        CHECK (priority IN ('critical','urgent','normal')),
    state           TEXT DEFAULT 'submitted'
        CHECK (state IN ('submitted','working','completed','failed','canceled','rejected')),
    result          TEXT,
    error           TEXT,
    created_at      TIMESTAMPTZ DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ
);

-- ── Indexes for query performance ──────────────────────
CREATE INDEX IF NOT EXISTS idx_workflows_state       ON bus.agent_workflows(state);
CREATE INDEX IF NOT EXISTS idx_workflows_deadline    ON bus.agent_workflows(deadline_at) WHERE state IN ('running','blocked');
CREATE INDEX IF NOT EXISTS idx_steps_workflow        ON bus.agent_workflow_steps(workflow_id);
CREATE INDEX IF NOT EXISTS idx_steps_state           ON bus.agent_workflow_steps(state);
CREATE INDEX IF NOT EXISTS idx_steps_assigned        ON bus.agent_workflow_steps(assigned_to);
CREATE INDEX IF NOT EXISTS idx_audit_workflow        ON bus.agent_workflow_audit(workflow_id);
CREATE INDEX IF NOT EXISTS idx_a2a_target            ON bus.a2a_tasks(target_agent, state);
