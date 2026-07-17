-- ─────────────────────────────────────────────────────────────
-- Hermes Cortex Agent Bus — Queue Schema
--
-- Lightweight message queue on Postgres using SKIP LOCKED.
-- No external extensions required.
--
-- Tables:
--   agent_bus_queues      — queue metadata (name, config)
--   agent_bus_messages    — messages (one row per message)
--   agent_bus_archives    — processed messages (for audit)
--
-- API:
--   bus.send(queue, message)       → msg_id
--   bus.read(queue, vt_seconds)    → msg (or NULL)
--   bus.archive(queue, msg_id)     → success
--   bus.requeue(queue, msg_id)     → success (reset vt, increment retry)
--   bus.delete(queue, msg_id)      → success
--   bus.depth(queue)               → integer
--   bus.list_queues()              → [{name, depth, dlq_depth}]
-- ─────────────────────────────────────────────────────────────

-- Schema for bus objects
CREATE SCHEMA IF NOT EXISTS bus;

-- ── Queue metadata ──────────────────────────────────────────

CREATE TABLE IF NOT EXISTS bus.queues (
    name            TEXT PRIMARY KEY,
    created_at      TIMESTAMPTZ DEFAULT now(),
    max_retries     INT DEFAULT 3,           -- moves to DLQ after this
    vt_default      INT DEFAULT 60,          -- default visibility timeout
    is_dlq          BOOLEAN DEFAULT false,    -- is this a dead-letter queue?
    parent_queue    TEXT REFERENCES bus.queues(name)  -- for DLQs, which queue they belong to
);

-- ── Messages ────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS bus.messages (
    msg_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    queue_name      TEXT NOT NULL REFERENCES bus.queues(name) ON DELETE CASCADE,
    body            JSONB NOT NULL,
    priority        INT DEFAULT 0,          -- higher = more important
    state           TEXT NOT NULL DEFAULT 'pending',
        CHECK (state IN ('pending', 'visible', 'processing', 'completed', 'failed', 'dlq')),
    enqueued_at     TIMESTAMPTZ DEFAULT now(),
    visible_after   TIMESTAMPTZ DEFAULT now(),  -- becomes visible for reading after this
    timeout_at      TIMESTAMPTZ,                -- vt expiry
    retry_count     INT DEFAULT 0,
    max_retries     INT DEFAULT 3,
    error           TEXT,
    correlation_id  TEXT,                   -- workflow tracking
    version         INT DEFAULT 1           -- message envelope version
);

CREATE INDEX IF NOT EXISTS idx_messages_dequeue 
    ON bus.messages (queue_name, priority DESC, enqueued_at ASC) 
    WHERE state = 'pending';

CREATE INDEX IF NOT EXISTS idx_messages_timeout
    ON bus.messages (queue_name) WHERE state = 'processing';

-- ── Archived messages (processed messages, append-only) ─────

CREATE TABLE IF NOT EXISTS bus.archives (
    like bus.messages INCLUDING ALL,
    archived_at     TIMESTAMPTZ DEFAULT now(),
    archived_by     TEXT
);

-- ── Send ─────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION bus.send(
    p_queue TEXT,
    p_body JSONB,
    p_priority INT DEFAULT 0,
    p_correlation_id TEXT DEFAULT NULL,
    p_max_retries INT DEFAULT NULL
) RETURNS UUID AS $$
DECLARE
    v_msg_id UUID;
    v_max_retries INT;
BEGIN
    -- Auto-create queue if it doesn't exist (idempotent)
    INSERT INTO bus.queues (name)
    VALUES (p_queue)
    ON CONFLICT (name) DO NOTHING;

    SELECT COALESCE(p_max_retries, q.max_retries, 3)
    INTO v_max_retries
    FROM bus.queues q WHERE q.name = p_queue;

    INSERT INTO bus.messages (queue_name, body, priority, correlation_id, max_retries)
    VALUES (p_queue, p_body, p_priority, p_correlation_id, v_max_retries)
    RETURNING msg_id INTO v_msg_id;

    RETURN v_msg_id;
