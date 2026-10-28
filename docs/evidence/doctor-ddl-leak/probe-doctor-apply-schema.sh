#!/usr/bin/env bash
# Measurement probe for backlog 72b2c69b — read-only.
# Establishes: (a) the deployed schema dir's max migration, (b) the repo tree's,
# (c) the LIVE tasks.schema_version, (d) the doctor's call site and
# cmd_apply_schema's candidate order resolve to the REPO tree.
set -u
echo "=== 1. deployed schema dir (~/.hermes-cortex/services/tasks/schema) ==="
ls -1 "$HOME/.hermes-cortex/services/tasks/schema/" 2>/dev/null | sort
echo "=== 2. repo schema dir ==="
ls -1 "$HOME/hermes-cortex/ops/services/tasks/schema/" 2>/dev/null | sort | tail -5
echo "=== 3. which migrate.py does cmd_apply_schema pick? (candidate list, in order) ==="
python3 - <<'PY'
import os, pathlib
home = pathlib.Path.home()
cands = [
    pathlib.Path(os.environ.get("CORTEX_REPO", "")) / "ops/services/tasks/migrate.py",
    home / "hermes-cortex/ops/services/tasks/migrate.py",
    home / ".hermes-cortex/scripts/ops/services/tasks/migrate.py",
    home / ".hermes-cortex/services/tasks/migrate.py",
]
print("CORTEX_REPO env =", repr(os.environ.get("CORTEX_REPO")))
picked = None
for i, c in enumerate(cands, 1):
    exists = c.exists()
    print(f"  {i}. exists={exists}  {c}")
    if exists and picked is None:
        picked = c
print("PICKED:", picked)
PY
echo "=== 4. live tasks.schema_version + task_upsert arity (via the deployed CLI's own psql seam) ==="
"$HOME/.hermes-cortex/venv/bin/python3" - <<'PY'
import importlib.util, pathlib
script = pathlib.Path.home() / ".hermes-cortex/scripts/task-db.py"
spec = importlib.util.spec_from_file_location("tdb", script)
tdb = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tdb)
print("live schema_version :", tdb.psql("SELECT COALESCE(MAX(version),0) FROM tasks.schema_version;").strip())
print("task_upsert count   :", tdb.psql("SELECT count(*) FROM pg_proc WHERE proname='task_upsert';").strip())
print("task_upsert args    :", tdb.psql("SELECT pg_get_function_arguments(oid) FROM pg_proc WHERE proname='task_upsert';").strip())
PY
echo "=== 5. doctor call site ==="
grep -n -- '--apply-schema' "$HOME/.hermes-cortex/scripts/cortex_doctor/checks.py" 2>/dev/null || \
  grep -n -- '--apply-schema' "$HOME/hermes-cortex/ops/scripts/manage/cortex_doctor/checks.py"
echo "=== 6. deployed doctor copy present? ==="
ls -l "$HOME/.hermes-cortex/scripts/cortex_doctor/checks.py" 2>/dev/null || echo "(no deployed checks.py at that path)"
