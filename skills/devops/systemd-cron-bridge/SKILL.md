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

### How a host learns it needs this

You do not have to reason about it: the doctor reports the gap itself. The
`Cron bridge migration` check counts ENABLED eligible `no_agent` jobs that have
no bridge unit AT ALL, and WARNs with the runbook path in its remediation — so
every host discovers its own un-migrated state on a routine scan, with no
fleet message to lose. Two details make it quiet enough to trust:

- Its eligibility predicate mirrors the generator's (`no_agent` + script, no
  `context_from`/`continuity`, no model pin), so it can never disagree with what
  the bridge can host.
- A unit file in ANY state counts as "considered" — a job deliberately left on
  the Hermes scheduler has a DISABLED unit, so it is never flagged as a gap.

**macOS:** systemd user timers are Linux-only, so the check reports INFO there
rather than warning forever about a mechanism the host cannot use. Do not
"port" the bridge to a host without systemd — that needs a different runner.

## Verify the standalone run actually delivers

A silent watchdog is a poor proof — it exits 0 without exercising delivery. Prove delivery on an **always-output** job: start the bridge service, then confirm the messenger's state/log shows a send at that timestamp. Silent-when-clean stays silent; an always-printing job proves the full systemd → runner → messenger chain.

### ⚠️ Retiring a bridged job: the timer OUTLIVES the job

Removing a job from `~/.hermes/cron/jobs.json` does **not** remove its bridge units.
`cortex-bus-bridge-generate.py` only CREATES units; it has no prune step, so a
retired job keeps firing from its systemd timer and keeps delivering to the user
— with the cron gone from every listing, so nothing looks wrong. Real case
(2026-10-02): `orch-task-board-digest` was retired, yet Luke kept receiving its
daily Telegram digest; the job was absent from `jobs.json` and from the `cronjob`
listing, and only `systemctl --user list-timers | grep board` showed it.

**Retire a bridged job in BOTH places:**
```bash
systemctl --user disable --now cortex-bridge-<name>.timer
rm -f ~/.config/systemd/user/cortex-bridge-<name>.{service,timer}
systemctl --user daemon-reload
systemctl --user list-timers --all | grep <name> || echo "gone"
```
Then remove the `create_cron` block from the installer (keep the name in the
uninstall array so other hosts clean up too), drop the `cron-manifest.yaml`
entry, and grep the docs/skills for the name.

**Pin the retirement with a test, or the next reinstall re-arms it.** Assert
(a) no `create_cron` block for the name, (b) the name is STILL in the uninstall
array, (c) no manifest entry, (d) `bash -n` on the installer exits 0. The
uninstall-only entry is deliberate — `fix-cron-duplicates.py` will warn about it,
and that warning is expected for a retirement rather than a defect to clear.

**Check the live host, not just the repo.** A timer can outlive the job for a
long time before anyone notices, so when a user reports noise from a job you
cannot find, grep the timer list by NAME FRAGMENT (`list-timers --all | grep -i
<word>`) — the unit is named `cortex-bridge-<job>`, which does not appear in any
cron listing.

## Cron → OnCalendar translation

Use `references/systemd-timer-oncalendar.md` — the correct syntax variants (minute-step is `*:0/N:00`, hour-step is `*:00/N:00` *not* `*/N:00:00`, ranges `..`, lists `,`) and the **`systemd-analyze calendar <expr>` validator** that catches a wrong form before it ships (validate every generated value; a step-position typo passes the generator silently). Also `systemd-analyze verify` the unit pair.

## Pitfalls

- **A unit test that invokes a delivery wrapper MUST route hermetically** — pass `--deliver local` + a temp `CORTEX_DEPLOY_HOME` so the run saves to a temp log and can never reach the real messenger. Omitting `--deliver` on a "does it execute" test makes every `pytest` run send a real message to the user's channel (subject `cron:<name>`), a side-effect a unit test must never have.
- **The bridge runs the REPO-path runner, not the deployed copy** — units `ExecStart` the repo `ops/scripts/...` path. When testing, invoke the same path the timers use; a stale deployed copy lacks the latest flags and errors (`unrecognized arguments`). Deploy anyway for consistency but test the live path.
- **Resolve `manage/`-prefixed and `.sh` scripts correctly** — `_resolve_script` must resolve relatives under the deployed scripts dir (so `manage/agent-x.sh` and flat `agent-x.py` both land), else a migrated `.sh` or subdir job silently no-ops.
- **A disabled quality watchdog is how garbage reaches the user** — if a user reports LLM-cron garbage delivered, check the watchdog timer is `active` (a `*/10` scan is the post-flight guard for exactly this); re-enable it before blaming the model. Pinning (`pinned:true`) locks the model but does NOT stop fallback substitution on provider outage — a garbage fallback model still runs and delivers.
- **Migrate in batches with a counter-verification**, not one blind sweep: after each batch, cross-check timer count vs remaining `enabled` no_agent jobs; the two must be disjoint.
- **Completion is a THREE-way check: two owners and zero owners are both failures.** "The timers are active" proves nothing on its own, and the disjointness check above catches only the first mode. Audit all three and report the counts, not a boolean:
  1. **double-run** — timer active AND the job still present in `jobs.json` → two owners, it fires twice.
  2. **orphaned job (the mode nothing reports)** — no timer owns it AND it is gone from `jobs.json` → **silently stopped**. A remove-the-Hermes-row migration creates this whenever a timer was never actually enabled; no scheduler is left looking, so nothing flags it. Detect it by name-set difference, never by counting.
  3. **orphan timer** — a `cortex-bridge-*.timer` unit whose job no longer exists in `jobs.json`.

  Practical form: build the name set from `timers.target.wants/cortex-bridge-*.timer` and the name set from `jobs.json`, then assert `overlap == 0` **and** that every job you intended to migrate lands in exactly one of the two sets.
- **The raw `jobs.json` row field is `id`, not `job_id`.** The `cronjob` tool and `hermes cron` CLI address `job_id`, but the file uses `id` — a mass-removal loop reading `j['job_id']` gets `None` for every row, removes nothing, and still prints one success-shaped line per job.
- **`systemctl --user enable` does NOT start the timer if `timers.target` was already reached** — it only drops the `timers.target.wants/` symlink. On a host already past boot (the normal cron/install context, no DBus session), a fresh `enable` leaves the unit `enabled-but-inactive`, silently never firing. Real case (2026-10-02): all 61 cortex-bridge timers were `enabled` but inactive — the wants symlinks were created after `timers.target` had been reached, no start was issued, and every stale-mycortex-source watchdog showed nothing out of place until the sensor flagged 7 stale sources. Fix: `systemctl --user start timers.target` — starts every wanted-but-inactive timer at once. Then verify with `systemctl --user list-timers --all | grep cortex-bridge` (count ACTIVE, not just ENABLED — `enabled` ≠ `active` for a timer).
