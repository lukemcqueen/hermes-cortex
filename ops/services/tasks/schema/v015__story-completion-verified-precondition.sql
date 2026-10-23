-- ============================================================================
-- tasks schema v015 — the story gate is verified, not authorised by a GUC
--
-- THE HOLE THIS CLOSES
-- v008 admitted `story → completed` by consulting the session GUC
-- `tasks.transition_reason`, and placed that early return ABOVE the R-3 story
-- gate ("a story may not be completed while any non-cancelled slice is active").
-- The reason string is written by the CALLER via set_config(), so the permission
-- to skip the gate was a value any writer could produce:
--
--     SELECT set_config('tasks.transition_reason', 'story_auto_complete', false);
--     SELECT tasks.task_upsert(p_id=>'<story>', p_status=>'completed');   -- gate skipped
--
-- Measured on the deployed store (host esther, captured in
-- docs/evidence/tasks-review-gate-2026-10-23/pre-change-functiondefs.txt): the
-- deployed check_transition carries that early return, and the gate, in that order.
-- `tasks.story_auto_complete()` (v008) is only ONE of the callers that can produce
-- that value — it is a mechanism, not a capability boundary.
--
-- Reachability: the caller needs UPDATE on the row it owns. RLS tasks_personal
-- admits a personal row whose created_by is the caller, so any profile role can do
-- this on its own story; a fleet writer can do it on a fleet row.
--
-- WHAT THIS DOES
-- The early return now verifies the PRECONDITION the auto-complete path satisfies
-- by construction — no active slice — instead of trusting a reason string. A story
-- may still complete from an open state (pending/in_progress), which the ordinary
-- auto-complete needs because stories are never claimed and stay `pending` while
-- their slices run; the reason is no longer consulted for permission at all. The
-- later RAISE for the active-slice case is unchanged and remains the refusal.
--
-- The GUC keeps its remaining, non-authorising use: event_after_update (v008) uses
-- it to LABEL the event trail `story_auto_complete`. That is provenance, not
-- permission — a forged label mislabels an event, it does not admit a transition.
--
-- WHAT THIS DOES NOT CHANGE (measured, not assumed)
-- A manual pending → completed through task_upsert() stays REFUSED: that function
-- pre-checks transition_allowed(), and the matrix (v012) forbids pending→completed
-- whatever the reason. The early return only ever admitted the RAW-UPDATE path (the
-- auto-complete trigger's own UPDATE, and any hand-written UPDATE by a caller that
-- could set the GUC), which is why the gate was walkable there and nowhere else.
-- So this migration removes a bypass without opening a path: the legitimate raw use
-- (auto-complete) satisfies the precondition by construction.
--
-- RECORD OF THE MEASUREMENTS THIS FILE CITES (re-runnable; the file states the contract,
-- the record is where the numbers come from):
--   plan review  : loop-governance cycle 13722 (adversarial_reviews, reviewer
--                  deepseek-v4-pro, verdict CLEAN) — it also recorded the one claim
--                  building FALSIFIED: that a manual pending→completed would become
--                  legal here. It does not; task_upsert's fast-fail refuses it first.
--   RED / GREEN  : docs/evidence/tasks-story-gate-2026-10-23/red-before-v015.txt
--                  (125 passed, 2 failed) and green-after-v015.txt (127 passed,
--                  0 failed), both the battery's own stdout for
--                  `bash tests/test-tasks-schema.sh`, run with v015 absent then present.
--   live proof   : docs/evidence/tasks-story-gate-2026-10-23/live-guard-proof.txt —
--                  deployed store at tasks schema_version 15, forged-reason probe on a
--                  story with an active slice refused, transaction never committed.
-- The AUTHORITATIVE contract is tests/test-tasks-schema.sh AC-L1-25; these artifacts
-- are its transcripts, not a substitute for it.
--
-- WHY A NEW FILE AND NOT AN EDIT TO v014
-- v014 is applied on live hosts; the version-gated runner SKIPS a version it has
-- already run. Editing it would leave every existing host unfixed while the repo
-- looked correct. Never edit a migration that has been applied.
--
-- Docs: docs/design/task-lifecycle-v2.md §4 (story auto-complete, R-3 gate).
-- ============================================================================

BEGIN;

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
    -- v015: story → completed from an OPEN state is admitted only when the story
    -- has no active slice — the same precondition the auto-complete path satisfies
    -- by construction. The reason string is NOT consulted: it is caller-settable,
    -- so it can label an event but never authorise a transition. Placed above the
    -- transition matrix because the matrix (v012) admits pending → in_progress/
    -- cancelled/blocked/waiting only, and a never-started story whose slices all
    -- finished legitimately completes from `pending`.
    IF NEW.kind = 'story' AND NEW.status = 'completed'
       AND OLD.status IN ('pending', 'in_progress')
       AND NOT EXISTS (
           SELECT 1 FROM tasks.tasks s
           WHERE s.parent_id = NEW.id
             AND s.status NOT IN ('completed', 'cancelled')
       ) THEN
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

COMMIT;
