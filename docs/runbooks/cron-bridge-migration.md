# Runbook — migrating crons to the HC bridge

> **Audience:** any agent migrating a host's `no_agent` crons off the Hermes
> `cronjob` scheduler onto standalone systemd timers. Linux and macOS.
> **Status:** current since the S2a migration (2026-09-30), endpoint corrected
> 2026-10-01.

## Why

The Hermes `cronjob` scheduler only runs while the Hermes gateway process is
alive. Hosting simple `no_agent` jobs on **systemd user timers** removes the
"gateway restart kills cron" coupling: the job fires whether or not Hermes is
up. LLM / chained jobs stay on the Hermes scheduler by design — they need the
agent loop.

## The one rule: exactly ONE owner

A job must be scheduled in exactly one place. A live timer **and** a live
Hermes entry = the job fires **twice**.

> **Remove the Hermes entry — do not merely pause it.**
> A paused row is not the endpoint. It is still an owner-in-waiting: a reinstall
> can resume it, and it leaves two sources of truth for one job. Pausing was an
> intermediate migration step; **removal is the finish line.**

Removal is now safe, because the installers and the doctor both understand
bridge ownership (see *Guards* below) — without them, removing a job was a
trap: `create_cron` recreates any missing job, so the next install would have
resurrected a second owner.

## Ownership marker

systemd's own enable symlink:

```
~/.config/systemd/user/timers.target.wants/cortex-bridge-<name>.timer
```

Present ⇒ the bridge owns the job (it is enabled). Absent ⇒ the bridge does
**not** own it, even if a unit file exists on disk. This is deliberately
filesystem-only: `systemctl --user` needs a DBus session, which a cron /
install / doctor context does not have.

## Procedure (per host)

```bash
cd ~/hermes-cortex && git pull --ff-only
bash ~/hermes-cortex/ops/scripts/cortex-update.sh          # deploys the bridge scripts
```

1. **Generate the units** from the host's own `jobs.json`:
   ```bash
   python3 ~/hermes-cortex/ops/scripts/cortex-bus-bridge-generate.py --dry-run   # inspect first
   python3 ~/hermes-cortex/ops/scripts/cortex-bus-bridge-generate.py
   ```
   It skips LLM / chained / non-translatable jobs and only emits simple
   `no_agent` ones.

2. **Enable the timers** (reload first — new units are invisible otherwise):
   ```bash
   systemctl --user daemon-reload
   systemctl --user enable --now cortex-bridge-<job>.timer
   ```
   ⚠️ **A job already paused for a reason** (e.g. `agent-daily-bible-reading`,
   `agent-hermes-update`, `orch-daily-regression-gate`, `agent-bus-retry-sweep`)
   gets a **disabled** unit — `enable --now` would undo a deliberate pause.
   Leave those paused in Hermes.

3. **Remove the Hermes entry** for every job whose timer you just enabled.
   Always list first — never guess IDs:
   ```bash
   hermes cron list                     # find the job_id by name
   hermes cron remove <job_id>
   ```

4. **Verify** (all three must hold):
   ```bash
   # a) no job is owned twice
   #    (timer active AND still present in Hermes jobs.json)
   # b) no job is owned by neither (silently stopped)
   # c) the doctor is healthy
   python3 ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py --quiet
   ```

## Guards (why this is safe now)

- **Installers** — `create_cron()` in `install-crons.sh` and
  `install-orch-crons.sh` returns early for a bridge-owned job, so an install
  run can never recreate one and hand the bridge a second owner.
- **Doctor** — `_bridge_owned_jobs()` in `cortex_doctor/checks.py` excludes
  bridge-owned names from the expected-cron comparison, the orphan scan and
  the extra-cron scan. Without it, every migrated job reports as `missing`
  (FAIL) the moment its Hermes row is removed.

## Pitfalls

- **`enable --now` on a deliberately paused job.** It un-pauses it. Use
  `enable` alone (or leave it disabled) for jobs paused for a reason.
- **Testing a bridge unit can deliver for real.** The runner takes
  `--deliver <target>`; a `local` target saves to
  `~/.hermes-cortex/cron-output/<job>.log` and never sends, while anything
  else sends Telegram. Never let a test run the wrapper without an explicit
  `--deliver local` + temp `CORTEX_DEPLOY_HOME`.
- **A silent watchdog proves nothing.** Exit 0 with empty stdout is the
  success case, so it cannot show the delivery chain works. Prove delivery on
  an always-output job, or check
  `systemctl --user status cortex-bridge-<job>.service` for
  `code=exited, status=0/SUCCESS` plus the runner's `--deliver` argument.
- **Verify with the marker, not with `is-active`** when running from a
  context that has no user DBus session.
