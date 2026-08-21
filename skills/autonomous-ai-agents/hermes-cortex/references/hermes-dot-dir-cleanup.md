# Cleaning Up `.hermes/` Directories from Project Roots

## Problem

Hermes Agent creates a `project-root/.hermes/` directory when it works
inside a project. This stores plans, sessions, scripts, and research docs
generated during agent sessions.

Over time, these accumulate across many project repos. They are:
- **Developer-local** — one developer's agent scratch files are meaningless to another
- **Not project source code** — they belong in developer home dirs or brain dirs
- **Git-controlled** — if the project's `.gitignore` doesn't cover `.hermes/`, they
  pollute `git status` output and risk accidental commits

## Detection

Find all `.hermes/` directories across project repos:

```bash
find ~/Developer -maxdepth 3 -type d -name '.hermes' \
  -not -path '/Users/$(whoami)/.hermes' \
  -not -path '/Users/$(whoami)/.hermes/*'
```

Check what's inside each before deciding what to keep:

```bash
find <project>/.hermes -type f | while read f; do
  echo "  $f ($(wc -c < "$f") bytes)"
done
```

## Assessment: What to Keep vs Delete

| Content | Value | Action |
|---------|-------|--------|
| `plans/*.md` | Medium — contains implementation plans | Archive to brain dir, then delete |
| `sessions/current.md` | Low — ephemeral session state | Delete directly |
| `scripts/*.sh` | Low — usually hardcoded paths, needs rewrite | Review; delete or archive if reusable |
| `*.md` at root | Medium — research docs, UX reviews, analysis | Archive to brain dir, then delete |

## Archive Workflow

For valuable content (plans, research docs, architecture analysis):

```bash
# 1. Create agents/ directory in the project's brain source
mkdir -p ~/brain/<project>/agents

# 2. Copy valuable files
cp <project>/.hermes/plans/*.md ~/brain/<project>/agents/
cp <project>/.hermes/*.md ~/brain/<project>/agents/

# 3. Git commit so mycortex sync picks them up
cd ~/brain/<project>
git add -A
git commit -m "archive: migrated agent plans from project .hermes dir"

# 4. Sync with mycortex
mycortex sync --source <project> --no-pull

# 5. Extract edges
mycortex extract --stale --source <project>
```

## Cleanup Workflow

### 1. Add `.hermes/` to project `.gitignore` (if missing)

```bash
echo "" >> <project>/.gitignore
echo "# Hermes Agent artifacts" >> <project>/.gitignore
echo ".hermes/" >> <project>/.gitignore
```

### 2. Remove the `.hermes/` directory

**ALWAYS one at a time** — each deletion gets a separate approval prompt:

```bash
rm -rf <project>/.hermes
```

Never batch multiple `rm -rf` calls in a single command. The user prefers
sequential destructive operations so each one can be reviewed and approved
independently.

### 3. Verify removal

```bash
# Confirm dir is gone
ls -la <project>/.hermes 2>&1

# Confirm .gitignore covers it
grep '\.hermes' <project>/.gitignore
```

## Prevention

Prevent recurrence by ensuring every project's `.gitignore` includes `.hermes/`:

```bash
for dir in ~/Developer/AI/* ~/Developer/ACME/* ~/Developer/PERSONAL/*; do
  if [ -d "$dir/.git" ] && ! grep -q '^\.hermes' "$dir/.gitignore" 2>/dev/null; then
    echo "❌ $dir — MISSING .hermes/ in .gitignore"
  fi
done
```

## Why This Pattern

- `.hermes/` in project roots is the **old pattern** — now replaced by
  `.hermes-cortex/` (project-anchored, gitignored-but-tracked) and
  `~/.hermes/` (home-dir, single source of truth)
- Valuable agent output (plans, research) belongs in `~/brain/<project>/agents/`
  where mycortex indexes and searches it via `/brain`
- Session state files (`sessions/current.md`) are ephemeral and have no
  durable value outside the conversation that produced them
