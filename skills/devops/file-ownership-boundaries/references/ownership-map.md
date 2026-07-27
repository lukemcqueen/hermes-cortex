# File Ownership Map — Quick Reference

## Domain Directory Map

| Domain | Base path | Config | Skills | Scripts | State |
|--------|-----------|--------|--------|---------|-------|
| **Hermes Agent** | `~/.hermes/` | `config.yaml` | `skills/` (built-in) | `scripts/` | Plugins, sessions, memory |
| **Our Repo** | `~/hermes-cortex/` | N/A (git tracked) | `skills/` (cortex-only) | `ops/scripts/` | N/A (git tracked) |
| **Deployed** | `~/.hermes-cortex/` | `skills.yaml` | `skills/` (synced from repo) | `scripts/` (synced from repo) | `state/`, `data/` |

## Ownership Test

```bash
# Quick check: is this file in our repo?
grep -q "hermes-cortex" <<< "$filepath" && echo "OURS" || echo "CHECK FURTHER"
```

## Do NOT Edit (Hermes Defaults)

- `~/.hermes/skills/workflow/task-start/*`
- `~/.hermes/skills/software-development/session-manager/*`
- `~/.hermes/skills/software-development/agent-flow/*`
- `~/.hermes/skills/software-development/reasoning-patterns/*`
- `~/.hermes/skills/software-development/reflexion-check/*`
- `~/.hermes/skills/software-development/agent-contract/*`
- `~/.hermes/skills/software-development/survey-before-action/*`
- `~/.hermes/skills/software-development/change-checklist/*`

## Edit Freely (Our Skills)

- `~/hermes-cortex/skills/devops/*`
- `~/hermes-cortex/skills/software-development/codebase-portability/*`
- `~/hermes-cortex/ops/scripts/*`
- `~/hermes-cortex/docs/*`
