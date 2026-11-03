#!/bin/bash
# Capture evidence for the task-db UUID-prefix change (cycle 14058).
# Re-runnable: each command prints above its own output; rc measured bare.
set -u

cd "$(dirname "$0")/../../.." || exit 2
REPO="$(pwd)"
OUT="$REPO/docs/evidence/task-uuid-prefix-2026-11-03/transcript.txt"
exec >"$OUT" 2>&1

echo "=== task-db UUID prefix/substring support — evidence (cycle 14058) ==="
echo "captured-at: $(git rev-parse --short=8 HEAD)  ($(date -Is))"
echo

say() { echo; echo "### $*"; }

say "Repo identity"
git log --oneline -1

say "Interpreter: pytest resolver"
PY=$(./ops/scripts/lib/python-with-module.sh --print pytest)
echo "PY=$PY"

say "Unit tests: new UUID-resolution tests (7)"
env -u PYTHONPATH -u PYTHONHOME "$PY" -m pytest tests/test_task_db_unit.py -q -k "resolve_uuid or add_parent_prefix or list_parent_prefix" 2>&1
echo "rc=$?"

say "Unit tests: whole test_task_db_unit.py"
env -u PYTHONPATH -u PYTHONHOME "$PY" -m pytest tests/test_task_db_unit.py -q 2>&1
echo "rc=$?"

say "Adversarial gate: task-db.py (A4)"
python3 ~/.hermes-cortex/scripts/adversarial-verify.py --file ops/scripts/manage/task-db.py --level A4 --gate 2>&1
echo "rc=$?"

say "Adversarial gate: task-mcp.py (A4)"
python3 ~/.hermes-cortex/scripts/adversarial-verify.py --file mcp-servers/task-mcp.py --level A4 --gate 2>&1
echo "rc=$?"

say "Live proof 1: summary with FULL uuid vs 8-char PREFIX (read-only)"
python3 ops/scripts/manage/task-db.py summary c579ef95-39a8-46ad-908d-d799b579e6ae 2>&1 | head -2
python3 ops/scripts/manage/task-db.py summary c579ef95 2>&1 | head -2

say "Live proof 2: no-match prefix fails cleanly"
python3 ops/scripts/manage/task-db.py summary 0000abcd 2>&1 | head -2
echo "rc=$?"

say "Live proof 3: task_add --parent <8-char prefix> lands under the story (mocked-free, real write), then cleanup"
python3 ops/scripts/manage/task-db.py add "ESTHER UUID-PREFIX PROOF slice under story c579ef95 (prefix-parent test)" --parent c579ef95 --kind slice --scope personal --repo ALL --no-notify 2>&1 | head -2
SLICE_ID=$(python3 ops/scripts/manage/task-db.py list --parent c579ef95-39a8-46ad-908d-d799b579e6ae --repo ALL 2>/dev/null | grep "UUID-PREFIX PROOF" | head -1 | awk '{print $1}')
echo "proof slice id: $SLICE_ID"
python3 ops/scripts/manage/task-db.py update "${SLICE_ID}" --status cancelled --reason "prefix-parent live proof cleanup" --no-notify 2>&1 | head -1
docker exec -i mycortex-postgres psql -U mycortex_reader_esther -d mycortex -c "DELETE FROM tasks.tasks WHERE id='${SLICE_ID}' RETURNING id;" 2>&1 | tail -2
docker exec -i mycortex-postgres psql -U mycortex_reader_esther -d mycortex -F'||' -c "SELECT count(*) FROM tasks.tasks WHERE content LIKE '%UUID-PREFIX PROOF%';" 2>&1 | tail -2