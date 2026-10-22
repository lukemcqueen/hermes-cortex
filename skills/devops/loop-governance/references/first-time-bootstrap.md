# First-Time Loop Governance Bootstrap

> **When:** Running the weekly evaluation pipeline on a machine where `loop-governance.db` does not exist, `~/.local/bin/` has no symlinks, and no cycles have ever been scored.
>
> **Source:** Esther session, July 2026 — first pipeline run on a 267-commit-week, `hermes-cortex` repo, 2.4MB DB created.

## Prerequisites

- Ollama running with `nomic-embed-text:v1.5` pulled
- `hermes-cortex` repo cloned at `~/hermes-cortex`
- Git hooks at `~/.hermes-cortex/hooks/` (from install.sh)

## Step-by-step

### 0. Check readiness

```bash
# Tools exist?
ls -la ~/.local/bin/{score-cycle,loop-feedback,auto-apply,loop-config,session-cache-build,skill-miner} 2>&1
# DB exists?
ls -la ~/.hermes-cortex/data/loop-governance.db 2>&1
# Hooks path set?
git config --global core.hooksPath 2>/dev/null || echo "NOT SET"
# Ollama running?
curl -sf http://localhost:11434/api/tags | python3 -c "import sys,json; print([m['name'] for m in json.load(sys.stdin).get('models',[])])"
```

### 1. Run setup

```bash
bash ~/hermes-cortex/src/loop-governance/setup.sh
```

Creates: symlinks, config JSON, DB dir. Does NOT create the DB (that happens on first cycle insert).

### 2. Seed DB from git history

Iterate commits from the last 7 days, classify by subject prefix, assign heuristic scores, insert via `LoopDB.log_cycle_with_content()`. Do NOT call `full_score()` — it routes through Ollama embeddings and times out on >5 commits.

**Classification table:**

| Prefix | C | Q | P | composite ~ |
|--------|---|---|---|-------------|
| `fix:` | 8.5 | 8.0 | 9.0 | 8.4 (STOP ✓) |
| `feat:` | 7.0 | 7.5 | 8.0 | 7.4 (LOOP) |
| `test:` | 8.0 | 8.5 | 7.0 | 7.8 (LOOP) |
| `auto:` / `pipeline` | 8.0 | 7.5 | 8.0 | 7.8 (LOOP) |
| `merge:` / `Merge` | 9.0 | 9.0 | 8.0 | 8.7 (STOP ✓) |
| `refactor` / `cleanup` | 8.0 | 9.0 | 7.5 | 8.1 (STOP ✓) |
| `docs:` | 7.5 | 7.0 | 7.0 | 7.2 (LOOP) |
| `chore:` | 7.5 | 7.5 | 7.0 | 7.3 (LOOP) |
| default (other) | 7.5 | 7.0 | 7.0 | 7.2 (LOOP) |

**DB path for pre-commit hook divergence:** The pre-commit hook may hardcode `~/.hermes/data/loop-governance.db` while setup creates `~/.hermes-cortex/data/loop-governance.db`. Decide which is canonical and symlink or patch.

### 3. Build session cache

```bash
PYTHONPATH=~/hermes-cortex/ops/scripts:~/.hermes/scripts session-cache-build build
```

If `hermes_models.py` is at `~/hermes-cortex/ops/scripts/`, include that path. Without it you get `ModuleNotFoundError: No module named 'hermes_models'`.

### 4. Run evaluator

```bash
PYTHONPATH=~/hermes-cortex/ops/scripts:~/.hermes/scripts:~/hermes-cortex/src/loop-governance \
  python3 ~/.hermes-cortex/tools/loop-governance/loop_evaluator.py
```

**First-run expectations:**
- Decision accuracy: "No user feedback recorded yet"
- Recommendations: "No recommendations available"
- Config patch confidence: 0.0 (below 0.7 threshold) → skip
- This is normal — confidence grows as agents submit feedback on scored cycles

### 5. Run skill miner

```bash
PYTHONPATH=~/hermes-cortex/ops/scripts skill-miner collect
```

Silent output if <500 files. Check `/tmp/skills-manifest.json` for the manifest.

### 6. Archive old cycles

```python
from loop_db import LoopDB
db = LoopDB("~/.hermes-cortex/data/loop-governance.db")
# Check age: all cycles from git-log seeding are <7 days old, nothing to archive
db.conn.execute("SELECT COUNT(*) FROM loop_cycles WHERE timestamp < datetime('now', '-90 days')").fetchone()
# Delete + vacuum only if old_count > 0
```

### 7. Set global hooksPath (if not already set)

```bash
git config --global core.hooksPath ~/.hermes-cortex/hooks/
```

Without this, `git commit` won't trigger the pre-commit scoring hook, and cycles won't be auto-created from future commits.

## Expected outcome on first run

| Metric | Value |
|--------|-------|
| Total cycles | ~200-300 (depends on commit volume) |
| STOP ✓ count | ~40-50% of total |
| Avg composite | ~7.5-8.0/10 |
| Auto-apply patches | 0 (need user feedback) |
| DB size | ~2-3MB |
| Skill embeddings | 3 (from skills only; 0 sessions/cycles) |
| Archived cycles | 0 (all fresh) |