END;
$$ LANGUAGE plpgsql;

-- ── Read (dequeue with visibility timeout) ──────────────────

CREATE OR REPLACE FUNCTION bus.read(
    p_queue TEXT,
    p_vt INT DEFAULT NULL
) RETURNS JSONB AS $$
DECLARE
    v_vt INT;
    v_msg RECORD;
    v_result JSONB;
BEGIN
    -- Get queue default vt if not specified
    SELECT COALESCE(p_vt, q.vt_default, 60)
    INTO v_vt
    FROM bus.queues q WHERE q.name = p_queue;

    -- Dequeue with SKIP LOCKED
    SELECT * INTO v_msg
    FROM bus.messages
    WHERE queue_name = p_queue
      AND state = 'pending'
      AND visible_after <= now()
    ORDER BY priority DESC, enqueued_at ASC
    LIMIT 1
    FOR UPDATE SKIP LOCKED;

    IF NOT FOUND THEN
        -- Only auto-fallback to DLQ from a main queue, not from inside a DLQ
        IF NOT EXISTS (SELECT 1 FROM bus.queues WHERE name = p_queue AND is_dlq = true) THEN
            -- Check DLQ next
            SELECT * INTO v_msg
            FROM bus.messages
            WHERE queue_name = p_queue || '_dlq'
              AND state = 'pending'
              AND visible_after <= now()
            ORDER BY enqueued_at ASC
            LIMIT 1
            FOR UPDATE SKIP LOCKED;

            IF FOUND THEN
                -- vt=0 = peek: return DLQ message without consuming
                IF v_vt = 0 THEN
                    RETURN jsonb_build_object(
                        'msg_id', v_msg.msg_id::text,
                        'queue', p_queue || '_dlq',
                        'body', v_msg.body,
                        'retry_count', v_msg.retry_count,
                        'correlation_id', v_msg.correlation_id,
                        'from_dlq', true,
                        'enqueued_at', v_msg.enqueued_at,
                        'vt_zero_peek', true
                    );
                END IF;

                -- Return DLQ message (normal — consume with vt)
                UPDATE bus.messages
                SET state = 'processing',
                    timeout_at = now() + (v_vt || ' seconds')::interval
                WHERE msg_id = v_msg.msg_id;

                RETURN jsonb_build_object(
                    'msg_id', v_msg.msg_id::text,
                    'queue', p_queue || '_dlq',
                    'body', v_msg.body,
                    'retry_count', v_msg.retry_count,
                    'correlation_id', v_msg.correlation_id,
                    'from_dlq', true,
                    'enqueued_at', v_msg.enqueued_at
                );
            END IF;
        END IF;

        IF NOT FOUND THEN
            RETURN NULL;
        END IF;
    END IF;

    -- vt=0 = peek: return message body without changing state (true non-destructive read)
    IF v_vt = 0 THEN
        RETURN jsonb_build_object(
            'msg_id', v_msg.msg_id::text,
            'queue', p_queue,
            'body', v_msg.body,
            'priority', v_msg.priority,
            'retry_count', v_msg.retry_count,
            'max_retries', v_msg.max_retries,
            'correlation_id', v_msg.correlation_id,
            'from_dlq', false,
            'enqueued_at', v_msg.enqueued_at,
            'vt_zero_peek', true
        );
    END IF;

    -- Mark as processing with visibility timeout
    UPDATE bus.messages
    SET state = 'processing',
        timeout_at = now() + (v_vt || ' seconds')::interval
    WHERE msg_id = v_msg.msg_id;

    RETURN jsonb_build_object(
        'msg_id', v_msg.msg_id::text,
        'queue', p_queue,
        'body', v_msg.body,
        'priority', v_msg.priority,
        'retry_count', v_msg.retry_count,
        'max_retries', v_msg.max_retries,
        'correlation_id', v_msg.correlation_id,
        'from_dlq', false,
        'enqueued_at', v_msg.enqueued_at,
        'timeout_at', now() + (v_vt || ' seconds')::interval
    );
