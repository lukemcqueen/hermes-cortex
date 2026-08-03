---
name: hermes-home-cleanup
description: "Use when cleaning ~/.hermes or ~/.hermes-cortex. Verify."
version: 1.0.0
category: devops
author: Esther
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [cleanup, maintenance, hermes, stale-files, disk-space]
    related_skills: [hermes-backup, hermes-cortex-maintenance, repo-organization, survey-before-action]
---

# Hermes Home Cleanup — Safe Stale-File Removal

Use when asked to "clean up" `~/.hermes` or `~/.hermes-cortex`, reclaim disk,
or audit what's safe to delete on a Hermes Agent server.

## Golden Rule

**`~/.hermes/` is Hermes Agent territory.** Most of it is live agent
machinery. Before labeling anything stale, verify against the **agent source**
(`~/.hermes/hermes-agent/`), not just cortex scripts. Two false "stale"
claims cost real time: `state-snapshots/` and `~/.hermes/hooks/` are both
agent-owned. Grep the agent repo before you rm.

## Verification Chain (run BEFORE deleting anything)

```bash
# 1. Is it referenced by the agent source?
grep -rn '<name>' ~/.hermes/hermes-agent/ 2>/dev/null | grep -v node_modules | grep -v venv | grep -v '\.git/'
# 2. Is it referenced by cortex scripts (repo + deployed)?
grep -rn '<name>' ~/hermes-cortex/ ~/.hermes-cortex/scripts/ ~/.hermes/plugins/ 2>/dev/null | grep -v '\.git/'
# 3. Is it a live cron's state file? (renamed crons keep old state filenames!)
python3 -c "import json;d=json.load(open('$HOME/.hermes/cron/jobs.json'));jobs=d.get('jobs',d) if isinstance(d,dict) else d;print([j.get('name') for j in jobs if isinstance(j,dict)])"
# 4. Is it a symlink target or consumed by install scripts?
grep -rn '<name>' ~/.hermes-cortex/scripts/install*.sh ~/hermes-cortex/ops/scripts/install*.sh 2>/dev/null
```

**Zero references in ALL FOUR = candidate. One reference = LIVE. Never guess.**

## LIVE — Do NOT Touch (agent-owned)

| Path | Why live |
|------|----------|
| `~/.hermes/hermes-agent/` | The running agent source + venv + node_modules (CLI at `~/.local/bin/hermes` runs from here) |
| `~/.hermes/state.db` (+ `-wal`/`-shm`) | Live session DB, written every turn. Never delete; checkpoint before copy (`PRAGMA wal_checkpoint(TRUNCATE)`) |
| `~/.hermes/state-snapshots/` | **Agent's own pre-update backup.** `hermes update` creates `*-pre-update/`; restore with `hermes backup restore --state pre-update` or `/snapshot restore`. Config: `updates.pre_update_backup` (quick/full/off), `backup_keep` |
| `~/.hermes/hooks/` | **Agent event-hook directory** (`gateway/hooks.py` scans for `HOOK.yaml` + `handler.py` dirs; web UI `/api/ops/hooks`). The DIRECTORY must stay. Plain files inside are ignored by the agent but may be pre-migration copies — verify, don't assume |
| `~/.hermes/cron/` (jobs.json, executions.db, ticker_*) | Live scheduler state |
| `~/.hermes/gateway.*`, `~/.hermes/processes.json`, `session.id`, `auth.json`, `.env` | Live runtime / secrets |
| `~/.hermes/state/bus-audit-watchdog.json` + `.state` | **LIVE** — the renamed `orch-bus-audit-watchdog` cron uses these EXACT filenames. A renamed cron keeps its old state files |
| `~/.hermes/state/worker-pending/`, `worker-completed/` | Live `agent-worker.py` machinery (`is_completed()` reads `.done` files; deleting can re-trigger old steps) |
| `~/.hermes-cortex/a2a/` | **DEPRECATED dir, zero consumers** — A2A service merged into agent-bus (`src/a2a/` → `ops/services/a2a/` → agent-bus). Bus server serves a HARDCODED card at `/.well-known/agent-card.json`; deployed card is `bus/agent-card.json` (register_orch in cortex-update.sh). `agent-card.json` there was last written 2026-07-27 by a one-off `generate-agent-card.py --output` run — no cron, script, or nginx route reads it. Safe to delete both files (keep the empty dir or remove it; nothing recreates it) |
| `~/.hermes-cortex/state/_cron_find.py` | LIVE — `install-crons.sh` + `install-orch-crons.sh` call it |
| `~/.hermes-cortex/data/loop-governance.db`, `session-embeddings.db` | Live governance/scoring DBs |
| `~/.hermes/bin/uv`, `uvx`, `tirith` | Python toolchain + security scanner (tirith referenced in `config.yaml` `security.tirith_*`) |
| `~/.hermes/node/`, `~/.hermes/lsp/` | Runtimes for desktop/LSP features |
| `~/.hermes/agent-profiles/` | SOUL.md templates — `soul-merge.py` + `pre-commit-score` read them |
| `~/.hermes/AGENTS.md.local`, any `local-*` | Preserved by rule (cortex-update never deletes) |
| `~/.hermes-cortex/state/deploy-backups/`, `scripts-unique-backup-*` | Recent deploy rollback safety nets |

