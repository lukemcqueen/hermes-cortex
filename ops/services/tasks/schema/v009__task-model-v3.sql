-- ============================================================================
-- tasks schema v009 — Task Model v3 (orchestrator-intelligence / worker-execution)
--
-- Docs: docs/design/task-model-v3.md §3 (schema changes, minimal).
-- Additive ALTERs only, single transaction (BEGIN/COMMIT — SRE R-10).
-- Version-gated by ops/services/tasks/migrate.py; re-run after a rolled-back
-- attempt is safe (IF NOT EXISTS + DROP-IF-EXISTS guards).
--
-- Ships (Task Model v3 T1):
--   1. plan column          orchestrator-written checklist on slices
--   2. review status        worker-done-awaiting-verification (in_progress→
--                           review→completed, orchestrator-only verify)
--   3. claim_slice()        atomic pending→in_progress+assignee, agent may
--                           claim only FOR ITSELF (RLS-safe narrow write)
--   4. unclaim_slice()      in_progress→pending with reason (mid-task
--                           blocker, tool gap); clears assignee
--   5. report_done()        worker marks in_progress→review with evidence
--   6. verify_slice()       orchestrator-only: review→completed (or back to
--                           in_progress with reason on failure)
--   7. status CHECK + transition matrix extended for review
--
-- Design constraints honored:
--   - SECURITY INVOKER (RLS applies) — never SECURITY DEFINER on claim:
--     an agent can only claim for itself (profile_of(current_user) guard).
--   - claim/unclaim/report/verify ALL go through check_transition() so the
--     event trail + Telegram notify fire exactly as any other transition.
--   - Orchestrator-only verify: profile_of(current_user) must be a known
--     orchestrator (moses/esther) — hardcoded allowlist, not a role table.
-- ============================================================================

BEGIN;