END;
$$ LANGUAGE plpgsql;

-- ── Archive (mark as completed, move to archive table) ──────

CREATE OR REPLACE FUNCTION bus.archive(
    p_queue TEXT,
    p_msg_id UUID,
    p_archived_by TEXT DEFAULT 'system'
) RETURNS BOOLEAN AS $$
DECLARE
    v_count INT;
BEGIN
    -- Move to archive
    INSERT INTO bus.archives
    SELECT m.*, now(), p_archived_by
    FROM bus.messages m
    WHERE m.msg_id = p_msg_id AND m.queue_name = p_queue;

    GET DIAGNOSTICS v_count = ROW_COUNT;
    IF v_count = 0 THEN
        RETURN FALSE;
    END IF;

    -- Delete from active queue
    DELETE FROM bus.messages
    WHERE msg_id = p_msg_id AND queue_name = p_queue;

    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

-- ── Requeue (failed message — increment retry, reset vt) ────
--
-- GUARD: If the message is already in a DLQ and has hit max_retries,
-- it stays in the same DLQ (end-of-line). Never creates DLQ-of-DLQ.
-- The 24h auto-archive in recover_timeouts() will clean it up.

CREATE OR REPLACE FUNCTION bus.requeue(
    p_queue TEXT,
    p_msg_id UUID,
    p_error TEXT DEFAULT NULL
) RETURNS BOOLEAN AS $$
DECLARE
    v_msg bus.messages;
    v_dlq TEXT;
    v_is_dlq BOOLEAN;
BEGIN
    SELECT * INTO v_msg
    FROM bus.messages
    WHERE msg_id = p_msg_id AND queue_name = p_queue
    FOR UPDATE;

    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;

    v_msg.retry_count := v_msg.retry_count + 1;

    IF v_msg.retry_count >= v_msg.max_retries THEN
        -- Check if we're already in a DLQ — never create DLQ-of-DLQ
        SELECT EXISTS (SELECT 1 FROM bus.queues WHERE name = p_queue AND is_dlq = true)
        INTO v_is_dlq;

        IF v_is_dlq THEN
            -- Already at end-of-line DLQ. Stay in place — reset visibility.
            -- Store caller error (if any) + structural marker so we can distinguish
            -- legitimate DLQ messages from watchdog-sampled artifacts.
            UPDATE bus.messages
            SET state = 'pending',
                visible_after = now(),
                timeout_at = NULL,
                retry_count = v_msg.retry_count,
                error = COALESCE(p_error || '; ', '') || 'max retries — DLQ end-of-line'
            WHERE msg_id = p_msg_id;
        ELSE
            -- Move to DLQ
            v_dlq := p_queue || '_dlq';

            -- Auto-create DLQ if needed
            INSERT INTO bus.queues (name, is_dlq, parent_queue)
            VALUES (v_dlq, true, p_queue)
            ON CONFLICT (name) DO NOTHING;

            UPDATE bus.messages
            SET state = 'pending',
                queue_name = v_dlq,
                visible_after = now(),
                timeout_at = NULL,
                retry_count = v_msg.retry_count,
                error = COALESCE(p_error, 'max retries exceeded — moved to DLQ')
            WHERE msg_id = p_msg_id;
        END IF;
    ELSE
        UPDATE bus.messages
        SET state = 'pending',
            visible_after = now(),
            timeout_at = NULL,
            retry_count = v_msg.retry_count,
            error = COALESCE(p_error, error)
        WHERE msg_id = p_msg_id;
    END IF;

    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

-- ── Delete ───────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION bus.delete(
    p_queue TEXT,
    p_msg_id UUID
) RETURNS BOOLEAN AS $$
BEGIN
    DELETE FROM bus.messages
    WHERE msg_id = p_msg_id AND queue_name = p_queue;
    RETURN FOUND;
