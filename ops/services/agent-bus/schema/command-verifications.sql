-- ─────────────────────────────────────────────────────────────
-- Hermes Cortex Agent Bus — Fleet Command Verifications
--
-- Tables:
--   bus.command_verifications — dispatch ledger with timeout/retry
--
-- Functions:
--   bus.record_dispatch()         — insert a new dispatch record
--   bus.verify_command()          — mark a command as verified
--   bus.get_pending_verifications() — pending + past deadline
--   bus.cleanup_verifications()   — purge old records
--
-- Agent-type awareness:
--   expected_response_subject = NULL = no response expected
--   (push-only agents like Titus, or COMMAND: subjects)
--   The verifier skips NULL expected_response_subject records.
-- ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS bus.command_verifications (
    correlation_id              VARCHAR(64) PRIMARY KEY,
    agent                       VARCHAR(64) NOT NULL,
    command_type                VARCHAR(32) NOT NULL
        CHECK (command_type IN ('EXEC', 'SEND', 'UPDATE_REQUEST',
                                'ROLLBACK_REQUEST', 'GIT_AUTH_CHECK',
                                'DIAGNOSTIC_REQUEST')),
    subject                     VARCHAR(255) NOT NULL,
    expected_response_subject   VARCHAR(64),
    msg_id                      UUID,
    dispatched_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    deadline_at                 TIMESTAMPTZ NOT NULL,
    status                      VARCHAR(32) NOT NULL DEFAULT 'pending',
    retry_count                 INT NOT NULL DEFAULT 0,
    max_retries                 INT NOT NULL DEFAULT 2,
    last_check_at               TIMESTAMPTZ,
    error_info                  TEXT,
    created_at                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_cmd_verif_status_deadline
    ON bus.command_verifications (status, deadline_at)
    WHERE status = 'pending';

CREATE INDEX IF NOT EXISTS idx_cmd_verif_corr
    ON bus.command_verifications (correlation_id);


-- Helper: column-qualified pg_temp wrapper to avoid PL/pgSQL ambiguity
CREATE OR REPLACE FUNCTION bus.record_dispatch(
    p_corr_id       VARCHAR(64),
    p_agent         VARCHAR(64),
    p_cmd_type      VARCHAR(32),
    p_subject       VARCHAR(255),
    p_expected_resp VARCHAR(64) DEFAULT NULL,
    p_msg_id        UUID DEFAULT NULL,
    p_timeout_sec   INT DEFAULT 600
) RETURNS TABLE(ret_corr_id VARCHAR(64), ret_status VARCHAR(32))
LANGUAGE plpgsql AS $BODY$
BEGIN
    INSERT INTO bus.command_verifications AS cv
        (correlation_id, agent, command_type, subject,
         expected_response_subject, msg_id, deadline_at)
    VALUES
        (p_corr_id, p_agent, p_cmd_type, p_subject,
         p_expected_resp, p_msg_id,
         now() + make_interval(secs => p_timeout_sec))
    ON CONFLICT (correlation_id) DO UPDATE
        SET retry_count = cv.retry_count + 1,
            deadline_at = now() + make_interval(secs => p_timeout_sec),
            status = 'pending',
            updated_at = now()
    RETURNING cv.correlation_id, cv.status INTO p_corr_id, p_subject;
    -- Return actual row since INTO vars are just discard targets
    RETURN QUERY SELECT cv2.correlation_id, cv2.status
        FROM bus.command_verifications cv2
        WHERE cv2.correlation_id = p_corr_id;
END;
$BODY$;


CREATE OR REPLACE FUNCTION bus.verify_command(
    p_corr_id   VARCHAR(64),
    p_status    VARCHAR(32) DEFAULT 'verified',
    p_err_info  TEXT DEFAULT NULL
) RETURNS TABLE(ret_corr_id VARCHAR(64), ret_status VARCHAR(32))
LANGUAGE plpgsql AS $BODY$
BEGIN
    RETURN QUERY
        UPDATE bus.command_verifications cv
            SET status = p_status,
                error_info = COALESCE(p_err_info, cv.error_info),
                last_check_at = now(),
                updated_at = now()
        WHERE cv.correlation_id = p_corr_id
        RETURNING cv.correlation_id, cv.status;
END;
$BODY$;


CREATE OR REPLACE FUNCTION bus.get_pending_verifications()
RETURNS TABLE(
    out_corr                    VARCHAR(64),
    out_agent                   VARCHAR(64),
    out_cmd_type                VARCHAR(32),
    out_subject                 VARCHAR(255),
    out_expected_response       VARCHAR(64),
    out_msg_id                  UUID,
    out_dispatched_at           TIMESTAMPTZ,
    out_deadline_at             TIMESTAMPTZ,
    out_retry_count             INT,
    out_max_retries             INT
)
LANGUAGE plpgsql AS $BODY$
BEGIN
    RETURN QUERY
        SELECT cv.correlation_id AS out_corr,
               cv.agent AS out_agent,
               cv.command_type AS out_cmd_type,
               cv.subject AS out_subject,
               cv.expected_response_subject AS out_expected_response,
               cv.msg_id AS out_msg_id,
               cv.dispatched_at AS out_dispatched_at,
               cv.deadline_at AS out_deadline_at,
               cv.retry_count AS out_retry_count,
               cv.max_retries AS out_max_retries
        FROM bus.command_verifications cv
        WHERE cv.status = 'pending'
          AND cv.deadline_at < now()
          AND cv.expected_response_subject IS NOT NULL
        ORDER BY cv.deadline_at;
END;
$BODY$;


CREATE OR REPLACE FUNCTION bus.cleanup_verifications(
    p_days INT DEFAULT 30
) RETURNS BIGINT
LANGUAGE plpgsql AS $BODY$
DECLARE
    v_deleted BIGINT;
BEGIN
    DELETE FROM bus.command_verifications
    WHERE created_at < now() - make_interval(days => p_days);
    GET DIAGNOSTICS v_deleted = ROW_COUNT;
    RETURN v_deleted;
END;
$BODY$;
