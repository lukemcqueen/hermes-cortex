# Privacy Architecture — Full Implementation Notes

Created during the June 2026 memory architecture overhaul. Reference for how gitignore, seed templates, and install integration work together.

## File Locations

| File | Location | Purpose |
|------|----------|---------|
| MEMORY.seed.md | `docs/templates/MEMORY.seed.md` | Starter memory with sections + design principles |
| USER.seed.md | `docs/templates/USER.seed.md` | Starter user profile template |
| gitignore.brain | `docs/templates/gitignore.brain` | .gitignore template for brain source repos |
| install.sh | `install.sh` (repo root) | Steps 5 + 9 enforce the architecture |

## Install Script Details

### Step 5 — Brain .gitignore
```bash
# SCRIPT_DIR is auto-detected from install.sh location
GITIGNORE_TEMPLATE="${SCRIPT_DIR}/docs/templates/gitignore.brain"
```
Iterates over `$SOURCES`, skips if .gitignore already exists, otherwise copies from template or writes inline fallback.

### Step 9 — Hermes Memory (no cortex seed, since 2026-08-05)
```bash
# REMOVED: seeding MEMORY.md/USER.md into a cortex-side memories dir.
```
Memory is Hermes-owned: Hermes reads `~/.hermes/memories/MEMORY.md` directly
and creates the files on its first memory write. A deploy-registered seed
previously clobbered live memory on every cortex-update (7× on 2026-08-05)
because the live file is personalized and the generic hash-overwrite path
replaced it with the blank template. Seeds in `docs/templates/` are
reference-only now.

## TOTAL_STEPS Accounting
When adding steps to install.sh:
1. Change `TOTAL_STEPS=15` (or whatever the new total is)
2. Add the step body before the Summary section
3. Insert a comment header `#  N. Step Name`
4. Renumber all subsequent comment headers

## Brain Repo Push Mapping
Brain repos on local `main` push to remote branch names matching the source:
- `~/brain/luke` → `brain-luke` on remote
- `~/brain/moses` → `main` on remote (special)
- `~/brain/shared` → `brain-shared`
- `~/brain/default` → `brain-default`
- `~/brain/amy` → `brain-amy`

## Gitignore Guard
The brain .gitignore pattern `MEMORY.md` only matches a file literally named `MEMORY.md`.
Files like `test_MEMORY.md` or `MEMORY-v2.md` are NOT matched — that's intentional.
