# Cron Consolidation Cleanup Procedure

## The Problem

When you consolidate crons (removing old ones, creating unified replacements),
you must clean up in **all layers** or the doctor (cortex-doctor.py) will
report false failures.

## The Five Cleanup Points

Every cron appears in multiple places. Removing it requires removing ALL:

| # | Layer | File | What to do |
|---|-------|------|------------|
| 1 | **Creation block** | `install-crons.sh` or `install-orch-crons.sh` | Remove the `create_cron` block |
| 2 | **Uninstall array** | `install-crons.sh` or `install-orch-crons.sh` | Remove the cron name from `for job in \\` list |
| 3 | **Running cron** | Hermes cron scheduler | `cronjob action='remove' job_id=<id>` |
| 4 | **Script registration** | `cortex-update.sh` | Remove `register()` call if the script no longer exists |
| 5 | **Docs sweep** | Multiple doc files (see below) | Update or remove references |

## Layer 5 — Docs Sweep

When retiring a pipeline (not just a single cron), you must sweep ALL docs files that reference the old system. Run a `search_files()` for the old cron/script name across the entire repo, then check each file below.

### Docs sweep checklist

| File | Check for |
|------|-----------|
| `AGENTS.md` | Skill collection pipeline section (may exist in 2 places) |
| `docs/pipeline-reference.md` | Pipeline flow table, processing section |
| `docs/fleet-reference.md` | Cron table entries |
| `docs/cron-schedules.md` | Cron table entries |
| `docs/SKILLS-MANIFEST.md` | Infrastructure scripts table |
| `docs/integration-audit.md` | Old pipeline references |
| `docs/migration-*.md` | Historical migration notes referencing old names |
| `skills/*/<name>/SKILL.md` | Any skill that references the old cron/script/pipeline |
| `ops/scripts/install/install-orch-crons.sh` | Cron prompt text that references old scripts |
| `ops/scripts/manage/*.sh` / `*.py` | Docstrings/comments mentioning old pipeline |

Do NOT stop at removing the old name — verify the new name is present in the same files where appropriate.

## What Happens If You Skip a Layer

| Skipped | Result |
|---------|--------|
| Uninstall array | Doctor shows `❌ Crons missing — N missing: <name>` — the doctor reads uninstall arrays as its "expected crons" list |
| Creation block | New installs will still try to create the cron (harmless but wrong) |
| Running cron | The cron still runs even though it's "removed" from the system |
| Script registration | Deployed scripts pile up on agents |

## Verification

After all four layers:

```bash
cronjob action='list'          # verify the cron is gone
python3 ~/hermes-cortex/ops/scripts/manage/cortex-doctor.py --quiet
# Expected: ✅ Crons registered (not ❌ Crons missing)
```

## Real Example

Consolidating 5 crons into `orch-skill-lifecycle` required removing from:
- `install-crons.sh` (creation block + uninstall array) — moved to orch installer
- `install-orch-crons.sh` (added creation block + uninstall array)
- `cortex-update.sh` (removed 3 script registrations)
- Running scheduler (5 cronjob remove calls)
- `core/governance/update.sh` (removed symlink)
