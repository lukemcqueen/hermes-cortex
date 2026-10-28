#!/usr/bin/env bash
# [72b2c69b] live verification of the DEPLOYED path.
#
# Run AFTER `bash cortex-update.sh`, so the doctor and task-db.py under test are
# the DEPLOYED copies — the ones the ~5-minute agent-message-handler tick runs.
#   bash docs/evidence/doctor-ddl-leak/verify.sh
set -u
cd "$(dirname "$0")/../../.." || exit 1
REPO=$PWD
DEPLOY="$HOME/.hermes-cortex"
PY="$HOME/.hermes-cortex/venv/bin/python"
DOCTOR="$DEPLOY/scripts/cortex-doctor.py"
TASK_DB="$DEPLOY/scripts/task-db.py"

echo "# [72b2c69b] the doctor REPORTS the tasks schema; it does not apply it."
echo "# captured-at: $(date -Iseconds)"
echo "# repo HEAD: $(git rev-parse --short HEAD)"
echo "# doctor under test (DEPLOYED): $DOCTOR"
echo

echo "── 1. the DEPLOYED call site carries no --apply-schema ──"
grep -n -- '--apply-schema' "$DOCTOR" "$DEPLOY/scripts/cortex_doctor/checks.py" && echo "FOUND — the leak is still live" || echo "no --apply-schema call in the deployed doctor (grep rc=$?)"
echo

echo "── 2. the DEPLOYED resolver prefers the deployed tree ──"
"$PY" - <<PY
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location("tdb", pathlib.Path("$TASK_DB"))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
for i, c in enumerate(m._migrate_candidates(), 1):
    print(f"  {i}. exists={c.exists()}  {c}")
first = next(c for c in m._migrate_candidates() if c.exists())
print(f"  PICKED: {first}")
print(f"  is the DEPLOYED tree: {str(first).startswith('$DEPLOY/')}")
print(f"  deployed_schema_version(): {m.deployed_schema_version()}")
PY
echo

echo "── 3. live schema BEFORE the doctor run ──"
"$PY" - <<PY
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location("tdb", pathlib.Path("$TASK_DB"))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print("  schema_version    :", m.psql("SELECT COALESCE(MAX(version),0) FROM tasks.schema_version;").strip())
print("  task_upsert count :", m.psql("SELECT count(*) FROM pg_proc WHERE proname='task_upsert';").strip())
PY
echo

echo "── 4. run the DEPLOYED doctor (the active path) ──"
"$DEPLOY/scripts/cortex-doctor.py" > "$HOME/.hermes/cache/scratch/ddl-doctor-run.txt" 2>&1
echo "  doctor rc=$?"
echo "  relevant lines:"
grep -a -E "Task Lifecycle v2 schema" "$HOME/.hermes/cache/scratch/ddl-doctor-run.txt" | sed 's/^/    /'
echo "  FAIL/ERROR lines in the whole run (expected: none):"
grep -a -E "❌|FAIL|Traceback" "$HOME/.hermes/cache/scratch/ddl-doctor-run.txt" | sed 's/^/    /' || echo "    (none)"
echo

echo "── 5. live schema AFTER the doctor run (must be IDENTICAL — no mutation) ──"
"$PY" - <<PY
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location("tdb", pathlib.Path("$TASK_DB"))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print("  schema_version    :", m.psql("SELECT COALESCE(MAX(version),0) FROM tasks.schema_version;").strip())
print("  task_upsert count :", m.psql("SELECT count(*) FROM pg_proc WHERE proname='task_upsert';").strip())
PY
echo

echo "── 6. deployed copy == repo source (ignoring the deploy's SOURCE header) ──"
for pair in "ops/scripts/manage/task-db.py:scripts/task-db.py" \
            "ops/scripts/manage/cortex_doctor/checks.py:scripts/cortex_doctor/checks.py"; do
  src="${pair%%:*}"; dst="$DEPLOY/${pair##*:}"
  a=$(grep -v '^# SOURCE:' "$REPO/$src" | sha256sum | cut -c1-16)
  b=$(grep -v '^# SOURCE:' "$dst" | sha256sum | cut -c1-16)
  printf "  %-46s repo=%s deployed=%s %s\n" "$src" "$a" "$b" \
    "$([ "$a" = "$b" ] && echo SAME || echo DIFFER)"
done
