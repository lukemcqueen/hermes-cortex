-- ============================================================================
-- tasks schema v010 — task model v3 fix: transition_allowed pending arc
--
-- v009 shipped transition_allowed WITHOUT the in_progress→pending arc
-- (unclaim feature). The v009 draft applied to live hosts before the fix,
-- and the version-gated runner skips re-running v009. This migration
-- re-creates transition_allowed with the full v3 matrix (idempotent
-- CREATE OR REPLACE — safe on hosts where v009 already has the fix).
--
-- Docs: docs/design/task-model-v3.md §3.
-- ============================================================================

BEGIN;

CREATE OR REPLACE FUNCTION tasks.transition_allowed(
    p_from   TEXT,
    p_to     TEXT,
    p_reason TEXT DEFAULT NULL
) RETURNS boolean
LANGUAGE plpgsql
IMMUTABLE
AS $$
BEGIN
    IF p_from = p_to THEN
        RETURN true;                       -- no-op gate (no transition)
    END IF;
    IF p_from = 'cancelled' THEN
        RETURN false;                      -- terminal
    END IF;
    CASE p_from
        WHEN 'pending' THEN
            RETURN p_to IN ('in_progress', 'cancelled', 'blocked', 'waiting');
        WHEN 'in_progress' THEN
            RETURN p_to IN ('paused', 'completed', 'cancelled',
                            'blocked', 'waiting', 'review', 'pending');
        WHEN 'review' THEN
            RETURN p_to IN ('completed', 'in_progress');
        WHEN 'paused' THEN
            RETURN p_to IN ('in_progress', 'completed', 'cancelled',
                            'blocked', 'waiting');
        WHEN 'blocked' THEN
            RETURN p_to IN ('in_progress', 'paused', 'completed',
                            'cancelled', 'waiting');
        WHEN 'waiting' THEN
            RETURN p_to IN ('in_progress', 'paused', 'blocked',
                            'completed', 'cancelled');
        WHEN 'completed' THEN
            RETURN p_to = 'in_progress' AND COALESCE(p_reason, '') = 'reopen';
        ELSE
            RETURN false;
    END CASE;
END;
$$;

COMMIT;