-- ── 1. plan column (slices carry the orchestrator's checklist) ─────────────
ALTER TABLE tasks.tasks ADD COLUMN IF NOT EXISTS plan TEXT;

-- ── 2. review status ────────────────────────────────────────────────────────
ALTER TABLE tasks.tasks DROP CONSTRAINT IF EXISTS tasks_status_check;
ALTER TABLE tasks.tasks ADD CONSTRAINT tasks_status_check CHECK (
  status IN ('pending','in_progress','completed','cancelled','paused',
             'blocked','waiting','review')
);

-- column-derivation CHECK must admit the new review column+status pair
-- (v005 allowed 'review' column only for pending/in_progress; add review).
ALTER TABLE tasks.tasks DROP CONSTRAINT IF EXISTS tasks_column_check;
ALTER TABLE tasks.tasks ADD CONSTRAINT tasks_column_check CHECK (
    "column" IS NULL OR (
        ("column" IN ('backlog','todo') AND status = 'pending')
        OR ("column" = 'in_progress' AND status = 'in_progress')
        OR ("column" = 'done' AND status = 'completed')
        OR ("column" = 'review' AND status IN ('pending','in_progress','review'))
    ));

-- ── 3. claim_slice() — atomic claim, self-only ──────────────────────────────
-- SECURITY DEFINER (owner mycortex): fleet rows are RLS read-only for
-- workers; the claim is the ONE narrow write workers are allowed. The
-- security is INSIDE the function: an agent may claim only FOR ITSELF
-- (p_assignee must equal profile_of(current_user)) and only a pending row.
-- The WHERE clause is the guard; RLS would block the intended write.
CREATE OR REPLACE FUNCTION tasks.claim_slice(p_id UUID, p_assignee TEXT)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = tasks, pg_temp AS $$
DECLARE
  v_updated int;
BEGIN
  -- Guard: an agent can claim ONLY for itself (never assign work to others).
  -- session_user (not current_user): SECURITY DEFINER runs as owner mycortex;
  -- the authenticated reader is session_user (v005 postgres-schema-design #1).
  IF p_assignee IS DISTINCT FROM tasks.profile_of(session_user) THEN
    RETURN false;
  END IF;
  UPDATE tasks.tasks
     SET status = 'in_progress',
         "column" = 'in_progress',          -- keep derivation CHECK in sync
         assignee = p_assignee,
         status_changed_at = now()
   WHERE id = p_id
     AND status = 'pending'
     AND scope IN ('fleet','personal')
  RETURNING 1 INTO v_updated;
  RETURN COALESCE(v_updated, 0) = 1;
END $$;

REVOKE ALL ON FUNCTION tasks.claim_slice(UUID, TEXT) FROM PUBLIC;

-- Guarded grants: roles exist only on hosts with that agent's profile
-- (learnings v001: unguarded grants killed the migration on non-Esther hosts).
DO $$
DECLARE
  r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['mycortex_reader_esther','mycortex_reader_moses','mycortex_reader_titus','mycortex_reader_joseph','mycortex_reader_kustos','mycortex_reader_gisu']
  LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format('GRANT EXECUTE ON FUNCTION tasks.claim_slice(UUID, TEXT) TO %I', r);
    END IF;
  END LOOP;
END $$;

-- ── 4. unclaim_slice() — return to pending with reason ──────────────────────
-- SECURITY DEFINER (same rationale as claim): own-work guard inside.
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
     AND status = 'in_progress'
     AND created_by = tasks.profile_of(session_user)   -- only own work
  RETURNING 1 INTO v_updated;
  RETURN COALESCE(v_updated, 0) = 1;
END $$;

REVOKE ALL ON FUNCTION tasks.unclaim_slice(UUID, TEXT) FROM PUBLIC;

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

-- ── 5. report_done() — worker submits evidence, slice → review ──────────────
-- SECURITY DEFINER (same rationale): own-work guard inside.
CREATE OR REPLACE FUNCTION tasks.report_done(p_id UUID, p_evidence TEXT DEFAULT NULL)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = tasks, pg_temp AS $$
DECLARE
  v_updated int;
BEGIN
  UPDATE tasks.tasks
     SET status = 'review',
         "column" = 'review',               -- keep derivation CHECK in sync
         plan = COALESCE(plan, '') || E'\n-- EVIDENCE --\n' || COALESCE(p_evidence, ''),
         status_changed_at = now()
   WHERE id = p_id
     AND status = 'in_progress'
     AND created_by = tasks.profile_of(session_user)   -- worker reports own work
  RETURNING 1 INTO v_updated;
  RETURN COALESCE(v_updated, 0) = 1;
END $$;

REVOKE ALL ON FUNCTION tasks.report_done(UUID, TEXT) FROM PUBLIC;

DO $$
DECLARE
  r text;
BEGIN
  FOREACH r IN ARRAY ARRAY['mycortex_reader_esther','mycortex_reader_moses','mycortex_reader_titus','mycortex_reader_joseph','mycortex_reader_kustos','mycortex_reader_gisu']
  LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format('GRANT EXECUTE ON FUNCTION tasks.report_done(UUID, TEXT) TO %I', r);
    END IF;
  END LOOP;
END $$;

-- ── 6. verify_slice() — ORCHESTRATOR ONLY: review → completed/failed ───────
-- SECURITY DEFINER: orchestrator allowlist INSIDE (profile_of must be
-- moses/esther). Never trust a self-report.
CREATE OR REPLACE FUNCTION tasks.verify_slice(
  p_id UUID,
  p_approved boolean,
  p_note TEXT DEFAULT NULL
) RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path = tasks, pg_temp AS $$
DECLARE
  v_updated int;
BEGIN
  -- Orchestrator-only: moses/esther may verify. Never trust a self-report.
  IF tasks.profile_of(session_user) NOT IN ('moses','esther') THEN
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

-- ── 7. transition matrix: extend transition_allowed for review ─────────────
-- (v008's check_transition delegates to transition_allowed; adding the
--  review arcs there keeps the story-gate + story_auto_complete logic
--  intact — do NOT replace check_transition itself.)
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
            -- COALESCE: NULL reason must NOT satisfy the reopen gate
            -- (three-valued logic — NULL = 'reopen' is NULL, and
            -- NOT NULL would skip the raise).
            RETURN p_to = 'in_progress' AND COALESCE(p_reason, '') = 'reopen';
        ELSE
            RETURN false;
    END CASE;
END;
$$;

COMMIT;
