# Rename: orch-backlog-driver → orch-bus-worker (2026-10-14)

## What and why

The orchestrator's autonomous work driver was renamed `orch-backlog-driver` →
`orch-bus-worker`. It does the same job (F-023 loop: pull pending + inbox-sourced
tasks, drive the top actionable one to a verified close), but the name now
reflects that its real input is the **bus** — every agent's routed suggestions
(PROPOSAL / ISSUES / IMPROVEMENTS / STRANDED_SKILL_LAND) become tracked tasks it
picks up. The old "backlog" name under-stated that; it also carried a stale
`NEVER_RESUME` hold from 2026-09-06 (the cron that powers the fleet
skill-improvement loop was paused). It is now a scheduled, enabled job.

## Convention table

| Item | Old | New |
|------|-----|-----|
| Cron job | `orch-backlog-driver` | `orch-bus-worker` |
| Skill dir | `skills/devops/orch-backlog-driver/SKILL.md` | `skills/devops/orch-bus-worker/SKILL.md` |
| Skill `name:` frontmatter | `orch-backlog-driver` | `orch-bus-worker` |
| Installer (create + uninstall array) | `orch-backlog-driver` | `orch-bus-worker` |
| `cron-manifest.yaml` entry | `orch-backlog-driver` | `orch-bus-worker` |
| Classifier routine token | `r"backlog"` | `r"backlog", r"bus-worker"` |
| `NEVER_RESUME` set | contained `dbcdec6bb40d` | removed (job deliberately resumed) |

The old cron `orch-backlog-driver` is removed; the new one is scheduled at
`0 8,14,20,22 * * *` (same cadence).

## How to apply on a host

A host converges by pulling origin and running cortex-update (deploys the renamed
skill + installer). On orchestrators (moses/esther), the live cron was already
recreated; if a host shows the old name, `cortex-update.sh` recreates it from the
installer's create block (the old paused job is removed by the uninstall array).

macOS hosts: no systemd cron — the Hermes cron scheduler handles it; pull + update.

## Verification

```bash
cronjob action=list                      # orch-bus-worker: state=scheduled
python3 tests/test_autonomy_classifier.py # all pass (bus-worker classifies routine)
grep -rn "orch-backlog-driver" ops/ tests/  # only historical-prose mentions remain
```

## Symptom → cause → fix

| Symptom | Cause | Fix |
|---------|-------|-----|
| `orch-bus-worker` not in cron list | old paused job removed, new not recreated | run `cortex-update.sh` (installer recreates it) |
| STRANDED_SKILL_LAND message not tracked | handler not wired for the subject | deploy handler; it now creates a task row + leaves it queued |
| New cron auto-paused shortly after start | stale `NEVER_RESUME` id | remove the id from the resumed job's set (done) |
