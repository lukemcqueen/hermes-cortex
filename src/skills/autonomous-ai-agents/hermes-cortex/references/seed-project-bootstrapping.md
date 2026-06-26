# seed-project.sh — Full Reference

## Purpose

Deploy Hermes Cortex development harness (AGENTS.md, .hermes-cortex/ infrastructure, loop-governance scoring, pre-commit hooks, project skills) to any project directory.

## Usage

```
seed-project.sh --project=<path> [options]

REQUIRED:
  --project=<path>     Target project directory (must be a git repo)

OPTIONS:
  --mode=merge|overwrite|diff    Default: merge
  --components=ALL|list          Default: ALL (AGENTS.md,.hermes-cortex,pre-commit,loop-gov,skills)
  --name=<name>                  Project display name (for AGENTS.md {{PROJECT_NAME}})
  --template=<path>              Custom AGENTS.md template
  --skill-refs=skill1,skill2     Project skill overrides to enable
  --no-backup                    Skip backup (only with --mode=overwrite)

RESTORE:
  --restore=<path>               Restore from most recent backup
  --restore=<path>@<timestamp>   Restore specific backup
  --list-backups=<path>          Show available backups
```

## Template Placeholders

AGENTS.seed.md uses these substitution patterns:

| Placeholder | Source | Example |
|-------------|--------|---------|
| `{{PROJECT_NAME}}` | `--name` flag or basename of project path | "My API" |
| `{{PROJECT_DESCRIPTION}}` | Auto-generated from project name | "my-api — seeded project" |
| `{{SEED_DATE}}` | Current UTC date | "2026-06-26" |
| `{{SEED_COMMIT}}` | Current hermes-cortex repo commit | "b432700" |

## Restore Scenarios

### Restore from latest backup
```bash
bash ~/.hermes-cortex/scripts/seed-project.sh --restore=/path/to/project
```

### Restore from a specific backup
```bash
# First list available backups
bash ~/.hermes-cortex/scripts/seed-project.sh --list-backups=/path/to/project
# Then restore one
bash ~/.hermes-cortex/scripts/seed-project.sh --restore=/path/to/project@20260626_150000-12345
```

### What gets restored
- AGENTS.md → project root
- .hermes-cortex/ → replaced from backup (backup history preserved)
- .git/hooks/pre-commit → restored

### What does NOT get restored
- Loop-governance wrappers (generated, not backed up — re-seed)
- Project skills (copied from global — re-seed)
- Files that didn't exist before the seed (first seed has no backup)

## Component Details

### AGENTS.md
- Source: `docs/templates/AGENTS.seed.md` or custom `--template`
- Template uses `{{PLACEHOLDER}}` substitution
- Agent execution contract (rules 1-11) from hermes-cortex AGENTS.md
- Loop-governance scoring section (CLI + MCP paths)
- Project-specific section for manual additions (dev setup, architecture, deployment, testing)

### .hermes-cortex/
- Creates: sessions/archive/, memory/, skills/ + .gitkeep files
- Writes `.gitignore` excluding: memory/, *.db, *.sqlite, .env, *.pem, *.key
- Backup excludes `.seed-backups/` directory (circular copy prevention)

### Pre-commit Hook
- Delegates to `install-score-hook.sh` when available
- Falls back to direct `cp` of `pre-commit-score`
- Runs `score-cycle` on every commit

### Loop-Governance
- Creates score-cycle and loop-feedback wrapper scripts in `.hermes-cortex/loop-governance/`
- Wrappers delegate to global score-cycle via `exec`
- Adds *.db and loop-gov.db to .gitignore

### Skills
- Copies SKILL.md + references/ from global ~/.hermes/skills/
- Default set: change-test-loop, engineering-approach, test-driven-development, save-lesson, spike, writing-plans
- Custom via `--skill-refs=comma,separated,list`

## Pitfalls

### 1. Destructive restore of incomplete backup
The original restore code did `rm -rf "${project}/.hermes-cortex"` BEFORE checking if the backup had `.hermes-cortex/`. A first-seed backup only has AGENTS.md (no .hermes-cortex/ to restore). The rm deleted the entire `.hermes-cortex/` including `.seed-backups/`. Fix: only restore .hermes-cortex/ when backup explicitly has it; move aside (never delete) the current version; restore original on cp failure.

### 2. Circular backup copy
`create_backup()` copies `.hermes-cortex/` recursively. Since the backup path is INSIDE `.hermes-cortex/.seed-backups/`, the copy would include the backup being written — infinite recursion. Fix: iterate over top-level items in `.hermes-cortex/` and skip `.seed-backups/`.

### 3. `local var=$(cmd)` with `set -e`
In bash, `local var=$(cmd)` masks the exit code of `cmd`. When `set -e` is active, a failed command inside `$()` causes the entire script to exit. Fix: split into `local var; var=$(cmd) || true`.

### 4. `exit` vs `return` in functions
`exit 0` inside a function terminates the entire calling process. Functions called from main() must use `return`, not `exit`. This is especially critical for the `--list-backups` and `--restore` paths which can call functions directly.

### 5. Timestamp collisions
`date +'%Y%m%d_%H%M%S'` has 1-second resolution. Two seeds in the same second create identical backup directory names. Fix: append `$RANDOM` to the timestamp.

### 6. Unclosed braces in template substitution
`${content//"{{PLACEHOLDER}"/value}` is missing one `}` — the pattern `{{PLACEHOLDER}` won't match `{{PLACEHOLDER}}` in the template. The placeholder stays unexpanded. Always verify both braces.

## Migration Patterns

### First-time seed on a project with existing .hermes-cortex/
```
1. Backups existing .hermes-cortex/ (without circular backup) ✓
2. Overwrites AGENTS.md if different (checksum)
3. Adds .gitignore entries (doesn't remove existing)
4. Installs/updates pre-commit hook
5. Loop-gov wrappers always created fresh (small files)
6. Skills only added (never removed from .hermes-cortex/skills/)
```

### Re-seeding (idempotent)
```
- Same output as first seed on unchanged source files
- Delta engine: only writes files with different checksums
- Pre-existing .seed-backups/ preserved across seeds
```
