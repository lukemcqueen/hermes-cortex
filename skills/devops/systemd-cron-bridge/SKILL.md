---
name: systemd-cron-bridge
version: 1.0.0
category: devops
description: "Use when hosting no_agent crons on systemd timers."
author: Hermes Cortex
license: MIT
metadata:
  hermes:
    tags: [cron, systemd, scheduler, independence, watchdog]
---

# systemd-cron-bridge — standalone hosting for no_agent crons

When a no_agent script cron must keep firing **even if the Hermes gateway / `cronjob` scheduler process is down**, host it on systemd user timers instead. This removes "gateway restart kills cron" and the "gateway down → N no_agent jobs don't run" coupling. Only **simple** no_agent jobs qualify (a script + deliver, no `context_from`/`continuity`/model pin); LLM and chained jobs stay on the Hermes `cronjob` scheduler by design (they need the agent loop).

## Pieces

- `cortex-bus-bridge-run.py` — the **delivery wrapper**. Runs the job's script standalone, delivers non-empty stdout. **empty stdout = silent** (the watchdog pattern is preserved). Source the cortex `.env` so tokens/models resolve.
- `cortex-bus-bridge-generate.py` — reads `~/.hermes/cron/jobs.json`, writes a user-scope systemd pair `~/.config/systemd/user/cortex-bridge-<job>.{service,timer}` per simple no_agent job, converting the cron expr to `OnCalendar`. Skips LLM/chained jobs and schedules it can't translate.

## `--deliver` routing (the load-bearing decision)

The wrapper MUST take `--deliver <target>` and route by it. **`local` = save-only to `<CORTEX_DEPLOY_HOME>/cron-output/<job>.log`, never a send; anything else = Telegram.** Do NOT let the runner default to Telegram: many no_agent jobs (`agent-message-handler`, `agent-learning-collector`, `agent-push-metrics`, `agent-session-mine`) are internal collectors whose stdout must never reach the channel. Migrating one without `--deliver local` silently spams the home channel with internal output.

## Migration = TWO steps per job, or you DOUBLE-RUN

For each job: `systemctl --user enable --now cortex-bridge-<job>.timer` **then
REMOVE the matching Hermes entry** — `hermes cron list` to find the job's `id`,
then `hermes cron remove <id>` (always list first; never guess IDs). A live
timer + a live `cronjob` tick = the job runs twice.

**Remove, do not merely pause.** A paused row is not the endpoint: it is an
owner-in-waiting (a reinstall can resume it) and it leaves two sources of truth
for one job. Pausing was an intermediate migration step; removal finishes it.
Removal is safe now because the installers, the doctor and the manifest check
all understand bridge ownership — see *Guards* below. (Before those guards,
removing a job was a trap: `create_cron` recreates any missing job, so the next
install would resurrect a second owner.)

**Leave already-paused jobs alone.** A job paused for a reason (bible-reading,
hermes-update, regression-gate, bus-retry-sweep) must get a `disabled` (not
enabled) unit — `enable --now` undoes the pause. Those are **not** migration
targets: keep their Hermes entry, still paused.

**Ownership marker.** `~/.config/systemd/user/timers.target.wants/cortex-bridge-<name>.timer`
present ⇒ the bridge owns the job. This is filesystem-only on purpose (no DBus
session is available in a cron/install/doctor context). A **disabled** unit is
absent from `wants/`, so a paused-for-a-reason job is never mistaken for a
migrated one.

Full per-host procedure, the 3-part verification, and pitfalls:
`docs/runbooks/cron-bridge-migration.md`.

### Guards that make removal safe

- **Installers** — `create_cron()` in `install-crons.sh` and
  `install-orch-crons.sh` returns early for a bridge-owned job, so an install
  run can never recreate one and hand the bridge a second owner.
- **Doctor** — `cortex_doctor/checks.py::_bridge_owned_jobs()` excludes bridged
  names from the expected-cron, orphan and extra scans.
- **Manifest** — `cron_manifest.py::check_drift()` skips bridged names, so a
  migrated job is not reported as "declared in manifest, absent from live jobs"
  (that FAIL blocks the pre-push deploy-sync gate).

## Verify the standalone run actually delivers

A silent watchdog is a poor proof — it exits 0 without exercising delivery. Prove delivery on an **always-output** job (e.g. `orch-task-board-digest`): start the bridge service, then confirm the messenger's state/log shows a send at that timestamp. Silent-when-clean stays silent; an always-printing job proves the full systemd → runner → messenger chain.

## Cron → OnCalendar translation

Use `references/systemd-timer-oncalendar.md` — the correct syntax variants (minute-step is `*:0/N:00`, hour-step is `*:00/N:00` *not* `*/N:00:00`, ranges `..`, lists `,`) and the **`systemd-analyze calendar <expr>` validator** that catches a wrong form before it ships (validate every generated value; a step-position typo passes the generator silently). Also `systemd-analyze verify` the unit pair.

## Pitfalls

- **A unit test that invokes a delivery wrapper MUST route hermetically** — pass `--deliver local` + a temp `CORTEX_DEPLOY_HOME` so the run saves to a temp log and can never reach the real messenger. Omitting `--deliver` on a "does it execute" test makes every `pytest` run send a real message to the user's channel (subject `cron:<name>`), a side-effect a unit test must never have.
- **The bridge runs the REPO-path runner, not the deployed copy** — units `ExecStart` the repo `ops/scripts/...` path. When testing, invoke the same path the timers use; a stale deployed copy lacks the latest flags and errors (`unrecognized arguments`). Deploy anyway for consistency but test the live path.
- **Resolve `manage/`-prefixed and `.sh` scripts correctly** — `_resolve_script` must resolve relatives under the deployed scripts dir (so `manage/agent-x.sh` and flat `agent-x.py` both land), else a migrated `.sh` or subdir job silently no-ops.
- **A disabled quality watchdog is how garbage reaches the user** — if a user reports LLM-cron garbage delivered, check the watchdog timer is `active` (a `*/10` scan is the post-flight guard for exactly this); re-enable it before blaming the model. Pinning (`pinned:true`) locks the model but does NOT stop fallback substitution on provider outage — a garbage fallback model still runs and delivers.
- **Migrate in batches with a counter-verification**, not one blind sweep: after each batch, cross-check timer count vs remaining `enabled` no_agent jobs; the two must be disjoint.
