# Auto-Profile Detection — Shell Wrapper Pattern

Auto-inject `hermes --profile <name>` when your current directory matches a registered project. Zero thinking, zero extra typing.

## The Pattern

A shell function wraps `hermes` to check `~/.cortex-projects.json` before dispatching:

```bash
# ~/.zshrc or ~/.bashrc
hermes() {
  local profile
  profile=$(python3 -c "
import json, os
cwd = os.getcwd()
try:
  with open(os.path.expanduser('~/.cortex-projects.json')) as f:
    for p in json.load(f):
      if cwd.startswith(p['location']):
        print(p.get('profile', p['project_name']))
        break
except: pass
" 2>/dev/null)
  if [ -n "$profile" ]; then
    command hermes --profile "$profile" "$@"
  else
    command hermes "$@"
  fi
}
```

## How It Works

- `cd ~/Developer/ACME/acme-works && hermes` → auto-injects `--profile acme-works`
- `cd ~/Developer/PERSONAL/echokorean && hermes` → auto-injects `--profile echokorean`
- `cd /tmp && hermes` → uses default profile (no match in registry)
- Subdirectory matching works — `cd acme-works/app/models` still matches the parent project

## Registry File

`~/.cortex-projects.json` is created by `scripts/cortex-profile.sh` and contains:

```json
[
  {
    "project_name": "acme-works",
    "location": "~/Developer/ACME/acme-works",
    "brain_source": "acme-works",
    "profile": "acme-works",
    "created": "2026-06-08T..."
  }
]
```

## Registration

```bash
# One-time setup:
bash scripts/cortex-profile.sh <project-name> <project-path>

# Registers in ~/.cortex-projects.json, creates Hermes profile,
# creates non-federated brain source.
```

## Alternative: Hermes Built-In Wrappers

Hermes can also generate wrapper scripts directly — no shell function needed:

```bash
hermes profile create acme-works
hermes profile alias acme-works           # creates ~/.local/bin/hermes-acme-works
hermes profile alias acme-works --name k  # creates ~/.local/bin/hermes-k
```

Then `hermes-acme-works` or `hermes-k` acts as `hermes --profile acme-works`. This is native Hermes, doesn't need `~/.cortex-projects.json`, but requires remembering which `hermes-*` command maps to which project.

## No Registry = No Matching

If the file doesn't exist or the current directory isn't under any registered path, the function falls through to plain `hermes` with no profile argument — standard default behavior.
