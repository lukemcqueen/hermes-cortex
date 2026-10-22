# Session Cache Path Fixes

> Applied by Esther, 2026-07-13. Three divergences found between the hardcoded paths in `session_cache.py` and the actual deployment layout of the Hermes Cortex fleet.

## Divergence 1: Session storage format

**Script expected:** `~/.hermes-cortex/sessions/*.md` (individual markdown files)

**Actual:** `~/.hermes/sessions/sessions.json` (single JSON blob)

**Fix:** Added a `SESSION_JSON` path constant and a JSON-parsing branch in `embed_sessions()`. The function now tries individual `.md` files first, then falls back to JSON parsing:

```python
SESSION_JSON = HOME / ".hermes" / "sessions" / "sessions.json"

# In embed_sessions():
# Try JSON session store
if SESSION_JSON.exists():
    raw = SESSION_JSON.read_text(encoding="utf-8", errors="replace")
    sessions_data = json.loads(raw)
    items = sessions_data if isinstance(sessions_data, list) else sessions_data.values()
    for i, session in enumerate(items):
        if i >= 30: break
        # ... embed each session
```

## Divergence 2: Skills directory

**Script expected:** `~/.hermes-cortex/skills/software-development/`

**Actual:** `~/.hermes/skills/` (flat directory with 60+ skill subdirectories)

**Fix:** Changed the constant:
```python
SKILLS_DIR = HOME / ".hermes" / "skills"  # not / ".hermes-cortex" / "skills" / "software-development"
```

## Divergence 3: DB schema columns

**Script queried:** `code_or_spec`, `output_text` — columns that don't exist

**Actual schema:** Uses `outcome_note` (TEXT) and `decision` (TEXT) on `loop_cycles`

**Fix:** Changed the SQL query:
```python
# Old (broken):
rows = src.execute(
    "SELECT id, task_id, code_or_spec, output_text FROM loop_cycles WHERE composite >= 6.0 ORDER BY composite DESC LIMIT 50"
).fetchall()

# New (working):
rows = src.execute(
    "SELECT id, task_id, outcome_note, decision FROM loop_cycles WHERE composite >= 6.0 ORDER BY composite DESC LIMIT 20"
).fetchall()
```

## Verification

After applying all three fixes, the build should produce:
```
Embedding sessions...    3 new session embeddings
Embedding loop DB cycles...  20 new cycle embeddings
Embedding skills...    24 new skill embeddings
```
And `cache_search(query="...")` from the MCP tool should return results across all three source types.
