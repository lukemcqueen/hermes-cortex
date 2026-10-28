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

echo "── 1. the DEPLOYED call site carries no --apply-schema CALL ──"
# Match the CONSTRUCT (the quoted argument a call passes), never the bare token:
# the bare token also matches the comment that EXPLAINS the fix, which would
# report the explanation as the defect (reflexion-check §4).
grep -n -E '["'"'"']--apply-schema["'"'"']' "$DOCTOR" "$DEPLOY/scripts/cortex_doctor/checks.py" \
  && echo "FOUND — the leak is still live" \
  || echo "rc=$? (1 = no quoted --apply-schema argument in the deployed doctor)"
echo "  and the read-only probe IS present in the deployed doctor:"
grep -n 'FROM tasks.schema_version' "$DEPLOY/scripts/cortex_doctor/checks.py" | sed 's/^/    /'
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
echo "  lines STARTING with the FAIL marker in the whole run (expected: none):"
# Anchor on the marker at line start: the bare token also appears inside prose
# ("resolve each ⚠️ or ❌ above"), which would report the summary as a failure.
grep -a -E "^[[:space:]]*❌" "$HOME/.hermes/cache/scratch/ddl-doctor-run.txt" | sed 's/^/    /' \
  || echo "    (none — no check FAILED)"
echo

echo "── 4b. the MIGRATION RUNNER never ran during the doctor run ──"
# migrate.py prints 'applying vNNN …' / 'schema now at version N'. Their absence
# is the decisive signal: the DDL path is gone, not merely idempotent.
for pat in 'applying v' 'schema now at version'; do
  n=$(grep -c -a -F "$pat" "$HOME/.hermes/cache/scratch/ddl-doctor-run.txt" || true)
  printf "    %-24s occurrences in the doctor transcript: %s (expected 0)\n" "'$pat'" "$n"
done
echo "    NOTE: the uncommitted-migration scenario is NOT re-run as a live probe."
echo "    Reproducing it would attempt a PRODUCTION write if the fix ever regressed,"
echo "    so it is demonstrated by the absent call site + the RED test instead"
echo "    (a defensive no-op on destructive steps without explicit instruction)."
echo

echo "── 4c. the NEW divergence WARN actually FIRES (probe the gate itself) ──"
# Point the resolver at a DEPLOYED tree that is one migration ahead of the live
# DB. A check that never fires is not a check, so the negative direction is
# demonstrated too — and because the doctor only reads now, this probe cannot
# touch production. (A unique dir per run: no rm -rf in an unattended job.)
FAKE="$(mktemp -d "$HOME/.hermes/cache/scratch/ddl-fake-deploy-XXXXXX")"
mkdir -p "$FAKE/services/tasks/schema"
printf -- '-- probe only; never applied\n' > "$FAKE/services/tasks/schema/v017__probe-noop.sql"
echo "  fake deployed tree: $FAKE (declares v017; live DB is at 16)"
CORTEX_DEPLOY_HOME="$FAKE" "$DEPLOY/scripts/cortex-doctor.py" \
  > "$HOME/.hermes/cache/scratch/ddl-doctor-ahead.txt" 2>&1
echo "  doctor rc=$?"
grep -a -E "Task Lifecycle v2 schema" "$HOME/.hermes/cache/scratch/ddl-doctor-ahead.txt" | sed 's/^/    /'
echo "  and the fake migration was NOT applied (live version must still be 16):"
"$PY" - <<PY
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location("tdb", pathlib.Path("$TASK_DB"))
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print("    live schema_version:", m.psql("SELECT COALESCE(MAX(version),0) FROM tasks.schema_version;").strip())
PY
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

echo "── 6. deployed copy == repo source (ignoring the deploy's header block) ──"
# The deploy prepends TWO header lines (`# SOURCE:` and `# Do NOT edit this
# file …`) plus a blank line. An earlier revision of this script stripped only
# the SOURCE line and therefore reported every freshly-deployed file as DIFFER —
# a false alarm caused by the probe, not by the deploy. Strip the whole header
# block and ignore the resulting blank-line shift; print the residual diff.
for pair in "ops/scripts/manage/task-db.py:scripts/task-db.py" \
            "ops/scripts/manage/cortex_doctor/checks.py:scripts/cortex_doctor/checks.py"; do
  src="${pair%%:*}"; dst="$DEPLOY/${pair##*:}"
  if diff -B <(grep -vE '^# (SOURCE|Do NOT edit this file)' "$REPO/$src") \
             <(grep -vE '^# (SOURCE|Do NOT edit this file)' "$dst") > /dev/null; then
    printf "  %-46s SAME (modulo the deploy header)\n" "$src"
  else
    printf "  %-46s DIFFER — residual diff:\n" "$src"
    diff -B <(grep -vE '^# (SOURCE|Do NOT edit this file)' "$REPO/$src") \
            <(grep -vE '^# (SOURCE|Do NOT edit this file)' "$dst") | sed 's/^/      /'
  fi
done
