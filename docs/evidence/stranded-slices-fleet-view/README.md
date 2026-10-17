# Stranded-slices fleet-view fix — evidence (2026-10-17)

Governed change b1c2756c "fix(doctor): orchestrator uses --repo ALL for
stranded-slice probe, worker stays repo-scoped".

## What changed

`ops/scripts/manage/cortex_doctor/task_integrity.py`:
- Added `_is_orchestrator()` (host-derived, same AGENT_TYPE/IS_ORCHESTRATOR /
  hostname rule as `cortex_doctor.config.AGENT_ROLE`) so the Stranded-slices
  probe queries the fleet view (`task-db list --assigned --repo ALL`) for an
  orchestrator — it must see stranded slices on every host — while a worker
  keeps its repo-scoped view (resolved from the repo root the probe passes as
  cwd, never the invoker's own working directory).

`tests/test_doctor_task_integrity.py`:
- `test_orchestrator_uses_the_fleet_view` — orchestrator sends `--repo ALL`.
- `test_worker_keeps_the_repo_scoped_view` — worker does NOT gain fleet view.
- Existing `test_the_repo_unknown_advisory_is_not_counted_as_a_stranded_slice`
  still proves the real two-line repo-unknown output is judged `COULD NOT
  VERIFY`, not as a phantom strand.

## Verification

- `test-run.txt` — full pytest run: **12 passed**.
- Live doctor (deployed path) run from a NON-repo cwd (agent home):
  `✅ Stranded slices — no pending slice is assigned-and-unstarted`.
- Live doctor run from the repo root: **0 FAIL** total, Stranded slices ✅.
- Commit pushed: `0031deec..b1c2756c main -> main`; header says
  "DOGFOOD PASSED — deployed state verified clean".
