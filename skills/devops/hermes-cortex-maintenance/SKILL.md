---
name: hermes-cortex-maintenance
version: 1.36.0
category: devops
description: >-
  Maintain an installed Hermes Cortex instance — update both the upstream
  Hermes Agent and the cortex repo layer, merge diverged histories, sync
  skills safely, and troubleshoot common issues. Covers the dual-update
  workflow (hermes update + cortex-update.sh), encrypted brain data backup,
  gbrain import, and recovery techniques.
---

# Hermes Cortex Maintenance v1.36.0

> **Maintaining your Hermes Cortex install** — pulling upstream changes,
> updating gbrain, syncing skills, and recovering when things go wrong.

## Prerequisites

- Hermes Cortex installed at `~/hermes-cortex/`
- Bun at `~/.bun/bin/bun`
- gbrain at `~/.bun/bin/gbrain`
- Ollama running as a systemd user service (or equivalent)

## Daily Auto-Update Timer (3am)

Hermes Cortex includes a **daily auto-update timer** that replaces all
standalone maintenance cron jobs.

### Install the timer

```bash
# Copy the systemd user unit + timer
cp ~/hermes-cortex/ops/install/hermes-cortex-update.{service,timer} ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now hermes-cortex-update.timer
```

Verify it's scheduled:

```bash
systemctl --user list-timers | grep hermes-cortex-update
```

## Dual-Update Workflow (manual)

### 1. Update upstream Hermes Agent

```bash
hermes update --yes
```

### 2. Update the cortex repo layer

```bash
cd ~/hermes-cortex
git pull --ff-only origin main
bash ops/scripts/cortex-update.sh
```

### 3. Merge diverged histories (if pull fails)

If `git pull` fails with diverged branches:

```bash
git fetch origin
git log --oneline HEAD..origin/main | head    # what's new upstream
git log --oneline origin/main..HEAD | head    # what's local-only
git merge origin/main                          # or: git rebase origin/main
# Resolve conflicts, then re-run cortex-update.sh
```

## Encrypted Brain Data Backup

Back up the brain data directory with encryption before major changes:

```bash
BACKUP_DIR=~/backups
mkdir -p "$BACKUP_DIR"
tar czf "$BACKUP_DIR/brain-$(date +%F).tgz" ~/brain
# If encrypted-at-rest storage is required, use gpg/age:
gpg --symmetric --cipher-algo AES256 "$BACKUP_DIR/brain-$(date +%F).tgz"
```

Restore:

```bash
tar xzf "$BACKUP_DIR/brain-<date>.tgz" -C ~
# or first: gpg --decrypt <file> | tar xz -C ~
```

## gbrain Import

```bash
# Import brain pages into gbrain
cd ~/brain && gbrain import --recursive . 2>&1 | tail -5
# Verify
gbrain search "test query" | head
```

## Troubleshooting Common Issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| `cortex-update.sh` purges the governance lock | Known side effect (Pitfall 2) | Re-acquire with `begin_change`; score pending cycles first |
| Skills not deploying | Stub guard blocked repo stub → deployed full | Restore full skill content first |
| Ollama cold-start slow | Model unloaded after idle | `OLLAMA_KEEP_ALIVE >= 5m` in the systemd unit |
| Doctor checksum mismatch | SOURCE header adds 3 lines to deployed files | Use `_content_md5()` (strips header) |
| Gateway restart needed after plugin change | File-on-disk ≠ change-live | Restart session/gateway, verify the change is loaded |

## Recovery Techniques

- **Corrupted deployed copy** → re-run `cortex-update.sh` (it re-syncs from repo)
- **Stuck governance lock** → never force-clear without `end_change` first;
  score the cycle, then `end_change`, then force-clear only if it rejects
- **Missing skill content** → restore from the bus archive or official registry
  (see the skill-restoration workflow)

## Related
- `hermes-cortex` — install/configure guide
- `cortex-preflight` — pre-change checks and deploy pitfalls
- `hermes-recovery` — disaster recovery
- `doc-freshness` — keeping AGENTS.md/SOUL.md current
