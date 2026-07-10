# Cortex Profiles

Optional profiles that layer on top of the neutral enterprise core. Each profile
adds skills, scripts, docs, and cron jobs for a specific use case or user.

## Available Profiles

| Profile | Contents | Use Case |
|---------|----------|----------|
| `personal/` | Bible reading skill, soul-refinement workflow, agent SOUL profiles (Moses, Esther, Titus, Kustos, Gisu) | Luke's personal agent deployment — spiritual disciplines and role definitions |

## Enterprise Core

Items NOT in any profile are part of the **neutral enterprise core** — they ship
with every installation and assume no specific personal or religious context.

## Adding a Profile

1. Create `profiles/<name>/` with `profile.yaml`
2. Add skills under `skills/`, scripts under `scripts/`, docs under `docs/`
3. Register profile-activated install steps in `install.sh`
