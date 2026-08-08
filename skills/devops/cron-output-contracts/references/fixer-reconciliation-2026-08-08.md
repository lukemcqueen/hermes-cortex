# Fixer Reconciliation Case Study (2026-08-08)

Full diagnosis + retirement record from the F-013 slice of the fleet
self-healing loop. The two fixers `agent-remediate-apply` and
`agent-apply-fixes` both ran every 10 minutes and LOOKED like duplicates.

## What was actually happening

| Cron | Input | Handlers | Deploy |
|------|-------|----------|--------|
| `agent-remediate-apply` (no_agent, 10m, deliver origin) | Sensor cron output dir `~/.hermes/cron/output/<id>/` | Own `fix_*` functions (nginx, service, disk, ollama, web_cache) | Registered in cortex-update.sh |
| `agent-apply-fixes` (no_agent, 10m, deliver local) | Marker files `~/.hermes-cortex/state/remediate/inbox-*.txt` | **Dynamically imported the SAME `fix_*` functions from agent-remediate-apply.py** | NOT registered in cortex-update.sh |

## Root cause 1 — hardcoded job id (the real bug)

`agent-remediate-apply.py` had `SENSOR_JOB_ID = "2c71ffaf3a55"`. The
`agent-remediation-sensor` cron had been recreated and ran under
`0afb2f94d9b7`. The fixer read a nonexistent output dir → "No sensor output
found" → no-op, silently, for weeks. The sensor looked healthy (its own
output dir was fresh) so nothing flagged it.

**Evidence trail:**
- `~/.hermes/cron/output/0afb2f94d9b7/` had fresh `.md` files; the
  hardcoded id's dir did not exist.
- `jobs.json` confirmed: `0afb2f94d9b7 agent-remediation-sensor`.

**Fix:** dynamic discovery by job NAME from `~/.hermes/cron/jobs.json`
(name → id → output dir), fallback = newest `.md` across
`~/.hermes/cron/output/`. Job ids are ephemeral; names are stable contracts.

## Root cause 2 — zombie cron (the "duplicate")

`agent-apply-fixes` was a zombie:
- Its marker input `~/.hermes-cortex/state/remediate/inbox-*.txt` was empty
  since **Jul 20** (dir mtime) — nothing wrote markers anymore.
- Deployed copy was a **Jul 23** artifact in `~/.hermes/scripts/` — the
  script had no `register()` in cortex-update.sh, so it never updated.
- It shared the same fix handlers via dynamic import → true duplication.

**Zombie detection checklist used:** (1) producer still writes? no.
(2) registered for deploy? no. (3) deployed copy fresh? no.
(4) handlers shared? yes. Verdict: remove.

## Retirement of agent-apply-fixes — every touchpoint

1. `cronjob action='remove'` (job `2290a7ccc803`)
2. `install-crons.sh`: removed `create_cron "agent-apply-fixes"` block +
   uninstall-array entry
3. `cortex-update.sh`: removed the `register(...agent-apply-fixes.py...)` line
4. `agent-stale-ref-watchdog.sh`: removed from `CRON_SCRIPTS` array
5. Deployed copies removed (`~/.hermes/scripts/`, `~/.hermes-cortex/scripts/`)
   + `git rm ops/scripts/agent/agent-apply-fixes.py`
6. Docs: `docs/cron-schedules.md`, `docs/cron-jobs-reference.md`,
   `README.md` (pipeline diagram + Recovery table), `docs/setup-reference.md`
   (key-scripts list) — all updated. Historical migration note in
   `docs/fleet-reference.md` left intact (intentional record).
7. `docs/DOCS-INDEX.md` gained entries for the two NEW docs added that day
   (pre-commit DOCS AUDIT warns otherwise).

## Verification sequence that closed the cycle

1. `bash -n` / `py_compile` on all changed scripts
2. Functional run of the repaired fixer from repo copy → read LIVE sensor
   output: "No issues in sensor output — system healthy" (exit 0)
3. `fix-cron-duplicates.py` → "All create names match uninstall arrays"
4. `adversarial-verify.py --file ... --level A2 --gate` → GATE_PASSED
   (3 pre-existing mediums: `shell=True` in run_cmd — accepted cron-runtime
   pattern, not from the edit)
5. Commit → `cortex-update.sh` (deploy; purges governance lock) →
   re-acquire lock → push (pre-push needs: doctor clean = deploy sync, and
   `adversarial-verifier` skill loaded)
6. `cronjob action='run'` on `agent-remediate-apply` → `last_status: ok`
   (refreshes scheduler status — manual `python3 script.py` does NOT)
7. Doctor: 0 fail

## Lessons that generalize

- Exit 0 + fresh logs ≠ the script is acting. Verify it reads the CURRENT
  producer output.
- Two crons that "duplicate" each other deserve a trace of inputs and
  handler origin before any removal — the overlap may be the symptom, not
  the disease.
- When a cron is recreated, every consumer of its output dir must be
  re-pointed — discovery-by-name removes the whole failure class.
