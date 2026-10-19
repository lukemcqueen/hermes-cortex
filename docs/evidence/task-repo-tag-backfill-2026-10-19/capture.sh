#!/usr/bin/env bash
# Evidence capture — cycle 13350 (task-repo-tag-backfill).
#
# Read-only EXCEPT the two restore calls, which are the tool under test: (1) the
# batch retag that is the deliverable, and (2) a no-op restore through the
# DEPLOYED copy, which proves the deployed build PRESERVES a tag it was not asked
# to change (the pre-change build set it to NULL — that is the discriminator).
set -uo pipefail
REPO="$HOME/hermes-cortex"
DEP="$HOME/.hermes-cortex/scripts"
PY="$HOME/.hermes-cortex/venv/bin/python3"
EV="$REPO/docs/evidence/task-repo-tag-backfill-2026-10-19"
OUT="$(mktemp -d)"
trap 'rm -rf "$OUT"' EXIT

# Redact $HOME AT THE GENERATOR (change-checklist Phase 1.5): this transcript is
# committed to a public repo, so no /home/<user> path may appear in it. Applied to
# every emitted line here rather than hand-patched in the committed copy, which
# would then disagree with the commands printed above it.
exec > >(sed -u "s|${HOME}|~|g")

say() { printf '\n=== %s\n' "$*"; }

say "revisions"
echo "base (pre-change) : $(git -C "$REPO" merge-base origin/main HEAD)"
echo "tip  (this cycle) : $(git -C "$REPO" rev-parse HEAD)"

say "DEPLOYED task-db.py carries the preserve-by-default restore"
grep -n '_PRESERVED_COLUMNS = ' "$DEP/task-db.py"
sed -n '/^UPSERT_SQL = /p' "$DEP/task-db.py"

say "the retag: 18 rows whose repo is derivable from the row itself"
echo "input : $EV/retag.json ($(python3 -c "import json;print(len(json.load(open('$EV/retag.json'))))" ) rows)"
echo "census + per-row diff (verify-retag.py, re-read every row)"
python3 "$EV/verify-retag.py" --verify --json "$EV/retag.json"
echo "verify rc=$?"

say "DEPLOYED copy: a restore that does NOT mention repo must not clear it"
NOOP="$OUT/noop.json"
python3 - "$NOOP" <<'PY'
import json, sys
items = json.load(open("docs/evidence/task-repo-tag-backfill-2026-10-19/retag.json"))
probe = [i for i in items if i["id"].startswith("f97dcffe")][0]
probe.pop("repo", None)          # deliberately absent: preserve, do not clear
json.dump([probe], open(sys.argv[1], "w"), indent=2)
print(f"  wrote {sys.argv[1]} for {probe['id'][:8]} WITHOUT a repo key")
PY
echo "  repo BEFORE: $(python3 -c "
import importlib.util
s=importlib.util.spec_from_file_location('t','ops/scripts/manage/task-db.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
print(m.psql(\"SELECT COALESCE(repo,'(null)') FROM tasks.tasks WHERE id='f97dcffe-3acd-454d-a7d1-b767ab53d3da';\"))")"
python3 "$DEP/task-db.py" restore "$NOOP"
echo "  restore rc=$?"
echo "  repo AFTER : $(python3 -c "
import importlib.util
s=importlib.util.spec_from_file_location('t','ops/scripts/manage/task-db.py'); m=importlib.util.module_from_spec(s); s.loader.exec_module(m)
print(m.psql(\"SELECT COALESCE(repo,'(null)')||' tags='||COALESCE(array_to_string(tags,','),'-') FROM tasks.tasks WHERE id='f97dcffe-3acd-454d-a7d1-b767ab53d3da';\"))")"
echo "  (the pre-change build wrote NULL here — a passed row would have read '(null)')"

say "hermetic suite — tests/test_task_db_unit.py (restore + shared-upsert pins)"
"$PY" -m pytest "$REPO/tests/test_task_db_unit.py" -q > "$OUT/pt.txt" 2>&1
echo "pytest rc=$?"
tail -2 "$OUT/pt.txt"

say "sibling suites that exercise the same write path"
"$PY" -m pytest "$REPO/tests/test_task_query_repo_scope.py" \
     "$REPO/tests/test_task_mcp_v3.py" "$REPO/tests/test_task_queue_visibility.py" \
     "$REPO/tests/test_task_queue_evidence.py" -q > "$OUT/sib.txt" 2>&1
echo "sibling pytest rc=$?  (1 = the pre-existing failures below)"
tail -5 "$OUT/sib.txt"

say "doctor (DEPLOYED tree)"
python3 "$REPO/ops/scripts/manage/cortex-doctor.py" --quiet > "$OUT/doc.txt" 2>&1
echo "doctor rc=$?"
grep -o 'Overall:.*' "$OUT/doc.txt" | head -1
grep -nE '^[[:space:]]+❌' "$OUT/doc.txt" | head -5
echo "note: 'Repo clean' warns while this transcript is uncommitted; re-run at the tip."

say "end of capture"
