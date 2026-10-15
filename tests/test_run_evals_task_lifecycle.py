# test_run_evals_task_lifecycle.py — RED/GREEN for the `task_lifecycle` gate fix.
#
# Bug (2026-10-15, nightly gate RED, slice 758ee911): commit aa293f41 made every
# task query fail closed (return NOTHING) when no repo resolves. The grader's
# `task-db.py list --tag regression-gate` subprocess has no session repo and no
# git repo in its cwd, so it printed the unknown-repo message + 'No tasks found'
# with rc 0, the probe id was never parsed, the gate went RED, and the probe row
# was stranded (cleanup only deleted when the id WAS found).
#
# Fix contract (this test):
#   1. The list subprocess carries an explicit `--repo regression-gate` scope.
#   2. The cleanup deletes by content+creator when the probe id is unknown, so a
#      failed run never strands a probe (zero-residue contract).
#   3. `probe_content` is bound before the try block, so the else-branch cannot
#      NameError (rebuts ADV-6159-2).
#   4. A list run with NO session repo and NO git repo returns zero rows and rc 0
#      (fail-closed — the aa293f41 contract) and leaves zero REGRESSION-GATE rows.

import importlib.util
import inspect
import os
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "run_evals", REPO / "ops" / "scripts" / "manage" / "run-evals.py"
)
assert _SPEC is not None and _SPEC.loader is not None, "spec load failed"
mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(mod)

FUNC_SRC = inspect.getsource(mod._task_lifecycle)


def test_list_call_has_explicit_repo_scope():
    # The construct to match: task-db list with --repo regression-gate. Match the
    # neighbouring tokens, not a bare literal (a docstring could quote it).
    m = re.search(
        r"str\(TASK_DB\),\s*\"list\",\s*\n\s*\"--repo\",\s*\"regression-gate\"",
        FUNC_SRC,
    )
    assert m, (
        "task-db list subprocess must pass --repo regression-gate "
        "(aa293f41 fail-closed regression); grep run-evals.py _task_lifecycle"
    )


def test_probe_content_bound_before_try():
    # ADV-6159-2 rebuttal: probe_content must be assigned BEFORE the try block so
    # the content-based cleanup branch is always safe, never an unbound NameError.
    defline = FUNC_SRC.index("probe_content = f\"REGRESSION-GATE-PROBE-")
    tryline = FUNC_SRC.index("try:")
    assert defline < tryline, "probe_content must be defined before the try block"


def test_cleanup_has_content_delete_branch():
    # The finally-cleanup must delete by content+creator when probe id is unknown.
    assert "content = '{probe_content}' AND created_by = '{probe_creator}'" in FUNC_SRC
    assert "finally:" in FUNC_SRC


def test_unsessioned_list_fails_closed_zero_rows():
    # The aa293f41 contract, live: task-db list with no session repo and a cwd
    # that is not a git repo returns ZERO rows + rc 0 (not an all-repos dump).
    env = dict(os.environ)
    env.pop("CORTEX_SESSION_REPO", None)
    r = subprocess.run(
        ["python3", str(REPO / "ops" / "scripts" / "manage" / "task-db.py"),
         "list", "--tag", "regression-gate"],
        capture_output=True, text=True, timeout=60, cwd="/tmp", env=env,
    )
    assert r.returncode == 0, f"unsessioned list must be fail-closed rc0: {r.stderr[-200:]}"
    assert "No tasks found" in r.stdout, f"expected 'No tasks found': {r.stdout[-200:]}"
    assert "REGRESSION-GATE-PROBE" not in r.stdout, (
        "assertion fails-closed and must NOT resurrect a stranded probe"
    )