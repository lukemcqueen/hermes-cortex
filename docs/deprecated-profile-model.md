# Deprecated: Profile-Per-Project Model (v1.x)

> **Archived: 2026-06-11**
> Superseded by [Knowledge Isolation Architecture](./knowledge-isolation-architecture.md)
>
> This document describes the **abandoned** profile-per-project model. Do not use
> this approach for new setups. It is preserved here for migration reference only.

## What Changed

**v1.x approach (deprecated):** Each project had its own Hermes profile (`--profile client-a`), separate MEMORY.md/USER.md files, and a `~/.cortex-projects.json` registry to orchestrate project, profile, brain, and gbrain source.

**v2.x approach (current):** One default profile. Project isolation is achieved entirely through gbrain source filtering (`--source <project>`). The pointer pattern keeps MEMORY.md compact.

## The Old Architecture

### Three-Layer Model

1. **Layer 1: Brain Directory** — `~/brain/<project>/` per project (still current)
2. **Layer 2: Hermes Profile** — `~/.hermes/profiles/<name>/` with isolated MEMORY.md/USER.md (deprecated)
3. **Layer 3: Project Registration** — `~/.cortex-projects.json` registry (deprecated)

### cortex-profile.sh

The `scripts/cortex-profile.sh` script automated creating a hermetic project profile:

```bash
bash scripts/cortex-profile.sh <project-name> [project-path]
```

It created:
- A project directory at `~/Developer/AI/<name>/`
- A Hermes profile at `~/.hermes/profiles/<name>/`
- A brain directory at `~/brain/<name>/`
- A gbrain source
- A `~/.cortex-projects.json` entry

This script remains in the repo for legacy users to migrate from, but new installations should not use it.

## Migration from v1.x to v2.x

If you have existing project profiles, merge them into the default profile:

### Step 1: Consolidate MEMORY.md

```bash
# Read each profile's MEMORY.md and merge unique entries into default
cat ~/.hermes/profiles/client-a/memories/MEMORY.md >> ~/.hermes/memories/MEMORY.md
cat ~/.hermes/profiles/client-b/memories/MEMORY.md >> ~/.hermes/memories/MEMORY.md

# Deduplicate and compress using the pointer pattern
# (Your agent can handle this automatically)
```

### Step 2: Verify Brain Directories

```bash
ls ~/brain/
# Ensure each project has a directory matching its gbrain source name
```

### Step 3: Remove Profile Directories

```bash
rm -rf ~/.hermes/profiles/client-a
rm -rf ~/.hermes/profiles/client-b
```

### Step 4: Remove Registry

```bash
rm -f ~/.cortex-projects.json
```

### Step 5: Start Agent Without Profile Flag

```bash
hermes  # No --profile flag → uses default profile
        # Use /brain with --source for project-specific queries
```

## Why We Changed

- **Lower cognitive load** — One agent identity, no switching profiles
- **Simpler setup** — No `cortex-profile.sh`, no `~/.cortex-projects.json`
- **Faster queries** — gbrain source filtering is instant; profile switching requires a new session
- **Less config** — One MEMORY.md, one USER.md, one set of skills and crons
- **Same isolation** — gbrain `--source` filtering achieves the same data separation without the overhead
