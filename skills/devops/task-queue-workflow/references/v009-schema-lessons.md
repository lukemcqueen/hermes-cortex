# v009/v010 Schema Lessons — Task Model v3 (2026-08-24)

Concrete SQL/RLS gotchas hit while building the tasks schema v009 (claim/
report/verify lifecycle) and v010 (transition-matrix fix). These are the
verified fixes — each was reproduced live against a scratch DB battery.

## 1. SECURITY DEFINER + current_user = silent guard failure

A SECURITY DEFINER function runs as its owner (superuser `mycortex`). An
identity guard reading `current_user` therefore sees `'mycortex'`, not the
authenticated caller — every self-only check returns false for real reader
roles, and the migration appears to "work" until a reader tries it.

Fix: use `session_user` inside SECURITY DEFINER functions.

```sql
-- wrong: profile_of(current_user) == 'mycortex' inside the function
-- right: profile_of(session_user) == 'esther' when mycortex_reader_esther calls
```

This is the same trap the existing RLS policy-helper pattern documents (pass
the caller as an ARGUMENT), applied to write functions. v005's
`task_log_event` already used `profile_of(session_user)` — copy that.

## 2. Narrow-write pattern for RLS-read-only fleet rows

Fleet rows are RLS read-only for workers (`is_fleet_writer` gate). Workers
must claim/report on them, so the claim functions are SECURITY DEFINER with
the security INSIDE:

- `claim_slice(p_id, p_assignee)`: WHERE status='pending' + p_assignee must
  equal `profile_of(session_user)` (self-only — an agent claims for itself,
  never assigns work to others). Single UPDATE = atomic, no double-claim.
- `unclaim_slice(p_id, p_reason)`: WHERE status='in_progress' AND
  created_by = `profile_of(session_user)` (only your own work).
- `report_done(p_id, p_evidence)`: same own-work guard → status='review'.
- `verify_slice(p_id, p_approved, p_note)`: guards
  `profile_of(session_user) IN ('moses','esther')` (orchestrator-only);
  approved → completed, rejected → back to in_progress with the gap in plan.

Never blanket-GRANT UPDATE to workers — the function IS the grant.

## 3. Adding a status: BOTH the status CHECK and the column CHECK

The status CHECK (`status IN (...,'review')`) is only half the work. A
separate column-derivation CHECK rejects the new status unless extended in
the SAME migration:

```sql
-- v009 also had to drop + re-add tasks_column_check to admit
-- ("column"='review' AND status='review')
```

Any function setting status directly must set the derivation column in the
SAME UPDATE or the CHECK fires (symptom: claim works, report fails with
"violates check constraint tasks_column_check").

## 4. Never edit an applied migration — ship a NEW file

v009 shipped `transition_allowed` WITHOUT the in_progress→pending arc
(unclaim needs it). Editing v009 did nothing on hosts where v009 already
applied — the runner reported "up to date (version 9)" and skipped. Fix:
v010 re-creates `transition_allowed` with `CREATE OR REPLACE` (idempotent).
Rule: the version-gated runner applies each file once; late fixes need a
new version number.

## 5. Extend the matrix helper, don't replace the trigger

v005/v008's `check_transition` trigger delegates to `transition_allowed()`
and carries story-gate + story_auto_complete GUC logic. Replacing
`check_transition` to add review arcs CLOBBERED that logic (story
auto-complete broke). Correct: extend `transition_allowed` with the new
arcs (`in_progress→review`, `review→completed/in_progress`, and
`in_progress→pending` for unclaim); leave the trigger alone.

## 6. Guarded DO-block grants (role-absent hosts)

`GRANT EXECUTE ... TO mycortex_reader_titus` fails the whole migration on
hosts where that role doesn't exist. Roles are per-host. Guard with a
DO-block that checks `pg_roles` and uses `format('%I')`:

```sql
DO $$ DECLARE r text; BEGIN
  FOREACH r IN ARRAY ARRAY['mycortex_reader_esther','mycortex_reader_titus',...]
  LOOP
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
      EXECUTE format('GRANT EXECUTE ON FUNCTION ... TO %I', r);
    END IF;
  END LOOP;
END $$;
```

(Learnings v001: an unguarded `mycortex_reader_esther` grant killed the
migration on every non-Esther host.)

## 7. psql battery: test as the READER role, not superuser

The L1 schema battery must run claim/unclaim/report/verify as
`mycortex_reader_esther` — running as superuser `mycortex` makes the
self-only guard correctly refuse, which LOOKS like a bug but is the
security working. Battery assertions: superuser claim refused (guard),
reader claim ok, double-claim refused, verify by non-orchestrator refused.

## 8. Reopen path needs the GUC, not a p_reason arg

`completed → in_progress` (reopen) requires the session GUC
`tasks.transition_reason = 'reopen'` set BEFORE the upsert — there is no
`p_reason` parameter on `task_upsert`. A test calling
`task_upsert(p_status=>'in_progress', p_reason=>'reopen')` fails with
"no function matches" — use `SET tasks.transition_reason='reopen'; SELECT
tasks.task_upsert(...)`.
