-- ============================================================================
-- learnings schema v002 — set_status() gains optional impact revision (F-006)
--
-- F-006 (orch-skill-lifecycle) is the ONLY UPDATE path (party L-1). It moves
-- learnings through the status machine AND revises impact_score when its
-- evaluation disagrees with the collector's initial guess (e.g. a lesson that
-- looked valuable but turned out low-value → impact 0/-1; a remediation that
-- measurably helped → +2/+3).
--
-- Change: set_status(p_id, p_status) → set_status(p_id, p_status, p_impact
-- DEFAULT NULL). p_impact NULL (or omitted — all existing callers) leaves
-- impact_score untouched; non-NULL must be in [-3, 3] (validated here for a
-- clean error; the column CHECK is fail-closed).
--
-- Backward compatible: the 2-arg call form resolves to this function via the
-- DEFAULT. The old 2-arg function is dropped so there is exactly ONE
-- set_status (no overload ambiguity for grants or callers).
-- ============================================================================

-- One canonical set_status: (UUID, TEXT, INT DEFAULT NULL)
DROP FUNCTION IF EXISTS learnings.set_status(UUID, TEXT);
CREATE OR REPLACE FUNCTION learnings.set_status(
    p_id     UUID,
    p_status TEXT,
    p_impact INT DEFAULT NULL
) RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = learnings, public
AS $$
BEGIN
    IF p_status NOT IN ('pending','evaluated','applied','verified','retired') THEN
        RAISE EXCEPTION 'learnings.set_status: invalid status %', p_status;
    END IF;
    IF p_impact IS NOT NULL AND (p_impact < -3 OR p_impact > 3) THEN
        RAISE EXCEPTION 'learnings.set_status: impact must be between -3 and 3, got %', p_impact;
    END IF;

    UPDATE learnings.learning
    SET status = p_status,
        impact_score = COALESCE(p_impact, impact_score),
        status_changed_at = now(),
        updated_at = now()
    WHERE id = p_id;

    RETURN FOUND;
END;
$$;

-- ── Grants (L-1 least privilege) ────────────────────────────────────────
-- The v001 grant was on the (UUID, TEXT) signature, which is now dropped.
-- Re-grant on the canonical (UUID, TEXT, INT) signature — the DEFAULT lets
-- 2-arg callers use it too. mycortex_reader covers every profile role
-- (esther/moses inherit); table DML remains ungranted (INSERT-only stays).
GRANT EXECUTE ON FUNCTION learnings.set_status(UUID, TEXT, INT) TO mycortex_reader;

-- Re-affirm capture grant on its canonical signature (unchanged, but keep
-- the file self-contained: a re-apply after any signature churn re-grants).
GRANT EXECUTE ON FUNCTION learnings.capture(learnings.learning_route, TEXT, TEXT, TEXT, INT, TEXT) TO mycortex_reader;
