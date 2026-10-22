# Governance Setup Verification

After installing or updating the loop-governance stack, verify each layer independently. Do not assume it works because the scripts exist.

## Three-Layer Stack

Layer | What | How to verify
------|------|-------------
**1. Plugin** | Blocks Hermes write tools without lock | `hermes plugins list \| grep governance` → enabled
**2. MCP Server** | Provides begin_change/end_change tools | `hermes mcp list` → loop-governance with 10 tools
**3. Git Hooks** | Auto-scores every commit | `git config --global core.hooksPath` → ~/.hermes-cortex/hooks

## Common Pitfalls Found In Production

### DB Path Divergence

The pre-commit hook may hardcode a different DB path than what setup creates.

**Symptom:** Pre-commit hook runs without error but cycles don't appear in the DB. The governance auditor reports 0 new cycles despite active commits.

**Check:**
```bash
grep 'DB_PATH' ~/.hermes-cortex/hooks/pre-commit
# Expected: DB_PATH="$HOME/.hermes-cortex/data/loop-governance.db"
# Wrong:    DB_PATH="$HOME/.hermes/data/loop-governance.db"
```

**Fix:** Patch the hook's `DB_PATH` to match where the actual DB lives:
```bash
# Expected DB location
ls -la ~/.hermes-cortex/data/loop-governance.db
```

### Session Cache Path Mismatch

The `session_cache.py` script may look for data in wrong locations.

**Symptom:** `session-cache-build build` reports 0 new embeddings even though sessions/cycles/skills exist.

**Root causes found in production:**
1. `SKILLS_DIR` pointed to `~/.hermes-cortex/skills/software-development/` but actual skills are at `~/.hermes/skills/`
2. Session reader expected `.md` files but sessions are in `~/.hermes/sessions/sessions.json` (JSON format)
3. `embed_loop_db()` queried nonexistent columns `code_or_spec`, `output_text` — actual columns are `outcome_note`, `decision`

**Check:**
```bash
grep -E 'SESSION_DIR|SKILLS_DIR|SESSION_JSON' ~/.hermes-cortex/tools/loop-governance/session_cache.py
grep -E 'SELECT.*FROM' ~/.hermes-cortex/tools/loop-governance/session_cache.py
```

**Fix:** Patch the paths and column names to match your actual deployment.

### Session Cache DB Existence

**Check:**
```bash
ls -la ~/.hermes-cortex/data/session-embeddings.db
```

If missing, build it:
```bash
PYTHONPATH=~/hermes-cortex/ops/scripts:~/.hermes/scripts \
  python3 ~/.hermes-cortex/tools/loop-governance/session_cache.py build
```

Expected output: some number of session, cycle, and skill embeddings.

### CLI Symlinks

All 6 CLI tools must be executable:
```bash
for tool in score-cycle loop-feedback auto-apply loop-config session-cache-build skill-miner; do
  test -x ~/.local/bin/$tool || echo "MISSING: $tool"
done
```

### MCP Server Tool Count

The loop-governance MCP server should expose 10 tools. Verify:
```bash
hermes mcp list
```

If the server is connected but has fewer tools, the server script may have failed to load all modules. Check the server logs:
```bash
journalctl --user -u hermes --since "5 minutes ago" | grep -i "mcp\|loop-gov\|error" | tail -10
```

### Hook File Permissions

Pre-commit and pre-push hooks must be executable:
```bash
ls -la ~/.hermes-cortex/hooks/{pre-commit,pre-push}
# Expected: -rwx... (at least 755)
```

## Full Verification Command

```bash
echo "=== Plugin ==="
hermes plugins list | grep governance-enforcer

echo "=== MCP ==="
hermes mcp list | grep loop-governance

echo "=== Hooks ==="
git config --global core.hooksPath
ls -la ~/.hermes-cortex/hooks/pre-commit

echo "=== DB ==="
ls -lh ~/.hermes-cortex/data/loop-governance.db
python3 -c "import sqlite3; print(sqlite3.connect('$HOME/.hermes-cortex/data/loop-governance.db').execute('SELECT COUNT(*) FROM loop_cycles').fetchone()[0], 'cycles')"

echo "=== Cache ==="
ls -lh ~/.hermes-cortex/data/session-embeddings.db 2>/dev/null || echo "Cache not built"

echo "=== Tools ==="
for t in score-cycle loop-feedback auto-apply loop-config session-cache-build skill-miner; do
  test -x ~/.local/bin/$t && echo "  $t: OK" || echo "  $t: MISSING"
done

echo "=== Locks ==="
ls ~/.hermes-cortex/state/.governance-*.json 2>/dev/null || echo "No active locks"
```
