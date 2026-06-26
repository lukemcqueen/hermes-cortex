# Story Implementation Gap Analysis

Systematic verification that actual implementation matches declared story artifacts.

## The Problem

Story docs (in `docs/tasks/sprint-*.md`) declare files via a "File List" section. But:
- Docs may say "complete" while files are missing or in `unknown/`
- Docs may reference TypeScript paths while implementation is Python (file list mismatch ≠ code gap)
- Context summaries can claim "incomplete" while actual doc body says "complete"
- Old file lists become stale when implementation shifts language (e.g., TS → Python)

## Gap Analysis Script

```python
import pathlib, re

root = pathlib.Path("/Users/luke/Developer/ACME/acme-royalty")
story_files = sorted(root.glob("docs/tasks/sprint-*.md"))

for f in story_files:
    content = f.read_text()
    status_match = re.search(r'\*\*Status:\*\* ([^\n]+)', content)
    status = status_match.group(1).strip() if status_match else "unknown"
    
    file_list_match = re.search(r'(?:## |### )File List\s*\n(.+?)(?=---|\Z)', content, re.DOTALL)
    declared = []
    if file_list_match:
        for line in file_list_match.group(1).strip().split('\n'):
            paths = re.findall(r'`([^\`]+)`', line)
            for p in paths:
                p = p.strip().rstrip('`')
                if '/' in p: declared.append(p)
    
    missing = [p for p in declared if not (root / p).exists()]
    if missing or not declared:
        print(f"\n{f.name} ({status}):")
        for m in missing: print(f"  MISSING: {m}")
        if not declared: print(f"  (no file list)")
```

## Trust Hierarchy

1. **Actual filesystem** — what files exist, where, and what language they're written in
2. **Doc body status** (`**Status:**`) — authoritative over frontmatter and context summaries
3. **Context summaries** — can be stale; always verify against actual files
4. **Story file lists** — check against filesystem; mismatch ≠ missing functionality

## Common Patterns

### Missing `ingestion_batches` table (Story 1-5)
- `ingestion_jobs` exists in initial schema
- `ingestion_batches` missing — no alembic migration, no DB table
- `StreamingProcessor` tracks checkpoint in-memory only — no durable resume on crash
- Fix: create alembic migration for `ingestion_batches` table

### Doc/impl path mismatch (Stories 1-5, 1-6)
- Doc says `apps/api/src/features/works/` (TypeScript)
- Actual is `apps/api/routers/works.py` (Python FastAPI)
- Code works fine — doc file list is simply wrong
- Not a gap to fix in code; gap is in doc accuracy

### `unknown/` has implementation (pre-existing gap)
- If implementation is in `unknown/` when it should be in `apps/` or `packages/`:
  1. Move files to correct location
  2. Update `lib.rs` / `__init__.py`
  3. `cargo build --lib` or `uv run pytest` to verify
  4. Commit