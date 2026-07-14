-- ─────────────────────────────────────────────────────────────
-- Agent Bus — Permissions and Auth Tables
-- ─────────────────────────────────────────────────────────────

-- Agent permissions (which queues each agent can read/write)
CREATE TABLE IF NOT EXISTS bus.permissions (
    agent_name      TEXT PRIMARY KEY,
    can_read        TEXT[] DEFAULT '{}',
    can_write       TEXT[] DEFAULT '{}',
    is_admin        BOOLEAN DEFAULT false,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- Seed all fleet agents with least-privilege permissions
-- Agents can only read their own queue and write to moses
-- Moses (admin) can read/write everything
INSERT INTO bus.permissions AS p (agent_name, can_read, can_write, is_admin)
VALUES
    ('moses',  ARRAY['inbox_moses'],   ARRAY['inbox_moses','inbox_esther','inbox_joseph','inbox_titus','inbox_gisu','inbox_kustos','workflow_dispatch','workflow_step_result','workflow_timeout'], true),
    ('esther', ARRAY['inbox_esther'],  ARRAY['inbox_moses'], false),
    ('joseph', ARRAY['inbox_joseph'],  ARRAY['inbox_moses'], false),
    ('titus',  ARRAY['inbox_titus'],   ARRAY['inbox_moses'], false),
    ('gisu',   ARRAY['inbox_gisu'],    ARRAY['inbox_moses'], false),
    ('kustos', ARRAY['inbox_kustos'],  ARRAY['inbox_moses'], false)
ON CONFLICT (agent_name) DO NOTHING;

-- Bearer tokens (per-agent, bcrypt-hashed)
CREATE TABLE IF NOT EXISTS bus.tokens (
    agent_name      TEXT PRIMARY KEY REFERENCES bus.permissions(agent_name),
    token_hash      TEXT NOT NULL,
    created_at      TIMESTAMPTZ DEFAULT now(),
    rotated_at      TIMESTAMPTZ,
    expires_at      TIMESTAMPTZ DEFAULT (now() + interval '90 days'),
    is_active       BOOLEAN DEFAULT true
);

-- Helper: validate a bearer token
-- Returns the agent name if valid, NULL otherwise
CREATE OR REPLACE FUNCTION bus.validate_token(p_token TEXT)
RETURNS TEXT AS $$
DECLARE
    v_agent TEXT;
BEGIN
    -- In production, use pgcrypto's crypt() for bcrypt comparison
    -- For now, we compare against all active tokens
    -- This will be replaced with proper bcrypt verification
    SELECT t.agent_name INTO v_agent
    FROM bus.tokens t
    WHERE t.is_active = true
      AND t.expires_at > now()
      AND t.token_hash = p_token;  -- TODO: replace with crypt(p_token, token_hash)
    
    RETURN v_agent;
END;
$$ LANGUAGE plpgsql;

-- Audit log for all bus operations
CREATE TABLE IF NOT EXISTS bus.audit_log (
    id              BIGSERIAL PRIMARY KEY,
    agent_name      TEXT,
    action          TEXT NOT NULL,     -- send, read, archive, requeue, delete
    queue           TEXT,
    detail          JSONB,
    ip_address      TEXT,
    success         BOOLEAN DEFAULT true,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_agent ON bus.audit_log(agent_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_queue ON bus.audit_log(queue, created_at DESC);

-- Helper: log an audit entry
CREATE OR REPLACE FUNCTION bus.audit(
    p_agent TEXT,
    p_action TEXT,
    p_queue TEXT DEFAULT NULL,
    p_detail JSONB DEFAULT NULL,
    p_ip TEXT DEFAULT NULL,
    p_success BOOLEAN DEFAULT true
) RETURNS VOID AS $$
BEGIN
    INSERT INTO bus.audit_log (agent_name, action, queue, detail, ip_address, success)
    VALUES (p_agent, p_action, p_queue, p_detail, p_ip, p_success);
END;
$$ LANGUAGE plpgsql;