END;
$$ LANGUAGE plpgsql;

-- ── Queue depth ──────────────────────────────────────────────

CREATE OR REPLACE FUNCTION bus.depth(p_queue TEXT)
RETURNS INT AS $$
BEGIN
    RETURN (SELECT count(*) FROM bus.messages
            WHERE queue_name = p_queue AND state = 'pending'
              AND visible_after <= now());
END;
$$ LANGUAGE plpgsql;

-- ── List all queues with metadata ───────────────────────────

CREATE OR REPLACE FUNCTION bus.list_queues()
RETURNS JSONB AS $$
BEGIN
    RETURN (
        SELECT jsonb_agg(jsonb_build_object(
            'name', q.name,
            'depth', (SELECT count(*) FROM bus.messages m 
                      WHERE m.queue_name = q.name AND m.state = 'pending'
                        AND m.visible_after <= now()),
            'processing', (SELECT count(*) FROM bus.messages m 
                          WHERE m.queue_name = q.name AND m.state = 'processing'),
            'dlq', q.is_dlq,
            'parent', q.parent_queue,
            'created', q.created_at
        ) ORDER BY q.name)
        FROM bus.queues q
    );
END;
$$ LANGUAGE plpgsql;

-- ── Recover timed-out messages (run every 5 minutes) ────────

CREATE OR REPLACE FUNCTION bus.recover_timeouts()
RETURNS INT AS $$
DECLARE
    v_recovered INT := 0;
    v_dlq_moved INT := 0;
    v_archived INT := 0;
BEGIN
    -- Step 1: Retry processing messages below max_retries
    UPDATE bus.messages
    SET state = 'pending',
        visible_after = now(),
        timeout_at = NULL,
        retry_count = retry_count + 1
    WHERE state = 'processing'
      AND timeout_at < now()
      AND retry_count < max_retries;

    GET DIAGNOSTICS v_recovered = ROW_COUNT;

    -- Step 2: Move over-max-retries to DLQ — but only if NOT already in one.
    -- DLQ messages that exhaust retries are DELETED (no deep-chain DLQ).
    WITH expired AS (
        UPDATE bus.messages m
        SET state = 'pending',
            -- If already in a DLQ: stay in same queue (will be deleted below)
            -- If not in a DLQ: move to DLQ
            queue_name = CASE
                WHEN m.queue_name LIKE '%\_dlq' THEN m.queue_name
                ELSE m.queue_name || '_dlq'
            END,
            visible_after = now(),
            timeout_at = NULL,
            error = COALESCE(error, 'max retries exceeded — moved to DLQ')
        FROM bus.queues q
        WHERE m.queue_name = q.name
          AND m.state = 'processing'
          AND m.timeout_at < now()
          AND m.retry_count >= m.max_retries
        RETURNING m.msg_id, m.queue_name, q.is_dlq
    ),
    -- Delete exhausted DLQ messages (no deeper chaining)
    deleted AS (
        DELETE FROM bus.messages m
        USING expired e
        WHERE m.msg_id = e.msg_id
          AND e.is_dlq = true
        RETURNING 1
    )
    SELECT count(*) INTO v_dlq_moved FROM expired;

    -- Step 3: Auto-archive old DLQ messages stuck in pending state
    -- (Messages that were moved to DLQ but never consumed)
    WITH archived AS (
        DELETE FROM bus.messages m
        USING bus.queues q
        WHERE m.queue_name = q.name
          AND q.is_dlq = true
          AND m.state = ANY (ARRAY['pending', 'processing'])
          AND m.enqueued_at < now() - interval '6 hours'
        RETURNING 1
    )
    SELECT count(*) INTO v_archived FROM archived;

    RETURN v_recovered + v_dlq_moved + v_archived;
END;
$$ LANGUAGE plpgsql;
