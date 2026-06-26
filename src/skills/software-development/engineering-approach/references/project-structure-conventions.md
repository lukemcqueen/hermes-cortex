# Project Structure Conventions

Acme-royalty monorepo structure and conventions that affect how work gets organized and committed.

## Directory Purposes

| Directory | Purpose | Git status |
|---|---|---|
| `apps/api/` | FastAPI Python backend | tracked |
| `apps/batch/` | Rust batch processing (import/export) | tracked |
| `apps/web/` | Next.js frontend | tracked |
| `packages/domain/` | Shared TypeScript business logic | tracked |
| `packages/schemas/` | TOML/JSON schema definitions | tracked |
| `docs/` | Story docs, architecture, research | **tracked** (was gitignored — now committed) |
| `unknown/` | Work in progress, unassigned files | **gitignored** — never commit here |
| `sql/` | SQL migrations (supplementary) | tracked |
| `scripts/` | Operational scripts (migration, ops) | tracked |

## Critical Rule: `unknown/` is Gitignored

Anything in `unknown/` is invisible to future sessions and won't survive `git clone`. If you find implementation in `unknown/` that should be tracked:
1. Move the files to the correct `apps/` or `packages/` location
2. Update `lib.rs` / `__init__.py` as needed
3. Verify with `cargo build --lib` or `uv run pytest`
4. Commit the migrated code

## `docs/` Should Be Tracked

The `docs/` folder (story docs, architecture docs, etc.) should be committed — it is the canonical record of what was built and why. It was previously gitignored and had to be unignored. If `docs/` appears gitignored in a new workspace, remove from `.gitignore` and commit the doc status updates.

## Selective Staging

Never `git add .` — always check `git status --short` first and only stage what's relevant to the current commit. Unrelated changes (web locale files, generated files, untracked directories) should remain unstaged.

```bash
git status --short   # review before staging
git add <specific_paths>
git commit -m "description"
```

If you accidentally stage everything: `git reset HEAD` to unstage, then add selectively.

## Story Doc Status Conventions

- Story docs are in `docs/tasks/sprint-*.md`
- Frontmatter `status:` and body `**Status:**` should agree — if they diverge, update frontmatter
- Body status is authoritative over frontmatter and context summaries when evidence conflicts
- Story docs should be committed when status changes (now that `docs/` is tracked)
- **Quick status scan:** `grep "^Status\|^status" docs/tasks/sprint-*.md` — one-liner to see all story statuses across an epic

## Story Doc Frontmatter vs Body Pattern

When cleaning up story docs, always check BOTH:
1. **Frontmatter** `status:` field (line 5 in docs)
2. **`## Completion` or `**Status:**` section** in the body

A story is genuinely complete when both agree AND the body contains a meaningful completion summary. If the body says "complete" but frontmatter says "in-progress" or "review" → update frontmatter. This is the most common doc drift pattern.

The cleanup workflow:
```bash
# Quick scan — frontmatter status
grep "^Status\|^status" docs/tasks/sprint-0-*.md

# For each story with wrong status:
# 1. Read the doc body for ## Completion / **Status:**
# 2. Verify artifacts exist (run tests, check files)
# 3. Update frontmatter
# 4. Add ## Completion section if missing
# 5. Commit
```

## Trust Hierarchy for Story Status

When context summaries, frontmatter, and doc body conflict:
1. **`sprint-status.yaml`** — authoritative ground truth; cross-references stories to git commits. If it says a story is done, trust it over doc frontmatter.
2. **Filesystem** — actual files existing (tests, models, migrations) are evidence
3. **Doc body** (`**Status:**`) — authoritative over frontmatter and summaries
4. **Frontmatter** (`status:`) — can drift from body
5. **Context summaries** — always stale; verify against actual files

**Quick reference for sprint-status.yaml:**
```bash
cat sprint-status.yaml | grep -E "stories:|status"
grep -A20 "^epic-0:" sprint-status.yaml
```

When a session says "story X is incomplete" but doc says "complete": read the doc, check the files, run the tests. Trust the evidence.

## Python Test Runner

Use `uv run pytest` — not `.venv/bin/python -m pytest`. The project uses `uv` as the package manager.

```bash
uv run pytest tests/test_specific.py -v
uv run pytest --tb=short  # full suite
```

## Rust Test Runner

```bash
cargo test --lib                    # library tests only
cargo test --lib --quiet            # less output
cargo build --lib                   # verify compiles
```

Target: 116+ tests in `apps/batch`, 311+ in `apps/api`.