## Truly Stale — Safe to Delete

> **Log policy (Luke, 2026-08-03): keep logs unless actually out of disk space.**
> Rotated log archives are NOT routine cleanup targets — only remove them when
> `df -h` shows real pressure (e.g. < 10% free). Same for any log under
> `~/.hermes/logs/` or `~/.hermes-cortex/logs/`.

| Path | Evidence | Saves |
|------|----------|-------|
| `~/.hermes-cortex/state/loop-governance.db` (0 bytes) | All scripts reference `data/loop-governance.db`, none reference `state/` copy. **Do NOT touch `data/loop-governance.db` — that is the live governance DB.** | 0 bytes (dead file) |
| `~/.hermes/hermes-agent/__pycache__/`, `~/.hermes-cortex/{scripts,offline}/__pycache__/` | Regenerable bytecode (Python rebuilds on import) | ~2.5 MB, 800+ dirs |
| `~/.hermes-cortex/a2a/task-state.db` | Zero references in agent source or cortex scripts (agent-card.json in same dir IS live) | 20 KB |
| `~/.hermes/state/post-commit-notify` + `.log` | Pre-migration leftovers: old hook wrote to `~/.hermes/state/`, current script writes to `.hermes-cortex/state/` | 3.5 KB |
| `~/.hermes/cron/output/<hash>/` subdirs older than 30 days | Scheduler run artifacts; doctor does NOT read cron/output. **Keep loose named deliverables** (e.g. `sustainability-briefing-*.md/.docx`) | several MB, 1000s of files |

## Verify-First (do NOT delete without owner OK)

| Path | Why |
|------|-----|
| `~/.hermes/hooks/post-commit` + `pre-commit` | Pre-migration copies of cortex git hooks (migration-2026-07-08 moved hooks to `~/.hermes-cortex/hooks/`). Agent ignores them (not hook dirs); git uses hooksPath → `~/.hermes-cortex/hooks`. But the DIRECTORY is agent infrastructure and files may be referenced manually — confirm with owner |
| `~/.hermes/state/worker-completed/*.done` | Live machinery reads them; old entries look stale but deleting can re-trigger steps in `agent-worker.py` |
| `~/.hermes/config.yaml.bak.*` | Config backup — "never destroy what you cannot restore." 76 KB, trivial; keep unless disk-critical |
| `post-commit-notify.sh` wiring | Deployed (registered in cortex-update.sh) but NOT the active post-commit hook (that's `post-commit-audit` via symlink). State files are stale, but the script may be intended to be wired — flag, don't delete |
| `~/.hermes-cortex/state/.hermes-session-*.id` | Auto-managed: `purge-stale-governance-locks.py` Phase 2 removes markers older than 24 h. Run that script, don't hand-delete |
| `~/.hermes/models_dev_cache.json` | Regenerable cache BUT `hermes-backup` skill copies it — part of backup surface. Tiny (3 MB); optional |

## Procedure

1. **Survey** — `du -sh ~/.hermes/* ~/.hermes-cortex/* | sort -rh`; identify top consumers
2. **Verify chain** — for each candidate, run the 4-step grep above
3. **Classify** — LIVE (skip) / STALE (delete) / VERIFY-FIRST (flag to owner)
4. **Delete stale only**, from the table above. Never `rm -rf` a LIVE path
5. **Re-verify** — `du -sh` before/after; `hermes doctor` / `cortex-doctor.py --quiet` still clean
6. **Report** — table of what was removed, evidence, space reclaimed
7. **Share** — push any new knowledge (new live/stale entries) back into this skill

## Pitfalls (learned the hard way)

- **Renamed crons keep old state filenames.** `bus-audit-watchdog` → `orch-bus-audit-watchdog` but the script still writes `~/.hermes/state/bus-audit-watchdog.*`. Grep the SCRIPT, not the cron name.
- **`state-snapshots/` is not orphaned** — it's the agent's pre-update rollback. No cortex script references it; the AGENT does.
- **`~/.hermes/hooks/` ≠ git hooks** — it's the agent's event-hook dir. Git hooks live under `~/.hermes-cortex/hooks/` (core.hooksPath).
- **Grep the agent source, not just cortex** — the false-stale items all had agent-side consumers.
- **Never delete while the gateway is writing** — `state.db` needs WAL checkpoint first if copied; never deleted.
- **cortex-update.sh purges governance locks mid-run** — if you run it during a cleanup session, re-acquire `begin_change` before continuing.

## Related

- `hermes-backup` — full backup procedure (use BEFORE aggressive cleanup)
- `hermes-cortex-maintenance` — update workflow
- `repo-organization` — canonical directory structure
