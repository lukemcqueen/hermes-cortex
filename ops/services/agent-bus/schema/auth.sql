-- ─────────────────────────────────────────────────────────────
-- Hermes Cortex Agent Bus — Auth Schema
--
-- Token-based authentication for the Agent Bus.
-- Tokens are stored bcrypt-hashed (SHA-256 PBKDF2 currently).
-- Each agent has a unique token that can be rotated independently.
-- Tokens auto-expire after 90 days.
--
-- Tables:
--   bus.tokens         — bearer token hashes per agent
--   bus.permissions    — per-agent queue permissions
--   bus.audit_log      — auth and operations audit trail
--
-- Functions:
--   bus.audit()        — log an audit event
-- ─────────────────────────────────────────────────────────────

-- ── Agent tokens ────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS bus.tokens (
    agent_name      TEXT PRIMARY KEY,
    token_hash      TEXT NOT NULL,
    is_active       BOOLEAN DEFAULT true,
    rotated_at      TIMESTAMPTZ DEFAULT now(),
    expires_at      TIMESTAMPTZ DEFAULT now() + INTERVAL '90 days',
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tokens_hash
    ON bus.tokens (token_hash)
    WHERE is_active = true;

-- ── Permissions ─────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS bus.permissions (
    agent_name      TEXT PRIMARY KEY,
    can_send        BOOLEAN DEFAULT true,
    can_read        BOOLEAN DEFAULT true,
    can_archive     BOOLEAN DEFAULT true,
    can_requeue     BOOLEAN DEFAULT true,
    can_delete      BOOLEAN DEFAULT false,
    can_admin       BOOLEAN DEFAULT false,
    labels          JSONB DEFAULT '{}'::jsonb,
    config          JSONB DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ DEFAULT now(),
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- Grant default permissions to fleet agents
-- NOTE: per-agent queue scoping lives in the runtime server (per-queue
-- can_read/can_write arrays). This schema seeds the base booleans for the
-- simple deployment; the shared orchestrator inbox is handled by the
-- runtime permission grants (moses+esther read/write inbox_orchestrator).
INSERT INTO bus.permissions (agent_name, can_send, can_read, can_archive, can_requeue, can_delete)
VALUES
    ('moses',  true,  true,  true,  true,  true),
    ('esther', true,  true,  true,  true,  false),
    ('joseph', true,  true,  true,  true,  false),
    ('titus',  true,  true,  true,  true,  false),
    ('gisu',   true,  true,  true,  true,  false),
    ('kustos', true,  true,  true,  true,  false)
ON CONFLICT (agent_name) DO NOTHING;

-- Shared orchestrator inbox — readable/writable by BOTH orchestrators so
-- the backup (Esther) can see worker fix requests when the primary (Moses)
-- is down/degraded, and Moses can check Esther's channel. Workers may SEND
-- fix requests here (contact-moses.sh / agent-message-handler target).
-- Created idempotently; both hosts' schemas apply it.
INSERT INTO bus.queues (name)
VALUES ('inbox_orchestrator')
ON CONFLICT (name) DO NOTHING;

-- ── Audit log ───────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS bus.audit_log (
    id              BIGSERIAL PRIMARY KEY,
    agent_name      TEXT,
    action          TEXT NOT NULL,          -- e.g. 'auth_failed', 'send', 'read', 'archive'
    queue_name      TEXT,
    details         JSONB,
    ip_address      TEXT,
    user_agent      TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_created
    ON bus.audit_log (created_at DESC);

CREATE INDEX IF NOT EXISTS idx_audit_log_agent
    ON bus.audit_log (agent_name);

-- ── Audit event function ────────────────────────────────────

CREATE OR REPLACE FUNCTION bus.audit(
    p_agent_name    TEXT,
    p_action        TEXT,
    p_queue_name    TEXT DEFAULT NULL,
    p_details       JSONB DEFAULT NULL,
    p_ip_address    TEXT DEFAULT NULL,
    p_user_agent    TEXT DEFAULT NULL
) RETURNS BIGINT AS $$
DECLARE
    v_id BIGINT;
BEGIN
    INSERT INTO bus.audit_log (agent_name, action, queue_name, details, ip_address, user_agent)
    VALUES (p_agent_name, p_action, p_queue_name, p_details, p_ip_address, p_user_agent)
    RETURNING id INTO v_id;

    RETURN v_id;
END;
$$ LANGUAGE plpgsql;
