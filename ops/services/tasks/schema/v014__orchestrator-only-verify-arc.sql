-- ============================================================================
-- tasks schema v014 — the verification arc is ORCHESTRATOR-ONLY on every path
--
-- THE HOLE THIS CLOSES (reported by Titus Pi, verified live on the deployed DB)
-- `tasks.verify_slice` is orchestrator-only: SECURITY DEFINER, a moses/esther
-- allowlist inside the function, and an EXECUTE grant held by no other profile
-- role. But the ARC it performs was legal on the generic write path, so the gate
-- was advisory rather than enforced:
--
--   * tasks.transition_allowed('review','completed') returns TRUE for every
--     caller — it is IMMUTABLE and takes no identity argument.
--   * tasks.check_transition() (BEFORE UPDATE, described in v005 as "the
--     authoritative gate for direct SQL AND task_upsert") consulted ONLY
--     transition_allowed. It carried no identity check.
--   * every profile role holds SELECT/INSERT/UPDATE/DELETE on tasks.tasks
--     (v001), so a worker's own `task_update`, `task-db.py update --status
--     completed`, or a raw UPDATE reached the same arc without verify_slice.
--
-- Measured consequence, hermetic scratch DB, role mycortex_reader_probe
-- (profile_of() -> 'probe', not a todos_fleet_writer member):
--     task_upsert(p_id, p_status=>'completed')  -> returned a UUID  (rc=0)
--     UPDATE tasks.tasks SET status='completed' -> UPDATE 1         (rc=0)
-- on a row its OWN caller had just reported into `review`. That is
-- self-graded work wearing the same status as verified work, which is the one
-- thing `review` exists to prevent.
--
-- WHY THE GUARD LIVES IN THE TRIGGER, NOT IN transition_allowed
-- The identity is not available to an IMMUTABLE role-agnostic function, and
-- removing the arc from the matrix would make verify_slice itself raise. The
-- trigger is the single choke point every write path funnels through (v005
-- already declares it authoritative), so the identity check belongs there.
--
-- SCOPE — what is deliberately NOT gated
-- Only the arc that CLAIMS verification (review -> completed) is gated.
-- review -> in_progress is the reject/stale arc: it asserts nothing about
-- verification and the 24h stale sweep (agent-message-handler Arm 3) uses it to
-- re-queue, so it stays open. in_progress -> completed (a worker finishing its
-- own work before reporting) is untouched, and the story auto-complete path
-- keeps its existing early return.
--
-- Docs: docs/design/task-model-v3.md §3.
-- ============================================================================

BEGIN;

-- ── 1. One source of truth for the orchestrator allowlist ───────────────────
-- Takes the identity EXPLICITLY (no default): a default of CURRENT_USER would
-- silently resolve to the DEFINER inside a SECURITY DEFINER function, which is
-- the wrong answer in exactly the case that matters. Every caller names the
-- identity it means — `session_user` survives SECURITY DEFINER, `current_user`
-- does not.
CREATE OR REPLACE FUNCTION tasks.is_orchestrator(p_role name)
RETURNS boolean
LANGUAGE sql
STABLE
AS $$
    SELECT tasks.profile_of(p_role) IN ('moses','esther');
$$;

REVOKE ALL ON FUNCTION tasks.is_orchestrator(name) FROM PUBLIC;

-- Every writer needs EXECUTE: check_transition is INVOKER, so the trigger's
-- call to is_orchestrator runs with the WRITER's privileges. Guarded grants —
-- a role that does not exist on a host would fail the migration (v001's rule).
DO $$
DECLARE
  r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['mycortex_reader','mycortex_admin']
  LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format('GRANT EXECUTE ON FUNCTION tasks.is_orchestrator(name) TO %I', r);
    END IF;
  END LOOP;
END $$;

-- ── 2. The gate itself ──────────────────────────────────────────────────────
-- v005's body (plus the v008 story_auto_complete early return and the story
-- gate) is preserved verbatim; the ONLY addition is the review-arc identity
-- check, placed AFTER the story_auto_complete early return so the story path
-- (which completes a story from the slice's AFTER trigger, under whatever
-- session_user ran the slice update) is untouched.
CREATE OR REPLACE FUNCTION tasks.check_transition()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_reason TEXT;
BEGIN
    IF OLD.status IS NOT DISTINCT FROM NEW.status THEN
        RETURN NEW;
    END IF;
    v_reason := NULLIF(current_setting('tasks.transition_reason', true), '');
    -- Auto-complete path: story → completed ONLY via the AFTER trigger's GUC.
    -- The trigger fires only when no active slices remain, so the R-3 story
    -- gate is satisfied by construction.
    IF NEW.kind = 'story' AND NEW.status = 'completed'
       AND v_reason = 'story_auto_complete' THEN
        RETURN NEW;
    END IF;
    -- v014: the verification arc is orchestrator-only. session_user (never
    -- current_user) is the authenticated caller, which is the identity that
    -- still holds inside verify_slice's SECURITY DEFINER context.
    IF OLD.status = 'review' AND NEW.status = 'completed'
       AND NOT tasks.is_orchestrator(session_user) THEN
        RAISE EXCEPTION
            'review -> completed requires orchestrator verification (caller %): '
            'the generic update path may not approve a slice — moses/esther run '
            'tasks.verify_slice', tasks.profile_of(session_user);
    END IF;
    -- COALESCE(..., false): transition_allowed must never leak NULL into
    -- the gate (three-valued logic would silently permit the transition).
    IF NOT COALESCE(tasks.transition_allowed(OLD.status, NEW.status, v_reason), false) THEN
        RAISE EXCEPTION 'illegal task transition: % -> % (reason: %)',
            OLD.status, NEW.status, COALESCE(v_reason, 'none');
    END IF;
    IF NEW.kind = 'story' AND NEW.status = 'completed' AND EXISTS (
        SELECT 1 FROM tasks.tasks s
        WHERE s.parent_id = NEW.id
          AND s.status NOT IN ('completed', 'cancelled')
    ) THEN
        RAISE EXCEPTION 'story % has active slices; cannot complete', NEW.id;
    END IF;
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION tasks.check_transition() FROM PUBLIC;

-- ── 3. verify_slice shares the ONE allowlist ────────────────────────────────
-- Behaviour is unchanged (moses/esther only); the inline literal is replaced so
-- the allowlist cannot drift from the trigger's copy.
CREATE OR REPLACE FUNCTION tasks.verify_slice(
  p_id UUID,
  p_approved boolean,
  p_note TEXT DEFAULT NULL
) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = tasks, pg_temp AS $$
DECLARE
  v_updated int;
BEGIN
  -- Orchestrator-only: moses/esther may verify. Never trust a self-report.
  IF NOT tasks.is_orchestrator(session_user) THEN
    RETURN false;
  END IF;
  UPDATE tasks.tasks
     SET status = CASE WHEN p_approved THEN 'completed' ELSE 'in_progress' END,
         "column" = CASE WHEN p_approved THEN 'done' ELSE 'in_progress' END,
         status_changed_at = now(),
         plan = CASE WHEN p_approved THEN plan
                     ELSE plan || E'\n-- VERIFY FAILED --\n' || COALESCE(p_note, 'no reason')
                END
   WHERE id = p_id
     AND status = 'review'
  RETURNING 1 INTO v_updated;
  RETURN COALESCE(v_updated, 0) = 1;
END $$;

REVOKE ALL ON FUNCTION tasks.verify_slice(UUID, BOOLEAN, TEXT) FROM PUBLIC;

DO $$
DECLARE
  r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['mycortex_reader_esther','mycortex_reader_moses']
  LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format('GRANT EXECUTE ON FUNCTION tasks.verify_slice(UUID, BOOLEAN, TEXT) TO %I', r);
    END IF;
  END LOOP;
END $$;

COMMIT;
