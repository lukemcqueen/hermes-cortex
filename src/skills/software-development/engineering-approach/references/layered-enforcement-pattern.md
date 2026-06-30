# Layered Enforcement Pattern

A reusable architecture for enforcing agent rules across all projects using three complementary layers: hard gate + soft guidance + safety net.

## The Three Layers

```
Layer 1: Pre-commit hook (hard gate)
  ├── Blocks commits that skip the rule
  ├── Runs automatically per-repo
  └── Bypassable via env var (SKIP_SCORE=1)

Layer 2: SOUL.md directive (soft guidance)
  ├── Every agent session starts with the rule in slot #1
  ├── Zero-touch — one edit, global effect
  └── Non-blocking — agents can still ignore

Layer 3: Cron auditor (safety net)
  ├── Periodic scan catches anything the other layers miss
  ├── Silent when compliant, flags unscoped changes
  └── Delivers to origin (Telegram/Slack) automatically
```

## Why Three Layers

Each layer catches what the previous one misses:

| Layer | Catches | Misses |
|-------|---------|--------|
| Pre-commit hook | Git-tracked repo changes | Ad-hoc edits outside git |
| SOUL.md directive | Every Hermes session | Agents that ignore directives |
| Cron auditor | Everything else | Only runs every N hours |

## When to Use This Pattern

Any time you need to enforce a new rule across all agent sessions and projects:

- Mandatory scoring/auditing of changes
- Required verification steps before commit
- Standardized logging or documentation requirements
- Policy changes that every agent must follow

## Implementation Checklist

1. **Pre-commit hook** — Create a hook script, deploy via `install-score-hook.sh --all`
2. **SOUL.md** — Add a `## Mandatory Directives` section to `~/.hermes/SOUL.md`
3. **Cron auditor** — Create a no_agent watchdog script, register in `install-crons.sh`
4. **Register** — Add new files to `cortex-update.sh` for auto-deployment
5. **Commit + push** — Push to origin/main so future installs get it
6. **Deploy** — Run `cortex-update.sh --force-all` then `install-score-hook.sh --all`

## Files (from hermes-cortex repo)

| Layer | File | Location |
|-------|------|----------|
| 1 | Pre-commit hook | `src/scripts/pre-commit-score` |
| 1 | Hook installer | `src/scripts/install-score-hook.sh` |
| 2 | SOUL.md directive | `~/.hermes/SOUL.md` |
| 3 | Cron auditor | `src/scripts/score-auditor.py` |
| 4 | Cron registration | `src/scripts/install-crons.sh` |
