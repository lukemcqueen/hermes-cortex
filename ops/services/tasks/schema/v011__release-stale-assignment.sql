-- ============================================================================
-- tasks schema v011 — release a stale hand-off
--
-- THE BUG THIS FIXES
-- A slice that is `pending` WITH an assignee is not claimable (claim_slice and the
-- worker pool both require assignee IS NULL) and is not `in_progress` either. So no
-- worker can take it and nobody is working it — it is stranded, while every board
-- view counts it as ordinary pending work (18 shown, 9 actually claimable).
--
-- Six such slices sat exactly like that from 2026-08-23 to 2026-10-04, all assigned
-- at decomposition time before any work began.
--
-- WHY THEY COULD NOT BE RECOVERED
-- unclaim_slice required status='in_progress', so an assignment handed out BEFORE
-- work started could never be given back. There was no release path at all.
--
-- WHAT THIS DOES
-- Widens the same function to release EITHER case, so `unclaim` covers both "give
-- back work I started" and "release a hand-off nobody started". The own-work guard
-- is unchanged — a worker still cannot release someone else's slice.
-- ============================================================================
BEGIN;

CREATE OR REPLACE FUNCTION tasks.unclaim_slice(p_id UUID, p_reason TEXT DEFAULT NULL)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = tasks, pg_temp AS $$
DECLARE
  v_updated int;
BEGIN
  UPDATE tasks.tasks
     SET status = 'pending',
         "column" = 'backlog',              -- keep derivation CHECK in sync
         assignee = NULL,
         status_changed_at = now()
   WHERE id = p_id
     AND created_by = tasks.profile_of(session_user)          -- only own work
     AND (
           status = 'in_progress'                             -- the original case:
                                                              -- give back started work
           OR (status = 'pending' AND assignee IS NOT NULL)    -- release a stale
                                                              -- hand-off, never started
         )
  RETURNING 1 INTO v_updated;
  RETURN COALESCE(v_updated, 0) = 1;
END $$;

REVOKE ALL ON FUNCTION tasks.unclaim_slice(UUID, TEXT) FROM PUBLIC;

-- Guarded grants: roles exist only on hosts carrying that agent's profile
-- (v001 lesson: an unguarded grant killed the migration on non-Esther hosts).
DO $$
DECLARE
  r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['mycortex_reader_esther','mycortex_reader_moses','mycortex_reader_titus','mycortex_reader_joseph','mycortex_reader_kustos','mycortex_reader_gisu']
  LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format('GRANT EXECUTE ON FUNCTION tasks.unclaim_slice(UUID, TEXT) TO %I', r);
    END IF;
  END LOOP;
END $$;

COMMIT;
