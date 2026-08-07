# Profiles — Optional Add-on Layers

Hermes Cortex ships with a neutral enterprise core. Personal or opinionated content lives in `profiles/` as optional add-on layers.

## Structure

| Profile | Contents |
|---------|----------|
| `personal/` | *Example only — not shipped.* Bible reading skill, soul-refinement workflow, agent SOUL profiles |

## How It Works

Profiles are mounted via symlinks. Each `profiles/<name>/` directory contains files and directories that get symlinked into the repo at their canonical locations. To activate a profile, run:

```bash
# Activate all profiles
bash ops/scripts/manage/profile-link.sh
```

To exclude a profile, remove its symlinks — the profile directory won't be shipped.

## Adding a New Profile

Create a new directory under `profiles/<name>/` with the same structure as the target location in the repo. Then add symlink creation logic to `ops/scripts/manage/profile-link.sh`.

> 💡 Profiles are NOT secrets. Secrets live in `.env` files and `auth.json`, never in profiles.
