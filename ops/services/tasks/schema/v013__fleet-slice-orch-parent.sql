-- ============================================================================
-- tasks schema v013 — check_tenant: allow fleet slice under orchestrator-owned
-- personal story (scope-versus-scrub contradiction, backlog f0c6afbf)
--
-- The pass protocol creates a fleet slice (claimable fleet-wide) beneath a
-- personal story it owns. Because an executable plan legitimately cites file
-- paths, the B-5 scrub gate (content_ok_for_fleet, RLS WITH CHECK) degrades that
-- path-citing STORY to scope=personal — correct behaviour: the gate exists to
-- keep PII (abs-path/email/IP) OUT of fleet rows (RLS-visible to every profile)
-- and is a deliberate fail-closed invariant, never to be weakened. But that
-- correctly-degraded personal story then forced a fleet slice under it to be
-- REFUSED by tasks.check_tenant() ("slice scope (fleet) exceeds parent scope
-- (personal)"), making the pass-protocol fleet form unusable for real plans.
--
-- Fix (narrow, Option B): relax check_tenant so a PII-clean fleet slice may sit
-- under a personal STORY owned by an ORCHESTRATOR (moses/esther — same hardcoded
-- allowlist verify_slice uses, v009). Safety: the SLICE's own content is still
-- enforced PII-clean by RLS WITH CHECK (content_ok_for_fleet) AND by the
-- fleet-writer role check, so no path/email/IP can leak into a fleet row. The
-- relaxation ONLY widens WHO may parent a fleet slice, never what a fleet row
-- may contain. Non-orchestrator personal parents remain refused (coherence).
--
-- Test: tests/test-tasks-schema.sh AC-L1-11c (RED → GREEN).
-- Additive CREATE OR REPLACE, version-gated. Single transaction.
-- ============================================================================

BEGIN;

CREATE OR REPLACE FUNCTION tasks.check_tenant()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    v_parent_scope TEXT;
    v_parent_kind  TEXT;
    v_parent_owner TEXT;
BEGIN
    IF NEW.parent_id IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT scope, kind, created_by INTO v_parent_scope, v_parent_kind, v_parent_owner
    FROM tasks.tasks
    WHERE id = NEW.parent_id;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'parent task % not found or not visible', NEW.parent_id;
    END IF;
    IF v_parent_kind IS DISTINCT FROM 'story' THEN
        RAISE EXCEPTION 'parent task % is not a story (kind=%)',
            NEW.parent_id, COALESCE(v_parent_kind, 'flat');
    END IF;
    -- v013: allow a fleet slice under a PERSONAL story owned by an orchestrator
    -- (moses/esther). The parent's path-citing plan correctly degraded to
    -- personal via the B-5 scrub gate; the slice's OWN content is still held
    -- PII-clean by RLS WITH CHECK. Other personal parents keep the coherence
    -- rule (no fleet slice under a non-orchestrator personal story).
    IF NEW.scope = 'fleet' AND v_parent_scope = 'personal'
       AND v_parent_owner NOT IN ('moses','esther') THEN
        RAISE EXCEPTION 'slice scope (fleet) exceeds parent scope (personal)';
    END IF;
    RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION tasks.check_tenant() FROM PUBLIC;

COMMIT;