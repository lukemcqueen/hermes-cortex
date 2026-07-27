# Layered Enforcement Pattern

A reusable architecture for enforcing agent rules across all projects using four complementary layers: unbypassable gate + hard gate + soft guidance + safety net.

## The Four Layers

```
Layer 0: MCP server (unbypassable gate)
  ├── Blocks write tools without active governance lock
  ├── Operates at Hermes tool level — catches ALL changes
  ├── No bypass possible (framework-level enforcement)
  └── Implemented by loop-gov-mcp.py

Layer 1: Pre-commit hook (hard gate)
  ├── Auto-scores every git commit for DB logging
  ├── Runs automatically per-repo
  ├── Bypassable via env var (SKIP_SCORE=1 — REMOVED July 2026)

Layer 2: SOUL.md directive (soft guidance)
  ├── Every agent session starts with the rule in slot #1
  ├── Zero-touch — one edit, global effect
  └── Non-blocking — agents can still ignore

Layer 3: Cron auditor (safety net)
  ├── Periodic scan catches anything the other layers miss
  ├── Silent when compliant, flags unscoped changes
  └── Delivers to origin (Telegram/Slack) automatically
```

## Why Four Layers

Each layer catches what the previous one misses:

| Layer | Catches | Misses |
|-------|---------|--------|
| MCP server (L0) | ALL write operations — git files, config-only, cron migrations, sudoers, nginx, systemd, packages | Nothing (catches at tool level before disk) |
| Pre-commit hook (L1) | Git-tracked repo changes | Ad-hoc edits outside git (but L0 already caught these) |
| SOUL.md directive (L2) | Every Hermes session | Agents that ignore directives |
| Cron auditor (L3) | Everything else | Only runs every N hours |

**Key insight:** The MCP server closes the "config-only blind spot" that previously required a separate watchdog. Cron provider swaps, sudoers edits, nginx config changes, and package installs all go through `write_file`, `patch`, `terminal`, or `cronjob` — all blocked by the MCP server without an active lock. No more gap.

## When to Use This Pattern

Any time you need to enforce a new rule across all agent sessions and projects:

- Mandatory scoring/auditing of changes
- Required verification steps before commit
- Standardized logging or documentation requirements
- Policy changes that every agent must follow

## Implementation Checklist

1. **MCP server** — Register `loop-gov-mcp.py` via `hermes mcp add`. This is the foundation — without it, the remaining layers are advisory.
2. **Pre-commit hook** — Create a hook script, deploy via `install-score-hook.sh --all`
3. **SOUL.md** — Add a `## Mandatory Directives` section to `~/.hermes/SOUL.md`
4. **Cron auditor** — Create a no_agent watchdog script, register in `install-crons.sh`
5. **Register** — Add new files to `cortex-update.sh` for auto-deployment
6. **Commit + push** — Push to origin/main so future installs get it
7. **Deploy** — Run `cortex-update.sh --force-all` then `install-score-hook.sh --all`

## Files (from hermes-cortex repo)

| Layer | File | Location |
|-------|------|----------|
| 0 | MCP server | `mcp-servers/loop-gov-mcp.py` |
| 1 | Pre-commit hook | `ops/scripts/pre-commit-score` |
| 1 | Hook installer | `ops/scripts/install-score-hook.sh` |
| 2 | SOUL.md directive | `~/.hermes/SOUL.md` |
| 3 | Cron auditor | `ops/scripts/manage/governance-auditor.py` |
| 3 | Cron registration | `ops/scripts/install-crons.sh` |
