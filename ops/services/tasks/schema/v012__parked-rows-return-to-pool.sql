-- ============================================================================
-- tasks schema v012 — a parked row can return to the pull pool
--
-- THE BUG THIS FIXES (found live, not theorised)
-- `waiting`, `blocked` and `paused` are the three PARKED states, and none of them
-- allowed a transition to `pending`. So a slice parked in any of them could never
-- re-enter the claim pool: `claim_slice` takes only `pending` rows, so the one and
-- only route back to work was a manual `--status in_progress` — i.e. the
-- orchestrator starting it personally, which defeats the pull model.
--
-- Observed directly while cleaning up six rows parked since 2026-08-23:
--     ERROR: illegal task transition: waiting -> pending
-- They had been unreachable by the worker pool for six weeks, and there was no
-- legal transition that could return them to it.
--
-- WHY THIS IS A NEW FILE AND NOT AN EDIT TO v011
-- v011 is already applied on live hosts. The version-gated runner SKIPS a version
-- it has already run, so editing v011 would leave every existing host unfixed
-- while looking correct in the repo. v010 exists for exactly this reason (v009 had
-- shipped before the fix). Never edit a migration that has been applied.
--
-- WHAT THIS DOES
-- Adds `pending` as an allowed target for the three parked states. The arcs that
-- were there before are unchanged, and `cancelled` stays terminal.
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
            -- v012: 'pending' added — a parked slice must be able to rejoin the pool.
            RETURN p_to IN ('in_progress', 'completed', 'cancelled',
                            'blocked', 'waiting', 'pending');
        WHEN 'blocked' THEN
            -- v012: 'pending' added — see above.
            RETURN p_to IN ('in_progress', 'paused', 'completed',
                            'cancelled', 'waiting', 'pending');
        WHEN 'waiting' THEN
            -- v012: 'pending' added — see above.
            RETURN p_to IN ('in_progress', 'paused', 'blocked',
                            'completed', 'cancelled', 'pending');
        WHEN 'completed' THEN
            RETURN p_to = 'in_progress' AND COALESCE(p_reason, '') = 'reopen';
        ELSE
            RETURN false;
    END CASE;
END;
$$;

COMMIT;
