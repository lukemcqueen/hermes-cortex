#!/usr/bin/env bash
# Live round trip for the v016 orchestrator write surface (backlog row 9fb2ddb6).
#
# Design: docs/design/task-model-v3-orchestrator-half.md rev 2 §4.2–4.4.
# Every value below is read back with an INDEPENDENT psql query — the CLI's own
# checkmark is never the evidence. The two scratch rows are cancelled (not
# deleted) at the end, so the transcript shows the whole lifecycle.
set -u
cd "$HOME/hermes-cortex"
TD="python3 ops/scripts/manage/task-db.py"
R="docker exec mycortex-postgres psql -U mycortex_reader_esther -d mycortex -t -A"
row() { $R -c "SELECT status || ' | col=' || COALESCE(\"column\",'<null>') || ' | plan=' || COALESCE(plan,'<null>') || ' | assignee=' || COALESCE(assignee,'<null>') || ' | corr=' || COALESCE(correlation_id,'<null>') || ' | deps=' || COALESCE(array_length(depends_on,1)::text,'0') FROM tasks.tasks WHERE id='$1';"; }

echo "### 0. schema under test"
$R -c "SELECT 'tasks schema_version=' || max(version) FROM tasks.schema_version;"
$R -c "SELECT 'task_upsert params=' || (SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='tasks' AND p.proname='task_upsert');"

echo
echo "### 1. add --plan  (the plan write surface, item (a))"
# A slice needs a parent (v013 tasks_hierarchy_coherence) — measured on the
# first run of this script, which is why the story exists here.
$TD add "RT-v016 scratch story" --kind story --priority 0 --repo hermes-cortex --no-notify
STORY=$($R -c "SELECT id FROM tasks.tasks WHERE content='RT-v016 scratch story' ORDER BY created_at DESC LIMIT 1;")
echo "STORY=$STORY"
$TD add "RT-v016 dependency slice" --kind slice --parent "$STORY" --priority 0 --repo hermes-cortex --no-notify
$TD add "RT-v016 scratch slice" --kind slice --parent "$STORY" --priority 0 --repo hermes-cortex \
    --plan 'step one; step two' --no-notify
A=$($R -c "SELECT id FROM tasks.tasks WHERE content='RT-v016 dependency slice' ORDER BY created_at DESC LIMIT 1;")
SID=$($R -c "SELECT id FROM tasks.tasks WHERE content='RT-v016 scratch slice' ORDER BY created_at DESC LIMIT 1;")
echo "A=$A"; echo "SID=$SID"
echo "read back: $(row "$SID")"

echo
echo "### 2. --status in_progress (ordinary lifecycle, unchanged)"
$TD update "$SID" --status in_progress --no-notify
echo "read back: $(row "$SID")"
$TD update "$A" --status in_progress --no-notify >/dev/null

echo
echo "### 3. METADATA-ONLY update on an in_progress row (no --status) — the §3 trap"
$TD update "$SID" --plan 'revised plan; more detail' --assignee joseph \
    --correlation-id corr-rt-v016 --depends-on "$A" --no-notify
echo "read back: $(row "$SID")"
echo "  ^ status MUST still be in_progress and col MUST be in_progress (NULL status would derive col=todo and raise 23514)"
echo "  ^ plan reassigned via read-back: $($R -c "SELECT plan FROM tasks.tasks WHERE id='$SID';")"
echo "  ^ worker-visible (list --assigned):"
$TD list --repo ALL --assigned --limit 50 2>/dev/null | grep -F "$SID" || echo "     (row not in this view)"

echo
echo "### 4. same-status + metadata must NOT be swallowed by the no-op gate"
$TD update "$SID" --status in_progress --plan 'third revision' --no-notify
echo "read back: $(row "$SID")"

echo
echo "### 5. honesty gates"
$TD update "$SID" --no-notify 2>&1 | tail -1
$TD update "$SID" --plan '   ' --no-notify 2>&1 | tail -1
$TD update "$SID" --depends-on 'not-a-uuid' --no-notify 2>&1 | tail -1
$TD update "$SID" --assignee '../../etc/passwd' --no-notify 2>&1 | tail -1

echo
echo "### 6. the VACUOUS-STATUS trap is still real on the live store (p_status omitted)"
docker exec mycortex-postgres psql -U mycortex_reader_esther -d mycortex -t -A \
  -v ON_ERROR_STOP=1 -c "SELECT tasks.task_upsert(p_id=>'$SID', p_plan=>'from a null status');" 2>&1 | tail -2
echo "read back (plan must NOT be 'from a null status'): $(row "$SID")"

echo
echo "### 7. cleanup — cancel both scratch rows (cancelled, not deleted)"
$TD update "$SID" --status cancelled --no-notify
$TD update "$A" --status cancelled --no-notify
echo "final slice: $(row "$SID")"
echo "final slice: $(row "$A")"
echo "final story: $($R -c "SELECT status FROM tasks.tasks WHERE id='$STORY';") (auto-completes when the last slice is cancelled)"
