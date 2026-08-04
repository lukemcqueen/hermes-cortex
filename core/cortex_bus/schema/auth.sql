-- ─────────────────────────────────────────────────────────────
-- Cortex Bus — Auth Schema (CANONICAL)
--
-- Single schema for BOTH orchestrator buses (Moses :13004 and
-- Esther :14004). Replaces the divergent boolean model
-- (can_send/can_read/can_archive/can_requeue) that used to live in
-- the deleted ops/services/agent-bus/schema/auth.sql.
--
-- ACL model: per-queue arrays.
--   can_read  TEXT[] — queues this agent may read from
--   can_write TEXT[] — queues this agent may send to
--   is_admin  BOOLEAN — bypasses all checks (moses)
--   '*' in an array grants all queues.
--
-- Tables:
--   bus.tokens         — bearer token hashes per agent
--   bus.permissions    — per-agent per-queue permissions
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

-- ── Permissions (per-queue arrays — CANONICAL) ──────────────

CREATE TABLE IF NOT EXISTS bus.permissions (
    agent_name      TEXT PRIMARY KEY,
    can_read        TEXT[] DEFAULT '{}',
    can_write       TEXT[] DEFAULT '{}',
    is_admin        BOOLEAN DEFAULT false,
    created_at      TIMESTAMPTZ DEFAULT now(),
    labels          JSONB DEFAULT '{}'::jsonb,
    config          JSONB DEFAULT '{}'::jsonb
);

-- ── Migration from the boolean model (backup host, 2026-08-04) ──
-- Idempotent. On a boolean-schema host (has can_send) the old boolean
-- can_read/can_write columns are DROPPED first — they share the same
-- names as the array columns, so ADD COLUMN IF NOT EXISTS would no-op.
-- Then the array columns are added and backfilled ('*' = all queues).
-- On an array-schema host this is a no-op.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.columns
             WHERE table_schema = 'bus' AND table_name = 'permissions'
               AND column_name = 'can_send') THEN
    ALTER TABLE bus.permissions DROP COLUMN can_read;
    ALTER TABLE bus.permissions DROP COLUMN can_write;
  END IF;
END $$;

ALTER TABLE bus.permissions ADD COLUMN IF NOT EXISTS can_read TEXT[] DEFAULT '{}';
ALTER TABLE bus.permissions ADD COLUMN IF NOT EXISTS can_write TEXT[] DEFAULT '{}';
ALTER TABLE bus.permissions ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT false;

UPDATE bus.permissions SET can_read = ARRAY['*'], can_write = ARRAY['*']
 WHERE is_admin = false
   AND can_read = '{}'::text[] AND can_write = '{}'::text[];

ALTER TABLE bus.permissions DROP COLUMN IF EXISTS can_send;
ALTER TABLE bus.permissions DROP COLUMN IF EXISTS can_archive;
ALTER TABLE bus.permissions DROP COLUMN IF EXISTS can_requeue;
ALTER TABLE bus.permissions DROP COLUMN IF EXISTS can_delete;
ALTER TABLE bus.permissions DROP COLUMN IF EXISTS can_admin;

-- ── Canonical grants (mirrors the primary's live grants) ────

INSERT INTO bus.permissions (agent_name, can_read, can_write, is_admin) VALUES
    ('moses',  ARRAY['inbox_moses','inbox_moses_dlq','inbox_health_check'],
               ARRAY['inbox_moses','inbox_esther','inbox_joseph','inbox_titus','inbox_gisu','inbox_kustos','workflow_dispatch','workflow_step_result','workflow_timeout','inbox_moses_dlq','inbox_health_check'],
               true),
    ('esther', ARRAY['inbox_esther','inbox_moses','inbox_orchestrator','inbox_joseph','inbox_titus','inbox_gisu','inbox_kustos'],
               ARRAY['inbox_moses','inbox_esther','inbox_orchestrator','inbox_joseph','inbox_titus','inbox_gisu','inbox_kustos','workflow_step_result','inbox_health_check'],
               false),
    ('gisu',   ARRAY['inbox_gisu'],
               ARRAY['inbox_health_check','workflow_step_result','inbox_moses','inbox_gisu','inbox_orchestrator'],
               false),
    ('joseph', ARRAY['inbox_joseph'],
               ARRAY['inbox_health_check','workflow_step_result','inbox_moses','inbox_orchestrator','inbox_joseph'],
               false),
    ('kustos', ARRAY['inbox_kustos'],
               ARRAY['inbox_health_check','workflow_step_result','inbox_moses','inbox_orchestrator','inbox_kustos'],
               false),
    ('titus',  ARRAY['inbox_titus'],
               ARRAY['inbox_health_check','inbox_titus','workflow_step_result','inbox_moses','inbox_orchestrator'],
               false)
ON CONFLICT (agent_name) DO NOTHING;

-- Shared orchestrator inbox — readable/writable by BOTH orchestrators so
-- the backup (Esther) can see worker fix requests when the primary (Moses)
-- is down/degraded, and Moses can check Esther's channel. Workers may SEND
-- fix requests here (contact-orchestrator.sh / agent-message-handler target).
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
