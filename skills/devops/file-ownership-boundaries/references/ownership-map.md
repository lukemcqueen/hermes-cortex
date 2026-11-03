# File Ownership Map — Quick Reference

## Domain Directory Map

| Domain | Base path | Config | Skills | Scripts | State |
|--------|-----------|--------|--------|---------|-------|
| **Hermes Agent** | `~/.hermes/` | `config.yaml` | `skills/` (built-in) | `scripts/` | Plugins, sessions, memory |
| **Our Repo** | `~/steadfaste-fleet/` | N/A (git tracked) | `skills/` (cortex-only) | `ops/scripts/` | N/A (git tracked) |
| **Deployed** | `~/.steadfaste-fleet/` | `skills.yaml` | `skills/` (synced from repo) | `scripts/` (synced from repo) | `state/`, `data/` |

## Ownership Test

```bash
# Quick check: is this file in our repo?
grep -q "steadfaste-fleet" <<< "$filepath" && echo "OURS" || echo "CHECK FURTHER"
```

## Do NOT Edit (Hermes Defaults)

- `~/.hermes/skills/workflow/task-start/*`
- `~/.hermes/skills/software-development/session-manager/*`
- `~/.hermes/skills/software-development/agent-flow/*` (absorbed reasoning-patterns 2026-08-20)
- `~/.hermes/skills/software-development/reflexion-check/*`
- `~/.hermes/skills/software-development/agent-contract/*`
- `~/.hermes/skills/software-development/survey-before-action/*` (absorbed cortex-preflight 2026-08-20)
- `~/.hermes/skills/software-development/change-checklist/*`

## Edit Freely (Our Skills)

- `~/steadfaste-fleet/skills/devops/*`
- `~/steadfaste-fleet/skills/software-development/codebase-portability/*`
- `~/steadfaste-fleet/ops/scripts/*`
- `~/steadfaste-fleet/docs/*`
